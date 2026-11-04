"""Tests the DATABASE_URL resolution logic in isolation (importing ledger.api.db
itself has import-time side effects -- engine creation -- so this tests the
pure resolution function via a fresh subprocess-free reimplementation check
by importing the module function directly and monkeypatching os.environ)."""
import importlib

import pytest


@pytest.fixture()
def clean_env(monkeypatch):
    for key in ("DATABASE_URL", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST", "POSTGRES_PORT"):
        monkeypatch.delenv(key, raising=False)


def _resolve():
    """Re-imports the module's resolver fresh each time so env changes take effect
    (the module only computes DATABASE_URL once at import time otherwise)."""
    from ledger.api import db

    importlib.reload(db)
    return db.DATABASE_URL


def test_explicit_database_url_wins(clean_env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://explicit:explicit@explicit-host:5432/explicit-db")
    monkeypatch.setenv("POSTGRES_USER", "should-be-ignored")
    monkeypatch.setenv("POSTGRES_PASSWORD", "should-be-ignored")
    monkeypatch.setenv("POSTGRES_DB", "should-be-ignored")
    assert _resolve() == "postgresql+psycopg2://explicit:explicit@explicit-host:5432/explicit-db"


def test_component_env_vars_build_url(clean_env, monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "ledger")
    monkeypatch.setenv("POSTGRES_PASSWORD", "s3cret")
    monkeypatch.setenv("POSTGRES_DB", "ledger")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    assert _resolve() == "postgresql+psycopg2://ledger:s3cret@postgres:5432/ledger"


def test_component_env_vars_default_host_and_port(clean_env, monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    assert _resolve() == "postgresql+psycopg2://u:p@localhost:5432/d"


def test_falls_back_to_default_when_nothing_set(clean_env):
    assert _resolve() == "postgresql+psycopg2://ledger:ledger@localhost:5432/ledger"


def test_partial_component_vars_fall_back_to_default(clean_env, monkeypatch):
    """Only POSTGRES_USER set, no password/db -- must not build a broken URL."""
    monkeypatch.setenv("POSTGRES_USER", "u")
    assert _resolve() == "postgresql+psycopg2://ledger:ledger@localhost:5432/ledger"
