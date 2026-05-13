import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("karigar.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        rid = getattr(request.state, "request_id", None)
        client = request.client.host if request.client else "-"
        logger.info(
            "%s %s %s %.2fms request_id=%s client=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            rid,
            client,
        )
        return response
