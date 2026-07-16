from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from app.api.errors import error_response
from app.core.config import Settings, get_settings
from app.core.security import constant_time_equal, hash_token

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        super().__init__(app)
        self.settings = settings or get_settings()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith("/api/") and request.method in UNSAFE_METHODS:
            cookie = request.cookies.get(self.settings.csrf_cookie_name)
            header = request.headers.get("X-CSRF-Token")
            if not cookie or not header or not constant_time_equal(cookie, header):
                return error_response(
                    request,
                    403,
                    "CSRF_INVALID",
                    "CSRF-токен отсутствует или недействителен",
                    {"reason": "CSRF_INVALID"},
                )
            request.state.csrf_hash = hash_token(header)
        return await call_next(request)


def set_csrf_cookie(response: Response, token: str, settings: Settings | None = None) -> None:
    value = settings or get_settings()
    response.set_cookie(
        value.csrf_cookie_name,
        token,
        httponly=False,
        secure=value.cookie_secure,
        samesite=value.cookie_samesite,
        path="/",
    )


def clear_csrf_cookie(response: Response, settings: Settings | None = None) -> None:
    value = settings or get_settings()
    response.delete_cookie(value.csrf_cookie_name, path="/", samesite=value.cookie_samesite)
