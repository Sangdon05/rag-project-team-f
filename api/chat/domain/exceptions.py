from api.shared.exceptions import InvalidInputError, UpstreamError


class InvalidConversationError(InvalidInputError):
    """대화 규칙 위반 (개수, 순서, 알 수 없는 role, 빈 content). error_code는 VALIDATION_ERROR 그대로 (R7)."""


class AnswerGenerationError(UpstreamError):
    """생성기가 답을 만들지 못함 (네트워크, 모델, SDK 오류, 빈 답변). 502."""

    error_code = "ANSWER_GENERATION_FAILED"
