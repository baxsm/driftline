"""ATE and RPE.

Two different questions, and reporting one for the other is a common way to be wrong:

- **ATE** is how far the aligned estimate sits from truth at each pose. It answers "how far
  has this drifted from where it should be", and because it is measured after a single global
  alignment, one early mistake shifts everything after it and inflates the whole curve.
- **RPE** is how wrong the *motion* is over a short segment. A trajectory that drifts far but
  moves correctly frame to frame has a large ATE and a small RPE, which is the signature of
  accumulated drift rather than bad local estimation.

Rotation error is the geodesic angle on SO(3), taken as the norm of the rotation vector of
the residual rotation. Differencing Euler angles instead is the classic mistake here: it
agrees near the identity and diverges near a gimbal singularity, so it looks correct in
exactly the tests likely to be written for it.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

Array = NDArray[np.float64]

# 20 frames at 20Hz is one second of motion, long enough for real drift to show over a
# segment and short enough that a run of a few hundred poses still yields many segments
DEFAULT_RPE_DELTA_FRAMES = 20


@dataclass(frozen=True, slots=True)
class Statistics:
    rmse: float
    mean: float
    median: float
    max: float
    min: float
    std: float


def summarize(errors: Array) -> Statistics:
    """RMSE is the headline because it penalises the large excursions that matter here.

    Mean and median sit next to it because a run with one bad stretch and a run that is
    uniformly poor can share an RMSE, and the gap between mean and median is what separates
    them.
    """
    values = np.asarray(errors, dtype=np.float64)
    if values.size == 0:
        raise ValueError("cannot summarize an empty error array")
    return Statistics(
        rmse=float(np.sqrt(np.mean(values**2))),
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        max=float(np.max(values)),
        min=float(np.min(values)),
        std=float(np.std(values)),
    )


def translation_errors(estimate_positions: Array, truth_positions: Array) -> Array:
    """Per pose distance between the aligned estimate and truth."""
    difference = np.asarray(estimate_positions, dtype=np.float64) - np.asarray(
        truth_positions, dtype=np.float64
    )
    return np.asarray(np.linalg.norm(difference, axis=1))


def rotation_errors_deg(estimate_rotations: Array, truth_rotations: Array) -> Array:
    """Per pose geodesic angle between the aligned estimate and truth, in degrees."""
    estimate = np.asarray(estimate_rotations, dtype=np.float64)
    truth = np.asarray(truth_rotations, dtype=np.float64)
    # residual carrying truth onto the estimate; its rotation angle is the error
    residual = np.transpose(truth, (0, 2, 1)) @ estimate
    return np.asarray(
        np.degrees(np.linalg.norm(Rotation.from_matrix(residual).as_rotvec(), axis=1))
    )


@dataclass(frozen=True, slots=True)
class RelativeErrors:
    translation: Array
    rotation_deg: Array
    #: index of the pose ending each segment, so a plot can place the value in time
    end_indices: NDArray[np.int64]


def _to_se3(rotations: Array, positions: Array) -> Array:
    count = positions.shape[0]
    poses = np.tile(np.eye(4), (count, 1, 1))
    poses[:, :3, :3] = rotations
    poses[:, :3, 3] = positions
    return poses


def _relative(a: Array, b: Array) -> Array:
    """The transform from `a` to `b`, as inv(a) @ b, for stacks of SE(3) matrices."""
    rotation_a = a[:, :3, :3]
    inverse_rotation = np.transpose(rotation_a, (0, 2, 1))
    relative = np.tile(np.eye(4), (a.shape[0], 1, 1))
    relative[:, :3, :3] = inverse_rotation @ b[:, :3, :3]
    relative[:, :3, 3] = np.einsum("nij,nj->ni", inverse_rotation, b[:, :3, 3] - a[:, :3, 3])
    return relative


def relative_pose_errors(
    estimate_rotations: Array,
    estimate_positions: Array,
    truth_rotations: Array,
    truth_positions: Array,
    delta_frames: int = DEFAULT_RPE_DELTA_FRAMES,
) -> RelativeErrors:
    """Compare the motion over each segment against the motion truth made over the same one.

    Segments are consecutive and do not overlap: indices step by delta and each is paired
    with the next. A sliding window would reuse most of each segment in its neighbour, and
    the resulting samples are correlated, so an RMSE over them understates the spread.
    """
    if delta_frames < 1:
        raise ValueError("delta must be at least 1 frame")

    count = estimate_positions.shape[0]
    starts = np.arange(0, count, delta_frames, dtype=np.int64)
    if starts.size < 2:
        raise ValueError("not enough poses for a single segment at this delta")
    first, second = starts[:-1], starts[1:]

    estimate = _to_se3(estimate_rotations, estimate_positions)
    truth = _to_se3(truth_rotations, truth_positions)

    estimate_motion = _relative(estimate[first], estimate[second])
    truth_motion = _relative(truth[first], truth[second])
    residual = _relative(truth_motion, estimate_motion)

    rotation_vectors = Rotation.from_matrix(residual[:, :3, :3]).as_rotvec()
    return RelativeErrors(
        translation=np.asarray(np.linalg.norm(residual[:, :3, 3], axis=1)),
        rotation_deg=np.asarray(np.degrees(np.linalg.norm(rotation_vectors, axis=1))),
        end_indices=second,
    )
