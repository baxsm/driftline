import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from api.errors import ApiError, api_error_handler, http_error_handler, validation_error_handler
from api.routes.auth import router as auth_router
from api.routes.compare import router as compare_router
from api.routes.datasets import router as datasets_router
from api.routes.runs import router as runs_router
from api.services.worker import Worker
from config import get_settings

settings = get_settings()
worker = Worker()

# the tests drive the worker directly so a run is deterministic rather than racing a poll
WORKER_DISABLED = os.getenv("DRIFTLINE_DISABLE_WORKER") == "1"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if not WORKER_DISABLED:
        worker.start()
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(title="driftline", version="0.1.0", lifespan=lifespan)

# The browser reaches this API through the frontend's own origin, which rewrites `/api/*` here,
# so browser requests arrive server to server and never need CORS. This stays for direct API
# use, and because a misconfigured proxy should fail loudly rather than be masked by a wildcard.
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
app.include_router(compare_router)
app.include_router(datasets_router)
app.include_router(runs_router)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}
