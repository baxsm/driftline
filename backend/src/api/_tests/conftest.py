"""API test fixtures.

These run against the real Postgres from docker-compose, not sqlite. The schema uses JSONB
and UUID columns, so a sqlite substitute would test a different database than the one that
ships. Each test gets its own transaction, rolled back afterwards, so the suite can run
repeatedly without leaving rows behind.
"""

import os
import uuid
from pathlib import Path

import cv2
import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from estimator._tests.synthetic import straight_line_sequence

DEFAULT_TEST_DATABASE = "postgresql+psycopg://driftline:driftline@localhost:5435/driftline"
os.environ.setdefault("DATABASE_URL", DEFAULT_TEST_DATABASE)
os.environ.setdefault("SESSION_SECRET", "test-secret-value-that-is-long-enough-32")
os.environ.setdefault("ENVIRONMENT", "test")
# the worker polls its own connection, which would not see the fixture's rolled back
# transaction. Tests that need a run executed call the worker directly instead.
os.environ["DRIFTLINE_DISABLE_WORKER"] = "1"

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


# matches the intrinsics the synthetic renderer projects with, so a recovered path can be
# compared against the path that generated it
CAMCHAIN = {
    "cam0": {
        "camera_model": "pinhole",
        "intrinsics": [400.0, 400.0, 320.0, 240.0],
        "distortion_model": "none",
        "distortion_coeffs": [0.0, 0.0, 0.0, 0.0],
        "resolution": [640, 480],
    }
}

EPOCH_NS = 1520530308199447626
FRAME_INTERVAL_NS = 50_000_000


def _write_sequence(root: Path, frames: int, with_ground_truth: bool) -> Path:
    """Write a synthetic sequence in the ASL layout the reader expects.

    When ground truth is asked for it is the camera path the images were rendered from, at
    six times the frame rate, which is the rate ratio TUM VI has. The truth is therefore the
    exact answer, so a scored run here measures the estimator rather than a guess about what
    the right answer was.
    """
    rendered = straight_line_sequence(frames=frames)
    data_dir = root / "mav0" / "cam0" / "data"
    data_dir.mkdir(parents=True)

    rows = ["#timestamp [ns],filename"]
    for index, image in enumerate(rendered.images):
        timestamp = EPOCH_NS + index * FRAME_INTERVAL_NS
        cv2.imwrite(str(data_dir / f"{timestamp}.png"), image)
        rows.append(f"{timestamp},{timestamp}.png")
    (root / "mav0" / "cam0" / "data.csv").write_text("\n".join(rows), encoding="utf-8")

    imu_dir = root / "mav0" / "imu0"
    imu_dir.mkdir(parents=True)
    (imu_dir / "data.csv").write_text(
        f"#timestamp,wx,wy,wz,ax,ay,az\n{EPOCH_NS},0,0,0,0,0,9.81\n",
        encoding="utf-8",
    )
    (root / "camchain.yaml").write_text(yaml.safe_dump(CAMCHAIN), encoding="utf-8")

    if with_ground_truth:
        truth_dir = root / "mav0" / "state_groundtruth_estimate0"
        truth_dir.mkdir(parents=True)
        truth_rows = ["#timestamp,tx,ty,tz,qw,qx,qy,qz"]
        step = FRAME_INTERVAL_NS // 6
        for index in range((frames - 1) * 6 + 1):
            timestamp = EPOCH_NS + index * step
            # the rendered path is a straight slide along +x at a fixed orientation
            x = (index / 6.0) * 0.25
            truth_rows.append(f"{timestamp},{x:.9f},0,0,1,0,0,0")
        (truth_dir / "data.csv").write_text("\n".join(truth_rows), encoding="utf-8")

    return root


@pytest.fixture
def sequence_on_disk(tmp_path: Path) -> Path:
    return _write_sequence(tmp_path / "plain", frames=10, with_ground_truth=False)


@pytest.fixture
def scorable_sequence(tmp_path: Path) -> Path:
    """A sequence long enough to score, with ground truth covering the whole path."""
    return _write_sequence(tmp_path / "scorable", frames=24, with_ground_truth=True)


@pytest.fixture
def registered_dataset(client, signed_in, sequence_on_disk) -> str:
    response = client.post("/api/datasets/register", json={"path": str(sequence_on_disk)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def scorable_dataset(client, signed_in, scorable_sequence) -> str:
    response = client.post("/api/datasets/register", json={"path": str(scorable_sequence)})
    assert response.status_code == 201, response.text
    assert response.json()["has_ground_truth"] is True
    return response.json()["id"]
