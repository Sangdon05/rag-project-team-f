"""답변 도메인. 순수 파이썬 (R1)."""

from dataclasses import dataclass
from enum import StrEnum

from api.chat.domain.exceptions import AnswerGenerationError

GENERATION_FAILED_MESSAGE = "답변을 생성하지 못했습니다. 잠시 후 다시 시도하세요."


class AnswerMode(StrEnum):
    MOCK = "mock"
    LLM = "llm"
    RAG = "rag"


@dataclass(frozen=True)
class Source:
    """출처. 값은 생성기(RAG)가 정한 그대로이며 검증·변환하지 않는다."""

    ref: int
    chunk_id: str
    source_ref_id: str


@dataclass(frozen=True)
class Answer:
    text: str
    mode: AnswerMode
    sources: tuple[Source, ...] = ()

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise AnswerGenerationError(GENERATION_FAILED_MESSAGE)
