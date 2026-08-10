"""Row to response shaping.

Every field returned by the API is named here rather than dumping ORM objects, so a column
added later (a password hash, an internal path) cannot leak into a response by default.
"""

from collections.abc import Sequence
from typing import Any

from db.models import Dataset, GroundTruthPose, Pose, PoseError, Run, RunMetrics, User


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


def pose_response(
    pose: GroundTruthPose | Pose, position: Sequence[float] | None = None
) -> dict[str, Any]:
    """Timestamps are sent as strings.

    JSON numbers are parsed as float64 in JavaScript, which cannot hold a 19 digit
    nanosecond value. Sending the integer as a string keeps it exact on the client.

    `position` replaces the stored translation, which is how an aligned trajectory is sent
    without keeping a second copy of every pose in the database.
    """
    tx, ty, tz = (pose.tx, pose.ty, pose.tz) if position is None else position
    body = {
        "timestamp_ns": str(pose.timestamp_ns),
        "tx": float(tx),
        "ty": float(ty),
        "tz": float(tz),
        "qw": pose.qw,
        "qx": pose.qx,
        "qy": pose.qy,
        "qz": pose.qz,
    }
    if isinstance(pose, Pose):
        body["frame_index"] = pose.frame_index
        body["tracked_features"] = pose.tracked_features
    return body


def run_response(run: Run) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "dataset_id": str(run.dataset_id),
        "label": run.label,
        "config": run.config,
        "config_hash": run.config_hash,
        "status": run.status,
        "failure_reason": run.failure_reason,
        "failure_frame": run.failure_frame,
        "processed_frames": run.processed_frames,
        "total_frames": run.total_frames,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat(),
    }


def metrics_response(metrics: RunMetrics) -> dict[str, Any]:
    """The scores, with everything needed to read them honestly.

    `alignment` and the matched counts travel with the numbers rather than being available
    separately. An ATE without its alignment mode is not comparable to anything, and one
    computed over a handful of matched poses is not a statement about the run, so the UI is
    never in a position to render a bare figure.
    """
    return {
        "ate_rmse": metrics.ate_rmse,
        "ate_mean": metrics.ate_mean,
        "ate_median": metrics.ate_median,
        "ate_max": metrics.ate_max,
        "ate_rot_rmse": metrics.ate_rot_rmse,
        "ate_rot_std": metrics.ate_rot_std,
        "rpe_trans_rmse": metrics.rpe_trans_rmse,
        "rpe_rot_rmse": metrics.rpe_rot_rmse,
        "rpe_delta_frames": metrics.rpe_delta_frames,
        "scale_error": metrics.scale_error,
        "alignment": metrics.alignment,
        "aligned_pose_count": metrics.aligned_pose_count,
        "candidate_pose_count": metrics.candidate_pose_count,
        "association_tolerance_ns": str(metrics.association_tolerance_ns),
        "computed_at": metrics.computed_at.isoformat(),
    }


def pose_error_response(error: PoseError) -> dict[str, Any]:
    return {
        "timestamp_ns": str(error.timestamp_ns),
        "trans_error": error.trans_error,
        "rot_error": error.rot_error,
    }


def run_summary(run: Run) -> dict[str, Any]:
    """List shape. The full config is omitted because the list only shows the hash."""
    return {
        "id": str(run.id),
        "dataset_id": str(run.dataset_id),
        "dataset_name": run.dataset.name if run.dataset else None,
        "label": run.label,
        "config_hash": run.config_hash,
        "status": run.status,
        "failure_reason": run.failure_reason,
        "processed_frames": run.processed_frames,
        "total_frames": run.total_frames,
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
