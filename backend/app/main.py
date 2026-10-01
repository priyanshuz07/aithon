from contextlib import asynccontextmanager
import logging
from pathlib import Path
import sys

backend_directory = str(Path(__file__).resolve().parents[1])
if backend_directory not in sys.path:
    sys.path.insert(0, backend_directory)

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import (
    adaptive_router,
    behavior_router,
    dashboard_router,
    demo_router,
    health_router,
    sessions_router,
)
from app.core.config import get_settings
from app.core.request_size_limit import RequestSizeLimitMiddleware
from app.db.init_db import initialize_database, purge_expired_sessions
from app.db.session import engine

settings = get_settings()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    if settings.data_retention_enabled:
        removed = purge_expired_sessions(engine, settings.data_retention_days)
        if removed:
            logger.info("Data retention removed %s expired sessions", removed)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=65_536)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database request failed", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "A database error occurred"})


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    safe_errors = [
        {
            "location": error.get("loc", ()),
            "message": error.get("msg", "Invalid request"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe_errors})


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unexpected request failure", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred"})


app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(sessions_router, prefix=settings.api_v1_prefix)
app.include_router(behavior_router)
app.include_router(dashboard_router)
app.include_router(adaptive_router)
app.include_router(demo_router)
app.frontend(
    "/",
    directory=str(Path(__file__).resolve().parents[2] / "frontend"),
    fallback=None,
)
