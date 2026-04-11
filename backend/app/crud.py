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
KEYWORD_SUMMARY_LIMIT = 12
KEYWORD_DETAIL_LIMIT = 40
KEYWORD_SAMPLE_LIMIT = 2
ENGLISH_KEYWORD_RE = re.compile(r'[a-z][a-z0-9+#._-]{2,}')
CHINESE_SEGMENT_RE = re.compile(r'[\u4e00-\u9fff]{2,32}')
PROMPT_SENTENCE_SPLIT_RE = re.compile(r'[。！？；;!\?\n]+')
ENGLISH_KEYWORD_STOPWORDS = {
    'the',
    'and',
    'for',
    'with',
    'that',
    'this',
    'from',
    'into',
    'what',
    'why',
    'how',
    'can',
    'could',
    'would',
    'should',
    'please',
    'help',
    'question',
    'problem',
    'answer',
    'assignment',
    'homework',
}
COMPUTER_TECHNICAL_KEYWORDS = (
    '数据结构',
    '算法',
    '时间复杂度',
    '空间复杂度',
    '递归',
    '指针',
    '引用',
    '空指针',
    '野指针',
    '数组',
    '链表',
    '队列',
    '遍历',
    '节点',
    '根节点',
    '叶子节点',
    '二叉树',
    '平衡树',
    '红黑树',
    '哈希',
    '哈希表',
    '图论',
    '动态规划',
    '贪心',
    '回溯',
    '并查集',
    '最短路径',
    '深度优先',
    '广度优先',
    '排序',
    '二分查找',
    '前缀和',
    '滑动窗口',
    '快速排序',
    '归并排序',
    '堆排序',
    '冒泡排序',
    '插入排序',
    '选择排序',
    '字符串',
    '编译原理',
    '编译器',
    '操作系统',
    '进程',
    '线程',
    '死锁',
    '同步',
    '并发',
    '虚拟内存',
    '页表',
    '中断',
    '文件系统',
    '计算机网络',
    '网络层',
    '传输层',
    '应用层',
    '数据库',
    '事务',
    '索引',
    '主键',
    '外键',
    '连接查询',
    '范式',
    '接口',
    '路由',
    '鉴权',
    '权限',
    '报错',
    '调试',
    '内存',
    '缓存',
    '协议',
    '套接字',
    '结构体',
    '函数',
    '参数',
    '返回值',
    '变量',
    '局部变量',
    '全局变量',
    '变量作用域',
    '作用域',
    '常量',
    '赋值',
    '赋值语句',
    '表达式',
    '语句',
    '条件语句',
    '条件判断',
    '判断语句',
    '循环',
    '循环语句',
    'for循环',
    'while循环',
    'do while循环',
    '嵌套循环',
    '死循环',
    'break',
    'continue',
    'return',
    'if语句',
    'else语句',
    'switch语句',
    '分支语句',
    '输入',
    '输出',
    '输入输出',
    '打印',
    '注释',
    '缩进',
    '函数调用',
    '函数定义',
    '调用函数',
    '形参',
    '实参',
    '默认参数',
    '布尔',
    '整型',
    '浮点型',
    '字符',
    '字符型',
    '字符串',
    '字符串拼接',
    '类型',
    '数据类型',
    '类型转换',
    '逻辑运算',
    '算术运算',
    '比较运算',
    '取余',
    '模运算',
    '下标',
    '索引访问',
    '列表',
    '字典',
    '集合',
    '元组',
    '数组下标',
    '越界访问',
    '空值',
    '异常',
    '异常处理',
    '错误处理',
    '调试输出',
    '类',
    '对象',
    '继承',
    '多态',
    '封装',
    '泛型',
    '模板',
    '计算机组成原理',
    '组成原理',
    '软件工程',
    '面向对象',
    '设计模式',
    'binary tree',
    'linked list',
    'hash table',
    'dynamic programming',
    'greedy',
    'backtracking',
    'depth first search',
    'breadth first search',
    'dfs',
    'bfs',
    'dp',
    'pointer',
    'recursion',
    'array',
    'stack',
    'queue',
    'graph',
    'tree',
    'sorting',
    'quick sort',
    'merge sort',
    'heap sort',
    'compiler',
    'operating system',
    'process',
    'thread',
    'deadlock',
    'database',
    'transaction',
    'index',
    'join',
    'normal form',
    'sql',
    'mysql',
    'postgresql',
    'redis',
    'mongodb',
    'python',
    'java',
    'c++',
    'c#',
    'javascript',
    'typescript',
    'html',
    'css',
    'vue',
    'react',
    'fastapi',
    'django',
    'flask',
    'node.js',
    'nodejs',
    'docker',
    'git',
    'linux',
    'tcp',
    'udp',
    'http',
    'https',
    'api',
    'json',
    'jwt',
    'for loop',
    'while loop',
    'if statement',
    'switch statement',
    'nested loop',
    'infinite loop',
    'break',
    'continue',
    'return',
    'variable',
    'local variable',
    'global variable',
    'scope',
    'function',
    'function call',
    'function definition',
    'parameter',
    'argument',
    'default parameter',
    'type',
    'data type',
    'type conversion',
    'boolean',
    'integer',
    'float',
    'string',
    'list',
    'dict',
    'dictionary',
    'tuple',
    'set',
    'index',
    'subscript',
    'exception',
    'try',
    'except',
    'print',
    'input',
)
CHINESE_TECHNICAL_HEADWORDS = tuple(
    sorted(
        {
            keyword
            for keyword in COMPUTER_TECHNICAL_KEYWORDS
            if not keyword.isascii() and 2 <= len(keyword) <= 8
        }
        | {
            '复杂度',
            '前序',
            '中序',
            '后序',
            '层序',
            '越界',
            '初始化',
            '空节点',
            '空树',
            '出口条件',
            '返回条件',
            '空值',
            '空引用',
            '空对象',
            '鉴权失败',
            '权限不足',
            '事务隔离',
            '回滚',
            '提交',
            '查询',
            '更新',
            '删除',
            '插入',
        },
        key=len,
        reverse=True,
    )
)
TECHNICAL_PHRASE_HINTS = (
    '定义',
    '原理',
    '实现',
    '过程',
    '步骤',
    '区别',
    '条件',
    '出口',
    '层序',
    '前序',
    '中序',
    '后序',
    '初始化',
    '越界',
    '为空',
    '失败',
    '失效',
    '冲突',
    '隔离',
    '回滚',
    '请求',
    '响应',
    '连接',
    '登录',
    '注册',
    '提交',
    '查询',
    '更新',
    '删除',
    '插入',
    '遍历',
)
PHRASE_TAIL_KEYWORDS = (
    '循环',
    '循环语句',
    '语句',
    '条件判断',
    '判断',
    '遍历',
    '排序',
    '查找',
    '复杂度',
    '鉴权',
    '配置',
    '初始化',
    '越界',
    '溢出',
    '隔离',
    '回滚',
    '提交',
    '查询',
    '更新',
    '删除',
    '插入',
    '报错',
    '异常',
    '条件',
    '出口条件',
    '实现',
    '原理',
    '定义',
    '区别',
    '过程',
    '步骤',
    '优化',
)
QUESTION_SUFFIX_HINTS = (
    '区别',
    '规则',
    '写法',
    '语法',
    '作用域',
    '参数传递',
    '异常处理',
    '错误处理',
    '越界',
    '流程',
    '顺序',
)
RULE_SUFFIX_HINTS = (
    '规则',
    '语法',
    '写法',
    '格式',
    '怎么写',
    '怎么用',
)
CHINESE_NOISE_PREFIXES = (
    '老师请问',
    '老师想问',
    '我想请教',
    '我想问一下',
    '我想问',
    '想问一下',
    '想问',
    '帮我看看',
    '帮我看',
    '请帮我',
    '请问',
    '问',
    '老师',
    '这个',
    '那个',
    '这道题',
    '那道题',
    '这题',
    '那题',
    '这里',
    '这个题',
    '这个地方',
    '为什么',
    '为啥',
    '怎么',
    '如何',
    '能不能',
    '可不可以',
    '是不是',
)
CHINESE_NOISE_SUFFIXES = (
    '是什么',
    '是什么意思',
    '为什么',
    '为啥',
    '怎么写',
    '怎么做',
    '怎么实现',
    '怎么理解',
    '怎么处理',
    '怎么办',
    '可以吗',
    '对吗',
    '吗',
    '呢',
    '呀',
    '啊',
    '吧',
)
PROGRAMMING_COMPOSITE_RULES = (
    (('for循环', 'while循环'), 'while循环和for循环的区别'),
    (('for循环', 'if语句'), 'for循环和if语句的区别'),
    (('while循环', 'if语句'), 'while循环和if语句的区别'),
    (('局部变量', '全局变量', '作用域'), '变量作用域'),
    (('函数调用', '形参', '实参'), '函数参数传递'),
    (('形参', '实参'), '函数参数传递'),
    (('列表', '下标', '越界'), '列表下标越界'),
    (('数组', '下标', '越界'), '数组下标越界'),
    (('try', 'except', '异常处理'), 'try except异常处理'),
    (('try', 'except'), 'try except异常处理'),
    (('for循环', '规则'), 'for循环规则'),
    (('while循环', '规则'), 'while循环规则'),
    (('if语句', '写法'), 'if语句写法'),
    (('if语句', '语法'), 'if语句语法'),
    (('switch语句', '写法'), 'switch语句写法'),
    (('break', 'continue'), 'break和continue的区别'),
)


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


def list_assignment_question_keywords(
    db: Session,
    *,
    assignment_id: int,
    teacher_id: int,
    limit: int = KEYWORD_SUMMARY_LIMIT,
) -> dict[str, Any] | None:
    assignment = get_assignment_by_id_for_teacher(db, assignment_id=assignment_id, teacher_id=teacher_id)
    if assignment is None:
        return None

    rows = _list_assignment_chat_keyword_rows(db, assignment_id=assignment_id)
    keyword_index: dict[str, dict[str, Any]] = {}

    for row in rows:
        record = row['record']
        user = row['user']
        prompt = record.prompt or ''
        if not prompt.strip():
            continue

        for keyword in _extract_prompt_keywords(prompt):
            item = keyword_index.setdefault(
                keyword,
                {
                    'keyword': keyword,
                    'count': 0,
                    'student_ids': set(),
                    'sample_prompts': [],
                    'sample_students': [],
                },
            )
            item['count'] += 1
            item['student_ids'].add(int(user.id))
            if len(item['sample_prompts']) < KEYWORD_SAMPLE_LIMIT and prompt not in item['sample_prompts']:
                item['sample_prompts'].append(_build_prompt_preview(prompt, limit=72))
            if len(item['sample_students']) < KEYWORD_SAMPLE_LIMIT and user.name not in item['sample_students']:
                item['sample_students'].append(user.name)

    keywords = _select_top_keywords(keyword_index.values(), limit=limit)
    return {
        'assignment': assignment,
        'keywords': keywords,
    }


def get_assignment_keyword_detail(
    db: Session,
    *,
    assignment_id: int,
    teacher_id: int,
    keyword: str,
    limit: int = KEYWORD_DETAIL_LIMIT,
) -> dict[str, Any] | None:
    assignment = get_assignment_by_id_for_teacher(db, assignment_id=assignment_id, teacher_id=teacher_id)
    if assignment is None:
        return None

    normalized_keyword = (keyword or '').strip()
    if not normalized_keyword:
        return {
            'assignment': assignment,
            'keyword': '',
            'count': 0,
            'student_count': 0,
            'matches': [],
        }

    rows = _list_assignment_chat_keyword_rows(db, assignment_id=assignment_id)
    matches: list[dict[str, Any]] = []
    student_ids: set[int] = set()

    for row in rows:
        record = row['record']
        user = row['user']
        submission = row['submission']
        prompt = record.prompt or ''
        if not _prompt_contains_keyword(prompt, normalized_keyword):
            continue

        student_ids.add(int(user.id))
        matches.append(
            {
                'record_id': int(record.id),
                'conversation_id': int(record.conversation_id or 0),
                'student_id': int(user.id),
                'student_account': user.account,
                'student_name': user.name,
                'generated_at': record.generated_at,
                'prompt': prompt,
                'content': record.content,
                'submitted_at': submission.updated_at if submission else None,
                'submission_answer_preview': _build_answer_preview(submission.answer_text if submission else None, limit=160),
            }
        )

    matches.sort(key=lambda item: (item['generated_at'], item['record_id']), reverse=True)
    return {
        'assignment': assignment,
        'keyword': normalized_keyword,
        'count': len(matches),
        'student_count': len(student_ids),
        'matches': matches[:limit],
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


def _list_assignment_chat_keyword_rows(db: Session, *, assignment_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ChatRecord, User, AnswerSubmission)
        .join(ChatConversation, ChatConversation.id == ChatRecord.conversation_id)
        .join(User, User.id == ChatConversation.user_id)
        .outerjoin(AnswerSubmission, AnswerSubmission.conversation_id == ChatConversation.id)
        .where(
            ChatConversation.assignment_id == assignment_id,
            User.role == UserRole.STUDENT,
        )
        .order_by(ChatRecord.generated_at.asc(), ChatRecord.id.asc())
    ).all()

    return [
        {
            'record': row[0],
            'user': row[1],
            'submission': row[2],
        }
        for row in rows
    ]


def _extract_prompt_keywords(prompt: str) -> set[str]:
    normalized = re.sub(r'\s+', ' ', (prompt or '').strip())
    if not normalized:
        return set()

    lowered = normalized.lower()
    keywords = _extract_technical_keywords(normalized)
    for sentence in _split_prompt_sentences(normalized):
        keywords.update(_extract_sentence_keywords(sentence))
        keywords.update(_extract_programming_composite_keywords(sentence))

    for match in ENGLISH_KEYWORD_RE.finditer(lowered):
        keyword = match.group(0).strip('._-')
        if keyword and keyword not in ENGLISH_KEYWORD_STOPWORDS and not keyword.isdigit():
            keywords.add(keyword)

    return keywords


def _extract_technical_keywords(prompt: str) -> set[str]:
    lowered = prompt.lower()
    keywords: set[str] = set()

    for keyword in COMPUTER_TECHNICAL_KEYWORDS:
        haystack = lowered if keyword.isascii() else prompt
        if keyword in haystack:
            keywords.add(keyword)

    return keywords


def _split_prompt_sentences(prompt: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in PROMPT_SENTENCE_SPLIT_RE.split(prompt)
        if sentence and sentence.strip()
    ]


def _extract_sentence_keywords(sentence: str) -> set[str]:
    scored_candidates: dict[str, int] = {}

    for keyword in _extract_technical_keywords(sentence):
        if keyword.isascii():
            continue
        primary_headword = _select_primary_headword(keyword)
        scored_candidates[keyword] = max(
            scored_candidates.get(keyword, 0),
            _score_sentence_keyword(keyword, primary_headword),
        )

    for segment in CHINESE_SEGMENT_RE.findall(sentence):
        for candidate in _extract_structured_phrase_candidates(segment):
            score = _score_sentence_keyword(candidate, _select_primary_headword(candidate))
            previous = scored_candidates.get(candidate)
            if previous is None or score > previous:
                scored_candidates[candidate] = score

    if not scored_candidates:
        return set()

    ranked = sorted(
        scored_candidates.items(),
        key=lambda item: (item[1], len(item[0]), item[0]),
        reverse=True,
    )

    selected: list[str] = []
    for keyword, _ in ranked:
        if any(keyword in existing or existing in keyword for existing in selected):
            continue
        selected.append(keyword)
        if len(selected) >= 4:
            break

    return set(selected)


def _extract_programming_composite_keywords(sentence: str) -> set[str]:
    lowered = sentence.lower()
    detected_keywords = _extract_technical_keywords(sentence)
    composites: set[str] = set()

    for required_keywords, phrase in PROGRAMMING_COMPOSITE_RULES:
        if all(_sentence_contains_token(sentence, lowered, token) for token in required_keywords):
            composites.add(phrase)

    if _sentence_contains_token(sentence, lowered, 'for循环') and _contains_specific_suffix(sentence, 'for循环', RULE_SUFFIX_HINTS):
        composites.add('for循环规则')
    if _sentence_contains_token(sentence, lowered, 'while循环') and _contains_specific_suffix(sentence, 'while循环', RULE_SUFFIX_HINTS):
        composites.add('while循环规则')
    if _sentence_contains_token(sentence, lowered, 'if语句') and _contains_specific_suffix(sentence, 'if语句', RULE_SUFFIX_HINTS):
        composites.add('if语句写法')

    if _contains_any_token(detected_keywords, ('局部变量', '全局变量', '变量')) and '作用域' in sentence:
        composites.add('变量作用域')
    if _contains_any_token(detected_keywords, ('函数调用', '函数', '形参', '实参')) and (
        '参数传递' in sentence or ('形参' in sentence and '实参' in sentence)
    ):
        composites.add('函数参数传递')
    if _contains_any_token(detected_keywords, ('列表', '数组')) and '下标' in sentence and '越界' in sentence:
        composites.add('列表下标越界' if '列表' in sentence else '数组下标越界')
    if _sentence_contains_token(sentence, lowered, 'try') and _sentence_contains_token(sentence, lowered, 'except'):
        if '异常处理' in sentence or '错误处理' in sentence:
            composites.add('try except异常处理')

    return composites


def _extract_structured_phrase_candidates(segment: str) -> set[str]:
    candidates: set[str] = set()

    for tail in PHRASE_TAIL_KEYWORDS:
        start = 0
        while True:
            index = segment.find(tail, start)
            if index < 0:
                break

            best_candidate = ''
            best_score = -1
            left_boundary = max(0, index - 6)
            tail_end = index + len(tail)

            for left in range(left_boundary, index + 1):
                candidate = _clean_chinese_keyword_candidate(segment[left:tail_end])
                if not candidate or not _is_valid_sentence_keyword(candidate, tail):
                    continue
                score = _score_sentence_keyword(candidate, tail)
                if score > best_score or (score == best_score and len(candidate) > len(best_candidate)):
                    best_candidate = candidate
                    best_score = score

            if best_candidate:
                candidates.add(best_candidate)

            start = index + 1

    return candidates


def _clean_chinese_keyword_candidate(candidate: str) -> str:
    cleaned = candidate.strip()
    updated = True
    while updated and cleaned:
        updated = False
        for prefix in CHINESE_NOISE_PREFIXES:
            if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
                cleaned = cleaned[len(prefix):]
                updated = True
                break
        if updated:
            continue
        for suffix in CHINESE_NOISE_SUFFIXES:
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix):
                cleaned = cleaned[:-len(suffix)]
                updated = True
                break

    return cleaned.strip()


def _is_valid_sentence_keyword(candidate: str, headword: str) -> bool:
    if len(candidate) < 2 or len(candidate) > 12:
        return False
    if headword not in candidate:
        return False
    if not _contains_chinese_technical_signal(candidate):
        return False
    if not _starts_with_chinese_technical_signal(candidate):
        return False
    if candidate in CHINESE_NOISE_PREFIXES or candidate in CHINESE_NOISE_SUFFIXES:
        return False
    if candidate.startswith(('的', '了', '把', '被')) or candidate.endswith(('的', '了', '把', '被')):
        return False
    if any(noise in candidate for noise in ('老师', '请问', '帮我', '看看', '一下', '为什么', '怎么', '如何', '什么', '有什么')):
        return False
    return True


def _score_sentence_keyword(candidate: str, headword: str) -> int:
    score = 0
    technical_hit_count = sum(1 for technical in CHINESE_TECHNICAL_HEADWORDS if technical in candidate)

    if candidate in COMPUTER_TECHNICAL_KEYWORDS:
        score += 3
    if candidate == headword:
        score += 1
    score += technical_hit_count * 2
    if len(candidate) > len(headword):
        score += 3
    if any(hint in candidate for hint in TECHNICAL_PHRASE_HINTS) and candidate != headword:
        score += 2
    return score


def _contains_chinese_technical_signal(candidate: str) -> bool:
    return any(technical in candidate for technical in CHINESE_TECHNICAL_HEADWORDS)


def _starts_with_chinese_technical_signal(candidate: str) -> bool:
    return any(candidate.startswith(technical) for technical in CHINESE_TECHNICAL_HEADWORDS)


def _sentence_contains_token(sentence: str, lowered: str, token: str) -> bool:
    haystack = lowered if token.isascii() else sentence
    needle = token.lower() if token.isascii() else token
    return needle in haystack


def _contains_any_token(detected_keywords: set[str], tokens: tuple[str, ...]) -> bool:
    return any(token in detected_keywords for token in tokens)


def _contains_specific_suffix(sentence: str, keyword: str, suffixes: tuple[str, ...]) -> bool:
    if keyword not in sentence:
        return False
    trailing = sentence[sentence.find(keyword) + len(keyword):]
    return any(suffix in trailing for suffix in suffixes)


def _select_primary_headword(candidate: str) -> str:
    matched = [technical for technical in CHINESE_TECHNICAL_HEADWORDS if technical in candidate]
    if not matched:
        return candidate
    return max(matched, key=len)


def _prompt_contains_keyword(prompt: str, keyword: str) -> bool:
    normalized_prompt = prompt or ''
    if not normalized_prompt or not keyword:
        return False
    if keyword.isascii():
        return keyword.lower() in normalized_prompt.lower()
    return keyword in normalized_prompt


def _select_top_keywords(keyword_items: Iterable[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    candidates = [
        {
            'keyword': item['keyword'],
            'count': int(item['count']),
            'student_count': len(item['student_ids']),
            'student_ids': set(item['student_ids']),
            'sample_prompts': item['sample_prompts'],
            'sample_students': item['sample_students'],
        }
        for item in keyword_items
        if int(item['count']) > 0
    ]

    candidates.sort(
        key=lambda item: (
            item['count'],
            item['student_count'],
            len(item['keyword']),
            item['keyword'],
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    for item in candidates:
        if _is_redundant_keyword(item, selected):
            continue

        selected.append(
            {
                'keyword': item['keyword'],
                'count': item['count'],
                'student_count': item['student_count'],
                'sample_prompts': item['sample_prompts'],
                'sample_students': item['sample_students'],
            }
        )
        if len(selected) >= limit:
            break

    return selected


def _is_redundant_keyword(item: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    for existing in selected:
        existing_keyword = existing['keyword']
        if (
            item['keyword'] in existing_keyword
            and item['count'] == existing['count']
            and item['student_count'] == existing['student_count']
        ):
            return True
    return False


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





