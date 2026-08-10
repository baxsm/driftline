import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.spatial.transform import Rotation

from geometry.transform import (
    Transform,
    compose,
    interpolate,
    invert,
    motion_from_relative_pose,
)

finite = st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False)
angles = st.floats(min_value=-np.pi, max_value=np.pi, allow_nan=False, allow_infinity=False)


def _transform(rx: float, ry: float, rz: float, tx: float, ty: float, tz: float) -> Transform:
    rotation = Rotation.from_euler("xyz", [rx, ry, rz]).as_matrix()
    return Transform(np.asarray(rotation, dtype=np.float64), np.array([tx, ty, tz]))


transforms = st.builds(_transform, angles, angles, angles, finite, finite, finite)


def test_identity_composes_to_no_change():
    t = _transform(0.3, -0.2, 1.1, 1.0, 2.0, 3.0)
    result = compose(Transform.identity(), t)
    assert np.allclose(result.matrix(), t.matrix())


@given(transforms)
@settings(max_examples=100, deadline=None)
def test_inverse_cancels(t: Transform):
    assert np.allclose(compose(t, invert(t)).matrix(), np.eye(4), atol=1e-9)
    assert np.allclose(compose(invert(t), t).matrix(), np.eye(4), atol=1e-9)


@given(transforms, transforms, transforms)
@settings(max_examples=60, deadline=None)
def test_composition_is_associative(a: Transform, b: Transform, c: Transform):
    left = compose(compose(a, b), c)
    right = compose(a, compose(b, c))
    assert np.allclose(left.matrix(), right.matrix(), atol=1e-9)


@given(transforms)
@settings(max_examples=100, deadline=None)
def test_quaternion_round_trips_through_matrix(t: Transform):
    restored = Transform.from_quaternion(t.quaternion(), t.translation)
    assert np.allclose(restored.rotation, t.rotation, atol=1e-9)


def test_composing_a_loop_returns_to_the_origin():
    """Four quarter turns with a step between each must close the square."""
    step = _transform(0.0, 0.0, np.pi / 2, 1.0, 0.0, 0.0)
    pose = Transform.identity()
    for _ in range(4):
        pose = compose(pose, step)
    assert np.allclose(pose.translation, np.zeros(3), atol=1e-9)
    assert np.allclose(pose.rotation, np.eye(3), atol=1e-9)


def test_motion_from_relative_pose_inverts_opencv_convention():
    """A camera moving +x makes recoverPose report t = -x, and the motion must be +x.

    This is the sign error that produces a backwards trajectory that still looks plausible.
    """
    rotation = np.eye(3)
    translation = np.array([-1.0, 0.0, 0.0])
    motion = motion_from_relative_pose(rotation, translation)
    assert np.allclose(motion.translation, np.array([1.0, 0.0, 0.0]))


def test_interpolate_returns_the_endpoints() -> None:
    start = Transform.identity()
    end = Transform(
        np.asarray(Rotation.from_euler("xyz", [0.3, -0.2, 0.5]).as_matrix()),
        np.array([1.0, 2.0, -3.0]),
    )

    assert np.allclose(interpolate(start, end, 0.0).rotation, start.rotation)
    assert np.allclose(interpolate(start, end, 1.0).translation, end.translation)


def test_interpolate_halfway_is_half_the_rotation() -> None:
    """Slerp, not component wise averaging: the midpoint has to still be a rotation."""
    start = Transform.identity()
    end = Transform(
        np.asarray(Rotation.from_euler("z", 90.0, degrees=True).as_matrix()),
        np.array([2.0, 0.0, 0.0]),
    )

    middle = interpolate(start, end, 0.5)
    angle = np.degrees(np.linalg.norm(Rotation.from_matrix(middle.rotation).as_rotvec()))

    assert angle == pytest.approx(45.0, abs=1e-9)
    assert np.allclose(middle.translation, [1.0, 0.0, 0.0])
    assert np.allclose(middle.rotation @ middle.rotation.T, np.eye(3), atol=1e-12)


def test_interpolate_clamps_outside_the_segment() -> None:
    start = Transform.identity()
    end = Transform(np.eye(3), np.array([4.0, 0.0, 0.0]))

    assert np.allclose(interpolate(start, end, -1.0).translation, start.translation)
    assert np.allclose(interpolate(start, end, 2.0).translation, end.translation)
