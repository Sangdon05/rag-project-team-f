"""추천 질문 도메인. 순수 파이썬 (R1)."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from api.suggestion.domain.exceptions import InvalidSuggestionError

INVALID_DATA_MESSAGE = "추천 질문 데이터가 올바르지 않습니다."


class SuggestionLevel(StrEnum):
    """사용자 등급. beginner=P1, novice=P2, expert=P3. 소문자 고정, 대소문자 구분."""

    BEGINNER = "beginner"
    NOVICE = "novice"
    EXPERT = "expert"


@dataclass(frozen=True)
class Suggestion:
    id: str
    text: str

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.text.strip():
            raise InvalidSuggestionError(INVALID_DATA_MESSAGE)


@dataclass(frozen=True)
class SuggestionSet:
    level: SuggestionLevel
    suggestions: tuple[Suggestion, ...]

    @classmethod
    def create(cls, level: SuggestionLevel, items: Iterable[Suggestion]) -> "SuggestionSet":
        """0개 허용. 등급 안에서 id가 중복되면 InvalidSuggestionError."""
        suggestions = tuple(items)
        ids = [item.id for item in suggestions]
        if len(ids) != len(set(ids)):
            raise InvalidSuggestionError(INVALID_DATA_MESSAGE)
        return cls(level=level, suggestions=suggestions)
