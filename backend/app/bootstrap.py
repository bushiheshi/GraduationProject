from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app.models import ChatConversation, ChatRecord, User, UserRole
from app.security import get_password_hash


def create_tables() -> None:
    # 根据当前 ORM 模型创建缺失的表；已存在的表会被跳过。
    Base.metadata.create_all(bind=engine)


def _get_columns_by_name(inspector, table_name: str) -> dict[str, dict]:
    return {column['name']: column for column in inspector.get_columns(table_name)}


def _compile_column_type(column: dict) -> str:
    column_type = column['type']
    try:
        return column_type.compile(dialect=engine.dialect).upper()
    except Exception:  # noqa: BLE001
        return str(column_type).upper()


def _find_foreign_key_name(
    foreign_keys: list[dict],
    *,
    referred_table: str,
    constrained_columns: list[str],
) -> str | None:
    return next(
        (
            foreign_key.get('name')
            for foreign_key in foreign_keys
            if foreign_key.get('referred_table') == referred_table
            and foreign_key.get('constrained_columns') == constrained_columns
        ),
        None,
    )


def ensure_conversation_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if 'chat_conversations' not in table_names or 'users' not in table_names:
        return

    columns = _get_columns_by_name(inspector, 'chat_conversations')
    user_columns = _get_columns_by_name(inspector, 'users')
    indexes = inspector.get_indexes('chat_conversations')
    foreign_keys = inspector.get_foreign_keys('chat_conversations')

    target_user_id_type = _compile_column_type(user_columns['id'])
    conversation_user_id_type = _compile_column_type(columns['user_id'])

    has_user_index = any(index.get('column_names') == ['user_id'] for index in indexes)
    has_updated_at_index = any(index.get('column_names') == ['updated_at'] for index in indexes)
    user_fk_name = _find_foreign_key_name(
        foreign_keys,
        referred_table='users',
        constrained_columns=['user_id'],
    )
    has_user_fk = bool(user_fk_name)

    with engine.begin() as conn:
        if has_user_fk and conversation_user_id_type != target_user_id_type:
            conn.execute(text(f'ALTER TABLE chat_conversations DROP FOREIGN KEY `{user_fk_name}`'))
            has_user_fk = False

        if conversation_user_id_type != target_user_id_type or columns['user_id'].get('nullable', True):
            conn.execute(
                text(
                    'ALTER TABLE chat_conversations '
                    f'MODIFY COLUMN user_id {target_user_id_type} NOT NULL'
                )
            )

        if not has_user_index:
            conn.execute(text('CREATE INDEX idx_chat_conversations_user_id ON chat_conversations (user_id)'))
        if not has_updated_at_index:
            conn.execute(text('CREATE INDEX idx_chat_conversations_updated_at ON chat_conversations (updated_at)'))
        if not has_user_fk:
            conn.execute(
                text(
                    'ALTER TABLE chat_conversations '
                    'ADD CONSTRAINT fk_chat_conversations_user_id '
                    'FOREIGN KEY (user_id) REFERENCES users(id)'
                )
            )


def ensure_chat_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if 'chat_records' not in table_names or 'chat_conversations' not in table_names or 'users' not in table_names:
        return

    columns = _get_columns_by_name(inspector, 'chat_records')
    conversation_columns = _get_columns_by_name(inspector, 'chat_conversations')
    user_columns = _get_columns_by_name(inspector, 'users')
    indexes = inspector.get_indexes('chat_records')
    foreign_keys = inspector.get_foreign_keys('chat_records')

    target_user_id_type = _compile_column_type(user_columns['id'])
    target_conversation_id_type = _compile_column_type(conversation_columns['id'])
    record_user_id_type = _compile_column_type(columns['user_id'])

    has_conversation_index = any(index.get('column_names') == ['conversation_id'] for index in indexes)
    user_fk_name = _find_foreign_key_name(
        foreign_keys,
        referred_table='users',
        constrained_columns=['user_id'],
    )
    conversation_fk_name = _find_foreign_key_name(
        foreign_keys,
        referred_table='chat_conversations',
        constrained_columns=['conversation_id'],
    )
    has_user_fk = bool(user_fk_name)
    has_conversation_fk = bool(conversation_fk_name)

    with engine.begin() as conn:
        if 'conversation_id' not in columns:
            conn.execute(
                text(
                    'ALTER TABLE chat_records '
                    f'ADD COLUMN conversation_id {target_conversation_id_type} NULL'
                )
            )
            columns['conversation_id'] = {'type': target_conversation_id_type, 'nullable': True}

        record_conversation_id_type = (
            columns['conversation_id']['type']
            if isinstance(columns['conversation_id']['type'], str)
            else _compile_column_type(columns['conversation_id'])
        )

        if has_user_fk and record_user_id_type != target_user_id_type:
            conn.execute(text(f'ALTER TABLE chat_records DROP FOREIGN KEY `{user_fk_name}`'))
            has_user_fk = False
        if has_conversation_fk and record_conversation_id_type != target_conversation_id_type:
            conn.execute(text(f'ALTER TABLE chat_records DROP FOREIGN KEY `{conversation_fk_name}`'))
            has_conversation_fk = False

        if record_user_id_type != target_user_id_type or columns['user_id'].get('nullable', True):
            conn.execute(
                text(
                    'ALTER TABLE chat_records '
                    f'MODIFY COLUMN user_id {target_user_id_type} NOT NULL'
                )
            )
        if (
            record_conversation_id_type != target_conversation_id_type
            or not columns['conversation_id'].get('nullable', True)
        ):
            conn.execute(
                text(
                    'ALTER TABLE chat_records '
                    f'MODIFY COLUMN conversation_id {target_conversation_id_type} NULL'
                )
            )

        if not has_conversation_index:
            conn.execute(text('CREATE INDEX idx_chat_conversation_id ON chat_records (conversation_id)'))
        if not has_user_fk:
            conn.execute(
                text(
                    'ALTER TABLE chat_records '
                    'ADD CONSTRAINT fk_chat_records_user_id '
                    'FOREIGN KEY (user_id) REFERENCES users(id)'
                )
            )
        if not has_conversation_fk:
            conn.execute(
                text(
                    'ALTER TABLE chat_records '
                    'ADD CONSTRAINT fk_chat_records_conversation_id '
                    'FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)'
                )
            )


def migrate_legacy_chat_records() -> None:
    db = SessionLocal()
    try:
        records = list(
            db.query(ChatRecord)
            .filter(ChatRecord.conversation_id.is_(None))
            .order_by(ChatRecord.user_id.asc(), ChatRecord.generated_at.asc(), ChatRecord.id.asc())
            .all()
        )
        if not records:
            return

        for record in records:
            conversation = ChatConversation(
                user_id=record.user_id,
                title=(record.prompt or '历史对话').strip()[:40] or '历史对话',
                created_at=record.generated_at,
                updated_at=record.generated_at,
            )
            db.add(conversation)
            db.flush()
            record.conversation_id = conversation.id

        db.commit()
    finally:
        db.close()


def seed_default_users() -> None:
    # 写入演示账号，便于首次启动后直接登录验证流程。
    db = SessionLocal()
    try:
        student = db.query(User).filter(User.account == 'student001').first()
        teacher = db.query(User).filter(User.account == 'teacher001').first()

        if not student:
            db.add(
                User(
                    account='student001',
                    name='Demo Student',
                    role=UserRole.STUDENT,
                    password_hash=get_password_hash('123456'),
                )
            )

        if not teacher:
            db.add(
                User(
                    account='teacher001',
                    name='Demo Teacher',
                    role=UserRole.TEACHER,
                    password_hash=get_password_hash('123456'),
                )
            )

        db.commit()
    finally:
        db.close()


def init_app_database(*, seed_demo_users: bool = True) -> None:
    # 统一数据库初始化入口：建表 + 可选种子数据。
    create_tables()
    ensure_conversation_schema()
    ensure_chat_schema()
    migrate_legacy_chat_records()

    if seed_demo_users:
        seed_default_users()


def ping_database() -> None:
    # 启动前执行轻量查询，便于尽早暴露连接配置问题。
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
