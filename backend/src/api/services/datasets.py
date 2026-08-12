"""Dataset registration and lookup.

Registering does not copy the sequence. It reads what is on disk, records the counts and
calibration the reader found, and stores the ground truth poses so the viewer can draw them
without touching the filesystem again.
"""

import uuid
from pathlib import Path

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

import logger
from datasets.errors import SequenceUnreadable
from datasets.reader import read_ground_truth, read_sequence
from db.models import Dataset, GroundTruthPose

from ..errors import ApiError

GROUND_TRUTH_CHUNK = 5000


def list_datasets(session: Session, user_id: uuid.UUID) -> list[Dataset]:
    statement = (
        select(Dataset).where(Dataset.user_id == user_id).order_by(Dataset.created_at.desc())
    )
    return list(session.scalars(statement))


def get_dataset(session: Session, user_id: uuid.UUID, dataset_id: str) -> Dataset:
    try:
        parsed = uuid.UUID(dataset_id)
    except ValueError:
        raise ApiError("dataset_not_found", "That sequence does not exist.") from None

    dataset = session.scalar(
        select(Dataset).where(Dataset.id == parsed, Dataset.user_id == user_id)
    )
    if not dataset:
        raise ApiError("dataset_not_found", "That sequence does not exist.")
    return dataset


def register_dataset(
    session: Session, user_id: uuid.UUID, path: str, name: str | None = None
) -> Dataset:
    try:
        info = read_sequence(path)
    except SequenceUnreadable as exc:
        logger.warn("datasets.register", {"path": path, "missing": exc.missing})
        raise ApiError("sequence_unreadable", exc.message) from exc

    existing = session.scalar(
        select(Dataset).where(Dataset.user_id == user_id, Dataset.path == info.path)
    )
    if existing:
        raise ApiError("path_already_registered", "That path is already registered.", "path")

    dataset = Dataset(
        user_id=user_id,
        name=name.strip() if name and name.strip() else info.name,
        source=info.source,
        path=info.path,
        has_ground_truth=info.has_ground_truth,
        frame_count=info.frame_count,
        imu_sample_count=info.imu_sample_count,
        duration_seconds=info.duration_seconds,
        camera_model=info.camera_model,
        calibration=info.calibration,
    )
    session.add(dataset)
    session.flush()

    if info.has_ground_truth:
        poses = read_ground_truth(Path(info.path))
        # a room sequence carries over 16000 truth poses, so these go in as plain mappings
        # through a core insert rather than as one ORM object per row
        rows = [
            {
                "dataset_id": dataset.id,
                "timestamp_ns": pose.timestamp_ns,
                "tx": pose.tx,
                "ty": pose.ty,
                "tz": pose.tz,
                "qw": pose.qw,
                "qx": pose.qx,
                "qy": pose.qy,
                "qz": pose.qz,
            }
            for pose in poses
        ]
        for start in range(0, len(rows), GROUND_TRUTH_CHUNK):
            session.execute(insert(GroundTruthPose), rows[start : start + GROUND_TRUTH_CHUNK])

    session.commit()
    session.refresh(dataset)
    logger.info(
        "datasets.register",
        {
            "dataset": str(dataset.id),
            "source": dataset.source,
            "frames": dataset.frame_count,
            "ground_truth": dataset.has_ground_truth,
        },
    )
    return dataset


def delete_dataset(session: Session, user_id: uuid.UUID, dataset_id: str) -> None:
    """Unregister a sequence. The files on disk are left alone."""
    dataset = get_dataset(session, user_id, dataset_id)
    session.delete(dataset)
    session.commit()
    logger.info("datasets.delete", {"dataset": dataset_id})


def ground_truth_poses(
    session: Session,
    dataset_id: uuid.UUID,
    stride: int = 1,
    from_ns: int | None = None,
    to_ns: int | None = None,
) -> tuple[list[GroundTruthPose], int]:
    """Return the decimated poses and the total before decimation.

    The total is what the UI needs to say "N of M drawn" honestly. Without it the caller has
    to compare against the frame count, which is a different number entirely.

    The optional window exists because truth covers the whole recording while a run may cover
    a slice of it. Overlaying all 141 seconds of a room sequence on a run that estimated 12 of
    them draws a dense tangle the short estimate disappears into, and implies the estimate
    spans a path it never saw. The window is applied before decimation, so the total still
    counts the poses in the range asked for.
    """
    filters = [GroundTruthPose.dataset_id == dataset_id]
    if from_ns is not None:
        filters.append(GroundTruthPose.timestamp_ns >= from_ns)
    if to_ns is not None:
        filters.append(GroundTruthPose.timestamp_ns <= to_ns)

    statement = (
        select(GroundTruthPose).where(*filters).order_by(GroundTruthPose.timestamp_ns)
    )
    poses = list(session.scalars(statement))
    return (poses[::stride] if stride > 1 else poses), len(poses)


def clear_ground_truth(session: Session, dataset_id: uuid.UUID) -> None:
    session.execute(delete(GroundTruthPose).where(GroundTruthPose.dataset_id == dataset_id))
