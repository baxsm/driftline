"""API test fixtures.

These run against the real Postgres from docker-compose, not sqlite. The schema uses JSONB
and UUID columns, so a sqlite substitute would test a different database than the one that
ships. Each test gets its own transaction, rolled back afterwards, so the suite can run
repeatedly without leaving rows behind.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_TEST_DATABASE = "postgresql+psycopg://driftline:driftline@localhost:5435/driftline"
os.environ.setdefault("DATABASE_URL", DEFAULT_TEST_DATABASE)
os.environ.setdefault("SESSION_SECRET", "test-secret-value-that-is-long-enough-32")
os.environ.setdefault("ENVIRONMENT", "test")

# these read the environment at import time, so they load after the defaults above
from db.models import Base
from db.session import get_session
from main import app


def _database_reachable(url: str) -> bool:
    try:
        engine = create_engine(url)
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        engine.dispose()
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def engine():
    url = os.environ["DATABASE_URL"]
    if not _database_reachable(url):
        pytest.skip(f"postgres is not reachable at {url}")
    created = create_engine(url)
    Base.metadata.create_all(created)
    yield created
    created.dispose()


@pytest.fixture
def session(engine) -> Session:
    """A session whose writes are discarded after the test.

    Services call `commit()`, which would end a plain outer transaction and leave rows
    behind. Binding the session with `join_transaction_mode="create_savepoint"` turns each
    of those commits into a savepoint release inside the outer transaction, so the final
    rollback still removes everything.
    """
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    db = factory()
    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(session) -> TestClient:
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def account() -> dict[str, str]:
    """A unique email per test, so a leftover row cannot collide with a fresh run."""
    return {"email": f"user-{uuid.uuid4().hex[:12]}@driftline.dev", "password": "testpassword123"}


@pytest.fixture
def signed_in(client, account) -> dict[str, str]:
    client.post("/api/auth/register", json=account)
    return account
