import sqlite3
from http.client import responses

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas.common import ErrorDetail, ErrorResponse


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


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(code="validation_error", message="Request validation failed")
    )
    return JSONResponse(status_code=422, content=error.model_dump())


async def storage_error_handler(request: Request, exc: sqlite3.Error) -> JSONResponse:
    error = ErrorResponse(error=ErrorDetail(code="storage_error", message="Storage operation failed"))
    return JSONResponse(status_code=500, content=error.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(sqlite3.Error, storage_error_handler)
