"""Relative camera motion from matched points.

Monocular geometry recovers translation only up to scale: the essential matrix cannot tell a
small motion through a small room from a large motion through a large one. `recoverPose`
therefore returns a unit translation, and this module keeps it that way rather than inventing
a scale factor that would look like a real distance.

The consequence is that a mono trajectory is only correct up to a single global scale, which
is exactly why phase 3 must align it with Sim(3) rather than SE(3). Reporting ATE on a mono
run under SE(3) alignment would measure the arbitrary unit above, not the estimate.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from geometry.transform import Transform, motion_from_relative_pose

Array = NDArray[np.float64]

# below this many correspondences the five point solver is not meaningfully constrained
MIN_CORRESPONDENCES = 8

# How far a triangulated point may sit from the camera, in units of the unit baseline, and
# still count as a real observation.
#
# `recoverPose` defaults this to 50, which is far too tight here. Translation is normalized to
# one unit, so a point 8 metres away seen across a 0.05 m baseline triangulates to roughly 160
# units and gets thrown out as though it were behind the camera. On a handheld 20Hz sequence
# that is most of the frame, and the symptom is a run that fails with a low inlier count while
# the pose it computed was actually correct. The chirality check is still doing its job of
# rejecting points behind the camera; only the distance ceiling is relaxed.
CHIRALITY_DISTANCE_THRESHOLD = 1.0e5


class MotionUnrecoverable(RuntimeError):
    """Raised when the geometry cannot be solved, carrying why for the failure inspector."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MotionEstimate:
    motion: Transform
    inlier_count: int
    correspondence_count: int


def estimate_motion(
    previous_points: Array,
    current_points: Array,
    camera_matrix: Array,
    ransac_threshold_px: float,
) -> MotionEstimate:
    """Camera motion between two frames, with translation normalized to unit length."""
    if len(previous_points) < MIN_CORRESPONDENCES:
        raise MotionUnrecoverable(
            f"only {len(previous_points)} tracked features, need {MIN_CORRESPONDENCES}"
        )

    source = np.asarray(previous_points, dtype=np.float64)
    target = np.asarray(current_points, dtype=np.float64)

    essential, mask = cv2.findEssentialMat(
        source, target, camera_matrix,
        method=cv2.RANSAC, prob=0.999, threshold=ransac_threshold_px,
    )
    if essential is None or essential.shape != (3, 3):
        # a degenerate configuration (pure rotation, or every point on one plane) returns
        # either nothing or a stack of candidates, and neither can be composed into a path
        raise MotionUnrecoverable("no single essential matrix fits these correspondences")

    inliers, rotation, translation, _ = cv2.recoverPose(
        essential, source, target, camera_matrix, CHIRALITY_DISTANCE_THRESHOLD, mask=mask
    )[:4]
    if inliers < MIN_CORRESPONDENCES:
        raise MotionUnrecoverable(f"only {int(inliers)} points passed the chirality check")

    return MotionEstimate(
        motion=motion_from_relative_pose(
            np.asarray(rotation, dtype=np.float64),
            np.asarray(translation, dtype=np.float64),
        ),
        inlier_count=int(inliers),
        correspondence_count=len(source),
    )
