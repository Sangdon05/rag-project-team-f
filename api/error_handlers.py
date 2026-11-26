"""shared 예외와 프레임워크 예외를 공통 에러 응답으로 바꾼다 (R6, R7).

내장 ValueError·LookupError는 등록하지 않는다 (라이브러리 버그가 4xx로 숨는다).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.shared.exceptions import ApiError
from api.shared.responses import ErrorResponse

logger = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = "요청한 경로를 찾을 수 없습니다."
METHOD_NOT_ALLOWED_MESSAGE = "허용하지 않는 메서드입니다."
HTTP_ERROR_MESSAGE = "요청을 처리할 수 없습니다."
INTERNAL_ERROR_MESSAGE = "서버 내부 오류가 발생했습니다."
VALIDATION_FALLBACK_MESSAGE = "요청 형식이 올바르지 않습니다."


def _error(status_code: int, error_code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    body = ErrorResponse(error_code=error_code, message=message).model_dump()
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return VALIDATION_FALLBACK_MESSAGE
    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", ()))
    msg = str(first.get("msg", "")) or VALIDATION_FALLBACK_MESSAGE
    return f"{loc}: {msg}" if loc else msg      # input 값은 넣지 않는다


async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error("%s 발생 (%s)", type(exc).__name__, exc.error_code)
    return _error(exc.status_code, exc.error_code, exc.message)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(400, "VALIDATION_ERROR", _validation_message(exc))


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return _error(404, "NOT_FOUND", NOT_FOUND_MESSAGE, exc.headers)
    if exc.status_code == 405:
        return _error(405, "METHOD_NOT_ALLOWED", METHOD_NOT_ALLOWED_MESSAGE, exc.headers)   # Allow 헤더 유지
    return _error(exc.status_code, "HTTP_ERROR", HTTP_ERROR_MESSAGE, exc.headers)


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("처리하지 못한 예외: %s", type(exc).__name__)
    return _internal_error()


def _internal_error() -> JSONResponse:
    return _error(500, "INTERNAL_ERROR", INTERNAL_ERROR_MESSAGE)


class UnhandledExceptionMiddleware:
    """CORS 안쪽에서 처리 못 한 예외를 500 INTERNAL_ERROR로 바꾼다 (health 설계안 0.4).

    Starlette의 Exception 핸들러는 ServerErrorMiddleware(CORS 바깥)에서 돌아 응답에 CORS 헤더가 없다.
    이 미들웨어를 CORS보다 먼저 add해서(나중에 add한 미들웨어가 바깥) CORS가 500 응답에도 헤더를 붙이게 한다.
    응답을 이미 보내기 시작했으면 바꿀 수 없으므로 다시 던진다.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if response_started:
                raise
            logger.exception("처리하지 못한 예외: %s", type(exc).__name__)
            await _internal_error()(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
