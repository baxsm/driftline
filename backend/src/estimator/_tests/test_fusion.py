"""Fusion tests.

These need gtsam, which has no Windows wheel, so they only execute in the fusion container.
They are marked `fusion` rather than silently skipped by an `importorskip` at module level:
a check that quietly disappears still reports the suite green, which is exactly how the evo
cross check in phase 3 went unnoticed when it stopped running.
"""

from itertools import pairwise

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from scipy.spatial.transform import Rotation

from datasets.parsing import ImuSample
from estimator import fusion as fusion_module
from estimator.fusion import (
    GRAVITY,
    FusionFailed,
    ImuNoise,
    KeyframeMotion,
    _preintegration_params,
    fuse,
    fusion_available,
    initialise,
    load_gtsam,
    preintegrate,
)
from estimator.imu import ImuStream, stream_from_samples
from geometry.transform import Transform

from .synthetic import inertial_sequence

pytestmark = pytest.mark.skipif(
    not fusion_available(), reason="gtsam is unavailable here, run this in the fusion image"
)


def _stream(samples) -> ImuStream:
    return stream_from_samples(samples)


def _still_stream(seconds: float = 2.0, rate: float = 200.0) -> ImuStream:
    """A device sitting still: gravity on z, nothing else."""
    count = int(seconds * rate)
    return stream_from_samples(
        [
            ImuSample(
                timestamp_ns=1_000_000_000_000_000_000 + round(i / rate * 1e9),
                wx=0.0,
                wy=0.0,
                wz=0.0,
                ax=0.0,
                ay=0.0,
                az=GRAVITY,
            )
            for i in range(count)
        ]
    )


def test_preintegrating_constant_acceleration_matches_the_closed_form():
    """A constant specific force over t seconds must integrate to the analytic result.

    With gravity cancelled exactly, position goes as 0.5*a*t^2 and velocity as a*t. This is
    the one place the integration itself is checked against arithmetic rather than against
    another run of the same code.
    """
    gtsam = load_gtsam()
    params = gtsam.PreintegrationCombinedParams.MakeSharedU(GRAVITY)
    params.setAccelerometerCovariance(np.eye(3) * 1e-8)
    params.setGyroscopeCovariance(np.eye(3) * 1e-10)
    params.setIntegrationCovariance(np.eye(3) * 1e-12)
    params.setBiasAccCovariance(np.eye(3) * 1e-10)
    params.setBiasOmegaCovariance(np.eye(3) * 1e-12)
    params.setBiasAccOmegaInit(np.eye(6) * 1e-10)

    summary = gtsam.PreintegratedCombinedMeasurements(params, gtsam.imuBias.ConstantBias())

    # specific force of exactly g upward is a body at rest in the frame this gravity
    # convention describes, so the acceleration it leaves behind is 2 m/s^2 along x
    acceleration = np.array([2.0, 0.0, GRAVITY])
    dt = 0.005
    steps = 200
    for _ in range(steps):
        summary.integrateMeasurement(acceleration, np.zeros(3), dt)

    elapsed = steps * dt
    assert summary.deltaTij() == pytest.approx(elapsed)
    assert summary.deltaVij()[0] == pytest.approx(2.0 * elapsed, rel=1e-9)
    assert summary.deltaPij()[0] == pytest.approx(0.5 * 2.0 * elapsed**2, rel=1e-9)
    # nothing rotated, so the delta rotation is the identity
    assert np.allclose(summary.deltaRij().matrix(), np.eye(3), atol=1e-12)


def test_preintegrating_a_still_device_leaves_it_still():
    """Gravity alone must not accumulate motion once it is accounted for."""
    gtsam = load_gtsam()
    stream = _still_stream(seconds=1.0)
    noise = ImuNoise()
    initial = initialise(stream)
    params = _preintegration_params(gtsam, noise, initial)
    window = stream.between(stream.timestamps_ns[0], stream.timestamps_ns[-1])
    summary = preintegrate(gtsam, params, gtsam.imuBias.ConstantBias(), window)

    predicted = summary.predict(
        gtsam.NavState(gtsam.Pose3(), np.zeros(3)), gtsam.imuBias.ConstantBias()
    )
    assert np.linalg.norm(predicted.position()) < 1e-6
    assert np.linalg.norm(predicted.velocity()) < 1e-6


@pytest.mark.parametrize("upward", [True, False])
def test_a_still_device_dead_reckons_nowhere_under_either_gravity_convention(upward):
    """The gravity convention check, stated as behaviour rather than as a sign.

    GTSAM's `n_gravity` is the gravity vector, while an accelerometer at rest reads the
    reaction to it, which points the other way. Reading that backwards applies gravity twice
    instead of cancelling it, and the failure is completely silent: no error is raised, the
    trajectory is finite and smooth, and it is simply five times too long. Getting this wrong
    on room1 turned a 13 m path into a 64 m one.

    A device sitting still is the case that separates the two: under the right convention it
    stays put, under the wrong one it accelerates away at 2g.
    """
    gtsam = load_gtsam()
    sign = 1.0 if upward else -1.0
    stream = stream_from_samples(
        [
            ImuSample(
                timestamp_ns=1_000_000_000_000_000_000 + i * 5_000_000,
                wx=0.0,
                wy=0.0,
                wz=0.0,
                ax=0.0,
                ay=0.0,
                az=sign * GRAVITY,
            )
            for i in range(400)
        ]
    )

    initial = initialise(stream)
    params = _preintegration_params(gtsam, ImuNoise(), initial)
    window = stream.between(stream.timestamps_ns[0], stream.timestamps_ns[-1])
    summary = preintegrate(gtsam, params, gtsam.imuBias.ConstantBias(), window)

    predicted = summary.predict(gtsam.NavState(), gtsam.imuBias.ConstantBias())
    assert float(np.linalg.norm(predicted.position())) < 1e-6
    assert float(np.linalg.norm(predicted.velocity())) < 1e-6


def test_splitting_a_window_and_composing_gives_the_same_motion():
    """Preintegrating [a,c] must match preintegrating [a,b] then [b,c].

    This is the property that makes keyframe placement a free choice. If it did not hold, the
    trajectory would depend on where the parallax threshold happened to fall.
    """
    gtsam = load_gtsam()
    sequence = inertial_sequence(frames=12)
    stream = _stream(sequence.imu)
    noise = ImuNoise()
    params = _preintegration_params(gtsam, noise, initialise(stream))
    bias = gtsam.imuBias.ConstantBias()

    start = sequence.frame_timestamps_ns[2]
    middle = sequence.frame_timestamps_ns[5]
    end = sequence.frame_timestamps_ns[8]

    whole = preintegrate(gtsam, params, bias, stream.between(start, end))
    first = preintegrate(gtsam, params, bias, stream.between(start, middle))
    second = preintegrate(gtsam, params, bias, stream.between(middle, end))

    assert whole.deltaTij() == pytest.approx(first.deltaTij() + second.deltaTij(), rel=1e-9)

    start_state = gtsam.NavState(gtsam.Pose3(), np.zeros(3))
    direct = whole.predict(start_state, bias)
    stepwise = second.predict(first.predict(start_state, bias), bias)

    assert np.allclose(direct.position(), stepwise.position(), atol=1e-6)
    assert np.allclose(direct.velocity(), stepwise.velocity(), atol=1e-6)


def test_initialisation_finds_which_way_is_down():
    stream = _still_stream()
    initial = initialise(stream)

    assert np.linalg.norm(initial.gravity_in_body) == pytest.approx(GRAVITY, rel=1e-9)
    assert initial.gravity_in_body[2] == pytest.approx(GRAVITY, rel=1e-9)
    # a still device is the unexcited case by definition
    assert not initial.is_excited
    assert initial.stillness == pytest.approx(0.0, abs=1e-12)


def test_initialisation_picks_the_stillest_window_not_the_first_one():
    """Gravity must be read where the device is quiet, not wherever the stream happens to open.

    A sequence that opens mid-motion and settles later would otherwise take its gravity
    direction from the moving part, which tilts every pose that follows.
    """
    turning = [
        ImuSample(
            timestamp_ns=1_000_000_000_000_000_000 + i * 5_000_000,
            wx=0.8,
            wy=0.0,
            wz=0.0,
            ax=2.5,
            ay=0.0,
            az=GRAVITY,
        )
        for i in range(400)
    ]
    still = [
        ImuSample(
            timestamp_ns=1_000_000_000_000_000_000 + (400 + i) * 5_000_000,
            wx=0.0,
            wy=0.0,
            wz=0.0,
            ax=0.0,
            ay=0.0,
            az=GRAVITY,
        )
        for i in range(400)
    ]

    initial = initialise(stream_from_samples([*turning, *still]))

    # the still half has gravity straight down z, the turning half does not
    assert initial.gravity_in_body[0] == pytest.approx(0.0, abs=1e-9)
    assert initial.gravity_in_body[2] == pytest.approx(GRAVITY, rel=1e-9)
    assert initial.stillness == pytest.approx(0.0, abs=1e-12)


def test_initialisation_reports_excitation_when_the_device_moves():
    sequence = inertial_sequence(frames=40)
    initial = initialise(_stream(sequence.imu))
    assert initial.is_excited


def test_initialisation_refuses_a_stream_with_no_measurable_force():
    stream = stream_from_samples(
        [
            ImuSample(
                timestamp_ns=1_000_000_000 + i * 5_000_000,
                wx=0.0,
                wy=0.0,
                wz=0.0,
                ax=0.0,
                ay=0.0,
                az=0.0,
            )
            for i in range(50)
        ]
    )
    with pytest.raises(FusionFailed, match="which way is down"):
        initialise(stream)


def _keyframes_from(sequence, indices):
    """Visual keyframe motions with translation reduced to a unit direction.

    This is what the front end hands fusion: a direction and no distance. Building them from
    the known poses isolates the fusion stage from front end error.

    The direction is expressed in the **body frame of the earlier keyframe**, which is what a
    camera bolted to the device actually measures. Building it in the world frame instead
    makes every non-rotating test pass and is exactly the confusion that let three frame bugs
    through, so the rotation is applied here rather than assumed away.
    """
    keyframes = [
        KeyframeMotion(
            frame_index=indices[0],
            timestamp_ns=sequence.frame_timestamps_ns[indices[0]],
            motion=Transform.identity(),
        )
    ]
    for previous, current in pairwise(indices):
        delta = sequence.poses[current].translation - sequence.poses[previous].translation
        in_body = sequence.poses[previous].rotation.T @ delta
        keyframes.append(
            KeyframeMotion(
                frame_index=current,
                timestamp_ns=sequence.frame_timestamps_ns[current],
                motion=Transform(np.eye(3), in_body / np.linalg.norm(in_body)),
            )
        )
    return keyframes


def test_fusion_recovers_metric_scale_the_camera_never_saw():
    """The point of the whole phase: unit directions in, real metres out.

    The visual input carries no distance at all, so a recovered path length near the true one
    can only have come from the IMU.
    """
    sequence = inertial_sequence(frames=60)
    indices = list(range(0, 60, 2))
    result = fuse(
        keyframes=_keyframes_from(sequence, indices),
        stream=_stream(sequence.imu),
        noise=ImuNoise(),
        body_to_camera=None,
    )

    truth = np.array([sequence.poses[i].translation for i in indices])
    true_length = float(np.linalg.norm(np.diff(truth, axis=0), axis=1).sum())

    assert result.path_length == pytest.approx(true_length, rel=0.15)

    estimated = np.array([state.pose.translation for state in result.states])
    errors = np.linalg.norm(estimated - truth, axis=1)
    assert float(np.sqrt((errors**2).mean())) < 0.25


def test_fused_velocity_follows_the_real_speed():
    """Velocity is a real output of fusion, so it must track the path rather than sit at zero."""
    sequence = inertial_sequence(frames=60)
    indices = list(range(0, 60, 2))
    result = fuse(
        keyframes=_keyframes_from(sequence, indices),
        stream=_stream(sequence.imu),
        noise=ImuNoise(),
        body_to_camera=None,
    )

    speeds = np.array([np.linalg.norm(state.velocity) for state in result.states])
    assert np.all(np.isfinite(speeds))
    # the synthetic path runs at roughly 1.4 m/s, and a stationary answer would be the tell
    assert speeds[2:-2].mean() > 0.5


def test_fusion_beats_the_visual_only_estimate_on_the_same_input():
    """The controlled proof that fusion helps.

    Visual-only cannot know how far the camera went, so its path is composed of unit steps.
    Both are compared after the Sim(3)/SE(3) rescaling each mode is entitled to, which is the
    fair comparison: fusion still has to win on shape, not just on scale.
    """
    sequence = inertial_sequence(frames=60)
    indices = list(range(0, 60, 2))
    keyframes = _keyframes_from(sequence, indices)

    truth = np.array([sequence.poses[i].translation for i in indices])

    visual = np.zeros((len(keyframes), 3))
    for i in range(1, len(keyframes)):
        visual[i] = visual[i - 1] + keyframes[i].motion.translation

    result = fuse(
        keyframes=keyframes,
        stream=_stream(sequence.imu),
        noise=ImuNoise(),
        body_to_camera=None,
    )
    fused = np.array([state.pose.translation for state in result.states])

    def best_scaled_rmse(estimate: np.ndarray) -> float:
        centred_estimate = estimate - estimate.mean(axis=0)
        centred_truth = truth - truth.mean(axis=0)
        denominator = float((centred_estimate**2).sum())
        scale = (
            float((centred_estimate * centred_truth).sum()) / denominator
            if denominator > 0
            else 1.0
        )
        residual = centred_truth - centred_estimate * scale
        return float(np.sqrt((residual**2).sum(axis=1).mean()))

    assert best_scaled_rmse(fused) < best_scaled_rmse(visual)


def test_fusion_recovers_scale_while_the_device_is_turning():
    """The same claim as above, but with the body frame rotating away from the world frame.

    This is the case that matters. Three separate frame handling bugs, in the visual factor,
    in the seeded attitude, and in the seeded step direction, passed every test on a
    non-rotating path because there the two frames coincide. All three appeared at once on the
    first real sequence with a turning camera. A fusion test on an unrotated path is not
    testing frame handling at all.
    """
    sequence = inertial_sequence(frames=60, yaw_per_second=0.7)
    indices = list(range(0, 60, 2))
    result = fuse(
        keyframes=_keyframes_from(sequence, indices),
        stream=_stream(sequence.imu),
        noise=ImuNoise(),
        body_to_camera=None,
    )

    truth = np.array([sequence.poses[i].translation for i in indices])
    true_length = float(np.linalg.norm(np.diff(truth, axis=0), axis=1).sum())

    assert result.path_length == pytest.approx(true_length, rel=0.2)

    estimated = np.array([state.pose.translation for state in result.states])
    assert float(np.sqrt((np.linalg.norm(estimated - truth, axis=1) ** 2).mean())) < 0.4


@pytest.mark.parametrize("window", [150, 20, 12])
def test_every_keyframe_comes_back_exactly_once(window, monkeypatch):
    """The windowing must not drop or duplicate a state, at any window size.

    Windows overlap and hand over from an interior state, so the arithmetic deciding where the
    next one starts has to line up exactly. Off by one either way is invisible in the metrics,
    which would simply be computed over slightly the wrong poses. The window is shrunk here
    rather than the run lengthened, because the default of 150 would take a single window on
    any sequence short enough to render quickly, and then this would test nothing.
    """
    monkeypatch.setattr(fusion_module, "WINDOW_KEYFRAMES", window)

    sequence = inertial_sequence(frames=60, yaw_per_second=0.4)
    indices = list(range(0, 60, 2))

    result = fuse(
        keyframes=_keyframes_from(sequence, indices),
        stream=_stream(sequence.imu),
        noise=ImuNoise(),
        body_to_camera=None,
    )

    assert [state.frame_index for state in result.states] == indices


def test_fusion_refuses_when_the_imu_does_not_span_the_frames():
    sequence = inertial_sequence(frames=20)
    keyframes = _keyframes_from(sequence, list(range(0, 20, 2)))
    truncated = stream_from_samples(sequence.imu[: len(sequence.imu) // 3])

    with pytest.raises(FusionFailed, match="does not span"):
        fuse(keyframes=keyframes, stream=truncated, noise=ImuNoise(), body_to_camera=None)


def test_fusion_refuses_a_single_keyframe():
    sequence = inertial_sequence(frames=20)
    with pytest.raises(FusionFailed, match="at least 2 keyframes"):
        fuse(
            keyframes=_keyframes_from(sequence, [0]),
            stream=_stream(sequence.imu),
            noise=ImuNoise(),
            body_to_camera=None,
        )


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    roll=st.floats(min_value=-0.6, max_value=0.6),
    pitch=st.floats(min_value=-0.6, max_value=0.6),
)
def test_gravity_direction_is_recovered_whatever_way_the_device_is_held(roll, pitch):
    """Rotating the device rotates the gravity it measures, and initialisation must follow.

    A gravity estimate that is right only when the device is level is the bug that curves a
    trajectory smoothly away while still rendering as a plausible path.
    """
    world_to_body = Rotation.from_euler("xy", [roll, pitch]).as_matrix().T
    measured = world_to_body @ np.array([0.0, 0.0, GRAVITY])

    stream = stream_from_samples(
        [
            ImuSample(
                timestamp_ns=1_000_000_000_000_000_000 + i * 5_000_000,
                wx=0.0,
                wy=0.0,
                wz=0.0,
                ax=float(measured[0]),
                ay=float(measured[1]),
                az=float(measured[2]),
            )
            for i in range(100)
        ]
    )

    initial = initialise(stream)
    assert np.allclose(initial.gravity_in_body, measured, atol=1e-9)
