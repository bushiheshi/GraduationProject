"""项目数据库初始化脚本。

用途：
1) 不依赖本机 psql 客户端，直接用 Python 连接远程/本地 PostgreSQL。
2) 自动创建数据库（如果不存在）。
3) 按当前 SQLAlchemy 模型创建缺失的表。
4) 可选写入演示账号。

运行方式（在 backend 目录下）：
    python scripts/init_db.py
    python scripts/init_db.py --skip-seed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许从 "backend/scripts" 直接运行时导入同级目录下的 app 包。
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import psycopg
from psycopg import sql

from app.bootstrap import init_app_database
from app.config import get_settings


def ensure_database_exists() -> None:
    """先连接 PostgreSQL 默认库，再创建目标数据库。"""
    settings = get_settings()

    # 先连接默认库，避免目标库不存在时无法建立连接。
    connect_kwargs = {
        'host': settings.postgres_host,
        'port': settings.postgres_port,
        'user': settings.postgres_user,
        'password': settings.postgres_password,
        'dbname': 'postgres',
        'autocommit': True,
    }
    if settings.postgres_sslmode:
        connect_kwargs['sslmode'] = settings.postgres_sslmode

    conn = psycopg.connect(
        **connect_kwargs,
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT 1 FROM pg_database WHERE datname = %s',
                (settings.postgres_db,),
            )
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL('CREATE DATABASE {}').format(sql.Identifier(settings.postgres_db))
                )
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Initialize project database')
    parser.add_argument(
        '--skip-seed',
        action='store_true',
        help='Only create database/tables, do not insert demo users',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        ensure_database_exists()
        init_app_database(seed_demo_users=not args.skip_seed)
        print('Database initialized successfully.')
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f'Database initialization failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
