from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crud import (
    create_chat_conversation,
    get_chat_conversation_by_id,
    list_chat_conversations_by_user,
    list_chat_records_by_conversation,
    list_chat_records_by_user,
    list_recent_chat_records_for_context,
    save_chat_completion,
)
from app.dependencies import get_current_user, get_db
from app.llm_service import (
    LLMConfigurationError,
    LLMUpstreamError,
    generate_completion,
    list_supported_models,
)
from app.models import ChatRecord, UserRole
from app.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatConversationCreateRequest,
    ChatConversationResponse,
    ChatModelInfo,
    ChatRecordResponse,
)

router = APIRouter(prefix='/api/chat', tags=['chat'])
settings = get_settings()


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
    )


@router.get('/conversations/{conversation_id}/records', response_model=list[ChatRecordResponse])
def get_conversation_records(
    conversation_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only students can use chat models')

    conversation = get_chat_conversation_by_id(db, conversation_id=conversation_id, user_id=current_user.id)
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Conversation not found')

    return list_chat_records_by_conversation(db, conversation_id=conversation_id, user_id=current_user.id)


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
        keep_limit=settings.chat_conversation_turn_limit,
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


def _to_conversation_response(item: dict) -> ChatConversationResponse:
    conversation = item['conversation']
    return ChatConversationResponse(
        id=conversation.id,
        title=conversation.title,
        updated_at=conversation.updated_at,
        last_generated_at=item.get('last_generated_at'),
        record_count=int(item.get('record_count') or 0),
    )

