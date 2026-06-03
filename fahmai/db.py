"""Postgres connection helper.

Builds a SQLAlchemy engine from .env. Connection precedence:
1. DATABASE_URL -- explicit full string, wins if set.
2. FAHMAI_DB_* -- ModelHarbor PostgreSQL defaults with password from FAHMAI_DB_PASSWORD.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[1]   # repo root (fahmai/db.py -> fahmai_hack/)
load_dotenv(ROOT / ".env")

DEFAULT_DB_HOST = "swarm-manager.modelharbor.com"
DEFAULT_DB_PORT = "54336"
DEFAULT_DB_NAME = "fahmai"
DEFAULT_DB_USER = "fahmai_app"


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"missing required environment variable {name}")
    return value


def database_url() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    pwd = quote(_required_env("FAHMAI_DB_PASSWORD"), safe="")
    host = os.getenv("FAHMAI_DB_HOST", DEFAULT_DB_HOST)
    port = os.getenv("FAHMAI_DB_PORT", DEFAULT_DB_PORT)
    user = os.getenv("FAHMAI_DB_USER", DEFAULT_DB_USER)
    name = os.getenv("FAHMAI_DB_NAME", DEFAULT_DB_NAME)
    return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{name}"


def get_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True)


if __name__ == "__main__":
    from sqlalchemy import text

    eng = get_engine()
    with eng.connect() as conn:
        v = conn.execute(text("select version()")).scalar()
        print("connected OK")
        print(v)
