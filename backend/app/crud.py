import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import ChatConversation, ChatRecord, User, UserRole

DEFAULT_CONVERSATION_TITLE = '新对话'


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
    created_at: datetime | None = None,
) -> ChatConversation:
    timestamp = created_at or datetime.utcnow()
    conversation = ChatConversation(
        user_id=user_id,
        title=_build_conversation_title(title or DEFAULT_CONVERSATION_TITLE),
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get_chat_conversation_by_id(db: Session, *, conversation_id: int, user_id: int) -> ChatConversation | None:
    stmt = select(ChatConversation).where(
        ChatConversation.id == conversation_id,
        ChatConversation.user_id == user_id,
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

    return [
        {
            'conversation': conversation,
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
        conversation.title = _build_conversation_title(prompt)

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


def _should_replace_conversation_title(title: str | None) -> bool:
    normalized = (title or '').strip()
    return not normalized or normalized == DEFAULT_CONVERSATION_TITLE


def _build_conversation_title(source: str) -> str:
    text = re.sub(r'[`#>*_\-]+', ' ', source or '')
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return DEFAULT_CONVERSATION_TITLE
    return text[:40]

