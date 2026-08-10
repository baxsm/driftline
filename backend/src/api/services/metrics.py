"""Scoring a finished run and reading the scores back.

Scoring happens once, in the worker, right after a run finishes. It is not computed per
request: the numbers are a property of the run, and recomputing them on every page load
would burn a few hundred milliseconds to produce the same answer, with the risk of the panel
and the plot disagreeing because they scored at different moments.
"""

import uuid
from typing import Any

import numpy as np
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

import logger
from db.models import Dataset, GroundTruthPose, Pose, PoseError, Run, RunMetrics
from estimator.artifacts import TUM_HEADER, tum_line
from estimator.camera import CalibrationMissing, camera_from_calibration
from metrics.alignment import Alignment, AlignmentMode, align_for_mode
from metrics.association import DEFAULT_TOLERANCE_NS, associate
from metrics.errors import DEFAULT_RPE_DELTA_FRAMES
from metrics.scoring import MIN_MATCHED_POSES, NotScorable, Score, Trajectory, score

POSE_ERROR_CHUNK = 2000

# a monocular estimate has no absolute scale, so it must be Sim(3) aligned. Anything that
# observes scale must be SE(3) aligned, because Sim(3) would rescale the estimate to fit and
# hide the scale drift that the mode exists to expose.
ALIGNMENT_FOR_MODE: dict[str, AlignmentMode] = {
    "mono": "sim3",
    "stereo": "se3",
    "stereo_inertial": "se3",
}


def alignment_for(config: dict[str, object]) -> AlignmentMode:
    mode = str(config.get("mode", "mono"))
    return ALIGNMENT_FOR_MODE.get(mode, "sim3")


def _trajectory_from(rows: list[Pose] | list[GroundTruthPose]) -> Trajectory:
    return Trajectory(
        timestamps_ns=np.array([row.timestamp_ns for row in rows], dtype=np.int64),
        positions=np.array([[row.tx, row.ty, row.tz] for row in rows], dtype=np.float64),
        quaternions=np.array(
            [[row.qw, row.qx, row.qy, row.qz] for row in rows], dtype=np.float64
        ),
    )


def estimate_trajectory(
    session: Session, run_id: uuid.UUID, calibration: dict[str, Any] | None = None
) -> Trajectory:
    """The estimated trajectory, in the body frame when the sequence ships an extrinsic.

    Poses are stored in the camera frame, which is what the estimator produces. Ground truth
    is recorded in the IMU body frame, so the two are only comparable after `T_cam_imu` is
    applied. On TUM VI the two frames are about 179 degrees apart.
    """
    rows = list(
        session.scalars(select(Pose).where(Pose.run_id == run_id).order_by(Pose.timestamp_ns))
    )
    trajectory = _trajectory_from(rows)
    extrinsic = _body_to_camera(calibration)
    return trajectory.to_body_frame(extrinsic) if extrinsic is not None else trajectory


def body_frame_positions(
    positions: Any, quaternions: Any, calibration: dict[str, Any] | None
) -> Any:
    """Camera frame positions re-expressed in the body frame, for drawing over truth."""
    extrinsic = _body_to_camera(calibration)
    if extrinsic is None or len(positions) == 0:
        return positions
    trajectory = Trajectory(
        timestamps_ns=np.zeros(len(positions), dtype=np.int64),
        positions=np.asarray(positions, dtype=np.float64),
        quaternions=np.asarray(quaternions, dtype=np.float64),
    )
    return trajectory.to_body_frame(extrinsic).positions


def _body_to_camera(calibration: dict[str, Any] | None) -> Any:
    if not calibration:
        return None
    try:
        return camera_from_calibration(calibration).body_to_camera
    except CalibrationMissing:
        return None


def truth_trajectory(session: Session, dataset_id: uuid.UUID) -> Trajectory:
    rows = list(
        session.scalars(
            select(GroundTruthPose)
            .where(GroundTruthPose.dataset_id == dataset_id)
            .order_by(GroundTruthPose.timestamp_ns)
        )
    )
    return _trajectory_from(rows)


def tum_document(trajectory: Trajectory) -> str:
    """Serialise a trajectory to TUM, the format `evo` reads."""
    lines = [TUM_HEADER]
    for timestamp, position, quaternion in zip(
        trajectory.timestamps_ns, trajectory.positions, trajectory.quaternions, strict=True
    ):
        lines.append(
            tum_line(
                int(timestamp),
                (float(position[0]), float(position[1]), float(position[2])),
                (
                    float(quaternion[0]),
                    float(quaternion[1]),
                    float(quaternion[2]),
                    float(quaternion[3]),
                ),
            )
        )
    return "".join(lines)


def clear_metrics(session: Session, run_id: uuid.UUID) -> None:
    session.execute(delete(PoseError).where(PoseError.run_id == run_id))
    session.execute(delete(RunMetrics).where(RunMetrics.run_id == run_id))


def save_score(session: Session, run_id: uuid.UUID, result: Score, tolerance_ns: int) -> None:
    """Replace any existing score for this run with a fresh one."""
    clear_metrics(session, run_id)

    session.add(
        RunMetrics(
            run_id=run_id,
            ate_rmse=result.ate_translation.rmse,
            ate_mean=result.ate_translation.mean,
            ate_median=result.ate_translation.median,
            ate_max=result.ate_translation.max,
            ate_rot_rmse=result.ate_rotation_deg.rmse,
            ate_rot_std=result.ate_rotation_deg.std,
            rpe_trans_rmse=result.rpe_translation.rmse if result.rpe_translation else None,
            rpe_rot_rmse=result.rpe_rotation_deg.rmse if result.rpe_rotation_deg else None,
            rpe_delta_frames=result.rpe_delta_frames,
            scale_error=result.scale_error,
            alignment=result.alignment.mode,
            aligned_pose_count=result.association.matched_count,
            candidate_pose_count=result.association.candidate_count,
            association_tolerance_ns=tolerance_ns,
        )
    )

    rows = [
        {
            "run_id": run_id,
            "timestamp_ns": error.timestamp_ns,
            "trans_error": error.translation,
            "rot_error": error.rotation_deg,
        }
        for error in result.pose_errors
    ]
    for start in range(0, len(rows), POSE_ERROR_CHUNK):
        session.execute(insert(PoseError), rows[start : start + POSE_ERROR_CHUNK])
    session.commit()


def score_run(
    session: Session,
    run: Run,
    tolerance_ns: int = DEFAULT_TOLERANCE_NS,
    rpe_delta_frames: int = DEFAULT_RPE_DELTA_FRAMES,
) -> Score | None:
    """Score a finished run, or return None when there is nothing to score against.

    Call `score_run_with_reason` when the caller has to say which case it was. None of them is
    an error, and none should leave a row of zeros behind that reads as a perfect run.
    """
    return score_run_with_reason(session, run, tolerance_ns, rpe_delta_frames)[0]


def score_run_with_reason(
    session: Session,
    run: Run,
    tolerance_ns: int = DEFAULT_TOLERANCE_NS,
    rpe_delta_frames: int = DEFAULT_RPE_DELTA_FRAMES,
) -> tuple[Score | None, str | None]:
    """Score a run, returning the reason when it could not be scored.

    The reasons are different claims and the caller has to be able to tell them apart. "this
    sequence has no ground truth" and "only two poses lined up with truth" both end in no
    metrics, but only one of them is about the sequence.
    """
    dataset = session.get(Dataset, run.dataset_id)
    if not dataset or not dataset.has_ground_truth:
        return None, "this sequence has no ground truth"

    estimate = estimate_trajectory(session, run.id, dataset.calibration)
    if len(estimate.timestamps_ns) == 0:
        return None, "the run produced no poses"

    truth = truth_trajectory(session, run.dataset_id)
    if len(truth.timestamps_ns) == 0:
        return None, "this sequence has no ground truth poses stored"

    try:
        result = score(
            estimate,
            truth,
            alignment_for(run.config),
            tolerance_ns=tolerance_ns,
            rpe_delta_frames=rpe_delta_frames,
        )
    except NotScorable as exc:
        logger.warn("metrics.not_scorable", {"run": str(run.id), "reason": str(exc)})
        return None, str(exc)

    save_score(session, run.id, result, tolerance_ns)
    logger.info(
        "metrics.scored",
        {
            "run": str(run.id),
            "alignment": result.alignment.mode,
            "ate_rmse": round(result.ate_translation.rmse, 6),
            "matched": result.association.matched_count,
        },
    )
    return result, None


def get_metrics(session: Session, run_id: uuid.UUID) -> RunMetrics | None:
    return session.get(RunMetrics, run_id)


def stored_alignment(session: Session, run: Run) -> Alignment | None:
    """Re-solve the alignment that the stored score was computed with.

    The transform itself is not stored, only its mode and the numbers it produced. It is
    re-solved from the same poses and the same association rule, so it is the same
    transform, and there is no second copy that can fall out of step with the metrics after
    a rerun. Solving Umeyama over a few thousand points is a millisecond.
    """
    metrics = get_metrics(session, run.id)
    if not metrics:
        return None

    dataset = session.get(Dataset, run.dataset_id)
    estimate = estimate_trajectory(
        session, run.id, dataset.calibration if dataset else None
    )
    truth = truth_trajectory(session, run.dataset_id)
    if len(estimate.timestamps_ns) == 0 or len(truth.timestamps_ns) == 0:
        return None

    association = associate(
        estimate.timestamps_ns, truth.timestamps_ns, metrics.association_tolerance_ns
    )
    if association.matched_count < MIN_MATCHED_POSES:
        return None

    return align_for_mode(
        estimate.take(association.estimate_indices).positions,
        truth.take(association.truth_indices).positions,
        metrics.alignment,  # type: ignore[arg-type]
    )


def pose_errors(
    session: Session, run_id: uuid.UUID, stride: int = 1
) -> tuple[list[PoseError], int]:
    """Per pose errors, decimated for the plot, with the total before decimation."""
    rows = list(
        session.scalars(
            select(PoseError)
            .where(PoseError.run_id == run_id)
            .order_by(PoseError.timestamp_ns)
        )
    )
    return (rows[::stride] if stride > 1 else rows), len(rows)
