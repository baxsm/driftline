"""IMU windowing tests. These need no gtsam and run everywhere."""

from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from datasets._tests.sequences import sequence_path
from datasets.parsing import ImuSample
from estimator.imu import (
    ImuUnavailable,
    check_continuity,
    open_imu,
    stream_from_samples,
)

BASE_NS = 1_520_530_308_181_901_469
RATE_NS = 5_000_000


@pytest.fixture(scope="module")
def sequence_root() -> Path:
    return sequence_path()


def _samples(count: int, start: int = BASE_NS, step: int = RATE_NS) -> list[ImuSample]:
    return [
        ImuSample(
            timestamp_ns=start + i * step,
            wx=0.001 * i,
            wy=0.0,
            wz=0.0,
            ax=0.0,
            ay=0.0,
            az=9.81,
        )
        for i in range(count)
    ]


def test_window_intervals_sum_to_the_window_duration():
    """No sample may be counted twice and none may be dropped.

    Preintegration multiplies each reading by its interval, so intervals that do not sum to
    the real elapsed time inflate or deflate the integrated motion without raising anything.
    """
    stream = stream_from_samples(_samples(100))
    start = BASE_NS + RATE_NS * 3
    end = BASE_NS + RATE_NS * 17

    window = stream.between(start, end)

    assert window.duration == pytest.approx((end - start) / 1e9, rel=1e-12)
    assert len(window) == len(window.intervals)
    assert np.all(window.intervals > 0)


def test_windows_that_touch_do_not_share_time():
    """Two back to back windows must cover the span exactly once between them."""
    stream = stream_from_samples(_samples(100))
    a, b, c = BASE_NS, BASE_NS + RATE_NS * 20, BASE_NS + RATE_NS * 41

    first = stream.between(a, b)
    second = stream.between(b, c)
    whole = stream.between(a, c)

    assert first.duration + second.duration == pytest.approx(whole.duration, rel=1e-12)


def test_a_window_starting_between_samples_keeps_the_reading_that_held():
    """The sample at or before the start is the one in force when the window opens."""
    stream = stream_from_samples(_samples(20))
    start = BASE_NS + RATE_NS * 4 + RATE_NS // 2
    end = BASE_NS + RATE_NS * 6

    window = stream.between(start, end)

    assert window.duration == pytest.approx((end - start) / 1e9, rel=1e-12)
    assert window.angular_velocities[0][0] == pytest.approx(0.004)


def test_a_backwards_window_is_refused():
    stream = stream_from_samples(_samples(10))
    with pytest.raises(ImuUnavailable, match="forward in time"):
        stream.between(BASE_NS + RATE_NS * 5, BASE_NS + RATE_NS * 2)


def test_repeated_timestamps_are_refused():
    """Two samples at one instant make the interval between them ambiguous."""
    samples = _samples(10)
    duplicated = [*samples, samples[4]]
    with pytest.raises(ImuUnavailable, match="repeats a timestamp"):
        stream_from_samples(duplicated)


def test_an_empty_stream_is_refused():
    with pytest.raises(ImuUnavailable, match="no imu samples"):
        stream_from_samples([])


def test_a_hole_in_the_stream_is_reported():
    """A gap large enough to invent motion across must fail rather than be integrated."""
    samples = [*_samples(50), *_samples(50, start=BASE_NS + RATE_NS * 50 + 2_000_000_000)]
    stream = stream_from_samples(samples)
    with pytest.raises(ImuUnavailable, match="gap"):
        check_continuity(stream)


def test_a_continuous_stream_passes_the_continuity_check():
    check_continuity(stream_from_samples(_samples(200)))


def test_samples_are_sorted_before_use():
    """A file that is not in time order must not produce negative intervals."""
    samples = _samples(20)
    shuffled = [samples[i] for i in (5, 1, 9, 0, 3, 2, 7, 4, 8, 6)]
    stream = stream_from_samples(shuffled)
    assert stream.timestamps_ns == sorted(stream.timestamps_ns)


def test_covers_reports_whether_the_span_is_present():
    stream = stream_from_samples(_samples(50))
    assert stream.covers(BASE_NS + RATE_NS, BASE_NS + RATE_NS * 40)
    assert not stream.covers(BASE_NS - 1, BASE_NS + RATE_NS * 40)
    assert not stream.covers(BASE_NS, BASE_NS + RATE_NS * 100)


@given(
    start_offset=st.integers(min_value=0, max_value=40),
    length=st.integers(min_value=1, max_value=40),
)
def test_any_window_sums_to_its_own_duration(start_offset, length):
    stream = stream_from_samples(_samples(120))
    start = BASE_NS + RATE_NS * start_offset
    end = start + RATE_NS * length
    window = stream.between(start, end)
    assert window.duration == pytest.approx((end - start) / 1e9, rel=1e-12)


def test_the_clean_imu_file_is_preferred_over_the_interpolated_one():
    """The mav0 path has to be looked for before the dso one.

    On TUM VI both exist and only one is safe to preintegrate: `dso/imu.txt` carries an extra
    interpolated sample at every camera timestamp. Reversing this tuple would silently double
    count intervals, so the order is pinned rather than left to whoever edits the list next.
    """
    from datasets.reader import IMU_CANDIDATES

    assert IMU_CANDIDATES[0].parts[0] == "mav0"
    assert IMU_CANDIDATES.index(Path("mav0") / "imu0" / "data.csv") < IMU_CANDIDATES.index(
        Path("dso") / "imu.txt"
    )


@pytest.mark.integration
def test_the_real_sequence_uses_the_clean_imu_file(sequence_root):
    """TUM VI ships two IMU files and only one of them is safe to preintegrate.

    `dso/imu.txt` carries an extra interpolated sample at every camera timestamp, which is
    2821 more rows than `mav0/imu0/data.csv` on room1. Preintegrating those counts the same
    interval twice and hands the integrator sub-microsecond steps, so the reader must pick the
    mav0 file.
    """
    stream = open_imu(sequence_root)

    assert len(stream) == 28122
    assert stream.median_interval_seconds == pytest.approx(0.005016, abs=1e-5)
    check_continuity(stream)
