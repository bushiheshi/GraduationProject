import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import AnswerSubmission, Assignment, ChatConversation, ChatRecord, User, UserRole

DEFAULT_CONVERSATION_TITLE = 'New Conversation'
DEFAULT_CONVERSATION_TITLE_ALIASES = {
    '',
    DEFAULT_CONVERSATION_TITLE,
    'New chat',
    'History Conversation',
    '新对话',
    '历史对话',
}
AUTO_CONVERSATION_TITLE_LIMIT = 40
MANUAL_CONVERSATION_TITLE_LIMIT = 120


def get_user_by_account(db: Session, account: str) -> User | None:
    stmt = select(User).where(User.account == account)
    return db.scalar(stmt)


def create_user(db: Session, account: str, name: str, role: UserRole, password_hash: str) -> User:
    user = User(
        account=account,
        name=name,
        role=role,
        password_hash=password_hash,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_chat_conversation(
    db: Session,
    *,
    user_id: int,
    title: str | None = None,
    assignment_id: int | None = None,
    created_at: datetime | None = None,
) -> ChatConversation:
    timestamp = created_at or datetime.utcnow()
    conversation = ChatConversation(
        user_id=user_id,
        assignment_id=assignment_id,
        title=_build_conversation_title(title or DEFAULT_CONVERSATION_TITLE, max_length=MANUAL_CONVERSATION_TITLE_LIMIT),
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def create_assignment_with_conversations(
    db: Session,
    *,
    teacher_id: int,
    title: str,
    description: str | None = None,
) -> dict[str, Any]:
    timestamp = datetime.utcnow()
    normalized_title = _build_conversation_title(title, max_length=MANUAL_CONVERSATION_TITLE_LIMIT)
    normalized_description = (description or '').strip() or None

    assignment = Assignment(
        teacher_id=teacher_id,
        title=normalized_title,
        description=normalized_description,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(assignment)
    db.flush()

    student_ids = list(
        db.scalars(
            select(User.id)
            .where(
                User.role == UserRole.STUDENT,
                User.is_active.is_(True),
            )
            .order_by(User.id.asc())
        )
    )
    if student_ids:
        db.add_all(
            [
                ChatConversation(
                    user_id=student_id,
                    assignment_id=assignment.id,
                    title=assignment.title,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                for student_id in student_ids
            ]
        )

    db.commit()
    db.refresh(assignment)
    return {
        'assignment': assignment,
        'student_count': len(student_ids),
        'submitted_count': 0,
    }


def get_assignment_by_id_for_teacher(
    db: Session,
    *,
    assignment_id: int,
    teacher_id: int,
) -> Assignment | None:
    stmt = select(Assignment).where(
        Assignment.id == assignment_id,
        Assignment.teacher_id == teacher_id,
    )
    return db.scalar(stmt)


def list_assignments_by_teacher(db: Session, *, teacher_id: int) -> list[dict[str, Any]]:
    assignments = list(
        db.scalars(
            select(Assignment)
            .where(Assignment.teacher_id == teacher_id)
            .order_by(Assignment.created_at.desc(), Assignment.id.desc())
        )
    )
    if not assignments:
        return []

    assignment_ids = [assignment.id for assignment in assignments]
    student_count_rows = db.execute(
        select(
            ChatConversation.assignment_id,
            func.count(ChatConversation.id),
        )
        .where(ChatConversation.assignment_id.in_(assignment_ids))
        .group_by(ChatConversation.assignment_id)
    ).all()
    submission_count_rows = db.execute(
        select(
            ChatConversation.assignment_id,
            func.count(AnswerSubmission.id),
        )
        .join(AnswerSubmission, AnswerSubmission.conversation_id == ChatConversation.id)
        .where(ChatConversation.assignment_id.in_(assignment_ids))
        .group_by(ChatConversation.assignment_id)
    ).all()

    student_counts = {row[0]: int(row[1] or 0) for row in student_count_rows if row[0] is not None}
    submission_counts = {row[0]: int(row[1] or 0) for row in submission_count_rows if row[0] is not None}

    return [
        {
            'assignment': assignment,
            'student_count': student_counts.get(assignment.id, 0),
            'submitted_count': submission_counts.get(assignment.id, 0),
        }
        for assignment in assignments
    ]


def list_assignment_submissions(
    db: Session,
    *,
    assignment_id: int,
    teacher_id: int,
) -> dict[str, Any] | None:
    assignment = get_assignment_by_id_for_teacher(db, assignment_id=assignment_id, teacher_id=teacher_id)
    if assignment is None:
        return None

    rows = db.execute(
        select(
            User.id,
            User.account,
            User.name,
            ChatConversation.id,
            AnswerSubmission.id,
            AnswerSubmission.updated_at,
            AnswerSubmission.source_filename,
            AnswerSubmission.answer_text,
        )
        .join(ChatConversation, ChatConversation.user_id == User.id)
        .outerjoin(AnswerSubmission, AnswerSubmission.conversation_id == ChatConversation.id)
        .where(
            ChatConversation.assignment_id == assignment_id,
            User.role == UserRole.STUDENT,
        )
        .order_by(User.id.asc())
    ).all()

    submissions = [
        {
            'student_id': int(row[0]),
            'student_account': row[1],
            'student_name': row[2],
            'conversation_id': int(row[3]),
            'has_submission': row[4] is not None,
            'submitted_at': row[5],
            'source_filename': row[6],
            'answer_preview': _build_answer_preview(row[7]),
        }
        for row in rows
    ]
    return {
        'assignment': assignment,
        'submissions': submissions,
    }


def get_assignment_submission_detail(
    db: Session,
    *,
    assignment_id: int,
    teacher_id: int,
    student_id: int,
) -> dict[str, Any] | None:
    assignment = get_assignment_by_id_for_teacher(db, assignment_id=assignment_id, teacher_id=teacher_id)
    if assignment is None:
        return None

    row = db.execute(
        select(
            User.id,
            User.account,
            User.name,
            ChatConversation.id,
            AnswerSubmission.id,
            AnswerSubmission.updated_at,
            AnswerSubmission.source_filename,
            AnswerSubmission.answer_text,
        )
        .join(ChatConversation, ChatConversation.user_id == User.id)
        .outerjoin(AnswerSubmission, AnswerSubmission.conversation_id == ChatConversation.id)
        .where(
            ChatConversation.assignment_id == assignment_id,
            User.role == UserRole.STUDENT,
            User.id == student_id,
        )
    ).first()

    if row is None:
        return None

    return {
        'assignment': assignment,
        'submission': {
            'student_id': int(row[0]),
            'student_account': row[1],
            'student_name': row[2],
            'conversation_id': int(row[3]),
            'has_submission': row[4] is not None,
            'submitted_at': row[5],
            'source_filename': row[6],
            'answer_text': row[7],
        },
    }


def get_chat_conversation_by_id(db: Session, *, conversation_id: int, user_id: int) -> ChatConversation | None:
    stmt = select(ChatConversation).where(
        ChatConversation.id == conversation_id,
        ChatConversation.user_id == user_id,
    )
    return db.scalar(stmt)


def get_answer_submission_by_conversation_id(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
) -> AnswerSubmission | None:
    stmt = select(AnswerSubmission).where(
        AnswerSubmission.user_id == user_id,
        AnswerSubmission.conversation_id == conversation_id,
    )
    return db.scalar(stmt)


def list_chat_conversations_by_user(db: Session, *, user_id: int) -> list[dict[str, Any]]:
    conversations = list(
        db.scalars(
            select(ChatConversation)
            .where(ChatConversation.user_id == user_id)
            .order_by(ChatConversation.updated_at.desc(), ChatConversation.id.desc())
        )
    )
    if not conversations:
        return []

    conversation_ids = [conversation.id for conversation in conversations]
    assignment_ids = [conversation.assignment_id for conversation in conversations if conversation.assignment_id is not None]

    stats_rows = db.execute(
        select(
            ChatRecord.conversation_id,
            func.count(ChatRecord.id),
            func.max(ChatRecord.generated_at),
        )
        .where(ChatRecord.conversation_id.in_(conversation_ids))
        .group_by(ChatRecord.conversation_id)
    ).all()
    stats = {
        row[0]: {
            'record_count': int(row[1] or 0),
            'last_generated_at': row[2],
        }
        for row in stats_rows
        if row[0] is not None
    }

    assignments = (
        list(db.scalars(select(Assignment).where(Assignment.id.in_(assignment_ids))))
        if assignment_ids
        else []
    )
    assignment_map = {assignment.id: assignment for assignment in assignments}

    return [
        {
            'conversation': conversation,
            'assignment': assignment_map.get(conversation.assignment_id),
            'record_count': stats.get(conversation.id, {}).get('record_count', 0),
            'last_generated_at': stats.get(conversation.id, {}).get('last_generated_at'),
        }
        for conversation in conversations
    ]


def save_chat_completion(
    db: Session,
    *,
    conversation: ChatConversation,
    user_id: int,
    model_name: str,
    generated_at: datetime,
    prompt: str,
    content: str,
    citations: list[str],
    keep_limit: int,
) -> tuple[ChatRecord, ChatConversation]:
    record = ChatRecord(
        user_id=user_id,
        conversation_id=conversation.id,
        model_name=model_name,
        generated_at=generated_at,
        prompt=prompt,
        content=content,
        citations=citations,
    )
    db.add(record)

    conversation.updated_at = generated_at
    if _should_replace_conversation_title(conversation.title):
        conversation.title = _build_conversation_title(prompt, max_length=AUTO_CONVERSATION_TITLE_LIMIT)

    db.flush()

    stale_ids = list(
        db.scalars(
            select(ChatRecord.id)
            .where(ChatRecord.conversation_id == conversation.id)
            .order_by(ChatRecord.generated_at.desc(), ChatRecord.id.desc())
            .offset(max(keep_limit, 0))
        )
    )
    if stale_ids:
        db.execute(delete(ChatRecord).where(ChatRecord.id.in_(stale_ids)))

    db.commit()
    db.refresh(conversation)
    db.refresh(record)
    return record, conversation


def list_chat_records_by_user(db: Session, *, user_id: int, limit: int = 20) -> list[ChatRecord]:
    stmt = (
        select(ChatRecord)
        .where(ChatRecord.user_id == user_id)
        .order_by(ChatRecord.generated_at.desc(), ChatRecord.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def list_chat_records_by_conversation(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    limit: int | None = None,
) -> list[ChatRecord]:
    stmt = (
        select(ChatRecord)
        .where(
            ChatRecord.conversation_id == conversation_id,
            ChatRecord.user_id == user_id,
        )
        .order_by(ChatRecord.generated_at.asc(), ChatRecord.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def list_recent_chat_records_for_context(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    limit: int,
) -> list[ChatRecord]:
    if limit <= 0:
        return []

    records = list(
        db.scalars(
            select(ChatRecord)
            .where(
                ChatRecord.conversation_id == conversation_id,
                ChatRecord.user_id == user_id,
            )
            .order_by(ChatRecord.generated_at.desc(), ChatRecord.id.desc())
            .limit(limit)
        )
    )
    records.reverse()
    return records


def upsert_answer_submission(
    db: Session,
    *,
    user_id: int,
    conversation_id: int,
    answer_text: str,
    source_filename: str | None,
) -> AnswerSubmission:
    submission = db.scalar(
        select(AnswerSubmission).where(
            AnswerSubmission.user_id == user_id,
            AnswerSubmission.conversation_id == conversation_id,
        )
    )

    if submission is None:
        submission = AnswerSubmission(
            user_id=user_id,
            conversation_id=conversation_id,
            answer_text=answer_text,
            source_filename=source_filename,
        )
        db.add(submission)
    else:
        submission.answer_text = answer_text
        submission.source_filename = source_filename

    db.commit()
    db.refresh(submission)
    return submission


def _build_answer_preview(answer_text: str | None, *, limit: int = 120) -> str | None:
    normalized = re.sub(r'\s+', ' ', (answer_text or '').strip())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return f'{normalized[:limit].rstrip()}...'


def _should_replace_conversation_title(title: str | None) -> bool:
    normalized = (title or '').strip()
    return normalized in DEFAULT_CONVERSATION_TITLE_ALIASES


def _build_conversation_title(source: str, *, max_length: int) -> str:
    text = re.sub(r'[`#>*_\-]+', ' ', source or '')
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return DEFAULT_CONVERSATION_TITLE
    return text[:max_length]





