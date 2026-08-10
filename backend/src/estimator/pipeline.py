"""The visual front end: images in, trajectory out.

Monocular, so the trajectory is correct up to one global scale factor. Each frame's unit
translation is composed onto the path as if it were one unit of distance, which means the
scale between consecutive frames is not preserved either. This is the known weakness of
frame to frame monocular odometry and it is why this phase exists: phase 4 fuses the IMU,
which observes real scale through gravity, and it has to be judged against this baseline.

Nothing here is smoothed, bundle adjusted, or loop closed. Drift is expected and is the
measurement, not a defect.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

import logger
from geometry.transform import Transform, compose

from .camera import Camera
from .config import EstimatorConfig
from .motion import MotionUnrecoverable, estimate_motion
from .tracker import Observation, TrackerState, advance

# corner strength relative to the best corner in the frame; below this a "corner" is noise
QUALITY_LEVEL = 0.01


@dataclass(frozen=True, slots=True)
class FrameResult:
    frame_index: int
    timestamp_ns: int
    pose: Transform
    tracked_features: int
    inlier_count: int
    observations: list[Observation]


@dataclass
class RunOutcome:
    frames: list[FrameResult] = field(default_factory=list)
    failure_reason: str | None = None
    failure_frame: int | None = None

    @property
    def failed(self) -> bool:
        return self.failure_reason is not None


ImageLoader = Callable[[int], NDArray[np.uint8]]
ProgressCallback = Callable[[FrameResult], None]


def run_pipeline(
    timestamps: list[int],
    load_image: ImageLoader,
    camera: Camera,
    config: EstimatorConfig,
    on_frame: ProgressCallback | None = None,
) -> RunOutcome:
    """Estimate a trajectory over the given frames.

    A frame whose geometry cannot be solved ends the run rather than being skipped. Skipping
    would leave a gap the composed path cannot represent, and the resulting trajectory would
    silently claim the camera travelled in a straight line across it.
    """
    outcome = RunOutcome()
    state = TrackerState()
    previous_image: NDArray[np.uint8] | None = None
    pose = Transform.identity()

    for frame_index, timestamp_ns in enumerate(timestamps):
        image = load_image(frame_index)

        state, matched_previous, matched_current = advance(
            state,
            previous_image,
            image,
            max_features=config.max_features,
            quality_level=QUALITY_LEVEL,
            min_distance=config.min_feature_distance_px,
            redetect_below=config.redetect_below,
        )

        if frame_index > 0:
            try:
                estimate = estimate_motion(
                    camera.undistort(matched_previous),
                    camera.undistort(matched_current),
                    camera.matrix,
                    config.ransac_threshold_px,
                )
            except MotionUnrecoverable as exc:
                outcome.failure_reason = exc.reason
                outcome.failure_frame = frame_index
                logger.warn(
                    "estimator.frame_failed",
                    {"frame": frame_index, "reason": exc.reason},
                )
                return outcome
            pose = compose(pose, estimate.motion)
            inliers = estimate.inlier_count
        else:
            inliers = 0

        result = FrameResult(
            frame_index=frame_index,
            timestamp_ns=timestamp_ns,
            pose=pose,
            tracked_features=len(state.points),
            inlier_count=inliers,
            observations=state.observations(),
        )
        outcome.frames.append(result)
        if on_frame:
            on_frame(result)

        previous_image = image

    return outcome


def frame_range(total: int, max_frames: int | None) -> Iterator[int]:
    limit = total if max_frames is None else min(total, max_frames)
    return iter(range(limit))
