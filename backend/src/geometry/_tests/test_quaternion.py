import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geometry.quaternion import (
    QuaternionError,
    canonical,
    from_matrix,
    geodesic_angle,
    normalize,
    to_matrix,
)

IDENTITY = np.array([1.0, 0.0, 0.0, 0.0])
HALF_TURN_Z = np.array([np.sqrt(0.5), 0.0, 0.0, np.sqrt(0.5)])

finite = st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False)


@st.composite
def unit_quaternions(draw):
    """Random unit quaternions, falling back to identity when the draw is near zero."""
    raw = np.array([draw(finite) for _ in range(4)], dtype=np.float64)
    if np.linalg.norm(raw) < 1e-6:
        return IDENTITY.copy()
    return raw / np.linalg.norm(raw)


def test_identity_maps_to_identity_matrix():
    assert np.allclose(to_matrix(IDENTITY), np.eye(3))


def test_quarter_turn_about_z():
    expected = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    assert np.allclose(to_matrix(HALF_TURN_Z), expected)


def test_geodesic_angle_of_quarter_turn_is_90_degrees():
    assert np.degrees(geodesic_angle(IDENTITY, HALF_TURN_Z)) == pytest.approx(90.0)


def test_rejects_wrong_shape():
    with pytest.raises(QuaternionError):
        normalize(np.array([1.0, 0.0, 0.0]))


def test_rejects_zero_quaternion():
    with pytest.raises(QuaternionError):
        normalize(np.zeros(4))


@given(unit_quaternions())
@settings(max_examples=200, deadline=None)
def test_matrix_round_trip(q):
    assert np.allclose(canonical(q), from_matrix(to_matrix(q)), atol=1e-9)


@given(unit_quaternions())
@settings(max_examples=200, deadline=None)
def test_sign_flip_is_the_same_rotation(q):
    # q and -q are the same rotation, and this sign ambiguity is a standing source of
    # silent error, so it is asserted rather than assumed
    assert np.allclose(to_matrix(q), to_matrix(-q), atol=1e-12)


@given(unit_quaternions())
@settings(max_examples=200, deadline=None)
def test_produces_valid_rotation_matrix(q):
    m = to_matrix(q)
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-9)
    assert np.linalg.det(m) == pytest.approx(1.0, abs=1e-9)


@given(unit_quaternions())
@settings(max_examples=200, deadline=None)
def test_geodesic_distance_to_self_is_zero(q):
    assert geodesic_angle(q, q) == pytest.approx(0.0, abs=1e-6)


@given(unit_quaternions())
@settings(max_examples=200, deadline=None)
def test_geodesic_ignores_sign(q):
    assert geodesic_angle(q, -q) == pytest.approx(0.0, abs=1e-6)


@given(unit_quaternions())
@settings(max_examples=200, deadline=None)
def test_canonical_picks_the_same_representative_for_q_and_minus_q(q):
    # the point of canonical is that the two representations of one rotation collapse to a
    # single value that can be compared component wise
    assert np.allclose(canonical(q), canonical(-q), atol=1e-12)


@given(unit_quaternions())
@settings(max_examples=200, deadline=None)
def test_canonical_preserves_the_rotation(q):
    assert np.allclose(to_matrix(canonical(q)), to_matrix(q), atol=1e-9)


def test_canonical_uses_non_negative_scalar_in_the_ordinary_case():
    assert canonical(np.array([-np.sqrt(0.5), 0.0, 0.0, np.sqrt(0.5)]))[0] >= 0.0


def test_canonical_resolves_a_half_turn_where_the_scalar_is_zero():
    # w == 0 cannot pick a sign, so the first non-zero component decides
    assert np.allclose(canonical(np.array([0.0, 0.0, 0.0, -1.0])), np.array([0.0, 0.0, 0.0, 1.0]))
