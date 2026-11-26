from api.suggestion.domain.provider import SuggestionProvider
from api.suggestion.domain.suggestion import SuggestionLevel, SuggestionSet


class SuggestionService:
    def __init__(self, provider: SuggestionProvider) -> None:
        self.provider = provider

    async def suggest(self, level: SuggestionLevel) -> SuggestionSet:
        items = await self.provider.list_for(level)
        return SuggestionSet.create(level, items)   # 불변식은 도메인에서 (R3)
