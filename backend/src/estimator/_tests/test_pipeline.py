"""Does the front end recover a camera path we generated ourselves?

Monocular translation has no scale, so the recovered path cannot be compared to the truth
directly. Both are normalized by their own total length first, which compares the shape of
the trajectory and leaves the unknown scale factor out of it.
"""

import numpy as np
import pytest

from estimator.camera import Camera
from estimator.config import EstimatorConfig
from estimator.pipeline import run_pipeline

from .synthetic import straight_line_sequence, turning_sequence


def _pinhole(matrix: np.ndarray) -> Camera:
    return Camera(
        width=640,
        height=480,
        matrix=matrix,
        distortion=np.zeros(4),
        distortion_model="none",
    )


def _normalized_path(positions: np.ndarray) -> np.ndarray:
    """Scale a path so its total travelled distance is 1, leaving mono scale out of it."""
    length = float(np.sum(np.linalg.norm(np.diff(positions, axis=0), axis=1)))
    if length < 1e-9:
        return positions - positions[0]
    return (positions - positions[0]) / length


def test_recovers_a_straight_line():
    sequence = straight_line_sequence()
    outcome = run_pipeline(
        timestamps=[i * 50_000_000 for i in range(len(sequence.images))],
        load_image=lambda i: sequence.images[i],
        camera=_pinhole(sequence.camera_matrix),
        config=EstimatorConfig(),
    )

    assert not outcome.failed, outcome.failure_reason
    assert len(outcome.frames) == len(sequence.images)

    estimated = _normalized_path(np.array([f.pose.translation for f in outcome.frames]))
    truth = _normalized_path(np.array([p.translation for p in sequence.poses]))

    assert np.all(np.isfinite(estimated))
    # the path is a straight line along +x, so the estimate must run the same way and not
    # double back, which is what a flipped translation sign would produce
    assert estimated[-1][0] > 0.8
    assert float(np.max(np.abs(estimated - truth))) < 0.12


def test_recovers_a_turning_path():
    sequence = turning_sequence()
    outcome = run_pipeline(
        timestamps=[i * 50_000_000 for i in range(len(sequence.images))],
        load_image=lambda i: sequence.images[i],
        camera=_pinhole(sequence.camera_matrix),
        config=EstimatorConfig(),
    )

    assert not outcome.failed, outcome.failure_reason
    estimated = np.array([f.pose.translation for f in outcome.frames])
    assert np.all(np.isfinite(estimated))

    truth_yaw = [
        float(np.arctan2(p.rotation[0, 2], p.rotation[0, 0])) for p in sequence.poses
    ]
    estimated_yaw = [
        float(np.arctan2(f.pose.rotation[0, 2], f.pose.rotation[0, 0])) for f in outcome.frames
    ]
    # the camera yaws steadily, so the recovered yaw must follow it rather than stay flat
    assert abs(estimated_yaw[-1] - truth_yaw[-1]) < 0.1


def test_blank_frames_fail_with_a_reason_and_a_frame_number():
    """A run that cannot be solved must say why, not return a silent path of identities.

    Blank frames have no corners, so no keyframe after the first can ever be solved. The run
    has to end saying so rather than reporting a successful trajectory that never moved.
    """
    blank = [np.full((480, 640), 30, dtype=np.uint8) for _ in range(6)]
    outcome = run_pipeline(
        timestamps=[i * 50_000_000 for i in range(len(blank))],
        load_image=lambda i: blank[i],
        camera=_pinhole(
            np.array([[400.0, 0, 320.0], [0, 400.0, 240.0], [0, 0, 1.0]])
        ),
        config=EstimatorConfig(),
    )

    assert outcome.failed
    assert outcome.failure_frame is not None
    assert "no motion could be solved" in (outcome.failure_reason or "")


def test_a_still_camera_fails_rather_than_reporting_a_path():
    """The degenerate case that broke every real run: a camera that is not translating.

    The essential matrix cannot separate rotation from translation without parallax, so the
    honest outcome is a failure naming the missing parallax, not a trajectory.
    """
    sequence = straight_line_sequence()
    still = [sequence.images[0] for _ in range(40)]
    outcome = run_pipeline(
        timestamps=[i * 50_000_000 for i in range(len(still))],
        load_image=lambda i: still[i],
        camera=_pinhole(sequence.camera_matrix),
        config=EstimatorConfig(max_frames_without_keyframe=20),
    )

    assert outcome.failed
    assert "px" in (outcome.failure_reason or "")
    assert "no keyframe" in (outcome.failure_reason or "")


def test_frames_between_keyframes_are_interpolated_not_held():
    """Non keyframe poses must move, otherwise the path stalls and then jumps.

    A held pose reports the camera as stationary across the gap and then teleporting at the
    next keyframe, which is not what happened and makes relative error meaningless.
    """
    sequence = straight_line_sequence(frames=24)
    outcome = run_pipeline(
        timestamps=[i * 50_000_000 for i in range(len(sequence.images))],
        load_image=lambda i: sequence.images[i],
        camera=_pinhole(sequence.camera_matrix),
        config=EstimatorConfig(keyframe_parallax_px=20.0),
    )

    assert not outcome.failed, outcome.failure_reason
    keyframes = [index for index, f in enumerate(outcome.frames) if f.is_keyframe]
    assert len(keyframes) > 2, "the sequence should have produced several keyframes"

    positions = np.array([f.pose.translation for f in outcome.frames])
    steps = np.linalg.norm(np.diff(positions, axis=0), axis=1)
    # up to the last keyframe every step moves. Frames after it are still waiting for a solve
    # that never came, and holding those is the honest thing to do.
    settled = steps[: keyframes[-1]]
    assert np.count_nonzero(settled < 1e-12) == 0


def test_max_frames_limits_the_run():
    sequence = straight_line_sequence()
    outcome = run_pipeline(
        timestamps=[i * 50_000_000 for i in range(6)],
        load_image=lambda i: sequence.images[i],
        camera=_pinhole(sequence.camera_matrix),
        config=EstimatorConfig(max_frames=6),
    )
    assert len(outcome.frames) == 6


def test_progress_callback_sees_every_frame():
    sequence = straight_line_sequence(frames=8)
    seen: list[int] = []
    run_pipeline(
        timestamps=[i * 50_000_000 for i in range(8)],
        load_image=lambda i: sequence.images[i],
        camera=_pinhole(sequence.camera_matrix),
        config=EstimatorConfig(),
        on_frame=lambda result: seen.append(result.frame_index),
    )
    assert seen == list(range(8))


@pytest.mark.parametrize("unknown", ["windowsize", "imu_gyro_noise", "mode_"])
def test_config_rejects_unknown_keys(unknown: str):
    with pytest.raises(ValueError):
        EstimatorConfig(**{unknown: 1})


def test_config_hash_is_stable_and_order_independent():
    a = EstimatorConfig(max_features=400, corner_quality=0.02)
    b = EstimatorConfig(corner_quality=0.02, max_features=400)
    assert a.hash() == b.hash()
    assert EstimatorConfig(max_features=401).hash() != a.hash()
