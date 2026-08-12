"""Queueing, executing, and reading back estimator runs."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, insert, nullslast, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql.elements import UnaryExpression

import logger
from db.models import Dataset, Pose, Run, RunMetrics
from estimator.config import EstimatorConfig

from ..errors import ApiError

POSE_CHUNK = 2000
TERMINAL_STATUSES = frozenset({"done", "failed"})


def _parse_id(run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(run_id)
    except ValueError:
        raise ApiError("run_not_found", "That run does not exist.") from None


def get_run(session: Session, user_id: uuid.UUID, run_id: str) -> Run:
    run = session.scalar(
        select(Run).where(Run.id == _parse_id(run_id), Run.user_id == user_id)
    )
    if not run:
        raise ApiError("run_not_found", "That run does not exist.")
    return run


def list_runs(
    session: Session,
    user_id: uuid.UUID,
    dataset_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "created",
    status: str | None = None,
) -> tuple[list[Run], int]:
    """Runs for one user, newest first by default or best first when sorted by ATE.

    Sorting happens in the database rather than in the client. The list is paginated, so
    sorting the page that arrived would order fifty rows out of however many exist and present
    the best of those fifty as the best overall.

    An unscored run has no ATE to sort by. Those rows sort last under `nullslast` rather than
    being filtered out, because "this run was never scored" is a state worth seeing in the list
    and dropping it would make runs disappear when the sort changed.
    """
    filters = [Run.user_id == user_id]
    if dataset_id:
        filters.append(Run.dataset_id == _parse_id(dataset_id))
    if status:
        filters.append(Run.status == status)

    total = session.scalar(select(func.count()).select_from(Run).where(*filters)) or 0

    orders: dict[str, UnaryExpression[Any]] = {
        "ate": nullslast(RunMetrics.ate_rmse.asc()),
        "created": Run.created_at.desc(),
        "dataset": Dataset.name.asc(),
    }
    order = orders.get(sort, orders["created"])

    statement = (
        select(Run)
        .join(Dataset, Dataset.id == Run.dataset_id)
        .outerjoin(RunMetrics, RunMetrics.run_id == Run.id)
        # the list renders each run's dataset name and ATE, so both are loaded with the page
        # rather than lazily per row, which would be two more queries for every run listed
        .options(joinedload(Run.dataset), joinedload(Run.metrics))
        .where(*filters)
        # a stable tiebreak, so two runs with equal ATE or the same dataset name do not swap
        # places between requests and make the list look like it is reordering itself
        .order_by(order, Run.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement)), int(total)


def queue_run(
    session: Session,
    user_id: uuid.UUID,
    dataset_id: str,
    config: EstimatorConfig,
    label: str | None = None,
) -> Run:
    dataset = session.scalar(
        select(Dataset).where(Dataset.id == _parse_id(dataset_id), Dataset.user_id == user_id)
    )
    if not dataset:
        raise ApiError("dataset_not_found", "That sequence does not exist.")

    total = dataset.frame_count
    if config.max_frames is not None:
        total = min(total, config.max_frames)

    run = Run(
        dataset_id=dataset.id,
        user_id=user_id,
        label=label.strip() if label and label.strip() else None,
        config=config.as_dict(),
        config_hash=config.hash(),
        status="queued",
        total_frames=total,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    logger.info(
        "runs.queue",
        {"run": str(run.id), "dataset": str(dataset.id), "frames": total},
    )
    return run


def delete_run(session: Session, user_id: uuid.UUID, run_id: str) -> Run:
    run = get_run(session, user_id, run_id)
    session.delete(run)
    session.commit()
    logger.info("runs.delete", {"run": run_id})
    return run


def claim_next_queued(session: Session) -> Run | None:
    """Take the oldest queued run and mark it running.

    `with_for_update(skip_locked=True)` means two workers never take the same row, and the
    row is committed as running before any work starts so a crash cannot leave it looking
    queued forever.
    """
    run = session.scalar(
        select(Run)
        .where(Run.status == "queued")
        .order_by(Run.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if not run:
        return None
    run.status = "running"
    run.started_at = datetime.now(UTC)
    session.commit()
    session.refresh(run)
    return run


def mark_progress(session: Session, run_id: uuid.UUID, processed: int) -> None:
    run = session.get(Run, run_id)
    if run:
        run.processed_frames = processed
        session.commit()


def finish_run(
    session: Session,
    run_id: uuid.UUID,
    status: str,
    failure_reason: str | None = None,
    failure_frame: int | None = None,
) -> None:
    run = session.get(Run, run_id)
    if not run:
        return
    run.status = status
    run.failure_reason = failure_reason
    run.failure_frame = failure_frame
    run.finished_at = datetime.now(UTC)
    session.commit()
    logger.info("runs.finish", {"run": str(run_id), "status": status})


def save_poses(session: Session, run_id: uuid.UUID, rows: list[dict[str, object]]) -> None:
    """Bulk insert estimated poses.

    A run is thousands of poses, so these go in as plain mappings through a core insert
    rather than as one ORM object per row.
    """
    for start in range(0, len(rows), POSE_CHUNK):
        session.execute(insert(Pose), rows[start : start + POSE_CHUNK])
    session.commit()


def clear_poses(session: Session, run_id: uuid.UUID) -> None:
    session.execute(delete(Pose).where(Pose.run_id == run_id))
    session.commit()


def trajectory(session: Session, run_id: uuid.UUID, stride: int = 1) -> tuple[list[Pose], int]:
    """Estimated poses, decimated for display, with the total before decimation."""
    statement = (
        select(Pose).where(Pose.run_id == run_id).order_by(Pose.timestamp_ns)
    )
    poses = list(session.scalars(statement))
    return (poses[::stride] if stride > 1 else poses), len(poses)
