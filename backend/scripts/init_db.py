"""项目数据库初始化脚本。

用途：
1) 不依赖本机 mysql 客户端，直接用 Python 连接远程/本地 MySQL。
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

import pymysql

from app.bootstrap import init_app_database
from app.config import get_settings


def ensure_database_exists() -> None:
    """先连接 MySQL 实例本身，再创建目标数据库。"""
    settings = get_settings()

    # 这里不指定 db，避免“数据库不存在”时无法连接。
    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset='utf8mb4',
        autocommit=True,
    )

    try:
        with conn.cursor() as cur:
            # 使用 IF NOT EXISTS 保证脚本可重复执行。
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_db}` "
                "DEFAULT CHARACTER SET utf8mb4 "
                "DEFAULT COLLATE utf8mb4_unicode_ci"
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
