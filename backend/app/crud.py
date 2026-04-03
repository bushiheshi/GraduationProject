import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import func, select
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

    conversation_ids = [int(row[3]) for row in rows]
    submitted_at_by_conversation = {
        int(row[3]): row[5]
        for row in rows
        if row[3] is not None
    }
    ai_usage_map = _build_ai_usage_summary_map(
        db,
        conversation_ids=conversation_ids,
        submitted_at_by_conversation=submitted_at_by_conversation,
        include_timeline=False,
    )

    submissions = []
    for row in rows:
        conversation_id = int(row[3])
        ai_usage = ai_usage_map.get(conversation_id, _build_empty_ai_usage_summary())
        submissions.append(
            {
                'student_id': int(row[0]),
                'student_account': row[1],
                'student_name': row[2],
                'conversation_id': conversation_id,
                'has_submission': row[4] is not None,
                'submitted_at': row[5],
                'source_filename': row[6],
                'answer_preview': _build_answer_preview(row[7]),
                'ai_usage_count': ai_usage['total_count'],
                'ai_models_used': ai_usage['models_used'],
                'ai_last_used_at': ai_usage['last_used_at'],
                'ai_learning_summary': ai_usage['learning_summary'],
            }
        )

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

    conversation_id = int(row[3])
    ai_usage = _build_ai_usage_summary_map(
        db,
        conversation_ids=[conversation_id],
        submitted_at_by_conversation={conversation_id: row[5]},
        include_timeline=True,
    ).get(conversation_id, _build_empty_ai_usage_summary(include_timeline=True))

    return {
        'assignment': assignment,
        'submission': {
            'student_id': int(row[0]),
            'student_account': row[1],
            'student_name': row[2],
            'conversation_id': conversation_id,
            'has_submission': row[4] is not None,
            'submitted_at': row[5],
            'source_filename': row[6],
            'answer_text': row[7],
            'ai_usage': ai_usage,
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


def _build_ai_usage_summary_map(
    db: Session,
    *,
    conversation_ids: Iterable[int],
    submitted_at_by_conversation: dict[int, datetime | None] | None = None,
    include_timeline: bool,
) -> dict[int, dict[str, Any]]:
    normalized_ids = [int(conversation_id) for conversation_id in conversation_ids]
    if not normalized_ids:
        return {}

    records = list(
        db.scalars(
            select(ChatRecord)
            .where(ChatRecord.conversation_id.in_(normalized_ids))
            .order_by(ChatRecord.conversation_id.asc(), ChatRecord.generated_at.asc(), ChatRecord.id.asc())
        )
    )
    records_by_conversation: dict[int, list[ChatRecord]] = defaultdict(list)
    for record in records:
        if record.conversation_id is not None:
            records_by_conversation[int(record.conversation_id)].append(record)

    submitted_at_map = submitted_at_by_conversation or {}
    return {
        conversation_id: _build_ai_usage_summary(
            records_by_conversation.get(conversation_id, []),
            submitted_at=submitted_at_map.get(conversation_id),
            include_timeline=include_timeline,
        )
        for conversation_id in normalized_ids
    }


AI_PROMPT_STAGE_RULES = (
    ('checking', '????', ('??', '??', '??', 'debug', 'check', 'verify', 'correct', 'review', '????', '????')),
    ('refinement', '????', ('??', '??', '??', '??', '??', '??', 'polish', 'rewrite', 'revise', 'improve')),
    ('planning', '????', ('??', '??', '??', '??', '??', '????', '???', 'outline', 'plan', 'approach')),
    ('concept', '????', ('???', '??', '??', '??', '??', '??', '??', 'example', 'what is', 'explain', 'difference')),
    ('drafting', '????', ('??', '?', '??', '??', '??', '??', '??', '??', 'write', 'generate', 'complete', 'implement')),
)
GENERAL_STAGE_KEY = 'general'
GENERAL_STAGE_LABEL = '继续追问'
STAGE_SUMMARY_PHRASES = {
    'checking': '检查与纠错',
    'refinement': '修改与润色',
    'planning': '规划解题思路',
    'concept': '理解概念与题意',
    'drafting': '生成答案内容',
    GENERAL_STAGE_KEY: '继续追问与补充',
}
TIMELINE_PROMPT_PREVIEW_LIMIT = 96


def _build_empty_ai_usage_summary(*, include_timeline: bool = False) -> dict[str, Any]:
    return {
        'total_count': 0,
        'first_used_at': None,
        'last_used_at': None,
        'pre_submission_count': 0,
        'post_submission_count': 0,
        'models_used': [],
        'model_stats': [],
        'stage_stats': [],
        'behavior_tags': [],
        'learning_summary': '未检测到该作业的 AI 使用记录。',
        'timeline': [] if include_timeline else [],
    }


def _build_ai_usage_summary(
    records: list[ChatRecord],
    *,
    submitted_at: datetime | None,
    include_timeline: bool,
) -> dict[str, Any]:
    if not records:
        return _build_empty_ai_usage_summary(include_timeline=include_timeline)

    model_counter: Counter[str] = Counter()
    stage_counter: Counter[str] = Counter()
    stage_labels: dict[str, str] = {GENERAL_STAGE_KEY: GENERAL_STAGE_LABEL}
    stage_sequence: list[str] = []
    timeline: list[dict[str, Any]] = []
    previous_stage_key: str | None = None
    pre_submission_count = 0

    for record in records:
        model_counter[record.model_name] += 1
        stage_key, stage_label = _classify_prompt_stage(record.prompt)
        stage_counter[stage_key] += 1
        stage_labels[stage_key] = stage_label

        if stage_key != previous_stage_key:
            stage_sequence.append(stage_key)
            previous_stage_key = stage_key

        if submitted_at is None or record.generated_at <= submitted_at:
            pre_submission_count += 1

        if include_timeline:
            timeline.append(
                {
                    'record_id': int(record.id),
                    'generated_at': record.generated_at,
                    'model_name': record.model_name,
                    'stage_label': stage_label,
                    'prompt_preview': _build_prompt_preview(record.prompt),
                }
            )

    total_count = len(records)
    first_used_at = records[0].generated_at
    last_used_at = records[-1].generated_at
    post_submission_count = max(total_count - pre_submission_count, 0)
    models_used = [name for name, _ in model_counter.most_common()]
    model_stats = [
        {'model_name': model_name, 'count': count}
        for model_name, count in model_counter.most_common()
    ]

    stage_stats: list[dict[str, Any]] = []
    for stage_key, stage_label, _ in AI_PROMPT_STAGE_RULES:
        count = stage_counter.get(stage_key, 0)
        if count:
            stage_stats.append({'key': stage_key, 'label': stage_label, 'count': count})
    if stage_counter.get(GENERAL_STAGE_KEY, 0):
        stage_stats.append(
            {'key': GENERAL_STAGE_KEY, 'label': GENERAL_STAGE_LABEL, 'count': stage_counter[GENERAL_STAGE_KEY]}
        )

    behavior_tags = _build_ai_behavior_tags(
        stage_counter=stage_counter,
        total_count=total_count,
        pre_submission_count=pre_submission_count,
        post_submission_count=post_submission_count,
        submitted_at=submitted_at,
    )
    learning_summary = _build_ai_learning_summary(
        total_count=total_count,
        models_used=models_used,
        first_used_at=first_used_at,
        last_used_at=last_used_at,
        stage_sequence=stage_sequence,
        stage_counter=stage_counter,
        pre_submission_count=pre_submission_count,
        post_submission_count=post_submission_count,
        submitted_at=submitted_at,
    )

    return {
        'total_count': total_count,
        'first_used_at': first_used_at,
        'last_used_at': last_used_at,
        'pre_submission_count': pre_submission_count,
        'post_submission_count': post_submission_count,
        'models_used': models_used,
        'model_stats': model_stats,
        'stage_stats': stage_stats,
        'behavior_tags': behavior_tags,
        'learning_summary': learning_summary,
        'timeline': timeline,
    }


def _classify_prompt_stage(prompt: str) -> tuple[str, str]:
    text = re.sub(r'\s+', ' ', (prompt or '').strip())
    if not text:
        return GENERAL_STAGE_KEY, GENERAL_STAGE_LABEL

    text_lower = text.lower()
    for stage_key, stage_label, keywords in AI_PROMPT_STAGE_RULES:
        for keyword in keywords:
            haystack = text_lower if keyword.isascii() else text
            if keyword in haystack:
                return stage_key, stage_label

    return GENERAL_STAGE_KEY, GENERAL_STAGE_LABEL


def _build_ai_behavior_tags(
    *,
    stage_counter: Counter[str],
    total_count: int,
    pre_submission_count: int,
    post_submission_count: int,
    submitted_at: datetime | None,
) -> list[str]:
    tags: list[str] = []

    if total_count >= 8:
        tags.append('轻度使用')
    elif total_count >= 3:
        tags.append('轻度使用')
    else:
        tags.append('轻度使用')

    if stage_counter.get('concept', 0) or stage_counter.get('planning', 0):
        tags.append('有自我校验')
    if stage_counter.get('drafting', 0):
        tags.append('使用 AI 生成内容')
    if stage_counter.get('refinement', 0):
        tags.append('有修改润色')
    if stage_counter.get('checking', 0):
        tags.append('有修改润色')
    if submitted_at is not None and post_submission_count > 0:
        tags.append('提交前完成交互')
    if submitted_at is not None and pre_submission_count == total_count and total_count > 0:
        tags.append('提交前完成交互')

    deduped_tags: list[str] = []
    for tag in tags:
        if tag not in deduped_tags:
            deduped_tags.append(tag)
    return deduped_tags


def _build_ai_learning_summary(
    *,
    total_count: int,
    models_used: list[str],
    first_used_at: datetime | None,
    last_used_at: datetime | None,
    stage_sequence: list[str],
    stage_counter: Counter[str],
    pre_submission_count: int,
    post_submission_count: int,
    submitted_at: datetime | None,
) -> str:
    if total_count <= 0:
        return '未检测到该作业的 AI 使用记录。'

    model_text = '、'.join(models_used) if models_used else '暂无模型记录'
    parts = [f'该学生在本次作业中共使用 AI {total_count} 次，涉及模型：{model_text}。']

    if first_used_at and last_used_at:
        if first_used_at == last_used_at:
            parts.append(f'记录到的使用时间为 {_format_summary_datetime(first_used_at)}。')
        else:
            parts.append(
                f'使用时间从 {_format_summary_datetime(first_used_at)} 持续到 {_format_summary_datetime(last_used_at)}。'
            )

    if stage_sequence:
        process_text = '，随后'.join(
            STAGE_SUMMARY_PHRASES.get(stage_key, GENERAL_STAGE_LABEL) for stage_key in stage_sequence
        )
        parts.append(f'学习过程大致表现为先{process_text}。')

    concept_and_plan = stage_counter.get('concept', 0) + stage_counter.get('planning', 0)
    refinement_and_checking = stage_counter.get('refinement', 0) + stage_counter.get('checking', 0)
    drafting_count = stage_counter.get('drafting', 0)

    if total_count == 1:
        parts.append('最近一次 AI 使用集中在单次请求，整体交互过程较短。')
    elif concept_and_plan > 0 and refinement_and_checking > 0:
        parts.append('整体上表现为先理解任务，再生成内容，最后进行修改或检查。')
    elif drafting_count >= max(2, total_count // 2 + total_count % 2) and concept_and_plan == 0:
        parts.append('对话主要集中在直接生成答案内容，前期独立拆解任务和结果校验的痕迹较少。')
    elif concept_and_plan > drafting_count:
        parts.append('对话重点更多放在理解题目和规划解题步骤上。')
    else:
        parts.append('对话呈现出边生成边调整的迭代使用方式。')

    if submitted_at is not None:
        if post_submission_count > 0:
            parts.append(
                f'提交后仍继续使用 AI {post_submission_count} 次，说明其在提交后还有补充或调整行为。'
            )
        else:
            parts.append(f'共 {pre_submission_count} 次 AI 交互均发生在提交前。')

    return ''.join(parts)


def _format_summary_datetime(value: datetime) -> str:
    return value.strftime('%Y-%m-%d %H:%M')


def _build_prompt_preview(prompt: str, *, limit: int = TIMELINE_PROMPT_PREVIEW_LIMIT) -> str:
    normalized = re.sub(r'\s+', ' ', (prompt or '').strip())
    if not normalized:
        return '????????'
    if len(normalized) <= limit:
        return normalized
    return f'{normalized[:limit].rstrip()}...'


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





