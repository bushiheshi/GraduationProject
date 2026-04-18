from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crud import (
    create_chat_conversation,
    get_answer_submission_by_conversation_id,
    get_chat_conversation_by_id,
    list_chat_conversations_by_user,
    list_chat_records_by_conversation,
    list_chat_records_by_user,
    list_recent_chat_records_for_context,
    save_chat_completion,
    upsert_answer_submission,
)
from app.dependencies import get_current_user, get_db
from app.llm_service import (
    LLMConfigurationError,
    LLMUpstreamError,
    generate_completion,
    list_supported_models,
)
from app.models import ChatRecord, UserRole
from app.models import Assignment
from app.schemas import (
    AnswerSubmissionResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatConversationCreateRequest,
    ChatConversationResponse,
    ChatModelInfo,
    ChatRecordResponse,
    StudentAssessmentSummaryResponse,
)
from app.services.answer_assessment import (
    AssessmentResourceError,
    assess_answer_credibility,
    build_student_assessment_summary,
)

router = APIRouter(prefix='/api/chat', tags=['chat'])
settings = get_settings()
MAX_ANSWER_TEXT_LENGTH = 100_000
MAX_ANSWER_FILE_SIZE = 200_000


@router.get('/models', response_model=list[ChatModelInfo])
def get_chat_models(current_user=Depends(get_current_user)):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only students can use chat models')

    return [
        ChatModelInfo(key=model.key, provider=model.provider, model_name=model.model_name)
        for model in list_supported_models()
    ]


@router.get('/conversations', response_model=list[ChatConversationResponse])
def get_conversations(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only students can use chat models')

    conversations = list_chat_conversations_by_user(db, user_id=current_user.id)
    return [_to_conversation_response(item) for item in conversations]


@router.post('/conversations', response_model=ChatConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ChatConversationCreateRequest | None = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only students can use chat models')

    conversation = create_chat_conversation(
        db,
        user_id=current_user.id,
        title=payload.title if payload else None,
    )
    return ChatConversationResponse(
        id=conversation.id,
        title=conversation.title,
        updated_at=conversation.updated_at,
        last_generated_at=None,
        record_count=0,
        assignment_id=conversation.assignment_id,
        assignment_description=None,
    )


@router.get('/conversations/{conversation_id}/records', response_model=list[ChatRecordResponse])
def get_conversation_records(
    conversation_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _require_student_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )
    return list_chat_records_by_conversation(db, conversation_id=conversation.id, user_id=current_user.id)


@router.get(
    '/conversations/{conversation_id}/answer-submission',
    response_model=AnswerSubmissionResponse | None,
)
def get_conversation_answer_submission(
    conversation_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _require_student_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )
    submission = get_answer_submission_by_conversation_id(
        db,
        user_id=current_user.id,
        conversation_id=conversation.id,
    )
    return AnswerSubmissionResponse.model_validate(submission) if submission is not None else None


@router.get(
    '/conversations/{conversation_id}/answer-submission/assessment',
    response_model=StudentAssessmentSummaryResponse,
)
def get_conversation_answer_assessment(
    conversation_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _require_student_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )
    submission = get_answer_submission_by_conversation_id(
        db,
        user_id=current_user.id,
        conversation_id=conversation.id,
    )
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Answer submission not found')

    try:
        result = assess_answer_credibility(
            answer_text=submission.answer_text,
            question_text=_build_assignment_question_text(db, assignment_id=conversation.assignment_id),
            ai_source='not_provided',
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AssessmentResourceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return StudentAssessmentSummaryResponse(**build_student_assessment_summary(result))


@router.post('/conversations/{conversation_id}/answer-submission', response_model=AnswerSubmissionResponse)
async def submit_answer(
    conversation_id: int,
    answer_text: str | None = Form(default=None),
    answer_file: UploadFile | None = File(default=None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _require_student_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )

    normalized_text = (answer_text or '').strip()
    uploaded_text, source_filename = await _read_answer_file(answer_file)

    if normalized_text and uploaded_text:
        normalized_text = f'{normalized_text}\n\n{uploaded_text}'
    elif uploaded_text:
        normalized_text = uploaded_text

    if not normalized_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Please provide answer text or upload a .txt file',
        )
    if len(normalized_text) > MAX_ANSWER_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Answer content must be at most {MAX_ANSWER_TEXT_LENGTH} characters',
        )

    submission = upsert_answer_submission(
        db,
        user_id=current_user.id,
        conversation_id=conversation.id,
        answer_text=normalized_text,
        source_filename=source_filename,
    )
    return AnswerSubmissionResponse.model_validate(submission)


@router.post('/completions', response_model=ChatCompletionResponse)
def create_completion(
    payload: ChatCompletionRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only students can chat with models')

    conversation = _resolve_conversation(db=db, user_id=current_user.id, conversation_id=payload.conversation_id)

    context_limit = max(settings.chat_conversation_turn_limit - 1, 0)
    context_records = list_recent_chat_records_for_context(
        db,
        conversation_id=conversation.id,
        user_id=current_user.id,
        limit=context_limit,
    )
    history_messages = _build_history_messages(context_records)

    try:
        result = generate_completion(
            model_key=payload.model,
            prompt=payload.prompt,
            history_messages=history_messages,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except LLMUpstreamError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    record, conversation = save_chat_completion(
        db,
        conversation=conversation,
        user_id=current_user.id,
        model_name=result['model_name'],
        generated_at=result['generated_at'],
        prompt=payload.prompt,
        content=result['content'],
        citations=result['citations'],
    )

    return ChatCompletionResponse(
        id=record.id,
        conversation_id=record.conversation_id,
        model_name=record.model_name,
        generated_at=record.generated_at,
        prompt=record.prompt,
        content=record.content,
        citations=record.citations,
        conversation_title=conversation.title,
    )


@router.get('/history', response_model=list[ChatRecordResponse])
def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only students can query chat history')

    return list_chat_records_by_user(db, user_id=current_user.id, limit=limit)


def _require_student_conversation(db: Session, *, current_user, conversation_id: int):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only students can use chat models')

    conversation = get_chat_conversation_by_id(db, conversation_id=conversation_id, user_id=current_user.id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Conversation not found')
    return conversation


def _resolve_conversation(db: Session, *, user_id: int, conversation_id: int | None):
    if conversation_id is None:
        return create_chat_conversation(db, user_id=user_id)

    conversation = get_chat_conversation_by_id(db, conversation_id=conversation_id, user_id=user_id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Conversation not found')
    return conversation


def _build_history_messages(records: list[ChatRecord]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for record in records:
        if record.prompt.strip():
            messages.append({'role': 'user', 'content': record.prompt.strip()})
        if record.content.strip():
            messages.append({'role': 'assistant', 'content': record.content.strip()})
    return messages


def _build_assignment_question_text(db: Session, *, assignment_id: int | None) -> str | None:
    if assignment_id is None:
        return None

    assignment = db.scalar(select(Assignment).where(Assignment.id == assignment_id))
    if assignment is None:
        return None

    parts = [assignment.title, assignment.description]
    return '\n'.join(part.strip() for part in parts if part and part.strip()) or None


async def _read_answer_file(answer_file: UploadFile | None) -> tuple[str, str | None]:
    if answer_file is None:
        return '', None

    source_filename = Path(answer_file.filename or '').name or None
    if source_filename and Path(source_filename).suffix.lower() != '.txt':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Only .txt files are supported',
        )

    data = await answer_file.read()
    if not data:
        return '', source_filename
    if len(data) > MAX_ANSWER_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Text file must be at most {MAX_ANSWER_FILE_SIZE} bytes',
        )

    try:
        content = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Text file must be UTF-8 encoded',
        ) from exc

    return content.strip(), source_filename


def _to_conversation_response(item: dict) -> ChatConversationResponse:
    conversation = item['conversation']
    assignment = item.get('assignment')
    return ChatConversationResponse(
        id=conversation.id,
        title=conversation.title,
        updated_at=conversation.updated_at,
        last_generated_at=item.get('last_generated_at'),
        record_count=int(item.get('record_count') or 0),
        assignment_id=conversation.assignment_id,
        assignment_description=assignment.description if assignment else None,
    )
