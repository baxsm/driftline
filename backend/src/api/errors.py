"""One error shape for the whole API.

Every failure returns `{ "error": { code, message, field? } }`. `code` is a stable string
the frontend can branch on, `message` is written for a person, and `field` names the
offending input on validation errors.
"""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

STATUS_BY_CODE = {
    "unauthorized": 401,
    "email_taken": 409,
    "invalid_credentials": 401,
    "dataset_not_found": 404,
    "path_already_registered": 409,
    "sequence_unreadable": 400,
    "validation_failed": 422,
}


class ApiError(HTTPException):
    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        super().__init__(status_code=STATUS_BY_CODE.get(code, 400), detail=message)
        self.code = code
        self.message = message
        self.field = field


def error_body(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if field:
        body["field"] = field
    return {"error": body}


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.field),
    )


async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    code = "unauthorized" if exc.status_code == 401 else "request_failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, str(exc.detail)),
    )


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Surface the first offending field so the client can point at the right input."""
    field = None
    message = "Check the submitted values and try again."
    errors = getattr(exc, "errors", None)
    if callable(errors):
        details = errors()
        if details:
            # a malformed body reports loc ("body", 0), where the 0 is a character offset
            # rather than a field, and naming it would point the user at nothing
            location = [
                str(part)
                for part in details[0].get("loc", [])
                if part != "body" and not isinstance(part, int)
            ]
            field = ".".join(location) or None
            message = details[0].get("msg", message)
    return JSONResponse(status_code=422, content=error_body("validation_failed", message, field))
