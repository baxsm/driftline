"""Pose recovery from an essential matrix, over the scene depths real sequences have.

The regression these guard is documented in `motion.py`: OpenCV's `recoverPose` discards
points past a fixed distance from the camera and returns a count that has nothing to do with
how many correspondences actually support the pose. Room geometry sits in that range, so a
correct pose was being thrown away and the run ended.
"""

import numpy as np
import pytest

from estimator.motion import MIN_CORRESPONDENCES, MotionUnrecoverable, estimate_motion

from .synthetic import distant_scene_correspondences

# A camera translating a few centimetres between keyframes sees a room metres away, which is
# 30 to 300 unit baselines. The last two are where OpenCV's counter collapses.
SCENE_DEPTHS = (10.0, 30.0, 60.0, 120.0, 300.0, 800.0)


@pytest.mark.parametrize("depth", SCENE_DEPTHS)
def test_recovers_translation_direction_at_every_scene_depth(depth: float):
    """The camera slides along +x, and must be found doing so however far the scene is.

    The RANSAC threshold is scaled with the depth rather than held at the 1 px default. At
    120 baselines these points only move 3.3 px between views, so a 1 px threshold is a third
    of the whole signal and admits essential matrices that fit the noise floor: the direction
    comes back 18 degrees off. That is `findEssentialMat` reaching its limit, not the
    decomposition, and OpenCV's own `recoverPose` returns the same wrong direction from the
    same matrix. The point of the parameters here is the scoring, so the threshold is kept
    below the disparity to isolate it.
    """
    source, target, matrix = distant_scene_correspondences(depth)
    threshold = min(1.0, 40.0 / depth)

    estimate = estimate_motion(source, target, matrix, threshold)

    direction = estimate.motion.translation / np.linalg.norm(estimate.motion.translation)
    assert direction[0] > 0.99
    assert abs(float(np.trace(estimate.motion.rotation) - 3.0)) < 1e-3


@pytest.mark.parametrize("depth", SCENE_DEPTHS)
def test_inlier_count_survives_a_distant_scene(depth: float):
    """A noiseless cloud must not be counted as a handful of points.

    This is the assertion that fails against `cv2.recoverPose`: at depth 60 it scores a
    perfect 400 point cloud as zero, and the pipeline reads that as lost tracking.
    """
    source, target, matrix = distant_scene_correspondences(depth, count=400)

    estimate = estimate_motion(source, target, matrix, 1.0)

    assert estimate.inlier_count > 300


def test_rejects_a_scene_with_no_consistent_motion():
    """Correspondences that fit no single essential matrix must raise, not invent a pose."""
    rng = np.random.default_rng(4)
    source, _, matrix = distant_scene_correspondences(30.0, count=200)
    scrambled = rng.uniform(0, 480, source.shape)

    with pytest.raises(MotionUnrecoverable) as raised:
        estimate_motion(source, scrambled, matrix, 1.0)

    assert str(raised.value.reason)


def test_too_few_correspondences_names_the_shortfall():
    source, target, matrix = distant_scene_correspondences(30.0, count=MIN_CORRESPONDENCES - 1)

    with pytest.raises(MotionUnrecoverable) as raised:
        estimate_motion(source, target, matrix, 1.0)

    assert str(MIN_CORRESPONDENCES) in raised.value.reason
