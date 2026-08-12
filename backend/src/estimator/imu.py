"""IMU samples, and the windows of them that sit between two keyframes.

Preintegration consumes every sample in an interval, so the only thing this module has to get
right is which samples belong to which interval and how long each one covers. Both are easy to
get subtly wrong in ways that do not raise: a sample counted twice inflates the integrated
motion, and a `dt` taken from the wrong pair of timestamps biases velocity without ever
producing an error.

One trap is specific to TUM VI. `dso/imu.txt` carries 30943 rows where `mav0/imu0/data.csv`
carries 28122, and the difference is exactly the camera frame count: the dso file has an extra
interpolated sample at every camera timestamp. Preintegrating that file counts those intervals
twice and hands the integrator sub-microsecond steps. The reader looks for the mav0 path first
for this reason, so the ordering in `IMU_CANDIDATES` is load bearing rather than stylistic.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from datasets.parsing import ImuSample, read_imu
from datasets.reader import IMU_CANDIDATES

Array = NDArray[np.float64]

# A gap this much larger than the sequence's own median spacing means samples are missing.
# Preintegrating across it would treat the last known acceleration as if it held for the whole
# gap, which is a fabricated motion rather than a measured one.
MAX_GAP_RATIO = 5.0


class ImuUnavailable(RuntimeError):
    """Raised when a sequence cannot supply the IMU data an inertial run needs."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ImuWindow:
    """The samples covering one interval, with the time each one is responsible for."""

    accelerations: Array
    angular_velocities: Array
    intervals: Array

    def __len__(self) -> int:
        return len(self.intervals)

    @property
    def duration(self) -> float:
        return float(self.intervals.sum())


@dataclass(frozen=True, slots=True)
class ImuStream:
    """Every IMU sample in a sequence, indexed by timestamp for interval queries."""

    timestamps_ns: list[int]
    accelerations: Array
    angular_velocities: Array

    def __len__(self) -> int:
        return len(self.timestamps_ns)

    @property
    def median_interval_seconds(self) -> float:
        if len(self.timestamps_ns) < 2:
            return 0.0
        gaps = np.diff(np.asarray(self.timestamps_ns, dtype=np.int64))
        return float(np.median(gaps)) / 1e9

    def covers(self, start_ns: int, end_ns: int) -> bool:
        return bool(
            self.timestamps_ns
            and self.timestamps_ns[0] <= start_ns
            and self.timestamps_ns[-1] >= end_ns
        )

    def between(self, start_ns: int, end_ns: int) -> ImuWindow:
        """The samples covering `[start_ns, end_ns)`, each with the time it accounts for.

        A sample's interval runs from its own timestamp to the next one, clipped to the
        window, so the intervals sum to exactly the window duration and no sample is counted
        in two windows. The sample at or before `start_ns` is included because its reading is
        what held at the moment the window opened.
        """
        if end_ns <= start_ns:
            raise ImuUnavailable(
                f"an imu window must move forward in time, got {start_ns} to {end_ns}"
            )

        first = max(bisect_right(self.timestamps_ns, start_ns) - 1, 0)
        last = bisect_left(self.timestamps_ns, end_ns)
        if last <= first:
            raise ImuUnavailable(f"no imu samples between {start_ns} and {end_ns}")

        edges = [start_ns, *self.timestamps_ns[first + 1 : last], end_ns]
        # differenced as integers before becoming seconds. A 19 digit nanosecond value has
        # more significant digits than float64 carries, so subtracting after the conversion
        # loses tens of nanoseconds per edge and the intervals stop summing to the window.
        intervals = np.asarray(
            [(later - earlier) / 1e9 for earlier, later in pairwise(edges)],
            dtype=np.float64,
        )

        return ImuWindow(
            accelerations=self.accelerations[first:last],
            angular_velocities=self.angular_velocities[first:last],
            intervals=intervals,
        )

    def largest_gap_seconds(self) -> float:
        if len(self.timestamps_ns) < 2:
            return 0.0
        gaps = np.diff(np.asarray(self.timestamps_ns, dtype=np.int64))
        return float(gaps.max()) / 1e9


def stream_from_samples(samples: list[ImuSample]) -> ImuStream:
    if not samples:
        raise ImuUnavailable("this sequence has no imu samples, so it cannot be fused")

    ordered = sorted(samples, key=lambda sample: sample.timestamp_ns)
    timestamps = [sample.timestamp_ns for sample in ordered]
    if len(set(timestamps)) != len(timestamps):
        raise ImuUnavailable("the imu file repeats a timestamp, so intervals are ambiguous")

    return ImuStream(
        timestamps_ns=timestamps,
        accelerations=np.array(
            [[sample.ax, sample.ay, sample.az] for sample in ordered], dtype=np.float64
        ),
        angular_velocities=np.array(
            [[sample.wx, sample.wy, sample.wz] for sample in ordered], dtype=np.float64
        ),
    )


def open_imu(sequence_path: str | Path) -> ImuStream:
    """Load the IMU stream for a sequence, preferring the clean 200Hz file."""
    root = Path(sequence_path).expanduser()
    for relative in IMU_CANDIDATES:
        candidate = root / relative
        if candidate.is_file():
            return stream_from_samples(read_imu(candidate))
    raise ImuUnavailable("this sequence ships no imu file, so it cannot be fused")


def check_continuity(stream: ImuStream) -> None:
    """Raise when the stream has a hole large enough to invent motion across."""
    median = stream.median_interval_seconds
    largest = stream.largest_gap_seconds()
    if median > 0 and largest > median * MAX_GAP_RATIO:
        raise ImuUnavailable(
            f"the imu stream has a {largest * 1e3:.0f} ms gap against its usual "
            f"{median * 1e3:.1f} ms, so motion across it cannot be measured"
        )
