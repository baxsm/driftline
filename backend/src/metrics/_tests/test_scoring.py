"""Scoring tests where the right answer is known without an oracle."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.spatial.transform import Rotation

from metrics.errors import relative_pose_errors, rotation_errors_deg, summarize
from metrics.scoring import NotScorable, Trajectory, score

from .trajectories import transform_trajectory, wandering_trajectory


def test_ground_truth_against_itself_is_zero() -> None:
    """The zero error test. If this is not zero, association or alignment is broken."""
    truth = wandering_trajectory(seed=12, count=150)

    result = score(truth, truth, "se3")

    assert result.ate_translation.rmse == pytest.approx(0.0, abs=1e-9)
    assert result.ate_rotation_deg.rmse == pytest.approx(0.0, abs=1e-7)
    assert result.association.matched_count == 150


def test_zero_error_holds_under_sim3_too() -> None:
    truth = wandering_trajectory(seed=13, count=150)

    result = score(truth, truth, "sim3")

    assert result.ate_translation.rmse == pytest.approx(0.0, abs=1e-9)
    assert result.alignment.scale == pytest.approx(1.0, rel=1e-9)


def test_alignment_absorbs_a_constant_offset() -> None:
    """Shifting every pose by the same vector must not show up as error.

    Alignment solves for the offset, so a trajectory that is the right shape in the wrong
    place scores zero. This is the intended behaviour and it is worth pinning down: it is
    also the reason ATE cannot detect a constant bias, and why the alignment that produced
    a number is reported next to it.
    """
    truth = wandering_trajectory(seed=14, count=120)
    estimate = Trajectory(
        truth.timestamps_ns.copy(),
        truth.positions + np.array([0.0, 0.35, 0.0]),
        truth.quaternions.copy(),
    )

    result = score(estimate, truth, "se3")

    assert result.ate_translation.rmse == pytest.approx(0.0, abs=1e-9)
    assert result.alignment.translation == pytest.approx(np.array([0.0, -0.35, 0.0]), abs=1e-9)


def test_alignment_absorbs_a_rigid_offset_but_not_noise() -> None:
    """A perfect estimate in a different frame scores zero; injected noise scores its size."""
    truth = wandering_trajectory(seed=15, count=200)
    rotation = np.asarray(Rotation.from_euler("xyz", [0.2, 0.5, -0.3]).as_matrix())

    exact = transform_trajectory(
        truth, rotation=rotation, translation=np.array([4.0, 1.0, -2.0]), scale=1.0
    )
    assert score(exact, truth, "se3").ate_translation.rmse == pytest.approx(0.0, abs=1e-9)

    noisy = transform_trajectory(
        truth,
        rotation=rotation,
        translation=np.array([4.0, 1.0, -2.0]),
        scale=1.0,
        noise=0.02,
    )
    # three independent axes at sigma each, so the expected distance is sigma*sqrt(3)
    assert score(noisy, truth, "se3").ate_translation.rmse == pytest.approx(
        0.02 * np.sqrt(3), rel=0.15
    )


def test_mono_scale_does_not_change_the_score() -> None:
    """Scaling a monocular estimate must leave the Sim(3) ATE untouched."""
    truth = wandering_trajectory(seed=16, count=150)
    estimate = transform_trajectory(
        truth, rotation=np.eye(3), translation=np.zeros(3), scale=1.0, noise=0.01
    )

    baseline = score(estimate, truth, "sim3").ate_translation.rmse
    scaled = Trajectory(
        estimate.timestamps_ns.copy(), estimate.positions * 37.0, estimate.quaternions.copy()
    )

    assert score(scaled, truth, "sim3").ate_translation.rmse == pytest.approx(
        baseline, rel=1e-6
    )


def test_se3_on_a_scaled_estimate_reports_the_scale_error() -> None:
    """The failure this project exists to surface, stated as a test.

    The same estimate scores near zero under Sim(3) and badly under SE(3). Picking the mode
    by what looks better would hide a completely unscaled trajectory.
    """
    truth = wandering_trajectory(seed=17, count=150)
    estimate = Trajectory(
        truth.timestamps_ns.copy(), truth.positions * 0.3, truth.quaternions.copy()
    )

    assert score(estimate, truth, "sim3").ate_translation.rmse == pytest.approx(0.0, abs=1e-8)
    assert score(estimate, truth, "se3").ate_translation.rmse > 0.1


def test_scale_error_is_none_for_se3() -> None:
    """SE(3) never solved for scale, so it must report nothing rather than a flattering 1.0."""
    truth = wandering_trajectory(seed=18, count=100)

    assert score(truth, truth, "se3").scale_error is None
    assert score(truth, truth, "sim3").scale_error == pytest.approx(1.0, rel=1e-9)


def test_refuses_to_score_when_almost_nothing_matches() -> None:
    """A run that matched a couple of poses must not report a confident ATE."""
    truth = wandering_trajectory(seed=19, count=100)
    estimate = Trajectory(
        truth.timestamps_ns + 10_000_000_000, truth.positions, truth.quaternions
    )

    with pytest.raises(NotScorable):
        score(estimate, truth, "se3")


def test_rpe_is_none_when_the_run_is_too_short_for_a_segment() -> None:
    """Too short for RPE is a reason to report no RPE, not to fail the whole score."""
    truth = wandering_trajectory(seed=20, count=8)

    result = score(truth, truth, "se3", rpe_delta_frames=20)

    assert result.rpe is None
    assert result.rpe_translation is None
    assert result.ate_translation.rmse == pytest.approx(0.0, abs=1e-9)


def test_pose_errors_are_one_per_matched_pose() -> None:
    truth = wandering_trajectory(seed=21, count=60)
    result = score(truth, truth, "se3")

    assert len(result.pose_errors) == result.association.matched_count
    assert [error.timestamp_ns for error in result.pose_errors] == list(truth.timestamps_ns)


def test_rotation_error_is_geodesic_not_euler() -> None:
    """A 180 degree rotation is where Euler differencing and the geodesic angle part ways."""
    identity = np.eye(3)[None, :, :]
    half_turn = Rotation.from_euler("x", 180, degrees=True).as_matrix()[None, :, :]

    assert rotation_errors_deg(half_turn, identity)[0] == pytest.approx(180.0, abs=1e-6)

    ninety = Rotation.from_euler("y", 90, degrees=True).as_matrix()[None, :, :]
    assert rotation_errors_deg(ninety, identity)[0] == pytest.approx(90.0, abs=1e-9)


def test_rpe_segments_do_not_overlap() -> None:
    """Consecutive pairs step by delta, so 100 poses at delta 20 give 4 segments."""
    truth = wandering_trajectory(seed=22, count=100)

    relative = relative_pose_errors(
        truth.rotations, truth.positions, truth.rotations, truth.positions, delta_frames=20
    )

    assert len(relative.translation) == 4
    assert list(relative.end_indices) == [20, 40, 60, 80]
    assert relative.translation == pytest.approx(np.zeros(4), abs=1e-9)


def test_summarize_rejects_an_empty_array() -> None:
    with pytest.raises(ValueError):
        summarize(np.zeros(0))


@settings(max_examples=30, deadline=None)
@given(seed=st.integers(1, 10_000))
def test_any_trajectory_scores_zero_against_itself(seed: int) -> None:
    truth = wandering_trajectory(seed=seed, count=50)

    assert score(truth, truth, "se3").ate_translation.rmse == pytest.approx(0.0, abs=1e-8)


@settings(max_examples=25, deadline=None)
@given(
    angles=st.tuples(st.floats(-3.0, 3.0), st.floats(-3.0, 3.0), st.floats(-3.0, 3.0)),
    offset=st.tuples(st.floats(-20.0, 20.0), st.floats(-20.0, 20.0), st.floats(-20.0, 20.0)),
)
def test_score_is_invariant_to_a_shared_rigid_transform(
    angles: tuple[float, float, float], offset: tuple[float, float, float]
) -> None:
    """Moving both trajectories together must not change the error between them.

    The score is a statement about how the two differ, so it cannot depend on the frame they
    happen to be expressed in.
    """
    truth = wandering_trajectory(seed=23, count=60)
    estimate = transform_trajectory(
        truth, rotation=np.eye(3), translation=np.zeros(3), scale=1.0, noise=0.05
    )
    baseline = score(estimate, truth, "se3").ate_translation.rmse

    rotation = np.asarray(Rotation.from_euler("xyz", angles).as_matrix())
    translation = np.array(offset)

    def moved(trajectory: Trajectory) -> Trajectory:
        positions = (rotation @ trajectory.positions.T).T + translation
        rotations = np.einsum("ij,njk->nik", rotation, trajectory.rotations)
        quaternions = Rotation.from_matrix(rotations).as_quat(scalar_first=True)
        return Trajectory(
            trajectory.timestamps_ns.copy(),
            np.asarray(positions, dtype=np.float64),
            np.asarray(quaternions, dtype=np.float64),
        )

    assert score(moved(estimate), moved(truth), "se3").ate_translation.rmse == pytest.approx(
        baseline, rel=1e-6
    )


def test_body_frame_conversion_undoes_a_camera_extrinsic() -> None:
    """The bug this exists to prevent: scoring a camera frame estimate against body truth.

    TUM VI mounts the camera about 179 degrees from the IMU, so an estimate that is perfect
    scores as almost completely wrong until `T_cam_imu` is applied. Here the truth is turned
    into a camera frame trajectory and then turned back, and the score has to return to zero.
    """
    truth = wandering_trajectory(seed=31, count=80)

    body_to_camera = np.eye(4)
    body_to_camera[:3, :3] = np.asarray(
        Rotation.from_euler("xyz", [2.39, 124.45, -128.80], degrees=True).as_matrix()
    )
    body_to_camera[:3, 3] = [0.047, -0.047, -0.068]

    world_to_body = np.tile(np.eye(4), (len(truth.positions), 1, 1))
    world_to_body[:, :3, :3] = truth.rotations
    world_to_body[:, :3, 3] = truth.positions
    world_to_camera = world_to_body @ np.linalg.inv(body_to_camera)

    as_camera = Trajectory(
        truth.timestamps_ns.copy(),
        np.asarray(world_to_camera[:, :3, 3], dtype=np.float64),
        np.asarray(
            Rotation.from_matrix(world_to_camera[:, :3, :3]).as_quat(scalar_first=True),
            dtype=np.float64,
        ),
    )

    # scored raw, the fixed mount shows up as a large rotation error that is not the estimate's
    assert score(as_camera, truth, "se3").ate_rotation_deg.rmse > 90.0

    recovered = as_camera.to_body_frame(body_to_camera)
    result = score(recovered, truth, "se3")
    assert result.ate_translation.rmse == pytest.approx(0.0, abs=1e-9)
    assert result.ate_rotation_deg.rmse == pytest.approx(0.0, abs=1e-7)


def test_body_frame_conversion_is_identity_for_an_identity_extrinsic() -> None:
    truth = wandering_trajectory(seed=32, count=40)

    unchanged = truth.to_body_frame(np.eye(4))

    assert np.allclose(unchanged.positions, truth.positions)
    assert score(unchanged, truth, "se3").ate_translation.rmse == pytest.approx(0.0, abs=1e-9)
