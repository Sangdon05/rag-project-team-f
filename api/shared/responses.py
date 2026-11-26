"""공통 응답 형식 (R7). presentation과 error_handlers만 import한다."""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    """성공 응답 `{"success": true, "data": {...}}`."""

    success: Literal[True] = Field(True, description="항상 true")
    data: T = Field(..., description="엔드포인트별 응답 본문")


class ErrorResponse(BaseModel):
    """실패 응답 `{"success": false, "error_code", "message"}`."""

    success: Literal[False] = Field(False, description="항상 false")
    error_code: str = Field(..., description="에러 코드 (예: VALIDATION_ERROR)")
    message: str = Field(..., description="사람이 읽는 오류 설명")
