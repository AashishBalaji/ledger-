"""Database engine/session setup.

Two ways to configure the connection, checked in order:
1. DATABASE_URL -- a single connection string. This is what docker-compose
   and CI use, since they don't need Kubernetes-style secret separation.
2. Component env vars (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
   POSTGRES_HOST, POSTGRES_PORT) -- built into a connection string here,
   never written to disk as a combined string anywhere upstream. This is
   what the Kubernetes deployment uses: credentials come from a Secret
   (envFrom secretRef), non-secret connection details (host/port) come
   from a ConfigMap, and the two are only ever joined in memory, in this
   process -- so no component sees the other's value at rest.

Falls back to a default matching docker-compose if neither is set.
"""
from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _resolve_database_url() -> str:
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit

    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    db_name = os.environ.get("POSTGRES_DB")
    if user and password and db_name:
        host = os.environ.get("POSTGRES_HOST", "localhost")
        port = os.environ.get("POSTGRES_PORT", "5432")
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"

    return "postgresql+psycopg2://ledger:ledger@localhost:5432/ledger"


DATABASE_URL = _resolve_database_url()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
