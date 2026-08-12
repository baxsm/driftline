"""Timestamp association tests."""

import numpy as np

from metrics.association import DEFAULT_TOLERANCE_NS, associate

MILLISECOND = 1_000_000


def test_picks_the_nearest_truth_pose() -> None:
    estimate = np.array([100, 200, 300], dtype=np.int64) * MILLISECOND
    truth = np.array([98, 105, 202, 260, 301], dtype=np.int64) * MILLISECOND

    result = associate(estimate, truth)

    assert result.matched_count == 3
    assert list(result.truth_indices) == [0, 2, 4]


def test_rejects_pairs_outside_the_tolerance() -> None:
    """A pose with no truth nearby is dropped rather than paired with a distant one."""
    estimate = np.array([100, 500, 900], dtype=np.int64) * MILLISECOND
    truth = np.array([101, 898], dtype=np.int64) * MILLISECOND

    result = associate(estimate, truth, tolerance_ns=20 * MILLISECOND)

    assert result.matched_count == 2
    assert list(result.estimate_indices) == [0, 2]
    assert result.candidate_count == 3


def test_counts_candidates_even_when_nothing_matches() -> None:
    """The count of poses offered is what makes "0 of 400 matched" reportable."""
    estimate = np.arange(400, dtype=np.int64) * MILLISECOND
    truth = np.array([10_000_000_000], dtype=np.int64)

    result = associate(estimate, truth)

    assert result.matched_count == 0
    assert result.candidate_count == 400


def test_handles_unsorted_truth() -> None:
    """Truth read from a file is not guaranteed sorted, and searchsorted needs it to be."""
    estimate = np.array([100, 200], dtype=np.int64) * MILLISECOND
    truth = np.array([201, 99], dtype=np.int64) * MILLISECOND

    result = associate(estimate, truth)

    assert result.matched_count == 2
    # index 1 holds 99ms and index 0 holds 201ms, so the pairing is reversed
    assert list(result.truth_indices) == [1, 0]


def test_empty_inputs_match_nothing() -> None:
    empty = np.zeros(0, dtype=np.int64)
    assert associate(empty, np.array([1], dtype=np.int64)).matched_count == 0
    assert associate(np.array([1], dtype=np.int64), empty).matched_count == 0


def test_sparse_estimate_against_dense_truth() -> None:
    """The real case: 20Hz estimate against 120Hz truth, every pose should match."""
    truth = np.arange(0, 6_000, dtype=np.int64) * (MILLISECOND * 100 // 12)
    estimate = np.arange(0, 1_000, dtype=np.int64) * (MILLISECOND * 50)

    result = associate(estimate, truth, DEFAULT_TOLERANCE_NS)

    assert result.matched_count == 1_000


def test_exact_tolerance_boundary_is_inclusive() -> None:
    estimate = np.array([0], dtype=np.int64)
    truth = np.array([DEFAULT_TOLERANCE_NS], dtype=np.int64)

    assert associate(estimate, truth).matched_count == 1
    assert associate(estimate, truth + 1).matched_count == 0
