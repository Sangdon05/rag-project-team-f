from pydantic import BaseModel, Field

from api.suggestion.domain.suggestion import SuggestionLevel, SuggestionSet


class SuggestionItem(BaseModel):
    id: str = Field(..., description="추천 질문 ID (등급 안에서 유일)")
    text: str = Field(..., description="질문 문장")


class SuggestionData(BaseModel):
    level: SuggestionLevel = Field(..., description="적용된 등급 (기본값이면 beginner)")
    suggestions: list[SuggestionItem] = Field(..., description="추천 질문. 0개일 수 있다")

    @classmethod
    def from_domain(cls, suggestion_set: SuggestionSet) -> "SuggestionData":
        return cls(
            level=suggestion_set.level,
            suggestions=[SuggestionItem(id=s.id, text=s.text) for s in suggestion_set.suggestions],
        )
