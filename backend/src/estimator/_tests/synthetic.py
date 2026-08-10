"""A synthetic sequence with a camera path and 3D points we control exactly.

This exists so estimator error can be measured without dataset error in the way. On a real
sequence a bad trajectory could come from the estimator, the calibration, or the data, and
those are not separable after the fact. Here the answer is known to machine precision.

Points are drawn as filled discs rather than single pixels because the corner detector and
KLT both work on image gradients over a window, and a one pixel dot has no gradient
structure to lock onto.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

from geometry.transform import Transform

Array = NDArray[np.float64]

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
FOCAL = 400.0


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
