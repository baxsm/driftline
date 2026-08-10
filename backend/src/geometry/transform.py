"""Rigid transforms on SE(3).

A transform here is a (rotation, translation) pair meaning "the pose of some frame expressed
in another frame". `compose(a, b)` applies b in a's frame, so if a is the pose of the camera
at frame 1 in world and b is the motion from frame 1 to frame 2, the result is the pose of
the camera at frame 2 in world.

The direction matters more than usual in this project. OpenCV's `recoverPose` returns the
rotation and translation that carry a point from the first camera's frame into the second
camera's frame, which is the inverse of how the camera itself moved. Feeding that straight
into a trajectory silently produces a path that runs backwards, and it still looks like a
plausible trajectory. `motion_from_relative_pose` does that inversion in one place so the
convention is stated once and tested, rather than being rediscovered at each call site.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation, Slerp

from .quaternion import canonical, from_matrix, to_matrix

Array = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Transform:
    rotation: Array
    translation: Array

    @staticmethod
    def identity() -> "Transform":
        return Transform(np.eye(3), np.zeros(3))

    @staticmethod
    def from_quaternion(quaternion: Array, translation: Array) -> "Transform":
        return Transform(to_matrix(quaternion), np.asarray(translation, dtype=np.float64))

    def quaternion(self) -> Array:
        return canonical(from_matrix(self.rotation))

    def matrix(self) -> Array:
        m = np.eye(4)
        m[:3, :3] = self.rotation
        m[:3, 3] = self.translation
        return m


def compose(outer: Transform, inner: Transform) -> Transform:
    return Transform(
        outer.rotation @ inner.rotation,
        outer.rotation @ inner.translation + outer.translation,
    )


def invert(transform: Transform) -> Transform:
    inverse_rotation = transform.rotation.T
    return Transform(inverse_rotation, -inverse_rotation @ transform.translation)


def interpolate(start: Transform, end: Transform, fraction: float) -> Transform:
    """A pose a fraction of the way from start to end.

    Rotation is slerped rather than interpolated component wise, because averaging two
    rotation matrices does not produce a rotation matrix. Used to fill in the frames between
    two keyframes: monocular geometry only solves at keyframes, and holding the previous pose
    across the gap would report the camera as stationary and then jumping.
    """
    ratio = float(np.clip(fraction, 0.0, 1.0))
    rotations = Rotation.from_matrix(np.stack([start.rotation, end.rotation]))
    slerped = Slerp([0.0, 1.0], rotations)([ratio])
    return Transform(
        np.asarray(slerped.as_matrix()[0], dtype=np.float64),
        start.translation + (end.translation - start.translation) * ratio,
    )


def motion_from_relative_pose(rotation: Array, translation: Array) -> Transform:
    """Turn an OpenCV relative pose into the camera's own motion.

    `recoverPose` gives the transform taking a point from camera 1's frame to camera 2's
    frame. The camera's movement between those frames is its inverse. Verified against a
    synthetic scene: a camera translating along +x makes `recoverPose` return t = -x.
    """
    return invert(
        Transform(
            np.asarray(rotation, dtype=np.float64),
            np.asarray(translation, dtype=np.float64).reshape(3),
        )
    )
