"""The compare route.

Separate from `/api/runs` because it is about a pair rather than about one run, and reads as
`/api/compare?run_a=&run_b=` rather than as a run subresource that happens to take a second id.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db.models import User
from db.session import get_session

from ..dependencies import current_user
from ..services import compare as service

router = APIRouter(prefix="/api/compare", tags=["compare"])


@router.get("")
def compare_runs(
    run_a: str = Query(min_length=1),
    run_b: str = Query(min_length=1),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return service.compare(session, user.id, run_a, run_b)
