from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.logging import log_exception

type ErrorDetails = Mapping[str, object]


class ApiException(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: ErrorDetails | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = dict(details or {})


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: ErrorDetails | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": dict(details or {}),
                "requestId": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiException)
    async def api_exception_handler(request: Request, exc: ApiException) -> JSONResponse:
        return error_response(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {"location": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return error_response(
            request,
            422,
            "VALIDATION_ERROR",
            "Переданы некорректные данные",
            {"fields": fields},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_exception_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        return error_response(
            request,
            409,
            "CONFLICT",
            "Операция конфликтует с текущим состоянием данных",
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        log_exception(
            {
                "requestId": getattr(request.state, "request_id", "unknown"),
                "method": request.method,
                "path": request.url.path,
            },
            exc,
        )
        return error_response(
            request,
            500,
            "INTERNAL_ERROR",
            "Внутренняя ошибка сервиса",
        )
