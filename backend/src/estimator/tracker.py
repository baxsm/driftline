"""Feature detection and frame to frame tracking.

Sparse optical flow (Lucas-Kanade) rather than descriptor matching. At 20Hz the camera moves
very little between frames, which is the case KLT is built for, and it avoids computing
descriptors on every frame.

Track identity is the part worth being careful about. A feature that is lost and later
redetected at the same pixel is a new observation, not a continuation, so it gets a new id.
Reusing the id would tell the rest of the pipeline that a point was seen continuously across
a gap it was never seen in.
"""

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

# KLT works in single precision and OpenCV rejects a float64 point array outright, so pixel
# coordinates stay float32 for as long as they are pixels. They widen to float64 in
# `camera.undistort`, which is where they stop being pixels and become geometry.
Points = NDArray[np.float32]
Image = NDArray[np.uint8]

# a KLT match that survives tracking forward then backward to within this many pixels is
# treated as reliable; anything further apart is a mistracked point
FORWARD_BACKWARD_TOLERANCE_PX = 1.0

LK_WINDOW = (21, 21)
LK_LEVELS = 3
LK_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01)


@dataclass(frozen=True, slots=True)
class Observation:
    track_id: int
    x: float
    y: float
    age: int


@dataclass
class TrackerState:
    points: Points = field(default_factory=lambda: np.empty((0, 2), dtype=np.float32))
    track_ids: list[int] = field(default_factory=list)
    ages: list[int] = field(default_factory=list)
    next_track_id: int = 0

    def observations(self) -> list[Observation]:
        return [
            Observation(track_id=tid, x=float(p[0]), y=float(p[1]), age=age)
            for tid, p, age in zip(self.track_ids, self.points, self.ages, strict=True)
        ]


def detect(
    image: Image,
    max_features: int,
    quality_level: float,
    min_distance: float,
    mask: Image | None = None,
) -> Points:
    """Corners worth tracking, as an (N, 2) array of pixel coordinates."""
    if max_features <= 0:
        return np.empty((0, 2), dtype=np.float32)
    # the stub types this as always returning an array, but a frame with no corners at all
    # really does come back as None
    corners: Any = cv2.goodFeaturesToTrack(
        image,
        maxCorners=max_features,
        qualityLevel=quality_level,
        minDistance=min_distance,
        mask=mask,
    )
    if corners is None:
        return np.empty((0, 2), dtype=np.float32)
    return np.asarray(corners, dtype=np.float32).reshape(-1, 2)


def _occupancy_mask(shape: tuple[int, int], points: Points, radius: float) -> Image:
    """Blank out a disc around every live point so redetection fills the gaps instead.

    Without this, `goodFeaturesToTrack` returns the same strong corners that are already
    being tracked and the track count never actually recovers.
    """
    mask = np.full(shape, 255, dtype=np.uint8)
    span = round(radius)
    for x, y in points:
        cv2.circle(mask, (round(float(x)), round(float(y))), span, 0, -1)
    return mask


def _flow(previous: Image, current: Image, points: Any) -> tuple[Any, Any]:
    """One KLT pass.

    `nextPts` is passed as None so OpenCV allocates the output itself, which its own docs
    describe but its type stub does not allow.
    """
    tracked, status, _ = cv2.calcOpticalFlowPyrLK(  # type: ignore[call-overload]
        previous,
        current,
        points,
        None,
        winSize=LK_WINDOW,
        maxLevel=LK_LEVELS,
        criteria=LK_CRITERIA,
    )
    return tracked, status


def track_forward(
    previous_image: Image,
    current_image: Image,
    points: Points,
) -> tuple[Points, NDArray[np.bool_]]:
    """Track points into the next frame and report which survived.

    Every match is verified by tracking it back to where it came from. A point that does not
    land near its origin is a mistrack, and mistracks are what put outliers into the pose
    solve, so they are dropped here rather than left for RANSAC to absorb.
    """
    if len(points) == 0:
        return np.empty((0, 2), dtype=np.float32), np.zeros(0, dtype=bool)

    source = points.reshape(-1, 1, 2)
    forward, forward_status = _flow(previous_image, current_image, source)
    backward, backward_status = _flow(current_image, previous_image, forward)

    round_trip = np.linalg.norm((source - backward).reshape(-1, 2), axis=1)
    height, width = current_image.shape[:2]
    tracked = forward.reshape(-1, 2)
    inside = (
        (tracked[:, 0] >= 0)
        & (tracked[:, 1] >= 0)
        & (tracked[:, 0] < width)
        & (tracked[:, 1] < height)
    )
    good = (
        forward_status.reshape(-1).astype(bool)
        & backward_status.reshape(-1).astype(bool)
        & (round_trip < FORWARD_BACKWARD_TOLERANCE_PX)
        & inside
    )
    return np.asarray(tracked, dtype=np.float32), np.asarray(good, dtype=bool)


def advance(
    state: TrackerState,
    previous_image: Image | None,
    current_image: Image,
    max_features: int,
    quality_level: float,
    min_distance: float,
    redetect_below: int,
) -> tuple[TrackerState, Points, Points]:
    """Carry tracks into the current frame, then top them up by detecting new ones.

    Returns the new state alongside the matched point pairs (previous, current) for the
    tracks that survived, which is what the pose solve consumes. New detections are not in
    the pairs, because they have not been seen twice yet.
    """
    matched_previous = np.empty((0, 2), dtype=np.float32)
    matched_current = np.empty((0, 2), dtype=np.float32)
    ids: list[int] = []
    ages: list[int] = []
    points = np.empty((0, 2), dtype=np.float32)

    if previous_image is not None and len(state.points) > 0:
        tracked, good = track_forward(previous_image, current_image, state.points)
        matched_previous = state.points[good]
        matched_current = tracked[good]
        points = tracked[good]
        ids = [tid for tid, keep in zip(state.track_ids, good, strict=True) if keep]
        ages = [age + 1 for age, keep in zip(state.ages, good, strict=True) if keep]

    next_id = state.next_track_id
    if len(points) < redetect_below:
        mask = (
            _occupancy_mask(current_image.shape[:2], points, min_distance)
            if len(points) > 0
            else None
        )
        fresh = detect(current_image, max_features - len(points), quality_level, min_distance, mask)
        if len(fresh) > 0:
            points = np.vstack([points, fresh]) if len(points) > 0 else fresh
            ids.extend(range(next_id, next_id + len(fresh)))
            ages.extend([0] * len(fresh))
            next_id += len(fresh)

    return (
        TrackerState(points=points, track_ids=ids, ages=ages, next_track_id=next_id),
        matched_previous,
        matched_current,
    )
