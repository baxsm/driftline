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
from estimator.camera import CalibrationMissing, camera_from_calibration
from estimator.config import EstimatorConfig
from estimator.images import open_frames
from estimator.pipeline import FrameResult, run_pipeline

from . import metrics as metrics_service
from . import runs as service

POLL_SECONDS = 1.0
# how often progress reaches the database, in frames; every frame would be one commit per
# frame, and the UI cannot show more than this anyway
PROGRESS_INTERVAL = 10


class RunFailed(RuntimeError):
    def __init__(self, reason: str, frame: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.frame = frame


def _pose_rows(run_id: Any, frames: list[FrameResult]) -> list[dict[str, Any]]:
    rows = []
    for frame in frames:
        w, x, y, z = frame.pose.quaternion()
        tx, ty, tz = frame.pose.translation
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

    total = len(frames) if config.max_frames is None else min(len(frames), config.max_frames)
    timestamps = frames.timestamps[:total]
    append_log(artifacts, f"{total} frames, camera model {camera.distortion_model}")

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
            load_image=frames.load,
            camera=camera,
            config=config,
            on_frame=on_frame,
        )
    except SequenceUnreadable as exc:
        raise RunFailed(exc.message, processed) from exc

    elapsed = time.monotonic() - started
    service.save_poses(session, run.id, _pose_rows(run.id, outcome.frames))
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


def _score(session: Session, run: Run, artifacts: RunArtifacts) -> None:
    """Score the run against ground truth, logging whatever the outcome was.

    Scoring never fails the run. The estimate is what the run produced, and it is still
    worth keeping and drawing when the comparison against truth cannot be made.
    """
    try:
        result = metrics_service.score_run(session, run)
    except Exception as exc:
        logger.error("worker.scoring_failed", exc)
        session.rollback()
        append_log(artifacts, "scoring failed, the estimate is kept")
        return

    if not result:
        append_log(artifacts, "not scored: this sequence has no usable ground truth")
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
        service.finish_run(session, run_id, "failed", "the estimator stopped unexpectedly")
    return True


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
