from abc import ABC, abstractmethod

from api.suggestion.domain.suggestion import Suggestion, SuggestionLevel


class SuggestionProvider(ABC):
    """등급별 추천 질문을 주는 포트."""

    @abstractmethod
    async def list_for(self, level: SuggestionLevel) -> tuple[Suggestion, ...]: ...
