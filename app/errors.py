import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    error: str
    message: str
    request_id: str | None = None


def _code_for_status(code: int) -> str:
    return {
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
        status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
    }.get(code, "HTTP_ERROR")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, str):
            message = detail
        elif isinstance(detail, (list, dict)):
            message = str(detail)
        else:
            message = "request failed"
        body = ErrorBody(
            error=_code_for_status(exc.status_code),
            message=message,
            request_id=_request_id(request),
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(exclude_none=True))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        body = ErrorBody(
            error="VALIDATION_ERROR",
            message=exc.errors()[0]["msg"] if exc.errors() else "invalid request",
            request_id=_request_id(request),
        )
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body.model_dump(exclude_none=True))

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        body = ErrorBody(
            error="RATE_LIMITED",
            message=str(exc.detail),
            request_id=_request_id(request),
        )
        return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content=body.model_dump(exclude_none=True))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        rid = _request_id(request)
        logger.exception("unhandled error request_id=%s", rid, exc_info=exc)
        body = ErrorBody(
            error="INTERNAL_ERROR",
            message="internal server error",
            request_id=rid,
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body.model_dump(exclude_none=True))
