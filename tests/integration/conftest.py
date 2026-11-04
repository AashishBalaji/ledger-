"""Integration test fixtures: real Postgres, real HTTP layer (via TestClient),
no mocking of the database. Requires a reachable Postgres instance at
DATABASE_URL (see docker-compose.yml / CI service container)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from ledger.api.db import Base, SessionLocal, engine
from ledger.api.main import app


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate all tables between tests so each test starts from a known,
    empty state without needing per-test mocking."""
    yield
    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE'))
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client():
    return TestClient(app)
