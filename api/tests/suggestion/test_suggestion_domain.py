"""suggestion 설계안 8절 도메인·서비스 (S1~S3)."""

import unittest

from api.suggestion.application.service import SuggestionService
from api.suggestion.domain.exceptions import InvalidSuggestionError
from api.suggestion.domain.provider import SuggestionProvider
from api.suggestion.domain.suggestion import Suggestion, SuggestionLevel, SuggestionSet
from api.suggestion.infrastructure.fake_provider import FAKE_SUGGESTIONS, FakeSuggestionProvider


class RecordingProvider(SuggestionProvider):
    def __init__(self, items=()):
        self.items = tuple(items)
        self.calls = []

    async def list_for(self, level):
        self.calls.append(level)
        return self.items


class SuggestionDomainTest(unittest.TestCase):
    def test_s1_blank_text_or_id_rejected(self):
        for kwargs in ({"id": "a", "text": "  "}, {"id": " ", "text": "q"}, {"id": "", "text": ""}):
            with self.subTest(**kwargs), self.assertRaises(InvalidSuggestionError):
                Suggestion(**kwargs)

    def test_s2_duplicate_id_rejected(self):
        items = [Suggestion("dup", "첫 질문"), Suggestion("dup", "둘째 질문")]
        with self.assertRaises(InvalidSuggestionError):
            SuggestionSet.create(SuggestionLevel.NOVICE, items)

    def test_create_keeps_order_and_allows_empty(self):
        items = [Suggestion("b", "둘"), Suggestion("a", "하나")]
        s = SuggestionSet.create(SuggestionLevel.EXPERT, items)
        self.assertEqual([i.id for i in s.suggestions], ["b", "a"])
        self.assertEqual(SuggestionSet.create(SuggestionLevel.BEGINNER, []).suggestions, ())

    def test_invalid_suggestion_is_internal_error(self):
        self.assertEqual(
            (InvalidSuggestionError.status_code, InvalidSuggestionError.error_code), (500, "INTERNAL_ERROR")
        )

    def test_level_values_are_lowercase(self):
        self.assertEqual([level.value for level in SuggestionLevel], ["beginner", "novice", "expert"])

    def test_fake_data_satisfies_invariants(self):
        for level in SuggestionLevel:
            with self.subTest(level=level):
                s = SuggestionSet.create(level, FAKE_SUGGESTIONS[level])
                self.assertGreaterEqual(len(s.suggestions), 2)


class SuggestionServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_s3_passes_level_and_returns_empty_set(self):
        provider = RecordingProvider()
        result = await SuggestionService(provider).suggest(SuggestionLevel.NOVICE)
        self.assertEqual(result, SuggestionSet(SuggestionLevel.NOVICE, ()))
        self.assertEqual(provider.calls, [SuggestionLevel.NOVICE])

    async def test_duplicate_provider_data_raises(self):
        provider = RecordingProvider([Suggestion("x", "a"), Suggestion("x", "b")])
        with self.assertRaises(InvalidSuggestionError):
            await SuggestionService(provider).suggest(SuggestionLevel.EXPERT)

    async def test_fake_provider_accepts_injected_data(self):
        data = {SuggestionLevel.EXPERT: (Suggestion("e", "q"),)}
        provider = FakeSuggestionProvider(data=data)
        self.assertEqual(await provider.list_for(SuggestionLevel.EXPERT), (Suggestion("e", "q"),))
        self.assertEqual(await provider.list_for(SuggestionLevel.BEGINNER), ())
        self.assertEqual(await FakeSuggestionProvider(data={}).list_for(SuggestionLevel.BEGINNER), ())


if __name__ == "__main__":
    unittest.main()
