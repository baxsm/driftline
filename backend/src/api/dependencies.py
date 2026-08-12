import uuid

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import User
from db.session import get_session

from .errors import ApiError
from .security import SESSION_COOKIE, read_session


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise ApiError("unauthorized", "Sign in to continue.")

    user_id = read_session(token)
    if not user_id:
        raise ApiError("unauthorized", "Your session expired. Sign in again.")

    try:
        parsed = uuid.UUID(user_id)
    except ValueError as exc:
        raise ApiError("unauthorized", "Your session is not valid. Sign in again.") from exc

    user = session.scalar(select(User).where(User.id == parsed))
    if not user:
        raise ApiError("unauthorized", "Your session is not valid. Sign in again.")
    return user
