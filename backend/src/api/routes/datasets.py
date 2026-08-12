from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db.models import User
from db.session import get_session

from ..dependencies import current_user
from ..errors import ApiError
from ..serializers import dataset_response, dataset_summary, pose_response
from ..services import datasets as service

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


class RegisterRequest(BaseModel):
    path: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=200)


@router.get("")
def list_datasets(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = service.list_datasets(session, user.id)
    return {"datasets": [dataset_summary(row) for row in rows]}


@router.post("/register", status_code=201)
def register(
    body: RegisterRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    dataset = service.register_dataset(session, user.id, body.path, body.name)
    return dataset_response(dataset)


@router.get("/{dataset_id}")
def get_dataset(
    dataset_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return dataset_response(service.get_dataset(session, user.id, dataset_id))


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(
    dataset_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    service.delete_dataset(session, user.id, dataset_id)


@router.get("/{dataset_id}/ground-truth")
def get_ground_truth(
    dataset_id: str,
    stride: int = Query(default=1, ge=1, le=1000),
    from_ns: str | None = Query(default=None, alias="from"),
    to_ns: str | None = Query(default=None, alias="to"),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Ground truth for a sequence, optionally only the span a run covered.

    The window is taken as a string because a nanosecond timestamp is 19 digits, which is past
    what a JSON number survives on the client that has to send it back.
    """
    dataset = service.get_dataset(session, user.id, dataset_id)
    poses, total = service.ground_truth_poses(
        session, dataset.id, stride, _timestamp(from_ns, "from"), _timestamp(to_ns, "to")
    )
    return {
        "poses": [pose_response(pose) for pose in poses],
        "stride": stride,
        "total": total,
        "has_ground_truth": dataset.has_ground_truth,
    }


def _timestamp(value: str | None, field: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise ApiError("bad_timestamp", "That is not a nanosecond timestamp.", field) from None
