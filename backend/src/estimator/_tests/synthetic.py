"""A synthetic sequence with a camera path and 3D points we control exactly.

This exists so estimator error can be measured without dataset error in the way. On a real
sequence a bad trajectory could come from the estimator, the calibration, or the data, and
those are not separable after the fact. Here the answer is known to machine precision.

Points are drawn as filled discs rather than single pixels because the corner detector and
KLT both work on image gradients over a window, and a one pixel dot has no gradient
structure to lock onto.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

from datasets.parsing import ImuSample
from geometry.transform import Transform

Array = NDArray[np.float64]

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
FOCAL = 400.0

GRAVITY = 9.81
IMU_RATE_HZ = 200.0


@dataclass(frozen=True, slots=True)
class SyntheticSequence:
    images: list[NDArray[np.uint8]]
    poses: list[Transform]
    camera_matrix: Array
    points: Array


def camera_matrix() -> Array:
    return np.array(
        [[FOCAL, 0.0, IMAGE_WIDTH / 2], [0.0, FOCAL, IMAGE_HEIGHT / 2], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def _render(points_world: Array, pose: Transform, matrix: Array) -> NDArray[np.uint8]:
    """Project world points into a camera at `pose` and draw them.

    A little deterministic texture goes into the background so the detector has something to
    reject, and so a frame is never uniformly flat.
    """
    image = np.full((IMAGE_HEIGHT, IMAGE_WIDTH), 40, dtype=np.uint8)
    grid = np.arange(IMAGE_WIDTH, dtype=np.uint8)
    image += (grid % 7)[None, :].astype(np.uint8)

    world_to_camera = pose.rotation.T
    offset = -world_to_camera @ pose.translation
    in_camera = (world_to_camera @ points_world.T).T + offset

    in_front = in_camera[:, 2] > 0.2
    visible = in_camera[in_front]
    if len(visible) == 0:
        return image

    projected = (matrix @ visible.T).T
    pixels = projected[:, :2] / projected[:, 2:3]

    radius = 3
    ys, xs = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    disc = (xs**2 + ys**2) <= radius**2

    for x, y in pixels:
        cx, cy = round(float(x)), round(float(y))
        if cx < radius or cy < radius:
            continue
        if cx >= IMAGE_WIDTH - radius or cy >= IMAGE_HEIGHT - radius:
            continue
        patch = image[cy - radius : cy + radius + 1, cx - radius : cx + radius + 1]
        patch[disc] = 235
    return image


def straight_line_sequence(frames: int = 24, step: float = 0.25) -> SyntheticSequence:
    """Camera sliding along +x with a fixed orientation, looking down +z.

    The step is large relative to the scene depth on purpose. Triangulation needs parallax,
    and a baseline that is tiny against the depth makes the depth ill conditioned, which
    shows up as points landing far behind the scene rather than as an obviously wrong pose.

    The point cloud spans the whole path rather than a fixed box, so a long sequence does not
    simply drive out the far side of the scene and lose every feature.
    """
    rng = np.random.default_rng(7)
    travel = frames * step
    count = 700 + frames * 12
    points = np.column_stack(
        [
            rng.uniform(-4.0, travel + 6.0, count),
            rng.uniform(-3.0, 3.0, count),
            rng.uniform(2.0, 8.0, count),
        ]
    )
    poses = [Transform(np.eye(3), np.array([i * step, 0.0, 0.0])) for i in range(frames)]
    matrix = camera_matrix()
    images = [_render(points, pose, matrix) for pose in poses]
    return SyntheticSequence(images=images, poses=poses, camera_matrix=matrix, points=points)


@dataclass(frozen=True, slots=True)
class InertialSequence:
    """A camera path with the IMU stream a real device would have recorded along it."""

    images: list[NDArray[np.uint8]]
    poses: list[Transform]
    camera_matrix: Array
    frame_timestamps_ns: list[int]
    imu: list[ImuSample]
    #: metres actually travelled, so a test can assert that fusion recovered the scale
    path_length: float


def _accelerating_path(
    amplitude: float, frequency: float
) -> tuple[Callable[[float], Array], Callable[[float], Array]]:
    """Position and acceleration for a smooth path that changes speed as well as direction.

    Two properties matter, and both are easy to lose by picking a prettier curve:

    Speed has to vary. A path travelled at constant speed is one a scale-free visual estimate
    reconstructs perfectly by composing equal unit steps, so comparing fusion against it
    measures nothing. The surge term below makes the distance covered between frames vary by
    several times over the path.

    Acceleration has to have a component along gravity. A purely horizontal acceleration
    barely changes the *magnitude* of the specific force, since it is perpendicular to a 9.81
    vector, which leaves gravity and accelerometer bias poorly separated.
    """
    surge = 0.55

    def phase(t: float) -> float:
        return frequency * t + surge * np.sin(frequency * t)

    def phase_rate(t: float) -> float:
        return frequency * (1.0 + surge * np.cos(frequency * t))

    def phase_acceleration(t: float) -> float:
        return -frequency**2 * surge * np.sin(frequency * t)

    def position(t: float) -> Array:
        angle = phase(t)
        return np.array(
            [
                amplitude * np.sin(angle),
                amplitude * (1.0 - np.cos(angle)),
                0.4 * np.sin(0.7 * angle),
            ]
        )

    def acceleration(t: float) -> Array:
        angle = phase(t)
        rate = phase_rate(t)
        rate_change = phase_acceleration(t)
        return np.array(
            [
                amplitude * (-np.sin(angle) * rate**2 + np.cos(angle) * rate_change),
                amplitude * (np.cos(angle) * rate**2 + np.sin(angle) * rate_change),
                0.4
                * 0.7
                * (-0.7 * np.sin(0.7 * angle) * rate**2 + np.cos(0.7 * angle) * rate_change),
            ]
        )

    return position, acceleration


def inertial_sequence(
    frames: int = 40,
    frame_rate_hz: float = 20.0,
    amplitude: float = 1.6,
    frequency: float = 0.9,
    start_timestamp_ns: int = 1_000_000_000_000_000_000,
    yaw_per_second: float = 0.0,
) -> InertialSequence:
    """A rendered camera path plus the IMU samples consistent with it.

    The accelerometer reports specific force, which is the path's own acceleration plus the
    reaction to gravity, expressed in the body frame. Getting that sum wrong is the classic
    silent fusion bug: the trajectory still comes out finite and smooth, just curved away from
    the truth, which is why this is derived from the path analytically rather than by
    differencing the rendered poses.

    Body and camera frames are deliberately identical here. The extrinsic is exercised
    separately by the tests that push a trajectory through a known 179 degree rotation.

    `yaw_per_second` turns the device as it travels, and it matters more than it looks. With
    the body held at identity the body and world frames coincide, so a fusion bug that mixes
    the two is invisible: three separate frame errors passed every test on this sequence and
    only appeared on the first real sequence with a turning camera. Any test that means to
    exercise frame handling has to set this.
    """
    position_at, acceleration_at = _accelerating_path(amplitude, frequency)

    def attitude_at(t: float) -> Array:
        return np.asarray(Rotation.from_euler("z", yaw_per_second * t).as_matrix())

    duration = (frames - 1) / frame_rate_hz
    rng = np.random.default_rng(23)
    count = 1400
    span = amplitude * 2.5
    points = np.column_stack(
        [
            rng.uniform(-span - 4.0, span + 4.0, count),
            rng.uniform(-span - 3.0, span + 3.0, count),
            rng.uniform(3.0, 11.0, count),
        ]
    )

    poses = [
        Transform(attitude_at(i / frame_rate_hz), position_at(i / frame_rate_hz))
        for i in range(frames)
    ]
    matrix = camera_matrix()
    images = [_render(points, pose, matrix) for pose in poses]

    frame_timestamps = [
        start_timestamp_ns + round(i / frame_rate_hz * 1e9) for i in range(frames)
    ]

    # the stream starts before the first frame and ends after the last, because
    # preintegration between two keyframes needs samples covering the whole interval
    sample_count = int(duration * IMU_RATE_HZ) + 3
    imu = []
    for index in range(sample_count):
        t = (index - 1) / IMU_RATE_HZ
        # the accelerometer is bolted to the device, so it reads the world frame specific
        # force expressed in the body frame, which is the world-to-body rotation applied
        specific_force = acceleration_at(t) + np.array([0.0, 0.0, GRAVITY])
        in_body = attitude_at(t).T @ specific_force
        imu.append(
            ImuSample(
                timestamp_ns=start_timestamp_ns + round(t * 1e9),
                wx=0.0,
                wy=0.0,
                wz=float(yaw_per_second),
                ax=float(in_body[0]),
                ay=float(in_body[1]),
                az=float(in_body[2]),
            )
        )

    positions = np.array([pose.translation for pose in poses])
    path_length = float(np.linalg.norm(np.diff(positions, axis=0), axis=1).sum())

    return InertialSequence(
        images=images,
        poses=poses,
        camera_matrix=matrix,
        frame_timestamps_ns=frame_timestamps,
        imu=imu,
        path_length=path_length,
    )


def turning_sequence(
    frames: int = 24, step: float = 0.25, yaw_per_frame: float = 0.02
) -> SyntheticSequence:
    """Camera translating while yawing, so rotation and translation are both non trivial."""
    rng = np.random.default_rng(11)
    travel = frames * step
    count = 900 + frames * 12
    points = np.column_stack(
        [
            rng.uniform(-8.0, travel + 8.0, count),
            rng.uniform(-3.0, 3.0, count),
            rng.uniform(2.0, 9.0, count),
        ]
    )
    poses = []
    for i in range(frames):
        rotation = Rotation.from_euler("y", i * yaw_per_frame).as_matrix()
        poses.append(
            Transform(
                np.asarray(rotation, dtype=np.float64),
                np.array([i * step, 0.0, 0.0]),
            )
        )
    matrix = camera_matrix()
    images = [_render(points, pose, matrix) for pose in poses]
    return SyntheticSequence(images=images, poses=poses, camera_matrix=matrix, points=points)
