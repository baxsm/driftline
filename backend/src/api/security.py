"""Password hashing and signed session cookies."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import get_settings

SESSION_COOKIE = "driftline_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt="driftline.session")


def sign_session(user_id: str) -> str:
    return _serializer().dumps({"user_id": user_id})


def read_session(token: str) -> str | None:
    """Return the user id in a session token, or None when it is invalid or expired."""
    try:
        payload = _serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("user_id")
    return user_id if isinstance(user_id, str) else None
