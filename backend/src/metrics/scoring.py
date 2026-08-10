"""Scoring one estimated trajectory against ground truth.

This is the one entry point the rest of the backend uses: give it two trajectories and the
estimator mode, and it associates, aligns, and measures in the order those have to happen.

The alignment mode is derived from the estimator mode rather than passed in, because it is
not a preference. A monocular estimate has no scale and must be Sim(3) aligned; anything
that observes scale must be SE(3) aligned. Letting a caller choose invites the one
combination that silently produces a good looking number for a broken estimator.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from geometry.quaternion import to_matrix

from .alignment import Alignment, AlignmentMode, align_for_mode
from .association import Association, associate
from .errors import (
    DEFAULT_RPE_DELTA_FRAMES,
    RelativeErrors,
    Statistics,
    relative_pose_errors,
    rotation_errors_deg,
    summarize,
    translation_errors,
)

Array = NDArray[np.float64]

# below this, an ATE is a statement about a handful of poses rather than about the run, and
# reporting it with the same confidence as a full trajectory would be misleading
MIN_MATCHED_POSES = 3


class NotScorable(ValueError):
    """Raised when there is not enough overlap to say anything honest about a run."""


@dataclass(frozen=True, slots=True)
class Trajectory:
    """A trajectory as the scorer wants it: sorted by time, quaternions Hamilton ordered."""

    timestamps_ns: NDArray[np.int64]
    positions: Array
    quaternions: Array

    def __post_init__(self) -> None:
        if not (len(self.timestamps_ns) == len(self.positions) == len(self.quaternions)):
            raise ValueError("timestamps, positions and quaternions must be the same length")

    @property
    def rotations(self) -> Array:
        if len(self.quaternions) == 0:
            return np.zeros((0, 3, 3))
        return np.stack([to_matrix(q) for q in self.quaternions])

    def take(self, indices: NDArray[np.int64]) -> "Trajectory":
        return Trajectory(
            timestamps_ns=self.timestamps_ns[indices],
            positions=self.positions[indices],
            quaternions=self.quaternions[indices],
        )


@dataclass(frozen=True, slots=True)
class PoseError:
    timestamp_ns: int
    translation: float
    rotation_deg: float


@dataclass(frozen=True, slots=True)
class Score:
    ate_translation: Statistics
    ate_rotation_deg: Statistics
    rpe: RelativeErrors | None
    rpe_translation: Statistics | None
    rpe_rotation_deg: Statistics | None
    alignment: Alignment
    association: Association
    pose_errors: list[PoseError]
    rpe_delta_frames: int

    @property
    def scale_error(self) -> float | None:
        """How far the Sim(3) scale sits from 1, as a ratio, for monocular runs only.

        Meaningless for SE(3), where the scale was never solved for and is 1 by definition.
        Returning 0.0 there would read as "no scale error" rather than "not measured".
        """
        if self.alignment.mode != "sim3":
            return None
        return self.alignment.scale


def score(
    estimate: Trajectory,
    truth: Trajectory,
    mode: AlignmentMode,
    tolerance_ns: int | None = None,
    rpe_delta_frames: int = DEFAULT_RPE_DELTA_FRAMES,
) -> Score:
    """Associate, align, then measure. Raises `NotScorable` when there is too little overlap."""
    association = (
        associate(estimate.timestamps_ns, truth.timestamps_ns)
        if tolerance_ns is None
        else associate(estimate.timestamps_ns, truth.timestamps_ns, tolerance_ns)
    )
    if association.matched_count < MIN_MATCHED_POSES:
        raise NotScorable(
            f"only {association.matched_count} estimated poses matched a ground truth pose"
        )

    paired_estimate = estimate.take(association.estimate_indices)
    paired_truth = truth.take(association.truth_indices)

    alignment = align_for_mode(paired_estimate.positions, paired_truth.positions, mode)
    aligned_positions = alignment.apply_positions(paired_estimate.positions)
    aligned_rotations = alignment.apply_rotations(paired_estimate.rotations)
    truth_rotations = paired_truth.rotations

    translation = translation_errors(aligned_positions, paired_truth.positions)
    rotation = rotation_errors_deg(aligned_rotations, truth_rotations)

    # a short run cannot furnish a single segment at the requested delta, which is a reason
    # to report no RPE rather than to fail the whole score
    relative: RelativeErrors | None
    try:
        relative = relative_pose_errors(
            aligned_rotations,
            aligned_positions,
            truth_rotations,
            paired_truth.positions,
            rpe_delta_frames,
        )
    except ValueError:
        relative = None

    return Score(
        ate_translation=summarize(translation),
        ate_rotation_deg=summarize(rotation),
        rpe=relative,
        rpe_translation=summarize(relative.translation) if relative else None,
        rpe_rotation_deg=summarize(relative.rotation_deg) if relative else None,
        alignment=alignment,
        association=association,
        pose_errors=[
            PoseError(int(timestamp), float(trans), float(rot))
            for timestamp, trans, rot in zip(
                paired_estimate.timestamps_ns, translation, rotation, strict=True
            )
        ],
        rpe_delta_frames=rpe_delta_frames,
    )
