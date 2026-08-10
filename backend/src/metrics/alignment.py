"""Umeyama alignment of an estimate onto ground truth.

An estimated trajectory starts wherever the estimator decided the origin was, which is not
where the truth starts. Comparing them without aligning first measures that arbitrary choice.
Umeyama finds the rigid transform, and optionally the scale, that minimises squared distance
between the two point sets in closed form.

Whether scale is solved for is the decision that matters most in this file, and it is not a
tuning knob:

- A monocular estimate has no absolute scale at all. Translation comes out of an essential
  matrix, which fixes direction and leaves length undetermined, so it must be Sim(3) aligned.
  Scoring it with SE(3) measures the arbitrary unit baseline, not the trajectory.
- A visual-inertial estimate observes scale through gravity, so scale is a real output of the
  estimator and must be SE(3) aligned. Using Sim(3) rescales the estimate to whatever fits
  truth best and **hides scale drift completely**, which is exactly the failure this project
  exists to surface. The ATE comes out looking good.

Neither mistake throws, so the mode is stored on the row and shown next to every number.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]

AlignmentMode = Literal["se3", "sim3"]


class AlignmentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Alignment:
    rotation: Array
    translation: Array
    scale: float
    mode: AlignmentMode

    def apply_positions(self, positions: Array) -> Array:
        """Map estimated positions into the truth frame.

        Scale multiplies the position before the rotation and offset, matching how the
        transform was solved. Applying it after would rescale the offset too.
        """
        points = np.asarray(positions, dtype=np.float64)
        return np.asarray((self.rotation @ (self.scale * points).T).T + self.translation)

    def apply_rotations(self, rotations: Array) -> Array:
        """Map estimated orientations into the truth frame.

        Scale does not appear here. Sim(3) scales lengths, and a rotation has none, so
        folding the scale into the rotation would leave a matrix that is no longer
        orthonormal and every rotation error computed from it would be wrong.
        """
        return np.asarray(self.rotation @ np.asarray(rotations, dtype=np.float64))


def umeyama(estimate: Array, truth: Array, with_scale: bool) -> Alignment:
    """Solve for the transform carrying `estimate` onto `truth`.

    Both are (n, 3) position arrays already paired by timestamp. Follows Umeyama 1991: the
    rotation comes from an SVD of the cross covariance, with a reflection guard so a
    degenerate fit cannot return a mirror instead of a rotation, and the scale is the ratio
    of the correlation to the variance of the **estimate**.

    That the variance is the estimate's, not the truth's, is what makes the returned scale
    the factor to multiply the estimate by. Swapping the two arrays returns its reciprocal,
    which is a plausible looking number and the wrong one.
    """
    x = np.asarray(estimate, dtype=np.float64)
    y = np.asarray(truth, dtype=np.float64)
    if x.shape != y.shape:
        raise AlignmentError("estimate and truth must have the same shape")
    if x.ndim != 2 or x.shape[1] != 3:
        raise AlignmentError(f"positions must be (n, 3), got {x.shape}")
    if x.shape[0] < 3:
        raise AlignmentError("need at least 3 matched poses to align")

    n = x.shape[0]
    mean_x = x.mean(axis=0)
    mean_y = y.mean(axis=0)
    centred_x = x - mean_x
    centred_y = y - mean_y

    variance_x = float(np.sum(centred_x**2) / n)
    covariance = (centred_y.T @ centred_x) / n

    u, singular_values, vt = np.linalg.svd(covariance)

    # a reflection has determinant -1 and fits a mirrored trajectory just as well in the
    # least squares sense, so the last singular direction is flipped when that happens
    correction = np.eye(3)
    if np.linalg.det(u) * np.linalg.det(vt) < 0.0:
        correction[2, 2] = -1.0

    rotation = u @ correction @ vt

    if with_scale:
        if variance_x <= 0.0:
            raise AlignmentError("cannot solve for scale on a stationary estimate")
        scale = float(np.trace(np.diag(singular_values) @ correction) / variance_x)
    else:
        scale = 1.0

    translation = mean_y - scale * (rotation @ mean_x)
    mode: AlignmentMode = "sim3" if with_scale else "se3"
    return Alignment(rotation, translation, scale, mode)


def align_for_mode(estimate: Array, truth: Array, mode: AlignmentMode) -> Alignment:
    return umeyama(estimate, truth, with_scale=mode == "sim3")
