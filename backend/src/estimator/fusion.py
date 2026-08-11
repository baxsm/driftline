"""Visual-inertial fusion: the IMU supplies the metres the camera cannot see.

A monocular camera observes the *direction* the camera moved between two keyframes and
nothing about how far. An accelerometer observes force, and gravity gives it an absolute
reference, so integrating it produces real distance. Fusing the two is what makes the estimate
metric, and metric scale is the phase's measurable claim.

The graph holds, per keyframe, a pose, a velocity and an IMU bias:

    CombinedImuFactor   between consecutive states, from the preintegrated samples between
                        their timestamps. It carries the bias random walk itself, which is
                        why it is used rather than ImuFactor plus a separate bias factor.
    DirectionFactor     the visual constraint, on translation direction only.
    priors              on the state each window opens with. On the first window that fixes
                        the gauge freedom every VI graph has; on later ones it is the seam
                        carrying what the previous window solved.

**Why the visual constraint is direction only.** The front end solves an essential matrix,
whose translation is a unit vector with no magnitude (`motion.py` keeps it that way rather
than inventing one). A `BetweenFactorPose3` would assert that unit length as a real distance,
which is one metre per keyframe of fabricated data, and the optimiser would fight the IMU for
it. Constraining the direction and letting the IMU set the length is the honest reading of
what each sensor measured.

**Why this is not the reprojection based sliding window in the phase doc.** That design needs
a landmark map, and the front end that shipped produces relative poses rather than tracked 3D
points. Building bundle adjustment first was the alternative. This form fuses what the
estimator actually produces, and it is judged by the same gate either way: scale error and ATE
against the visual-only baseline.

**Solved in overlapping windows.** Not for speed, but because one graph over a whole run
stops converging. Over 214 keyframes a single batch lands within 4% of the true path length;
over 751 it exhausts Levenberg-Marquardt's iteration budget and returns 333 m against a real
141 m, with 71 degrees of relative rotation error. Each window is small enough to converge,
and its final solved pose, velocity and bias anchor the next one, so the seams stay
continuous. `ISAM2` was tried as the incremental alternative and is worse here, 49.6 cm rmse
against batch's 1.6 cm on the same synthetic path, because it relinearises lazily and the
early linearisation points are poor while the visual seed is still far from metric. This
build of GTSAM exposes neither `IncrementalFixedLagSmoother` nor `marginalizeLeaves`, so a
true marginalising fixed lag smoother is not available to call.

**Known limitation, measured rather than assumed.** Accelerometer bias and scale are only
weakly observable under constant velocity: the specific force is then almost entirely gravity,
and a bias along the direction of travel looks like a slightly different speed. Measured on a
straight constant velocity path, scale came back 11.8% out and the bias was never found; on an
accelerating, turning path the same code recovered scale to 3.3% and the bias to within 0.002.
Excitation is a property of the sequence rather than something the estimator can supply, so
`initialise` reports how much of it there was and the worker logs when there was little.

GTSAM ships no Windows wheel on any version, so this module is imported lazily by
`pipeline.py` and the runtime that lacks it says so rather than failing at import time.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from geometry.transform import Transform

from .imu import ImuStream, ImuWindow

# gtsam is typed as `Any` throughout rather than imported for annotations. It is a pybind11
# module with no stubs and no Windows wheel, so importing it for typing alone would make the
# type check fail on the machine this is developed on while proving nothing.
Array = NDArray[np.float64]

# gravity magnitude in m/s^2. The sequences here are all recorded on earth at close to sea
# level, and solving for it would need a longer static segment than a room sequence provides.
GRAVITY = 9.81

# samples averaged for the initial gravity direction and gyro bias. At 200Hz this is a second
# of data, which is enough to average out noise without assuming a long static hold.
INITIALISATION_SAMPLES = 200

# how far into the stream to look for that window, in seconds. Bias drifts over a recording,
# so a quiet stretch from the far end describes the sensor at a different time than the run.
INITIALISATION_SEARCH_SECONDS = 20.0

# a state is only kept if the optimiser actually moved it somewhere finite
MAX_PLAUSIBLE_SPEED = 50.0

# keyframes used to solve for the starting velocity. Enough to be well conditioned against
# noise, few enough that accumulated bias has not yet bent the dead reckoning.
INITIAL_VELOCITY_KEYFRAMES = 12

# short independent integrations used to estimate a typical speed. Bias error grows with the
# square of the interval, so many short segments beat one long one.
SPEED_SEGMENTS = 40
SPEED_SEGMENT_MIN_NS = 500_000_000

# keyframes solved together in one graph. Measured rather than picked: 214 keyframes converge
# to within 4% of the true path length, while 751 in one graph exhausts the optimiser's
# iterations and returns a path more than twice as long as the real one.
WINDOW_KEYFRAMES = 150

# keyframes of a window that are re-solved by the next one. The last state in a graph has no
# factor leaving it, so it soaks up the window's residual error and is the worst possible
# state to hand over from. These are discarded and resolved with their successors instead.
WINDOW_OVERLAP = 10


class FusionUnavailable(RuntimeError):
    """Raised when this runtime cannot run fusion at all, naming why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class FusionFailed(RuntimeError):
    """Raised when fusion could run but the estimate cannot be trusted."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def load_gtsam() -> Any:
    """Import GTSAM, or explain what is missing.

    GTSAM publishes manylinux and macOS wheels only, so a native Windows checkout cannot run
    fusion however the environment is configured. Saying that plainly is better than an
    ImportError traceback, because the fix is a container rather than a reinstall.
    """
    try:
        import gtsam
    except ImportError as exc:  # pragma: no cover - depends on the runtime, not the code
        raise FusionUnavailable(
            "gtsam is not installed in this runtime, so inertial runs cannot be executed "
            "here. gtsam publishes linux and macos wheels only, so this needs the docker "
            "image rather than a windows checkout"
        ) from exc
    return gtsam


def fusion_available() -> bool:
    try:
        load_gtsam()
    except FusionUnavailable:
        return False
    return True


@dataclass(frozen=True, slots=True)
class ImuNoise:
    """Noise densities as kalibr reports them, in continuous time units."""

    accelerometer_density: float = 0.0028
    gyroscope_density: float = 0.00016
    accelerometer_random_walk: float = 0.00086
    gyroscope_random_walk: float = 0.000022

    @staticmethod
    def from_calibration(calibration: dict[str, Any] | None) -> "ImuNoise":
        """Read the sequence's own noise figures, falling back to the TUM VI values.

        Real TUM VI noise differs from the EuRoC defaults by about 3.5x on accelerometer
        random walk, and getting this wrong by an order of magnitude makes the optimiser
        trust the wrong sensor without ever failing.
        """
        imu = (calibration or {}).get("imu")
        if not isinstance(imu, dict):
            return ImuNoise()
        defaults = ImuNoise()
        return ImuNoise(
            accelerometer_density=_positive(
                imu.get("accelerometer_noise_density"), defaults.accelerometer_density
            ),
            gyroscope_density=_positive(
                imu.get("gyroscope_noise_density"), defaults.gyroscope_density
            ),
            accelerometer_random_walk=_positive(
                imu.get("accelerometer_random_walk"), defaults.accelerometer_random_walk
            ),
            gyroscope_random_walk=_positive(
                imu.get("gyroscope_random_walk"), defaults.gyroscope_random_walk
            ),
        )


def _positive(value: object, fallback: float) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


@dataclass(frozen=True, slots=True)
class Initialisation:
    """The state the graph starts from, and how well the data supported finding it."""

    gravity_in_body: Array
    #: how much the specific force vector varies over the window, in m/s^2: the mean distance
    #: of each reading from the average. Near zero means the device was held still, which is
    #: exactly when scale is weakly observable.
    excitation: float
    #: mean angular rate over the window gravity was measured in, rad/s. Only small enough to
    #: have measured gyro bias if it were near zero, which on handheld data it never is.
    stillness: float = 0.0

    @property
    def is_excited(self) -> bool:
        return self.excitation > 0.05


def initialise(stream: ImuStream, sample_count: int = INITIALISATION_SAMPLES) -> Initialisation:
    """Estimate gravity direction from the stillest stretch of the stream.

    **Gyro bias is deliberately not estimated here, and that is the whole lesson of this
    function.** Averaging angular rate to get bias only works if the device is genuinely
    still, and a handheld sequence never is. Measured on room1: the true gyro bias is about
    0.0005 rad/s, while the quietest one second window anywhere in the opening twenty seconds
    still turns at 0.046 rad/s, a hundred times larger. Averaging measures the motion, not the
    bias.

    The cost of getting it wrong is not proportional. Feeding a bias that is seventy times too
    large into preintegration tilted the trajectory by 19 degrees over 8 seconds, and a tilt
    does not stay in the rotation: it misprojects gravity, so a slice of 9.81 m/s^2 leaks into
    the accelerations and integrates twice. Dead reckoning went from 0.2 metres of error to 36
    metres on that one number. Starting from zero instead leaves 0.22 degrees.

    So bias starts at zero and the factor graph solves for it, which is what the bias random
    walk in `CombinedImuFactor` exists to do. Gravity *direction* is still taken from the
    quietest window, because that only needs the average force to be dominated by gravity,
    which holds at 9.81 against the fractional m/s^2 of a handheld wobble.
    """
    if len(stream) == 0:
        raise FusionFailed("there are no imu samples to initialise from")

    count = min(sample_count, len(stream))
    start = _stillest_window(stream, count)

    accelerations = stream.accelerations[start : start + count]

    mean_force = np.asarray(accelerations.mean(axis=0), dtype=np.float64)
    magnitude = float(np.linalg.norm(mean_force))
    if magnitude < 1e-6:
        raise FusionFailed(
            "the imu samples average to no measurable force, so which way is down cannot be "
            "established"
        )

    # measured on the force *vector*, not on its magnitude. A device accelerating
    # horizontally barely changes the magnitude of what it feels, because the change is
    # perpendicular to a 9.81 gravity vector, so a magnitude based figure calls real motion
    # stationary.
    deviation = float(np.linalg.norm(accelerations - mean_force, axis=1).mean())

    return Initialisation(
        gravity_in_body=mean_force / magnitude * GRAVITY,
        #: how much the window still rotated, so the caller can see the estimate is not
        #: resting on a genuinely static hold
        stillness=float(
            np.linalg.norm(stream.angular_velocities[start : start + count], axis=1).mean()
        ),
        excitation=deviation,
    )


def _stillest_window(stream: ImuStream, count: int) -> int:
    """Index of the window of `count` samples with the least rotation in it.

    Only the opening stretch is searched. Bias drifts over a long recording, so a quiet window
    from the far end of a two minute sequence describes the sensor at a different time than
    the one the run starts at.
    """
    total = len(stream)
    if total <= count:
        return 0

    searchable = min(total, max(count * 2, int(INITIALISATION_SEARCH_SECONDS * 200)))
    rates = np.linalg.norm(stream.angular_velocities[:searchable], axis=1)

    # mean rate over every window, via a cumulative sum so this stays one pass
    cumulative = np.concatenate([[0.0], np.cumsum(rates)])
    starts = np.arange(0, len(rates) - count + 1)
    if len(starts) == 0:
        return 0
    means = (cumulative[starts + count] - cumulative[starts]) / count
    return int(starts[int(np.argmin(means))])


def _preintegration_params(gtsam: Any, noise: ImuNoise, initial: Initialisation) -> Any:
    """Continuous densities become the covariances GTSAM integrates with.

    A density is per root hertz, so its square is the covariance per second, which is the unit
    the integrator wants. Squaring is easy to forget and the failure is silent: the estimate
    degrades gradually rather than breaking.

    The gravity convention is taken from the data rather than assumed, and the direction of
    the test is worth stating because guessing it from the sign of the measurement gets it
    backwards. GTSAM's `n_gravity` is the gravity *vector* in the navigation frame, while an
    accelerometer at rest reads *specific force*, which is the reaction to it and points the
    other way. So a device whose measured force is +9.8 on z is one where gravity is -9.8 on
    z, and it needs `MakeSharedU`.

    The check on this is behavioural rather than algebraic: a still device dead reckons to
    nowhere under the right convention, and accelerates away at 2g under the wrong one. Getting
    it wrong on room1 produced a path five times longer than the real one, with no error
    raised anywhere.
    """
    measured_force_is_positive_z = float(initial.gravity_in_body[2]) > 0.0
    params = (
        gtsam.PreintegrationCombinedParams.MakeSharedU(GRAVITY)
        if measured_force_is_positive_z
        else gtsam.PreintegrationCombinedParams.MakeSharedD(GRAVITY)
    )
    params.setAccelerometerCovariance(np.eye(3) * noise.accelerometer_density**2)
    params.setGyroscopeCovariance(np.eye(3) * noise.gyroscope_density**2)
    params.setBiasAccCovariance(np.eye(3) * noise.accelerometer_random_walk**2)
    params.setBiasOmegaCovariance(np.eye(3) * noise.gyroscope_random_walk**2)
    # discretisation error only, kept small next to the sensor noise above
    params.setIntegrationCovariance(np.eye(3) * 1e-8)
    params.setBiasAccOmegaInit(np.eye(6) * 1e-5)
    return params


def preintegrate(gtsam: Any, params: Any, bias: Any, window: ImuWindow) -> Any:
    """Fold one window of samples into a single relative motion constraint."""
    summary = gtsam.PreintegratedCombinedMeasurements(params, bias)
    for acceleration, angular_velocity, interval in zip(
        window.accelerations, window.angular_velocities, window.intervals, strict=True
    ):
        if interval <= 0:
            continue
        summary.integrateMeasurement(acceleration, angular_velocity, float(interval))
    return summary


def direction_error(gtsam: Any, measured_direction: Array) -> Any:
    """A factor on the direction of travel between two poses, never on its length.

    The measurement is a direction in the **body frame** of the earlier keyframe, because that
    is what the camera observed, while the poses it constrains live in the world frame. The
    residual therefore rotates the measurement forward by that pose's own orientation before
    comparing. Skipping that rotation is not a small error and it hides well: with every pose
    seeded upright the two frames coincide, so a synthetic test with no rotation passes and
    the first real sequence with a turning camera diverges instead.

    Jacobians are numeric: they are evaluated once per factor per iteration over a 3x6 block,
    which does not show up next to preintegration, and an analytic derivative of a normalised
    difference is a good place to put a sign error that only manifests as slow convergence.
    """
    unit = np.asarray(measured_direction, dtype=np.float64)
    unit = unit / max(float(np.linalg.norm(unit)), 1e-12)

    def residual_for(values: Any, key_a: int, key_b: int) -> Array:
        earlier = values.atPose3(key_a)
        delta = values.atPose3(key_b).translation() - earlier.translation()
        length = float(np.linalg.norm(delta))
        if length < 1e-9:
            # coincident poses have no direction to constrain, and dividing here would put a
            # nan into the graph that never recovers
            return np.zeros(3, dtype=np.float64)
        expected = np.asarray(earlier.rotation().matrix(), dtype=np.float64) @ unit
        return np.asarray(delta / length - expected, dtype=np.float64)

    def error(factor: Any, values: Any, jacobians: Any) -> Array:
        key_a, key_b = factor.keys()[0], factor.keys()[1]
        residual = residual_for(values, key_a, key_b)

        if jacobians is not None and len(jacobians) > 0:
            step = 1e-6
            for slot, key in enumerate((key_a, key_b)):
                block = np.zeros((3, 6), dtype=np.float64)
                base = values.atPose3(key)
                for axis in range(6):
                    delta = np.zeros(6)
                    delta[axis] = step
                    bumped = gtsam.Values(values)
                    bumped.update(key, base.retract(delta))
                    block[:, axis] = (residual_for(bumped, key_a, key_b) - residual) / step
                jacobians[slot] = block

        return residual

    return error


@dataclass(frozen=True, slots=True)
class FusedState:
    """One keyframe after fusion."""

    frame_index: int
    timestamp_ns: int
    pose: Transform
    velocity: Array


@dataclass(frozen=True, slots=True)
class KeyframeMotion:
    """What the visual front end recovered between two keyframes."""

    frame_index: int
    timestamp_ns: int
    #: camera motion from the previous keyframe, translation being a unit direction only
    motion: Transform


@dataclass
class FusionResult:
    states: list[FusedState]
    initialisation: Initialisation
    optimiser_iterations: int = 0

    @property
    def path_length(self) -> float:
        if len(self.states) < 2:
            return 0.0
        positions = np.array([state.pose.translation for state in self.states])
        return float(np.linalg.norm(np.diff(positions, axis=0), axis=1).sum())


@dataclass(frozen=True, slots=True)
class _WindowAnchor:
    """The state a window inherits from the one before it."""

    pose: Any
    velocity: Array
    bias: Any


@dataclass(frozen=True, slots=True)
class _SolvedState:
    """One keyframe as the window solver leaves it, still carrying its gtsam objects."""

    frame_index: int
    timestamp_ns: int
    gtsam_pose: Any
    velocity: Array
    bias: Any

    def as_fused(self) -> FusedState:
        return FusedState(
            frame_index=self.frame_index,
            timestamp_ns=self.timestamp_ns,
            pose=Transform(
                np.asarray(self.gtsam_pose.rotation().matrix(), dtype=np.float64),
                np.asarray(self.gtsam_pose.translation(), dtype=np.float64),
            ),
            velocity=self.velocity,
        )


def _solve_window(
    gtsam: Any,
    params: Any,
    keyframes: list[KeyframeMotion],
    directions: dict[int, Array],
    stream: ImuStream,
    anchor: _WindowAnchor,
    step: float,
) -> tuple[list[_SolvedState], int]:
    """Solve one window of keyframes, starting from the state the previous window ended in."""
    pose_key, velocity_key, bias_key = (
        gtsam.symbol_shorthand.X,
        gtsam.symbol_shorthand.V,
        gtsam.symbol_shorthand.B,
    )

    graph = gtsam.NonlinearFactorGraph()
    values = gtsam.Values()

    # The first state of the window is anchored on what the previous one solved. For the very
    # first window that is the gauge freedom every VI graph has, which has to be pinned or the
    # optimiser wanders it instead of converging. For later windows it is the seam, and it is
    # pinned tightly on pose and loosely on velocity and bias so the new measurements can still
    # correct them.
    graph.add(
        gtsam.PriorFactorPose3(
            pose_key(0), anchor.pose, gtsam.noiseModel.Isotropic.Sigma(6, 1e-4)
        )
    )
    graph.add(
        gtsam.PriorFactorVector(
            velocity_key(0), anchor.velocity, gtsam.noiseModel.Isotropic.Sigma(3, 0.5)
        )
    )
    graph.add(
        gtsam.PriorFactorConstantBias(
            bias_key(0), anchor.bias, gtsam.noiseModel.Isotropic.Sigma(6, 0.1)
        )
    )

    direction_noise = gtsam.noiseModel.Robust.Create(
        gtsam.noiseModel.mEstimator.Huber.Create(0.1),
        gtsam.noiseModel.Isotropic.Sigma(3, 0.05),
    )

    values.insert(pose_key(0), anchor.pose)
    values.insert(velocity_key(0), anchor.velocity)
    values.insert(bias_key(0), anchor.bias)

    position = np.asarray(anchor.pose.translation(), dtype=np.float64)
    # Orientation is carried forward by integrating the gyro, not left at identity. Seeding
    # every pose upright works only for the first window, whose anchor happens to be the
    # identity; from the second window on it hands the optimiser a set of poses rotated away
    # from where the device was actually pointing, and the IMU factors cannot reconcile that.
    # On room1 that was the difference between converging in 20 iterations and running out of
    # iterations with a path five times too long.
    attitude = anchor.pose.rotation()

    for index in range(1, len(keyframes)):
        previous, current = keyframes[index - 1], keyframes[index]
        summary = preintegrate(
            gtsam, params, anchor.bias, stream.between(previous.timestamp_ns, current.timestamp_ns)
        )

        graph.add(
            gtsam.CombinedImuFactor(
                pose_key(index - 1),
                velocity_key(index - 1),
                pose_key(index),
                velocity_key(index),
                bias_key(index - 1),
                bias_key(index),
                summary,
            )
        )

        direction = directions.get(index)
        if direction is not None:
            graph.add(
                gtsam.CustomFactor(
                    direction_noise,
                    [pose_key(index - 1), pose_key(index)],
                    direction_error(gtsam, direction),
                )
            )
            # the measurement is a direction in the body frame at this keyframe, so it is
            # rotated into the world frame the positions accumulate in before it is stepped
            # along. Adding it unrotated builds a seed that ignores where the device was
            # pointing, which is the same error as seeding the attitude at identity.
            elapsed = (current.timestamp_ns - previous.timestamp_ns) / 1e9
            position = position + attitude.matrix() @ direction * step * elapsed

        attitude = attitude.compose(summary.deltaRij())
        values.insert(pose_key(index), gtsam.Pose3(attitude, gtsam.Point3(*position)))
        values.insert(velocity_key(index), anchor.velocity)
        values.insert(bias_key(index), anchor.bias)

    optimiser = gtsam.LevenbergMarquardtOptimizer(graph, values)
    solved = optimiser.optimize()

    states = []
    for index, keyframe in enumerate(keyframes):
        velocity = np.asarray(solved.atVector(velocity_key(index)), dtype=np.float64)
        if not np.all(np.isfinite(velocity)) or float(np.linalg.norm(velocity)) > (
            MAX_PLAUSIBLE_SPEED
        ):
            raise FusionFailed(
                "the optimiser diverged: it solved a keyframe velocity of "
                f"{float(np.linalg.norm(velocity)):.0f} m/s, which is not a real motion"
            )
        states.append(
            _SolvedState(
                frame_index=keyframe.frame_index,
                timestamp_ns=keyframe.timestamp_ns,
                gtsam_pose=solved.atPose3(pose_key(index)),
                velocity=velocity,
                bias=solved.atConstantBias(bias_key(index)),
            )
        )

    return states, int(optimiser.iterations())


def fuse(
    keyframes: list[KeyframeMotion],
    stream: ImuStream,
    noise: ImuNoise,
    body_to_camera: Array | None,
) -> FusionResult:
    """Solve a metric trajectory from visual directions and IMU measurements.

    Poses come back in the **body frame**, because that is the frame the IMU measures in and
    the frame ground truth is recorded in. The visual motions arrive in the camera frame and
    are rotated across by the calibration extrinsic before they enter the graph, so no part of
    the pipeline has to remember to do it afterwards.
    """
    gtsam = load_gtsam()

    if len(keyframes) < 2:
        raise FusionFailed(
            f"fusion needs at least 2 keyframes and the visual front end solved {len(keyframes)}"
        )

    first, last = keyframes[0].timestamp_ns, keyframes[-1].timestamp_ns
    if not stream.covers(first, last):
        raise FusionFailed(
            "the imu stream does not span the frames that were estimated, so the motion "
            "between them cannot be integrated"
        )

    initial = initialise(stream)
    params = _preintegration_params(gtsam, noise, initial)

    rotation = np.eye(3) if body_to_camera is None else np.asarray(body_to_camera)[:3, :3].T

    # every visual direction, rotated into the body frame once, so the velocity solve and the
    # factors below cannot disagree about which frame they are in
    directions: dict[int, Array] = {}
    for index in range(1, len(keyframes)):
        in_body = rotation @ keyframes[index].motion.translation
        length = float(np.linalg.norm(in_body))
        if length > 1e-9:
            directions[index] = np.asarray(in_body / length, dtype=np.float64)

    zero_bias = gtsam.imuBias.ConstantBias(np.zeros(3), np.zeros(3))
    starting_velocity = _initial_velocity(gtsam, params, zero_bias, stream, keyframes, directions)
    step = _metric_step(gtsam, params, zero_bias, stream, keyframes, starting_velocity)

    # Solved in overlapping windows rather than as one graph over the whole run. A single
    # batch is both faster and more accurate up to a few hundred keyframes, but it stops
    # converging beyond that: over 751 keyframes it ran out of iterations and returned a path
    # 333 m long against a real 141 m, while the same code over 214 keyframes landed within
    # 4% of truth. Each window here is small enough to converge, and the overlap carries the
    # solved pose, velocity and bias into the next one so the seams stay continuous.
    states: list[_SolvedState] = []
    iterations = 0
    anchor = _WindowAnchor(
        pose=gtsam.Pose3(),
        velocity=starting_velocity,
        bias=zero_bias,
    )

    start = 0
    while start < len(keyframes) - 1:
        end = min(start + WINDOW_KEYFRAMES, len(keyframes))
        solved, used = _solve_window(
            gtsam=gtsam,
            params=params,
            keyframes=keyframes[start:end],
            directions={i - start: d for i, d in directions.items() if start <= i < end},
            stream=stream,
            anchor=anchor,
            step=step,
        )
        iterations += used

        if end >= len(keyframes):
            states.extend(solved)
            break

        # Hand over from an interior state rather than the last one. The final keyframe in a
        # window has an IMU factor arriving at it and none leaving, so it is the least
        # constrained state in the graph and it absorbs whatever error the window could not
        # explain: on room1 it solved 3.8 m/s where the truth was 1.1. Anchoring the next
        # window on that carries the error forward and the run diverges a window or two later.
        # The overlap exists so there is a well constrained state to hand over instead.
        handover = len(solved) - 1 - WINDOW_OVERLAP
        states.extend(solved[:handover])
        anchor = _WindowAnchor(
            pose=solved[handover].gtsam_pose,
            velocity=solved[handover].velocity,
            bias=solved[handover].bias,
        )
        # Seed the next window from the speed this one actually solved rather than from the
        # opening guess. `_metric_step` reads several times high while the bias is unsolved,
        # and reusing that number for every window lets the same overshoot compound down the
        # run until a window diverges outright.
        step = _solved_speed(solved, fallback=step)
        start += handover

    return FusionResult(
        states=[state.as_fused() for state in states],
        initialisation=initial,
        optimiser_iterations=iterations,
    )


def _metric_step(
    gtsam: Any,
    params: Any,
    bias: Any,
    stream: ImuStream,
    keyframes: list[KeyframeMotion],
    starting_velocity: Array,
    segments: int = SPEED_SEGMENTS,
) -> float:
    """A typical speed in metres per second, for seeding the trajectory at roughly the right size.

    Taken as the median over short independent segments rather than from one long integration.
    Bias error grows with the square of the time integrated over, so a single pass across a
    whole run is dominated by it, while a segment of a second or two is not. The median then
    discards the segments where the device turned sharply and the rotation error was worst.

    Even so this reads high, because an unsolved accelerometer bias inflates every segment in
    the same direction: on room1 it returns about 4 m/s where the truth is 0.8. That is
    tolerable and it is why the result is only ever used to *seed* the optimiser, never to
    scale the output. The magnitude is what matters, not the value.
    """
    if len(keyframes) < 3:
        return float(np.linalg.norm(starting_velocity))

    span = keyframes[-1].timestamp_ns - keyframes[0].timestamp_ns
    if span <= 0:
        return float(np.linalg.norm(starting_velocity))

    length = max(span // max(segments, 1), SPEED_SEGMENT_MIN_NS)
    speeds = []
    for index in range(1, len(keyframes)):
        start = keyframes[index - 1].timestamp_ns
        end = start + length
        if end > keyframes[-1].timestamp_ns or not stream.covers(start, end):
            break
        summary = preintegrate(gtsam, params, bias, stream.between(start, end))
        travelled = float(np.linalg.norm(summary.predict(gtsam.NavState(), bias).position()))
        speeds.append(travelled / (length / 1e9))

    if not speeds:
        return float(np.linalg.norm(starting_velocity))
    return float(np.clip(np.median(speeds), 0.01, MAX_PLAUSIBLE_SPEED))


def _solved_speed(states: list["_SolvedState"], fallback: float) -> float:
    """The median speed a solved window settled on, for seeding the next one."""
    speeds = [float(np.linalg.norm(state.velocity)) for state in states]
    if not speeds:
        return fallback
    median = float(np.median(speeds))
    return float(np.clip(median, 0.01, MAX_PLAUSIBLE_SPEED)) if median > 0 else fallback


def _initial_velocity(
    gtsam: Any,
    params: Any,
    bias: Any,
    stream: ImuStream,
    keyframes: list[KeyframeMotion],
    directions: dict[int, Array],
) -> Array:
    """Solve for how fast the device was already moving at the first keyframe.

    A run does not have to begin at rest, and here it usually does not: any run using
    `start_frame` opens partway through a recording, with the device already travelling. This
    is not a detail. Seeding the graph at zero velocity when the truth is 2.2 m/s leaves the
    optimiser at 1.87 m rmse on the synthetic path, against 0.007 m when the starting velocity
    is right, because the preintegration factors are consistent with a whole family of
    trajectories and the starting velocity is what picks one out of it.
    """
    usable = min(len(keyframes) - 1, INITIAL_VELOCITY_KEYFRAMES)
    if usable < 2:
        return np.zeros(3)

    start = keyframes[0].timestamp_ns

    # Where the IMU alone, starting from rest, says the device would have gone by each
    # keyframe. The real position is that plus whatever the starting velocity carried it,
    # which is linear in the unknown: p_j = v0 * t_j + rest_j.
    from_rest = [np.zeros(3)]
    # attitude at each keyframe relative to the first, so a body frame measurement can be
    # rotated into the frame `from_rest` is accumulating in
    attitudes = [np.eye(3)]
    for index in range(1, usable + 1):
        summary = preintegrate(
            gtsam, params, bias, stream.between(start, keyframes[index].timestamp_ns)
        )
        from_rest.append(
            np.asarray(summary.predict(gtsam.NavState(), bias).position(), dtype=np.float64)
        )
        attitudes.append(np.asarray(summary.deltaRij().matrix(), dtype=np.float64))

    # Each visual measurement says which way the device moved between two keyframes, and a
    # direction is the statement that the cross product with the real step vanishes. That is
    # linear in v0, so the whole opening stretch solves in one least squares rather than being
    # left to the optimiser, which cannot recover from a bad starting velocity.
    rows, targets = [], []
    for index in range(1, usable + 1):
        measured = directions.get(index)
        if measured is None:
            continue
        # the measurement is in the body frame of the earlier keyframe; the cross product
        # below only means anything once both sides are in the same frame
        direction = attitudes[index - 1] @ measured
        elapsed = (keyframes[index].timestamp_ns - keyframes[index - 1].timestamp_ns) / 1e9
        skew = np.array(
            [
                [0.0, -direction[2], direction[1]],
                [direction[2], 0.0, -direction[0]],
                [-direction[1], direction[0], 0.0],
            ]
        )
        rows.append(skew * elapsed)
        targets.append(-skew @ (from_rest[index] - from_rest[index - 1]))

    if len(rows) < 2:
        return np.zeros(3)

    solution, *_ = np.linalg.lstsq(np.vstack(rows), np.concatenate(targets), rcond=None)
    velocity = np.asarray(solution, dtype=np.float64)
    if not np.all(np.isfinite(velocity)) or float(np.linalg.norm(velocity)) > (MAX_PLAUSIBLE_SPEED):
        return np.zeros(3)
    return velocity


__all__ = [
    "GRAVITY",
    "FusedState",
    "FusionFailed",
    "FusionResult",
    "FusionUnavailable",
    "ImuNoise",
    "Initialisation",
    "KeyframeMotion",
    "fuse",
    "fusion_available",
    "initialise",
    "load_gtsam",
    "preintegrate",
]
