"""suggestion 설계안 8절 API (S4~S8) + level 중복 query 동작 확인."""

import unittest

from api.suggestion.application.service import SuggestionService
from api.suggestion.domain.provider import SuggestionProvider
from api.suggestion.infrastructure.fake_provider import FakeSuggestionProvider
from api.suggestion.presentation.dependencies import provide_suggestion_service
from api.tests.support import client_for, make_app

URL = "/api/v1/suggestion"


class BrokenProvider(SuggestionProvider):
    async def list_for(self, level):
        raise RuntimeError("secret-detail")


class SuggestionApiTest(unittest.IsolatedAsyncioTestCase):
    def client(self, provider=None, raise_app_exceptions=True):
        app = make_app()
        if provider is not None:
            service = SuggestionService(provider)
            app.dependency_overrides[provide_suggestion_service] = lambda: service
        return client_for(app, raise_app_exceptions=raise_app_exceptions)

    async def test_s4_default_level_is_beginner(self):
        async with self.client() as c:
            r = await c.get(URL)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIs(body["success"], True)
        self.assertEqual(body["data"]["level"], "beginner")
        items = body["data"]["suggestions"]
        self.assertGreaterEqual(len(items), 2)
        for item in items:
            self.assertEqual(set(item), {"id", "text"})
            self.assertIsInstance(item["id"], str)
            self.assertIsInstance(item["text"], str)

    async def test_s5_expert_level(self):
        async with self.client() as c:
            r = await c.get(URL, params={"level": "expert"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["level"], "expert")
        self.assertTrue(all(i["id"].startswith("expert-") for i in r.json()["data"]["suggestions"]))

    async def test_s6_invalid_level_is_validation_error(self):
        async with self.client() as c:
            for query in ("level=bad", "level=Beginner", "level="):
                with self.subTest(query=query):
                    r = await c.get(f"{URL}?{query}")
                    body = r.json()
                    self.assertEqual(r.status_code, 400)
                    self.assertEqual(set(body), {"success", "error_code", "message"})
                    self.assertEqual((body["success"], body["error_code"]), (False, "VALIDATION_ERROR"))
                    self.assertTrue(body["message"].startswith("query.level: "), body["message"])

    async def test_s7_empty_provider_returns_empty_list(self):
        async with self.client(FakeSuggestionProvider(data={})) as c:
            r = await c.get(URL, params={"level": "novice"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"success": True, "data": {"level": "novice", "suggestions": []}})

    async def test_s8_provider_failure_hides_detail(self):
        with self.assertLogs("api.error_handlers", level="ERROR"):
            async with self.client(BrokenProvider(), raise_app_exceptions=False) as c:
                r = await c.get(URL)
        self.assertEqual(r.status_code, 500)
        self.assertEqual((r.json()["success"], r.json()["error_code"]), (False, "INTERNAL_ERROR"))
        self.assertNotIn("secret-detail", r.text)

    async def test_repeated_level_uses_last_value(self):
        async with self.client() as c:
            r = await c.get(f"{URL}?level=novice&level=expert")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"]["level"], "expert")

    async def test_post_is_method_not_allowed(self):
        async with self.client() as c:
            r = await c.post(URL)
        self.assertEqual((r.status_code, r.json()["error_code"]), (405, "METHOD_NOT_ALLOWED"))


if __name__ == "__main__":
    unittest.main()
