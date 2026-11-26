from api.shared.exceptions import InvalidInputError, NotFoundError, UpstreamError

INVALID_SOURCE_REF_ID_MESSAGE = "source_ref_id는 도감번호 3자리(예: 001)여야 합니다."
DOCUMENT_NOT_FOUND_MESSAGE = "문서를 찾을 수 없습니다."
DOCUMENT_SOURCE_MESSAGE = "문서를 읽지 못했습니다. 잠시 후 다시 시도하세요."


class InvalidSourceRefIdError(InvalidInputError):
    """source_ref_id가 도감번호 3자리가 아님. 400 VALIDATION_ERROR (R7)."""

    def __init__(self, message: str = INVALID_SOURCE_REF_ID_MESSAGE) -> None:
        super().__init__(message)


class DocumentNotFoundError(NotFoundError):
    """형식은 맞지만 문서 파일이 없음. 404."""

    error_code = "DOCUMENT_NOT_FOUND"

    def __init__(self, message: str = DOCUMENT_NOT_FOUND_MESSAGE) -> None:
        super().__init__(message)


class DocumentSourceError(UpstreamError):
    """문서 저장소 읽기 실패 (같은 번호 파일 여럿, 폴더 없음, 권한, 디코딩 등). 502."""

    error_code = "DOCUMENT_SOURCE_FAILED"

    def __init__(self, message: str = DOCUMENT_SOURCE_MESSAGE) -> None:
        super().__init__(message)
