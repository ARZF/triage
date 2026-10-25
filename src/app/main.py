import logging
from contextlib import asynccontextmanager
from http.client import responses

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.health import router
from app.api.chat import router as chat_router
from app.api.demo import router as demo_router
from app.api.dictionaries import router as dictionary_router
from app.agent.dictionaries import load_dictionaries
from app.config import Settings
from app.schemas.common import ErrorDetail, ErrorResponse

settings = Settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Keep HTTP client diagnostics from logging headers at DEBUG level.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dictionaries()
    yield


app = FastAPI(title="Healthcare Agent", lifespan=lifespan)
app.include_router(router)
app.include_router(chat_router)
app.include_router(demo_router)
app.include_router(dictionary_router)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(
            code=f"http_{exc.status_code}",
            message=responses.get(exc.status_code, "HTTP error"),
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error.model_dump(),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(code="validation_error", message="Request validation failed")
    )
    return JSONResponse(status_code=422, content=error.model_dump())
