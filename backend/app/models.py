from datetime import datetime
from enum import Enum

from sqlalchemy import BIGINT, JSON, Boolean, DateTime, Enum as SqlEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, Enum):
    STUDENT = 'student'
    TEACHER = 'teacher'


class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, index=True)
    account: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(
            UserRole,
            name='userrole',
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class GradeClass(Base):
    __tablename__ = 'grade_classes'
    __table_args__ = (
        UniqueConstraint('grade_label', 'class_label', name='uq_grade_classes_grade_class'),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, index=True)
    grade_label: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    class_label: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class ClassMembership(Base):
    __tablename__ = 'class_memberships'
    __table_args__ = (
        UniqueConstraint('class_id', 'user_id', name='uq_class_memberships_class_user'),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, index=True)
    class_id: Mapped[int] = mapped_column(BIGINT, ForeignKey('grade_classes.id'), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey('users.id'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Assignment(Base):
    __tablename__ = 'assignments'

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(BIGINT, ForeignKey('users.id'), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class ChatConversation(Base):
    __tablename__ = 'chat_conversations'

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey('users.id'), nullable=False, index=True)
    assignment_id: Mapped[int | None] = mapped_column(
        BIGINT,
        ForeignKey('assignments.id'),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False, default='New Conversation')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        index=True,
    )


class ChatRecord(Base):
    __tablename__ = 'chat_records'

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey('users.id'), nullable=False, index=True)
    conversation_id: Mapped[int | None] = mapped_column(
        BIGINT,
        ForeignKey('chat_conversations.id'),
        nullable=True,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AnswerSubmission(Base):
    __tablename__ = 'answer_submissions'

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(BIGINT, ForeignKey('users.id'), nullable=False, index=True)
    conversation_id: Mapped[int] = mapped_column(
        BIGINT,
        ForeignKey('chat_conversations.id'),
        nullable=False,
        unique=True,
        index=True,
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

