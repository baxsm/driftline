"""Dataset registration and lookup.

Registering does not copy the sequence. It reads what is on disk, records the counts and
calibration the reader found, and stores the ground truth poses so the viewer can draw them
without touching the filesystem again.
"""

import uuid
from pathlib import Path

from sqlalchemy import delete, select
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
        for start in range(0, len(poses), GROUND_TRUTH_CHUNK):
            session.bulk_save_objects(
                [
                    GroundTruthPose(
                        dataset_id=dataset.id,
                        timestamp_ns=pose.timestamp_ns,
                        tx=pose.tx,
                        ty=pose.ty,
                        tz=pose.tz,
                        qw=pose.qw,
                        qx=pose.qx,
                        qy=pose.qy,
                        qz=pose.qz,
                    )
                    for pose in poses[start : start + GROUND_TRUTH_CHUNK]
                ]
            )

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
    session: Session, dataset_id: uuid.UUID, stride: int = 1
) -> list[GroundTruthPose]:
    statement = (
        select(GroundTruthPose)
        .where(GroundTruthPose.dataset_id == dataset_id)
        .order_by(GroundTruthPose.timestamp_ns)
    )
    poses = list(session.scalars(statement))
    return poses[::stride] if stride > 1 else poses


def clear_ground_truth(session: Session, dataset_id: uuid.UUID) -> None:
    session.execute(delete(GroundTruthPose).where(GroundTruthPose.dataset_id == dataset_id))
