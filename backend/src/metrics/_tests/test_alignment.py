"""Alignment tests that do not need an oracle, because the answer is known exactly."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.spatial.transform import Rotation

from metrics.alignment import AlignmentError, umeyama

from .trajectories import wandering_trajectory


def test_recovers_a_known_rigid_transform() -> None:
    """The known answer test. Apply a transform, align, get the transform back."""
    truth = wandering_trajectory(seed=3, count=120).positions
    rotation = np.asarray(Rotation.from_euler("xyz", [0.4, 1.1, -0.6]).as_matrix())
    translation = np.array([3.0, -1.0, 2.5])
    moved = (rotation @ truth.T).T + translation

    alignment = umeyama(moved, truth, with_scale=False)

    # aligning the moved points back onto truth undoes what was applied
    assert alignment.rotation == pytest.approx(rotation.T, abs=1e-9)
    assert alignment.apply_positions(moved) == pytest.approx(truth, abs=1e-9)
    assert alignment.scale == pytest.approx(1.0, abs=1e-12)


def test_recovers_a_known_scale() -> None:
    truth = wandering_trajectory(seed=4, count=120).positions
    rotation = np.asarray(Rotation.from_euler("z", 0.9).as_matrix())
    scaled = (rotation @ (truth * 0.25).T).T + np.array([1.0, 2.0, 3.0])

    alignment = umeyama(scaled, truth, with_scale=True)

    # the estimate was a quarter of truth, so it has to be multiplied by four
    assert alignment.scale == pytest.approx(4.0, rel=1e-9)
    assert alignment.apply_positions(scaled) == pytest.approx(truth, abs=1e-9)


def test_se3_leaves_scale_alone() -> None:
    """Without scale correction the fit must not quietly rescale to fit better."""
    truth = wandering_trajectory(seed=6, count=100).positions
    alignment = umeyama(truth * 0.5, truth, with_scale=False)

    assert alignment.scale == 1.0
    # a half sized estimate cannot be made to match by rotation and offset alone
    assert alignment.apply_positions(truth * 0.5) != pytest.approx(truth, abs=1e-3)


def test_rejects_a_reflection() -> None:
    """A mirrored point set must come back as a rotation, not a reflection.

    Least squares is happy to return a determinant of -1, which fits the data and is not a
    rotation. Every pose built from it afterwards would be wrong.
    """
    truth = wandering_trajectory(seed=8, count=90).positions
    mirrored = truth * np.array([1.0, 1.0, -1.0])

    alignment = umeyama(mirrored, truth, with_scale=False)

    assert np.linalg.det(alignment.rotation) == pytest.approx(1.0, abs=1e-9)


def test_rejects_too_few_poses() -> None:
    with pytest.raises(AlignmentError):
        umeyama(np.zeros((2, 3)), np.zeros((2, 3)), with_scale=False)


def test_rejects_mismatched_shapes() -> None:
    with pytest.raises(AlignmentError):
        umeyama(np.zeros((5, 3)), np.zeros((4, 3)), with_scale=False)


@settings(max_examples=40, deadline=None)
@given(
    angles=st.tuples(
        st.floats(-3.0, 3.0), st.floats(-3.0, 3.0), st.floats(-3.0, 3.0)
    ),
    offset=st.tuples(
        st.floats(-50.0, 50.0), st.floats(-50.0, 50.0), st.floats(-50.0, 50.0)
    ),
)
def test_alignment_recovers_any_rigid_transform(
    angles: tuple[float, float, float], offset: tuple[float, float, float]
) -> None:
    """For any rotation and offset, aligning the moved points back returns the original."""
    truth = wandering_trajectory(seed=2, count=60).positions
    rotation = np.asarray(Rotation.from_euler("xyz", angles).as_matrix())
    moved = (rotation @ truth.T).T + np.array(offset)

    aligned = umeyama(moved, truth, with_scale=False).apply_positions(moved)

    assert aligned == pytest.approx(truth, abs=1e-6)


@settings(max_examples=30, deadline=None)
@given(scale=st.floats(0.01, 100.0))
def test_sim3_recovers_any_positive_scale(scale: float) -> None:
    """Scaling a monocular estimate by any factor is undone by Sim(3) alignment.

    This is the property that makes a monocular ATE meaningful at all: the estimator's
    arbitrary choice of scale must not change the score.
    """
    truth = wandering_trajectory(seed=9, count=80).positions
    alignment = umeyama(truth * scale, truth, with_scale=True)

    assert alignment.scale == pytest.approx(1.0 / scale, rel=1e-6)
    assert alignment.apply_positions(truth * scale) == pytest.approx(truth, abs=1e-6)
