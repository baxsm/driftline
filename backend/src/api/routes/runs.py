"""Run routes.

`POST /api/runs` enqueues and returns immediately. The estimator work happens in the worker
thread, and the client follows it on `/events`.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import get_settings
from datasets.errors import SequenceUnreadable
from db.models import Dataset, User
from db.session import get_session, session_scope
from estimator.artifacts import artifacts_for, read_log, read_tracks
from estimator.config import EstimatorConfig
from estimator.images import open_frames

from ..dependencies import current_user
from ..errors import ApiError
from ..serializers import pose_response, run_response, run_summary
from ..services import runs as service

router = APIRouter(prefix="/api/runs", tags=["runs"])

# a client that reconnects forever would hold a worker thread open, so a stream that has not
# reached a terminal status by this point closes and lets the client poll instead
STREAM_TIMEOUT_SECONDS = 900
STREAM_INTERVAL_SECONDS = 0.5
MAX_TRACK_FRAMES = 100


class CreateRunRequest(BaseModel):
    dataset_id: str = Field(min_length=1)
    label: str | None = Field(default=None, max_length=200)
    config: EstimatorConfig = Field(default_factory=EstimatorConfig)


@router.get("")
def list_runs(
    dataset_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows, total = service.list_runs(session, user.id, dataset_id, limit, offset)
    return {"runs": [run_summary(run) for run in rows], "total": total}


@router.post("", status_code=201)
def create_run(
    body: CreateRunRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = service.queue_run(session, user.id, body.dataset_id, body.config, body.label)
    return run_response(run)


@router.get("/{run_id}")
def get_run(
    run_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return run_response(service.get_run(session, user.id, run_id))


@router.delete("/{run_id}", status_code=204)
def delete_run(
    run_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    run = service.delete_run(session, user.id, run_id)
    artifacts = artifacts_for(get_settings().storage_dir, str(run.id))
    if artifacts.root.is_dir():
        for path in artifacts.root.iterdir():
            path.unlink(missing_ok=True)
        artifacts.root.rmdir()


@router.get("/{run_id}/trajectory")
def get_trajectory(
    run_id: str,
    stride: int = Query(default=1, ge=1, le=1000),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = service.get_run(session, user.id, run_id)
    poses, total = service.trajectory(session, run.id, stride)
    return {
        "poses": [pose_response(pose) for pose in poses],
        "stride": stride,
        "total": total,
        # mono translation has no absolute scale, so the viewer must not present these as
        # metres and phase 3 must align with Sim(3) rather than SE(3)
        "scale_is_arbitrary": run.config.get("mode", "mono") == "mono",
    }


@router.get("/{run_id}/tracks")
def get_tracks(
    run_id: str,
    from_frame: int = Query(default=0, ge=0, alias="from"),
    to_frame: int = Query(default=0, ge=0, alias="to"),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = service.get_run(session, user.id, run_id)
    last = to_frame if to_frame >= from_frame else from_frame
    if last - from_frame >= MAX_TRACK_FRAMES:
        raise ApiError(
            "range_too_large",
            f"Ask for at most {MAX_TRACK_FRAMES} frames at a time.",
            "to",
        )

    artifacts = artifacts_for(get_settings().storage_dir, str(run.id))
    table = read_tracks(artifacts, from_frame, last)

    frames: list[dict[str, Any]] = []
    for frame_index, group in table.groupby("frame_index", sort=True):
        frames.append(
            {
                "frame_index": int(frame_index),
                "timestamp_ns": str(int(group["timestamp_ns"].iloc[0])),
                "features": [
                    {
                        "id": int(row.track_id),
                        "x": float(row.x),
                        "y": float(row.y),
                        "age": int(row.age),
                    }
                    for row in group.itertuples()
                ],
            }
        )
    return {"frames": frames}


@router.get("/{run_id}/frames/{frame_index}")
def get_frame_image(
    run_id: str,
    frame_index: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    """One frame of the sequence, so the tracking view can draw features over it.

    Served as `application/octet-stream` with no content disposition. A download manager
    extension will grab any response that looks like a downloadable file and hand back an
    empty body, which reads downstream as a corrupt image.
    """
    run = service.get_run(session, user.id, run_id)
    dataset = session.get(Dataset, run.dataset_id)
    if not dataset:
        raise ApiError("dataset_not_found", "That sequence does not exist.")

    try:
        frames = open_frames(dataset.path)
    except SequenceUnreadable as exc:
        raise ApiError("sequence_unreadable", exc.message) from exc

    if frame_index < 0 or frame_index >= len(frames):
        raise ApiError("frame_not_found", "That frame is not in this sequence.")

    path = frames.path_for(frame_index)
    if not path.is_file():
        raise ApiError("frame_not_found", "That frame is listed but missing from disk.")

    return Response(
        content=path.read_bytes(),
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{run_id}/log", response_class=PlainTextResponse)
def get_log(
    run_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> str:
    run = service.get_run(session, user.id, run_id)
    return read_log(artifacts_for(get_settings().storage_dir, str(run.id)))


def _progress_event(run: Any) -> str:
    body = {
        "frame": run.processed_frames,
        "total": run.total_frames,
        "status": run.status,
        "failure_reason": run.failure_reason,
        "failure_frame": run.failure_frame,
    }
    return f"data: {json.dumps(body)}\n\n"


@router.get("/{run_id}/events")
async def stream_events(
    run_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Progress while a run is in flight, closing when it reaches a terminal status.

    Each poll opens its own short lived session. Holding the request's session open for the
    length of a run would keep one connection from the pool busy doing nothing.
    """
    run = service.get_run(session, user.id, run_id)
    user_id = user.id
    run_key = str(run.id)

    async def events() -> AsyncIterator[str]:
        waited = 0.0
        last_payload = ""
        while waited < STREAM_TIMEOUT_SECONDS:
            with session_scope() as poll_session:
                current = service.get_run(poll_session, user_id, run_key)
                payload = _progress_event(current)
                status = current.status

            if payload != last_payload:
                last_payload = payload
                yield payload

            if status in service.TERMINAL_STATUSES:
                return

            await asyncio.sleep(STREAM_INTERVAL_SECONDS)
            waited += STREAM_INTERVAL_SECONDS

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
