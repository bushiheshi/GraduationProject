from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app.models import AnswerSubmission, Assignment, ChatConversation, ChatRecord, User, UserRole
from app.security import get_password_hash


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def _get_columns_by_name(inspector, table_name: str) -> dict[str, dict]:
    return {column['name']: column for column in inspector.get_columns(table_name)}


def _compile_column_type(column: dict) -> str:
    column_type = column['type']
    try:
        return column_type.compile(dialect=engine.dialect).upper()
    except Exception:  # noqa: BLE001
        return str(column_type).upper()


def _quote_identifier(identifier: str) -> str:
    quote_char = '"' if engine.dialect.name == 'postgresql' else '`'
    return f'{quote_char}{identifier.replace(quote_char, quote_char * 2)}{quote_char}'


def _alter_column_type_and_nullability(
    conn,
    *,
    table_name: str,
    column_name: str,
    column_type: str,
    nullable: bool,
) -> None:
    table_ident = _quote_identifier(table_name)
    column_ident = _quote_identifier(column_name)

    if engine.dialect.name == 'postgresql':
        conn.execute(text(f'ALTER TABLE {table_ident} ALTER COLUMN {column_ident} TYPE {column_type}'))
        conn.execute(
            text(
                f'ALTER TABLE {table_ident} ALTER COLUMN {column_ident} '
                f'{"DROP" if nullable else "SET"} NOT NULL'
            )
        )
        return

    null_sql = 'NULL' if nullable else 'NOT NULL'
    conn.execute(text(f'ALTER TABLE {table_ident} MODIFY COLUMN {column_ident} {column_type} {null_sql}'))


def _add_column(
    conn,
    *,
    table_name: str,
    column_name: str,
    column_type: str,
    nullable: bool,
) -> None:
    table_ident = _quote_identifier(table_name)
    column_ident = _quote_identifier(column_name)
    null_sql = 'NULL' if nullable else 'NOT NULL'
    conn.execute(text(f'ALTER TABLE {table_ident} ADD COLUMN {column_ident} {column_type} {null_sql}'))


def _drop_foreign_key(conn, *, table_name: str, constraint_name: str) -> None:
    table_ident = _quote_identifier(table_name)
    constraint_ident = _quote_identifier(constraint_name)

    if engine.dialect.name == 'postgresql':
        conn.execute(text(f'ALTER TABLE {table_ident} DROP CONSTRAINT IF EXISTS {constraint_ident}'))
        return

    conn.execute(text(f'ALTER TABLE {table_ident} DROP FOREIGN KEY {constraint_ident}'))


def _create_index(conn, *, table_name: str, index_name: str, column_names: list[str]) -> None:
    table_ident = _quote_identifier(table_name)
    index_ident = _quote_identifier(index_name)
    columns_sql = ', '.join(_quote_identifier(column_name) for column_name in column_names)
    conn.execute(text(f'CREATE INDEX {index_ident} ON {table_ident} ({columns_sql})'))


def _add_foreign_key(
    conn,
    *,
    table_name: str,
    constraint_name: str,
    column_name: str,
    referred_table: str,
    referred_column: str = 'id',
) -> None:
    table_ident = _quote_identifier(table_name)
    constraint_ident = _quote_identifier(constraint_name)
    column_ident = _quote_identifier(column_name)
    referred_table_ident = _quote_identifier(referred_table)
    referred_column_ident = _quote_identifier(referred_column)
    conn.execute(
        text(
            f'ALTER TABLE {table_ident} '
            f'ADD CONSTRAINT {constraint_ident} '
            f'FOREIGN KEY ({column_ident}) REFERENCES {referred_table_ident}({referred_column_ident})'
        )
    )


def _add_unique_constraint(
    conn,
    *,
    table_name: str,
    constraint_name: str,
    column_names: list[str],
) -> None:
    table_ident = _quote_identifier(table_name)
    constraint_ident = _quote_identifier(constraint_name)
    columns_sql = ', '.join(_quote_identifier(column_name) for column_name in column_names)
    conn.execute(text(f'ALTER TABLE {table_ident} ADD CONSTRAINT {constraint_ident} UNIQUE ({columns_sql})'))


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


def _find_unique_constraint_name(
    unique_constraints: list[dict],
    constrained_columns: list[str],
) -> str | None:
    return next(
        (
            unique_constraint.get('name')
            for unique_constraint in unique_constraints
            if unique_constraint.get('column_names') == constrained_columns
        ),
        None,
    )


def ensure_assignment_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if 'assignments' not in table_names or 'users' not in table_names:
        return

    columns = _get_columns_by_name(inspector, 'assignments')
    user_columns = _get_columns_by_name(inspector, 'users')
    indexes = inspector.get_indexes('assignments')
    foreign_keys = inspector.get_foreign_keys('assignments')

    target_teacher_id_type = _compile_column_type(user_columns['id'])
    assignment_teacher_id_type = _compile_column_type(columns['teacher_id'])

    has_teacher_index = any(index.get('column_names') == ['teacher_id'] for index in indexes)
    teacher_fk_name = _find_foreign_key_name(
        foreign_keys,
        referred_table='users',
        constrained_columns=['teacher_id'],
    )
    has_teacher_fk = bool(teacher_fk_name)

    with engine.begin() as conn:
        if has_teacher_fk and assignment_teacher_id_type != target_teacher_id_type:
            _drop_foreign_key(conn, table_name='assignments', constraint_name=teacher_fk_name)
            has_teacher_fk = False

        if assignment_teacher_id_type != target_teacher_id_type or columns['teacher_id'].get('nullable', True):
            _alter_column_type_and_nullability(
                conn,
                table_name='assignments',
                column_name='teacher_id',
                column_type=target_teacher_id_type,
                nullable=False,
            )

        if not has_teacher_index:
            _create_index(
                conn,
                table_name='assignments',
                index_name='idx_assignments_teacher_id',
                column_names=['teacher_id'],
            )
        if not has_teacher_fk:
            _add_foreign_key(
                conn,
                table_name='assignments',
                constraint_name='fk_assignments_teacher_id',
                column_name='teacher_id',
                referred_table='users',
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

    assignment_table_exists = 'assignments' in table_names
    target_assignment_id_type = None
    if assignment_table_exists:
        assignment_columns = _get_columns_by_name(inspector, 'assignments')
        target_assignment_id_type = _compile_column_type(assignment_columns['id'])

    has_user_index = any(index.get('column_names') == ['user_id'] for index in indexes)
    has_updated_at_index = any(index.get('column_names') == ['updated_at'] for index in indexes)
    has_assignment_index = any(index.get('column_names') == ['assignment_id'] for index in indexes)
    user_fk_name = _find_foreign_key_name(
        foreign_keys,
        referred_table='users',
        constrained_columns=['user_id'],
    )
    assignment_fk_name = _find_foreign_key_name(
        foreign_keys,
        referred_table='assignments',
        constrained_columns=['assignment_id'],
    )
    has_user_fk = bool(user_fk_name)
    has_assignment_fk = bool(assignment_fk_name)

    with engine.begin() as conn:
        if has_user_fk and conversation_user_id_type != target_user_id_type:
            _drop_foreign_key(conn, table_name='chat_conversations', constraint_name=user_fk_name)
            has_user_fk = False

        if conversation_user_id_type != target_user_id_type or columns['user_id'].get('nullable', True):
            _alter_column_type_and_nullability(
                conn,
                table_name='chat_conversations',
                column_name='user_id',
                column_type=target_user_id_type,
                nullable=False,
            )

        if assignment_table_exists and target_assignment_id_type is not None:
            if 'assignment_id' not in columns:
                _add_column(
                    conn,
                    table_name='chat_conversations',
                    column_name='assignment_id',
                    column_type=target_assignment_id_type,
                    nullable=True,
                )
                columns['assignment_id'] = {'type': target_assignment_id_type, 'nullable': True}

            conversation_assignment_id_type = (
                columns['assignment_id']['type']
                if isinstance(columns['assignment_id']['type'], str)
                else _compile_column_type(columns['assignment_id'])
            )

            if has_assignment_fk and conversation_assignment_id_type != target_assignment_id_type:
                _drop_foreign_key(conn, table_name='chat_conversations', constraint_name=assignment_fk_name)
                has_assignment_fk = False

            if (
                conversation_assignment_id_type != target_assignment_id_type
                or not columns['assignment_id'].get('nullable', True)
            ):
                _alter_column_type_and_nullability(
                    conn,
                    table_name='chat_conversations',
                    column_name='assignment_id',
                    column_type=target_assignment_id_type,
                    nullable=True,
                )

            if not has_assignment_index:
                _create_index(
                    conn,
                    table_name='chat_conversations',
                    index_name='idx_chat_conversations_assignment_id',
                    column_names=['assignment_id'],
                )
            if not has_assignment_fk:
                _add_foreign_key(
                    conn,
                    table_name='chat_conversations',
                    constraint_name='fk_chat_conversations_assignment_id',
                    column_name='assignment_id',
                    referred_table='assignments',
                )

        if not has_user_index:
            _create_index(
                conn,
                table_name='chat_conversations',
                index_name='idx_chat_conversations_user_id',
                column_names=['user_id'],
            )
        if not has_updated_at_index:
            _create_index(
                conn,
                table_name='chat_conversations',
                index_name='idx_chat_conversations_updated_at',
                column_names=['updated_at'],
            )
        if not has_user_fk:
            _add_foreign_key(
                conn,
                table_name='chat_conversations',
                constraint_name='fk_chat_conversations_user_id',
                column_name='user_id',
                referred_table='users',
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
            _add_column(
                conn,
                table_name='chat_records',
                column_name='conversation_id',
                column_type=target_conversation_id_type,
                nullable=True,
            )
            columns['conversation_id'] = {'type': target_conversation_id_type, 'nullable': True}

        record_conversation_id_type = (
            columns['conversation_id']['type']
            if isinstance(columns['conversation_id']['type'], str)
            else _compile_column_type(columns['conversation_id'])
        )

        if has_user_fk and record_user_id_type != target_user_id_type:
            _drop_foreign_key(conn, table_name='chat_records', constraint_name=user_fk_name)
            has_user_fk = False
        if has_conversation_fk and record_conversation_id_type != target_conversation_id_type:
            _drop_foreign_key(conn, table_name='chat_records', constraint_name=conversation_fk_name)
            has_conversation_fk = False

        if record_user_id_type != target_user_id_type or columns['user_id'].get('nullable', True):
            _alter_column_type_and_nullability(
                conn,
                table_name='chat_records',
                column_name='user_id',
                column_type=target_user_id_type,
                nullable=False,
            )
        if record_conversation_id_type != target_conversation_id_type or not columns['conversation_id'].get(
            'nullable',
            True,
        ):
            _alter_column_type_and_nullability(
                conn,
                table_name='chat_records',
                column_name='conversation_id',
                column_type=target_conversation_id_type,
                nullable=True,
            )

        if not has_conversation_index:
            _create_index(
                conn,
                table_name='chat_records',
                index_name='idx_chat_conversation_id',
                column_names=['conversation_id'],
            )
        if not has_user_fk:
            _add_foreign_key(
                conn,
                table_name='chat_records',
                constraint_name='fk_chat_records_user_id',
                column_name='user_id',
                referred_table='users',
            )
        if not has_conversation_fk:
            _add_foreign_key(
                conn,
                table_name='chat_records',
                constraint_name='fk_chat_records_conversation_id',
                column_name='conversation_id',
                referred_table='chat_conversations',
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
                title=(record.prompt or 'History Conversation').strip()[:40] or 'History Conversation',
                created_at=record.generated_at,
                updated_at=record.generated_at,
            )
            db.add(conversation)
            db.flush()
            record.conversation_id = conversation.id

        db.commit()
    finally:
        db.close()


def ensure_answer_submission_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if 'answer_submissions' not in table_names:
        return
    if 'chat_conversations' not in table_names or 'users' not in table_names:
        return

    columns = _get_columns_by_name(inspector, 'answer_submissions')
    user_columns = _get_columns_by_name(inspector, 'users')
    conversation_columns = _get_columns_by_name(inspector, 'chat_conversations')
    indexes = inspector.get_indexes('answer_submissions')
    foreign_keys = inspector.get_foreign_keys('answer_submissions')
    unique_constraints = inspector.get_unique_constraints('answer_submissions')

    target_user_id_type = _compile_column_type(user_columns['id'])
    target_conversation_id_type = _compile_column_type(conversation_columns['id'])
    submission_user_id_type = _compile_column_type(columns['user_id'])

    has_user_index = any(index.get('column_names') == ['user_id'] for index in indexes)
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
    has_conversation_unique = bool(
        _find_unique_constraint_name(unique_constraints, ['conversation_id'])
        or any(index.get('unique') and index.get('column_names') == ['conversation_id'] for index in indexes)
    )

    with engine.begin() as conn:
        if 'conversation_id' not in columns:
            _add_column(
                conn,
                table_name='answer_submissions',
                column_name='conversation_id',
                column_type=target_conversation_id_type,
                nullable=True,
            )
            columns['conversation_id'] = {'type': target_conversation_id_type, 'nullable': True}

        if 'chat_record_id' in columns:
            conn.execute(
                text(
                    'UPDATE answer_submissions AS submissions '
                    'SET conversation_id = records.conversation_id '
                    'FROM chat_records AS records '
                    'WHERE submissions.chat_record_id = records.id '
                    'AND submissions.conversation_id IS NULL'
                )
            )

            chat_record_id_type = _compile_column_type(columns['chat_record_id'])
            if not columns['chat_record_id'].get('nullable', True):
                _alter_column_type_and_nullability(
                    conn,
                    table_name='answer_submissions',
                    column_name='chat_record_id',
                    column_type=chat_record_id_type,
                    nullable=True,
                )

        if engine.dialect.name == 'postgresql':
            conn.execute(
                text(
                    'DELETE FROM answer_submissions AS older '
                    'USING answer_submissions AS newer '
                    'WHERE older.id < newer.id '
                    'AND older.conversation_id IS NOT NULL '
                    'AND older.conversation_id = newer.conversation_id'
                )
            )

        submission_conversation_id_type = (
            columns['conversation_id']['type']
            if isinstance(columns['conversation_id']['type'], str)
            else _compile_column_type(columns['conversation_id'])
        )

        if submission_user_id_type != target_user_id_type or columns['user_id'].get('nullable', True):
            _alter_column_type_and_nullability(
                conn,
                table_name='answer_submissions',
                column_name='user_id',
                column_type=target_user_id_type,
                nullable=False,
            )

        null_conversation_count = conn.execute(
            text('SELECT COUNT(*) FROM answer_submissions WHERE conversation_id IS NULL')
        ).scalar_one()
        should_require_conversation_id = null_conversation_count == 0
        if submission_conversation_id_type != target_conversation_id_type or (
            should_require_conversation_id and columns['conversation_id'].get('nullable', True)
        ):
            _alter_column_type_and_nullability(
                conn,
                table_name='answer_submissions',
                column_name='conversation_id',
                column_type=target_conversation_id_type,
                nullable=not should_require_conversation_id,
            )

        if not has_user_index:
            _create_index(
                conn,
                table_name='answer_submissions',
                index_name='idx_answer_submissions_user_id',
                column_names=['user_id'],
            )
        if not has_conversation_index:
            _create_index(
                conn,
                table_name='answer_submissions',
                index_name='idx_answer_submissions_conversation_id',
                column_names=['conversation_id'],
            )
        if not has_user_fk:
            _add_foreign_key(
                conn,
                table_name='answer_submissions',
                constraint_name='fk_answer_submissions_user_id',
                column_name='user_id',
                referred_table='users',
            )
        if not has_conversation_fk:
            _add_foreign_key(
                conn,
                table_name='answer_submissions',
                constraint_name='fk_answer_submissions_conversation_id',
                column_name='conversation_id',
                referred_table='chat_conversations',
            )
        if not has_conversation_unique:
            _add_unique_constraint(
                conn,
                table_name='answer_submissions',
                constraint_name='uq_answer_submissions_conversation_id',
                column_names=['conversation_id'],
            )


def seed_default_users() -> None:
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
    create_tables()
    ensure_assignment_schema()
    ensure_conversation_schema()
    ensure_chat_schema()
    migrate_legacy_chat_records()
    ensure_answer_submission_schema()

    if seed_demo_users:
        seed_default_users()


def ping_database() -> None:
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
