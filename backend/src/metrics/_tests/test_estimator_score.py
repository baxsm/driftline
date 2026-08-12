"""Score the real estimator against a path we generated, end to end.

Every other test in this folder feeds the scorer trajectories built to have a known answer.
This one runs the actual front end over rendered images and scores what comes out, so it
covers the joins the unit tests cannot: that the estimator's poses and the truth poses agree
on what a timestamp means, that a monocular estimate is Sim(3) aligned, and that the numbers
that reach the database are the ones the metrics produced.

The camera path is known to machine precision, so a bad score here is the estimator or the
wiring and never the data. That is a stronger check than a real sequence would give, where a
bad number could equally be the calibration or the images.
"""

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from estimator._tests.synthetic import straight_line_sequence, turning_sequence
from estimator.camera import Camera
from estimator.config import EstimatorConfig
from estimator.pipeline import run_pipeline
from metrics.scoring import Trajectory, score

FRAME_INTERVAL_NS = 50_000_000
EPOCH_NS = 1_520_530_000_000_000_000


def _pinhole(matrix: np.ndarray) -> Camera:
    return Camera(
        width=640, height=480, matrix=matrix, distortion=np.zeros(4), distortion_model="none"
    )


def _timestamps(count: int) -> np.ndarray:
    return (np.arange(count) * FRAME_INTERVAL_NS + EPOCH_NS).astype(np.int64)


def _truth_trajectory(sequence) -> Trajectory:
    positions = np.array([pose.translation for pose in sequence.poses], dtype=np.float64)
    quaternions = np.array([pose.quaternion() for pose in sequence.poses], dtype=np.float64)
    return Trajectory(_timestamps(len(sequence.poses)), positions, quaternions)


def _estimate_trajectory(frames) -> Trajectory:
    positions = np.array([frame.pose.translation for frame in frames], dtype=np.float64)
    quaternions = np.array([frame.pose.quaternion() for frame in frames], dtype=np.float64)
    timestamps = np.array([frame.timestamp_ns for frame in frames], dtype=np.int64)
    return Trajectory(timestamps, positions, quaternions)


def _run(sequence) -> Trajectory:
    outcome = run_pipeline(
        timestamps=list(_timestamps(len(sequence.images))),
        load_image=lambda index: sequence.images[index],
        camera=_pinhole(sequence.camera_matrix),
        config=EstimatorConfig(),
    )
    assert not outcome.failed, outcome.failure_reason
    return _estimate_trajectory(outcome.frames)


def test_straight_line_scores_within_a_plausible_band() -> None:
    """The recovered path should be close, and close in a way worth stating.

    A published visual-inertial system reports ATE in the centimetres on a room sequence.
    This is a monocular front end with no loop closure and no bundle adjustment, so it will
    be worse, but on a 6 m synthetic path with perfect images it should still land well
    under a tenth of the path length. A result near zero would mean the scorer is comparing
    something to itself, and a result of several metres would mean the estimate is wrong.
    """
    sequence = straight_line_sequence()
    truth = _truth_trajectory(sequence)
    estimate = _run(sequence)

    result = score(estimate, truth, "sim3")

    path_length = float(
        np.sum(np.linalg.norm(np.diff(truth.positions, axis=0), axis=1))
    )
    assert result.association.matched_count == len(sequence.poses)
    assert result.alignment.mode == "sim3"
    assert 0.0 < result.ate_translation.rmse < path_length * 0.1
    assert result.scale_error is not None and result.scale_error > 0.0


def test_turning_path_recovers_the_rotation_rate() -> None:
    """RPE is what says whether the rotation is right; absolute rotation error cannot.

    Alignment is solved on positions alone, which is what evo does and what the literature
    reports. On a path that is close to a straight line the position fit barely constrains
    the rotation about the direction of travel, so the aligned orientations keep a roughly
    constant offset about that axis. Here it is about 17 degrees, near constant across the
    run: the spread of the per pose error is under a degree, so it is a frame offset and not
    drift.

    Absolute rotation error would therefore be reporting the alignment's blind spot rather
    than the estimator's rotation. The rate of rotation over a segment is unaffected by a
    constant offset, so RPE is the number that answers the question.
    """
    sequence = turning_sequence()
    truth = _truth_trajectory(sequence)
    estimate = _run(sequence)

    result = score(estimate, truth, "sim3", rpe_delta_frames=5)

    assert result.rpe_rotation_deg is not None
    assert result.rpe_translation is not None
    assert result.rpe_rotation_deg.rmse < 2.0
    assert len(result.pose_errors) == result.association.matched_count

    # a constant offset, not accumulating error
    assert result.ate_rotation_deg.std < 1.0


def test_a_deliberately_wrong_estimate_scores_badly() -> None:
    """The scorer must be able to fail a run, not just pass good ones.

    A metric that reports a small number whatever it is given is indistinguishable from a
    working one until something is actually broken. Here the estimate is bent away from
    truth by a rotation that grows along the run, which no single alignment can undo.
    """
    sequence = straight_line_sequence()
    truth = _truth_trajectory(sequence)
    estimate = _run(sequence)

    growing = np.linspace(0.0, 2.0, len(estimate.positions))
    zero = np.zeros_like(growing)
    drift = Rotation.from_rotvec(np.column_stack([zero, growing, zero])).as_matrix()
    wrecked = Trajectory(
        estimate.timestamps_ns.copy(),
        np.einsum("nij,nj->ni", drift, estimate.positions),
        estimate.quaternions.copy(),
    )

    good = score(estimate, truth, "sim3").ate_translation.rmse
    bad = score(wrecked, truth, "sim3").ate_translation.rmse

    assert bad > good * 5


def test_estimate_and_truth_agree_on_timestamps() -> None:
    """The estimator stamps poses with the frame's own timestamp, so every pose matches.

    If the estimator ever numbered poses from its own counter instead, association would
    quietly drop most of the run and the ATE would be computed over whatever happened to
    line up.
    """
    sequence = straight_line_sequence(frames=12)
    estimate = _run(sequence)

    assert list(estimate.timestamps_ns) == list(_timestamps(12))


def test_scoring_the_estimate_against_itself_is_zero() -> None:
    sequence = straight_line_sequence(frames=12)
    estimate = _run(sequence)

    result = score(estimate, estimate, "se3")

    assert result.ate_translation.rmse == pytest.approx(0.0, abs=1e-9)
