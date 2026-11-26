"""기반 예외. 순수 파이썬이며 모든 계층(domain 포함)이 import한다 (R1, R6).

HTTP 변환은 api/error_handlers.py가 한다. message에는 사용자에게 보여도 되는 문장만 넣는다.
"""


class ApiError(Exception):
    """기반 예외. 처리 못 한 서버 오류(500 INTERNAL_ERROR)."""

    status_code = 500
    error_code = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputError(ApiError):
    """도메인 입력 규칙 위반. 하위 클래스는 error_code를 바꾸지 않는다 (R7)."""

    status_code = 400
    error_code = "VALIDATION_ERROR"


class NotFoundError(ApiError):
    """대상 없음. 하위 클래스가 error_code를 구체화할 수 있다."""

    status_code = 404
    error_code = "NOT_FOUND"


class UpstreamError(ApiError):
    """외부 의존(답변 생성기, 문서 저장소) 실패. 하위 클래스가 error_code를 구체화한다."""

    status_code = 502
    error_code = "UPSTREAM_ERROR"
