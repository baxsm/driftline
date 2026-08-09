"""Row to response shaping.

Every field returned by the API is named here rather than dumping ORM objects, so a column
added later (a password hash, an internal path) cannot leak into a response by default.
"""

from typing import Any

from db.models import Dataset, GroundTruthPose, User


def user_response(user: User) -> dict[str, Any]:
    return {"id": str(user.id), "email": user.email}


def dataset_response(dataset: Dataset) -> dict[str, Any]:
    return {
        "id": str(dataset.id),
        "name": dataset.name,
        "source": dataset.source,
        "path": dataset.path,
        "has_ground_truth": dataset.has_ground_truth,
        "frame_count": dataset.frame_count,
        "imu_sample_count": dataset.imu_sample_count,
        "duration_seconds": dataset.duration_seconds,
        "camera_model": dataset.camera_model,
        "calibration": dataset.calibration,
        "created_at": dataset.created_at.isoformat(),
    }


def dataset_summary(dataset: Dataset) -> dict[str, Any]:
    """List shape. Calibration is omitted because the list never renders it."""
    return {
        "id": str(dataset.id),
        "name": dataset.name,
        "source": dataset.source,
        "has_ground_truth": dataset.has_ground_truth,
        "frame_count": dataset.frame_count,
        "imu_sample_count": dataset.imu_sample_count,
        "duration_seconds": dataset.duration_seconds,
        "camera_model": dataset.camera_model,
        "created_at": dataset.created_at.isoformat(),
    }


def pose_response(pose: GroundTruthPose) -> dict[str, Any]:
    """Timestamps are sent as strings.

    JSON numbers are parsed as float64 in JavaScript, which cannot hold a 19 digit
    nanosecond value. Sending the integer as a string keeps it exact on the client.
    """
    return {
        "timestamp_ns": str(pose.timestamp_ns),
        "tx": pose.tx,
        "ty": pose.ty,
        "tz": pose.tz,
        "qw": pose.qw,
        "qx": pose.qx,
        "qy": pose.qy,
        "qz": pose.qz,
    }
