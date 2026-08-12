"""The background worker that executes queued runs.

Runs never execute inside a request. A room sequence is 2821 frames and takes minutes, which
is far past any sensible request timeout, so `POST /api/runs` only enqueues.

One thread polling the queue is enough at this scale. Celery and a broker would add an
external service to run and monitor without changing what a single user can get through.
The claim is done with `SELECT ... FOR UPDATE SKIP LOCKED`, so adding a second worker later
is a configuration change rather than a rewrite.
"""

import threading
import time
from bisect import bisect_right
from typing import Any

from sqlalchemy.orm import Session

import logger
from config import get_settings
from datasets.errors import SequenceUnreadable
from db.models import Dataset, Run
from db.session import session_scope
from estimator.artifacts import (
    RunArtifacts,
    append_log,
    artifacts_for,
    prepare,
    write_tracks,
    write_trajectory,
)
from estimator.camera import CalibrationMissing, Camera, camera_from_calibration
from estimator.config import EstimatorConfig
from estimator.fusion import (
    FusionFailed,
    FusionResult,
    FusionUnavailable,
    ImuNoise,
    fuse,
)
from estimator.images import open_frames
from estimator.imu import ImuUnavailable, check_continuity, open_imu
from estimator.pipeline import FrameResult, RunOutcome, run_pipeline
from geometry.transform import interpolate

from . import metrics as metrics_service
from . import runs as service

POLL_SECONDS = 1.0
# how much of an unexpected exception's message reaches the failure panel. Long enough to name
# the cause, short enough that a stack of nested import errors does not fill the screen.
UNEXPECTED_REASON_LIMIT = 300
# how often progress reaches the database, in frames; every frame would be one commit per
# frame, and the UI cannot show more than this anyway
PROGRESS_INTERVAL = 10


class RunFailed(RuntimeError):
    def __init__(self, reason: str, frame: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.frame = frame


def _pose_rows(
    run_id: Any,
    frames: list[FrameResult],
    velocities: dict[int, Any] | None = None,
) -> list[dict[str, Any]]:
    speeds = velocities or {}
    rows = []
    for frame in frames:
        w, x, y, z = frame.pose.quaternion()
        tx, ty, tz = frame.pose.translation
        velocity = speeds.get(frame.frame_index)
        rows.append(
            {
                "run_id": run_id,
                "frame_index": frame.frame_index,
                "timestamp_ns": frame.timestamp_ns,
                "tx": float(tx),
                "ty": float(ty),
                "tz": float(tz),
                "qw": float(w),
                "qx": float(x),
                "qy": float(y),
                "qz": float(z),
                "tracked_features": frame.tracked_features,
                # left null on a visual-only run, where there is no scale and so no speed
                "vx": float(velocity[0]) if velocity is not None else None,
                "vy": float(velocity[1]) if velocity is not None else None,
                "vz": float(velocity[2]) if velocity is not None else None,
            }
        )
    return rows


def execute_run(session: Session, run: Run) -> None:
    """Run the estimator over one sequence and persist everything it produced.

    Whatever happens, the run ends in `done` or `failed` with a reason. A run left in
    `running` after a crash would show a spinner that never resolves.
    """
    settings = get_settings()
    artifacts = artifacts_for(settings.storage_dir, str(run.id))
    prepare(artifacts)

    dataset = session.get(Dataset, run.dataset_id)
    if not dataset:
        raise RunFailed("the sequence this run points at has been removed")

    config = EstimatorConfig.model_validate(run.config)
    append_log(artifacts, f"run {run.id} on {dataset.name}")
    append_log(artifacts, f"config {config.canonical_json()}")

    try:
        frames = open_frames(dataset.path)
    except SequenceUnreadable as exc:
        raise RunFailed(exc.message) from exc

    try:
        camera = camera_from_calibration(dataset.calibration)
    except CalibrationMissing as exc:
        raise RunFailed(str(exc)) from exc

    start = config.start_frame
    if start >= len(frames):
        raise RunFailed(
            f"this sequence has {len(frames)} frames, so it cannot start at frame {start}"
        )

    available = len(frames) - start
    total = available if config.max_frames is None else min(available, config.max_frames)
    timestamps = frames.timestamps[start : start + total]

    def load_frame(index: int) -> Any:
        return frames.load(start + index)

    where = f" from frame {start}" if start else ""
    append_log(artifacts, f"{total} frames{where}, camera model {camera.distortion_model}")

    processed = 0

    def on_frame(result: FrameResult) -> None:
        nonlocal processed
        processed = result.frame_index + 1
        if processed % PROGRESS_INTERVAL == 0:
            service.mark_progress(session, run.id, processed)

    started = time.monotonic()
    try:
        outcome = run_pipeline(
            timestamps=timestamps,
            load_image=load_frame,
            camera=camera,
            config=config,
            on_frame=on_frame,
        )
    except SequenceUnreadable as exc:
        raise RunFailed(exc.message, processed) from exc

    elapsed = time.monotonic() - started

    velocities: dict[int, Any] | None = None
    if config.mode == "mono_inertial":
        velocities = _fuse(dataset, camera, outcome, artifacts)

    service.save_poses(session, run.id, _pose_rows(run.id, outcome.frames, velocities))
    write_tracks(artifacts, outcome.frames)
    write_trajectory(artifacts, outcome.frames)
    service.mark_progress(session, run.id, len(outcome.frames))

    append_log(artifacts, f"estimated {len(outcome.frames)} poses in {elapsed:.1f}s")

    # a run that lost tracking still estimated a real trajectory up to that point, so it is
    # scored too rather than being left without any measure of how far it had drifted
    _score(session, run, artifacts)

    if outcome.failed:
        append_log(
            artifacts,
            f"failed at frame {outcome.failure_frame}: {outcome.failure_reason}",
        )
        raise RunFailed(outcome.failure_reason or "the run failed", outcome.failure_frame)

    append_log(artifacts, "done")
    service.finish_run(session, run.id, "done")


def _fuse(
    dataset: Dataset,
    camera: Camera,
    outcome: RunOutcome,
    artifacts: RunArtifacts,
) -> dict[int, Any]:
    """Replace the visual trajectory with the metric one the IMU makes possible.

    The visual estimate is kept until this succeeds. If fusion cannot run, the run fails
    rather than quietly saving the unit-scale visual path under an inertial label, because
    that path would then be scored with SE(3) alignment and read as a catastrophically wrong
    metric estimate instead of an honest "this did not run".
    """
    try:
        stream = open_imu(dataset.path)
        check_continuity(stream)
        result = fuse(
            keyframes=outcome.keyframe_motions,
            stream=stream,
            noise=ImuNoise.from_calibration(dataset.calibration),
            body_to_camera=camera.body_to_camera,
        )
    except (FusionUnavailable, FusionFailed, ImuUnavailable) as exc:
        append_log(artifacts, f"fusion failed: {exc.reason}")
        raise RunFailed(exc.reason, outcome.failure_frame) from exc

    initialisation = result.initialisation
    append_log(
        artifacts,
        f"fused {len(result.states)} keyframes in {result.optimiser_iterations} iterations, "
        f"path {result.path_length:.2f} m",
    )
    if not initialisation.is_excited:
        # not a failure: the estimate is real, but scale rests on weak observability and
        # saying so is more useful than a number presented without its caveat
        append_log(
            artifacts,
            f"note: specific force varied by only {initialisation.excitation:.3f} m/s^2 "
            "during initialisation, so metric scale is weakly observed here",
        )

    return _apply_fused(outcome, result)


def _apply_fused(outcome: RunOutcome, result: FusionResult) -> dict[int, Any]:
    """Write the fused keyframe poses back over every frame, interpolating between them.

    Frames between keyframes are slerped exactly as the visual pipeline does, so the two
    modes produce a pose for every frame and the trajectory has no gaps to explain.
    """
    by_frame = {state.frame_index: state for state in result.states}
    keyframes = sorted(by_frame)
    if not keyframes:
        return {}

    first, last = keyframes[0], keyframes[-1]

    for position, frame in enumerate(outcome.frames):
        index = frame.frame_index

        if index in by_frame:
            pose = by_frame[index].pose
        elif index <= first:
            pose = by_frame[first].pose
        elif index >= last:
            # the tail after the last keyframe was never solved metrically, so it holds the
            # last fused pose rather than extrapolating a motion nothing measured
            pose = by_frame[last].pose
        else:
            after = bisect_right(keyframes, index)
            earlier, later = keyframes[after - 1], keyframes[after]
            pose = interpolate(
                by_frame[earlier].pose,
                by_frame[later].pose,
                (index - earlier) / (later - earlier),
            )

        outcome.frames[position] = frame.at_pose(pose)

    return {state.frame_index: state.velocity for state in result.states}


def _score(session: Session, run: Run, artifacts: RunArtifacts) -> None:
    """Score the run against ground truth, logging whatever the outcome was.

    Scoring never fails the run. The estimate is what the run produced, and it is still
    worth keeping and drawing when the comparison against truth cannot be made.
    """
    try:
        result, reason = metrics_service.score_run_with_reason(session, run)
    except Exception as exc:
        logger.error("worker.scoring_failed", exc)
        session.rollback()
        append_log(artifacts, "scoring failed, the estimate is kept")
        return

    if not result:
        append_log(artifacts, f"not scored: {reason}")
        return

    append_log(
        artifacts,
        f"scored against ground truth, {result.alignment.mode} aligned: "
        f"ate rmse {result.ate_translation.rmse:.4f}, "
        f"{result.association.matched_count} of {result.association.candidate_count} "
        f"poses matched",
    )


def process_one(session: Session) -> bool:
    """Claim and execute a single queued run. Returns whether there was one."""
    run = service.claim_next_queued(session)
    if not run:
        return False

    run_id = run.id
    try:
        execute_run(session, run)
    except RunFailed as exc:
        service.finish_run(session, run_id, "failed", exc.reason, exc.frame)
    except Exception as exc:  # the worker thread must not die on one bad run
        logger.error("worker.run_crashed", exc)
        session.rollback()
        service.finish_run(session, run_id, "failed", _unexpected_reason(exc))
    return True


def _unexpected_reason(exc: Exception) -> str:
    """Describe a crash the estimator did not anticipate, naming what actually went wrong.

    A bare "the estimator stopped unexpectedly" is the failure mode this project treats as
    unacceptable: the reason is the product, and a run that says nothing sends whoever reads it
    to the container logs. This happened for real. A missing parquet engine crashed a run after
    fusion had already succeeded, and the panel gave no hint that the estimate itself was fine
    and only writing it out had failed.

    The exception type is included because it is what makes the message searchable, and the
    text because it usually names the missing piece.
    """
    detail = str(exc).strip().splitlines()
    summary = detail[0] if detail else ""
    if len(summary) > UNEXPECTED_REASON_LIMIT:
        summary = f"{summary[:UNEXPECTED_REASON_LIMIT].rstrip()}..."
    named = f"{type(exc).__name__}: {summary}" if summary else type(exc).__name__
    return f"the estimator stopped unexpectedly, {named}"


def _loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            with session_scope() as session:
                worked = process_one(session)
        except Exception as exc:
            logger.error("worker.loop", exc)
            worked = False
        if not worked:
            stop.wait(POLL_SECONDS)


class Worker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=_loop, args=(self._stop,), daemon=True)
        self._thread.start()
        logger.info("worker.start", "polling for queued runs")

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("worker.stop", "stopped")
