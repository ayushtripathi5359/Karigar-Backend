import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    header_name = "X-Request-ID"

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(self.header_name)
        rid = incoming if incoming else str(uuid.uuid4())
        request.state.request_id = rid
        response = await call_next(request)
        response.headers[self.header_name] = rid
        return response
