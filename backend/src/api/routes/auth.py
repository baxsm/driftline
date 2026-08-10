from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import logger
from config import get_settings
from db.models import User
from db.session import get_session

from ..dependencies import current_user
from ..errors import ApiError
from ..security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    hash_password,
    sign_session,
    verify_password,
)
from ..serializers import user_response

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


def _set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
        path="/",
    )


@router.post("/register", status_code=201)
def register(
    body: Credentials,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    user = User(email=body.email.lower(), password_hash=hash_password(body.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiError("email_taken", "That email is already registered.", "email") from None

    session.refresh(user)
    _set_session_cookie(response, str(user.id))
    logger.info("auth.register", {"user": str(user.id)})
    return user_response(user)


@router.post("/login")
def login(
    body: Credentials,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    user = session.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(user.password_hash, body.password):
        # identical response either way, so this cannot be used to probe for accounts
        raise ApiError("invalid_credentials", "That email and password do not match.")

    _set_session_cookie(response, str(user.id))
    logger.info("auth.login", {"user": str(user.id)})
    return user_response(user)


@router.post("/logout")
def logout(response: Response, user: User = Depends(current_user)) -> dict[str, Any]:
    response.delete_cookie(SESSION_COOKIE, path="/")
    logger.info("auth.logout", {"user": str(user.id)})
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict[str, Any]:
    return user_response(user)
