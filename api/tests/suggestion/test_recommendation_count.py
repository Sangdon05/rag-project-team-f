"""Four fixed question candidates per level; no provider or model calls."""
import unittest
from api.suggestion.domain.suggestion import SuggestionLevel
from api.suggestion.infrastructure.fake_provider import FakeSuggestionProvider
from api.tests.support import client_for, make_app


class RecommendationCountTest(unittest.IsolatedAsyncioTestCase):
    async def test_provider_preserves_three_candidates_and_adds_a_fourth(self):
        provider = FakeSuggestionProvider()
        expected_first_three = {
            SuggestionLevel.BEGINNER: ("파이리는 뭐한테 약해?", "피카츄는 진화하면 누구야?", "꼬부기는 무슨 기술 배워?"),
            SuggestionLevel.NOVICE: ("이상해씨 골랐는데 뭐부터 보면 돼?", "종족치가 뭐야?", "타입 상성은 어떻게 읽어?"),
            SuggestionLevel.EXPERT: ("리자몽 특수 종족치 몇임?", "잠만보 레벨업 기술 뭐 있음?", "스타미 스피드 종족치랑 타입 어떻게 됨?"),
        }
        for level in SuggestionLevel:
            with self.subTest(level=level):
                items = await provider.list_for(level)
                self.assertEqual(len(items), 4)
                self.assertEqual(tuple(item.text for item in items[:3]), expected_first_three[level])
                self.assertEqual([item.id for item in items], [f"{level.value}-{index:02}" for index in range(1, 5)])

    async def test_real_http_api_returns_exactly_four_for_each_persona_level(self):
        async with client_for(make_app()) as client:
            for level in SuggestionLevel:
                with self.subTest(level=level):
                    response = await client.get("/api/v1/suggestion", params={"level": level.value})
                    self.assertEqual(response.status_code, 200)
                    data = response.json()["data"]
                    self.assertEqual(data["level"], level.value)
                    self.assertEqual(len(data["suggestions"]), 4)
                    self.assertEqual(len({item["id"] for item in data["suggestions"]}), 4)
