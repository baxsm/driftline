"""Matching an estimated trajectory to ground truth in time.

The estimate and the truth are on different clocks and different rates: 20Hz against 120Hz
on TUM VI. Nothing lines up exactly, so each estimated pose is paired with the nearest truth
pose and the pair is dropped when the gap is too large.

The tolerance is the part worth getting right. Too loose and poses hundreds of milliseconds
apart are paired, and the distance the camera moved in between is reported as trajectory
error. Too tight and most poses are dropped, and an ATE computed over the survivors is a
confident number about 5% of the run. Both look like a working metric, which is why the
matched count is carried out of here and shown in the UI rather than being an internal
detail.

Truth indices are allowed to repeat. At 120Hz truth against 20Hz estimate that never
happens, but forcing a one to one matching would silently drop estimated poses when the
truth is sparser, and a dropped pose is worse than a reused one: it changes which part of
the trajectory is being scored without saying so.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]

# 20ms, half a frame interval at 20Hz. Wider than this and a pair spans more than the gap
# between consecutive estimated poses, which stops being an association at all.
DEFAULT_TOLERANCE_NS = 20_000_000


@dataclass(frozen=True, slots=True)
class Association:
    """Indices into the estimate and truth arrays, paired elementwise."""

    estimate_indices: NDArray[np.int64]
    truth_indices: NDArray[np.int64]
    #: estimated poses offered for matching, so the UI can say "N of M matched"
    candidate_count: int

    @property
    def matched_count(self) -> int:
        return len(self.estimate_indices)


def associate(
    estimate_timestamps_ns: NDArray[np.int64],
    truth_timestamps_ns: NDArray[np.int64],
    tolerance_ns: int = DEFAULT_TOLERANCE_NS,
) -> Association:
    """Pair each estimated pose with the nearest truth pose within the tolerance.

    Timestamps stay integers here. A nanosecond value is 19 digits, which is past what a
    float64 holds exactly, and this whole function is differences between such values.
    """
    estimate = np.asarray(estimate_timestamps_ns, dtype=np.int64)
    truth = np.asarray(truth_timestamps_ns, dtype=np.int64)

    if estimate.size == 0 or truth.size == 0:
        empty = np.zeros(0, dtype=np.int64)
        return Association(empty, empty, int(estimate.size))

    order = np.argsort(truth, kind="stable")
    sorted_truth = truth[order]

    # searchsorted finds the insertion point, so the nearest truth pose is on one side or the
    # other of it; both are checked rather than assuming the left one
    right = np.searchsorted(sorted_truth, estimate)
    left = np.clip(right - 1, 0, sorted_truth.size - 1)
    right = np.clip(right, 0, sorted_truth.size - 1)

    left_gap = np.abs(estimate - sorted_truth[left])
    right_gap = np.abs(estimate - sorted_truth[right])
    nearest = np.where(left_gap <= right_gap, left, right)
    gap = np.minimum(left_gap, right_gap)

    within = gap <= tolerance_ns
    estimate_indices = np.nonzero(within)[0].astype(np.int64)
    truth_indices = order[nearest[within]].astype(np.int64)

    return Association(estimate_indices, truth_indices, int(estimate.size))
