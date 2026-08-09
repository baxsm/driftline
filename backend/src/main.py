from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from api.errors import ApiError, api_error_handler, http_error_handler, validation_error_handler
from api.routes.auth import router as auth_router
from api.routes.datasets import router as datasets_router
from config import get_settings

settings = get_settings()

app = FastAPI(title="driftline", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(HTTPException, http_error_handler)  # type: ignore[arg-type]

app.include_router(auth_router)
app.include_router(datasets_router)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}
