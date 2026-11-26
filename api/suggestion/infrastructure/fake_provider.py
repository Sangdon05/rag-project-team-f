"""고정 데이터 제공자.

평가셋(eval/)과 무관하게 새로 쓴 질문이다 (R16). 답변(정답)은 넣지 않고 질문 문장만 둔다.
"""

from collections.abc import Mapping

from api.suggestion.domain.provider import SuggestionProvider
from api.suggestion.domain.suggestion import Suggestion, SuggestionLevel

FAKE_SUGGESTIONS: dict[SuggestionLevel, tuple[Suggestion, ...]] = {
    SuggestionLevel.BEGINNER: (
        Suggestion("beginner-01", "파이리는 뭐한테 약해?"),
        Suggestion("beginner-02", "피카츄는 진화하면 누구야?"),
        Suggestion("beginner-03", "꼬부기는 무슨 기술 배워?"),
        Suggestion("beginner-04", "이상해씨는 무슨 타입이야?"),
    ),
    SuggestionLevel.NOVICE: (
        Suggestion("novice-01", "이상해씨 골랐는데 뭐부터 보면 돼?"),
        Suggestion("novice-02", "종족치가 뭐야?"),
        Suggestion("novice-03", "타입 상성은 어떻게 읽어?"),
        Suggestion("novice-04", "꼬부기는 몇 레벨에 진화해?"),
    ),
    SuggestionLevel.EXPERT: (
        Suggestion("expert-01", "리자몽 특수 종족치 몇임?"),
        Suggestion("expert-02", "잠만보 레벨업 기술 뭐 있음?"),
        Suggestion("expert-03", "스타미 스피드 종족치랑 타입 어떻게 됨?"),
        Suggestion("expert-04", "라이츄 스피드 종족치 몇임?"),
    ),
}


class FakeSuggestionProvider(SuggestionProvider):
    def __init__(self, data: Mapping[SuggestionLevel, tuple[Suggestion, ...]] | None = None) -> None:
        self.data = FAKE_SUGGESTIONS if data is None else data

    async def list_for(self, level: SuggestionLevel) -> tuple[Suggestion, ...]:
        return tuple(self.data.get(level, ()))
