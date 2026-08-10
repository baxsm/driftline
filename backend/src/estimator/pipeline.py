"""The visual front end: images in, trajectory out.

Monocular, so the trajectory is correct up to one global scale factor. Each keyframe's unit
translation is composed onto the path as if it were one unit of distance, which means the
scale between keyframes is not preserved either. This is the known weakness of monocular
odometry and it is why phase 4 exists: fusing the IMU observes real scale through gravity,
and it has to be judged against this baseline.

Geometry is solved between keyframes rather than between consecutive frames. The essential
matrix needs the camera to have actually translated, and at 20Hz a handheld camera moves
about 0.7 px between frames, which is nowhere near enough to separate rotation from
translation. Tracking still runs on every frame, because a track is only useful if it is
followed continuously; it is only the pose solve that waits for parallax.

Nothing here is smoothed, bundle adjusted, or loop closed. Drift is expected and is the
measurement, not a defect.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

import logger
from geometry.transform import Transform, compose, interpolate

from .camera import Camera
from .config import EstimatorConfig
from .motion import MotionUnrecoverable, estimate_motion
from .tracker import Observation, TrackerState, advance

CLAHE_CLIP_LIMIT = 3.0
CLAHE_TILE_GRID = (8, 8)

# below this many correspondences back to the keyframe there is nothing to solve, and it is
# better to take a new keyframe than to solve a badly constrained one
MIN_KEYFRAME_CORRESPONDENCES = 20


@dataclass(frozen=True, slots=True)
class FrameResult:
    frame_index: int
    timestamp_ns: int
    pose: Transform
    tracked_features: int
    inlier_count: int
    observations: list[Observation]
    is_keyframe: bool = False
    parallax_px: float = 0.0

    def at_pose(self, pose: Transform) -> "FrameResult":
        return FrameResult(
            frame_index=self.frame_index,
            timestamp_ns=self.timestamp_ns,
            pose=pose,
            tracked_features=self.tracked_features,
            inlier_count=self.inlier_count,
            observations=self.observations,
            is_keyframe=self.is_keyframe,
            parallax_px=self.parallax_px,
        )


@dataclass
class RunOutcome:
    frames: list[FrameResult] = field(default_factory=list)
    failure_reason: str | None = None
    failure_frame: int | None = None
    keyframe_count: int = 0

    @property
    def failed(self) -> bool:
        return self.failure_reason is not None


ImageLoader = Callable[[int], NDArray[np.uint8]]
ProgressCallback = Callable[[FrameResult], None]


def enhance(image: NDArray[np.uint8], clahe: Any | None = None) -> NDArray[np.uint8]:
    """Contrast limited equalisation, so detection has something to find in a dark frame.

    Global equalisation would also brighten the frame, but it stretches the whole histogram
    at once and amplifies sensor noise in the large flat dark regions these sequences are
    mostly made of. CLAHE works per tile and clips, which keeps the noise down.
    """
    operator = clahe if clahe is not None else _new_clahe()
    return np.asarray(operator.apply(image), dtype=np.uint8)


def _new_clahe() -> Any:
    return cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID)


def _correspondences(
    keyframe_points: dict[int, NDArray[np.float32]],
    track_ids: list[int],
    points: NDArray[np.float32],
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """The points visible both at the keyframe and now, in matching order."""
    pairs = [
        (keyframe_points[track_id], point)
        for track_id, point in zip(track_ids, points, strict=True)
        if track_id in keyframe_points
    ]
    if not pairs:
        empty = np.empty((0, 2), dtype=np.float32)
        return empty, empty
    return (
        np.array([pair[0] for pair in pairs], dtype=np.float32),
        np.array([pair[1] for pair in pairs], dtype=np.float32),
    )


def _median_parallax(
    source: NDArray[np.float32], target: NDArray[np.float32]
) -> float:
    if len(source) == 0:
        return 0.0
    return float(np.median(np.linalg.norm(target - source, axis=1)))


def run_pipeline(
    timestamps: list[int],
    load_image: ImageLoader,
    camera: Camera,
    config: EstimatorConfig,
    on_frame: ProgressCallback | None = None,
) -> RunOutcome:
    """Estimate a trajectory over the given frames.

    Every frame gets a pose. Frames between keyframes carry the last solved pose forward
    rather than inventing motion for them, because monocular geometry cannot say how far the
    camera moved in a step it could not solve. A keyframe whose geometry cannot be solved
    ends the run rather than being skipped, since skipping would leave a gap the composed
    path cannot represent.
    """
    outcome = RunOutcome()
    state = TrackerState()
    previous_image: NDArray[np.uint8] | None = None
    pose = Transform.identity()

    keyframe_points: dict[int, NDArray[np.float32]] = {}
    frames_since_keyframe = 0
    # frames held at the previous keyframe's pose, waiting for the next solve to spread the
    # motion across them
    pending: list[int] = []

    def settle(previous_pose: Transform, solved_pose: Transform) -> None:
        """Spread the motion just solved across the frames that were waiting for it."""
        steps = len(pending) + 1
        for offset, position in enumerate(pending, start=1):
            frame = outcome.frames[position]
            outcome.frames[position] = frame.at_pose(
                interpolate(previous_pose, solved_pose, offset / steps)
            )
        pending.clear()

    # one CLAHE operator for the whole run rather than one per frame
    clahe = _new_clahe() if config.enhance_contrast else None

    for frame_index, timestamp_ns in enumerate(timestamps):
        image = load_image(frame_index)
        if clahe is not None:
            image = enhance(image, clahe)

        state, _, _ = advance(
            state,
            previous_image,
            image,
            max_features=config.max_features,
            quality_level=config.corner_quality,
            min_distance=config.min_feature_distance_px,
            redetect_below=config.redetect_below,
        )

        is_keyframe = False
        parallax = 0.0
        inliers = 0

        if frame_index == 0:
            keyframe_points = dict(zip(state.track_ids, state.points, strict=True))
            is_keyframe = True
            outcome.keyframe_count += 1
        else:
            frames_since_keyframe += 1
            source, target = _correspondences(keyframe_points, state.track_ids, state.points)
            parallax = _median_parallax(source, target)

            enough_points = len(source) >= MIN_KEYFRAME_CORRESPONDENCES
            moved = parallax >= config.keyframe_parallax_px

            if enough_points and moved:
                try:
                    estimate = estimate_motion(
                        camera.undistort(source),
                        camera.undistort(target),
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
                previous_pose = pose
                pose = compose(pose, estimate.motion)
                settle(previous_pose, pose)
                inliers = estimate.inlier_count
                is_keyframe = True
                outcome.keyframe_count += 1
                keyframe_points = dict(zip(state.track_ids, state.points, strict=True))
                frames_since_keyframe = 0
            elif frames_since_keyframe >= config.max_frames_without_keyframe:
                reason = (
                    f"no keyframe in {frames_since_keyframe} frames: the camera has moved "
                    f"{parallax:.1f} px against the {config.keyframe_parallax_px:.1f} px "
                    "needed to solve for motion"
                    if enough_points
                    else (
                        f"no keyframe in {frames_since_keyframe} frames: only {len(source)} "
                        f"features still match the last keyframe, need "
                        f"{MIN_KEYFRAME_CORRESPONDENCES}"
                    )
                )
                outcome.failure_reason = reason
                outcome.failure_frame = frame_index
                logger.warn(
                    "estimator.keyframe_starved",
                    {"frame": frame_index, "parallax": round(parallax, 2)},
                )
                return outcome
            elif not enough_points:
                # the keyframe has aged out of view, so start a new one here rather than
                # solving against a handful of survivors
                keyframe_points = dict(zip(state.track_ids, state.points, strict=True))
                frames_since_keyframe = 0

        result = FrameResult(
            frame_index=frame_index,
            timestamp_ns=timestamp_ns,
            pose=pose,
            tracked_features=len(state.points),
            inlier_count=inliers,
            observations=state.observations(),
            is_keyframe=is_keyframe,
            parallax_px=parallax,
        )
        outcome.frames.append(result)
        if not is_keyframe:
            pending.append(len(outcome.frames) - 1)
        if on_frame:
            on_frame(result)

        previous_image = image

    # a run that never solved a single keyframe estimated nothing. Every pose in it is the
    # identity carried forward, which would otherwise be reported as a successful run whose
    # trajectory happens to be a point.
    if not outcome.failed and outcome.keyframe_count < 2 and len(outcome.frames) > 1:
        outcome.failure_reason = (
            "no motion could be solved: the camera never moved far enough between frames "
            f"to reach the {config.keyframe_parallax_px:.1f} px of parallax needed"
        )
        outcome.failure_frame = len(outcome.frames) - 1

    return outcome


def frame_range(total: int, max_frames: int | None) -> Iterator[int]:
    limit = total if max_frames is None else min(total, max_frames)
    return iter(range(limit))
