"""chat 설계안 8절 API (T13~T18) + 생성기 선택 조립."""

import os
import unittest
from unittest import mock

from api.chat.application.service import AskService
from api.chat.domain.answer import Answer, AnswerMode, Source
from api.chat.domain.conversation import ConversationLimits
from api.chat.domain.exceptions import AnswerGenerationError
from api.chat.infrastructure.llm_generator import LlmAnswerGenerator
from api.chat.infrastructure.mock_generator import MockAnswerGenerator
from api.chat.presentation.dependencies import provide_ask_service
from api.container import create_answer_generator
from api.main import create_app
from api.shared.settings import Settings
from api.tests.chat.fakes import FakeGenerator
from api.tests.support import SETTINGS, client_for, make_app

URL = "/api/v1/chat"
MAX = SETTINGS.max_messages


def alternating(n):
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(n)]


class ChatApiTest(unittest.IsolatedAsyncioTestCase):
    def client(self, generator=None, raise_app_exceptions=True):
        app = make_app()
        if generator is not None:
            service = AskService(generator, ConversationLimits(MAX))
            app.dependency_overrides[provide_ask_service] = lambda: service
        return client_for(app, raise_app_exceptions=raise_app_exceptions)

    def assert_error(self, r, status, code):
        body = r.json()
        self.assertEqual(r.status_code, status, r.text)
        self.assertEqual(set(body), {"success", "error_code", "message"})
        self.assertEqual((body["success"], body["error_code"]), (False, code))
        self.assertIsInstance(body["message"], str)

    async def test_t13_default_wiring_is_mock(self):
        async with self.client() as c:
            r = await c.post(URL, json={"messages": [{"role": "user", "content": " 꼬부기 타입? "}]})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIs(body["success"], True)
        self.assertIsInstance(body["data"]["answer"], str)
        self.assertIn("꼬부기 타입?", body["data"]["answer"])
        self.assertEqual(body["data"]["mode"], "mock")
        self.assertEqual(body["data"]["sources"], [])

    async def test_t14_sources_passed_through(self):
        sources = (Source(1, "chunk-b", "doc_b"), Source(2, "chunk-a", "doc_a"))
        generator = FakeGenerator(Answer(text="근거 [1] [2]", mode=AnswerMode.RAG, sources=sources))
        async with self.client(generator) as c:
            r = await c.post(URL, json={"messages": alternating(3), "extra": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"], {
            "answer": "근거 [1] [2]",
            "mode": "rag",
            "sources": [
                {"ref": 1, "chunk_id": "chunk-b", "source_ref_id": "doc_b"},
                {"ref": 2, "chunk_id": "chunk-a", "source_ref_id": "doc_a"},
            ],
        })
        self.assertEqual(len(generator.calls), 1)

    async def test_t15_validation_errors(self):
        broken_order = [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
        cases = {
            "empty_messages": {"json": {"messages": []}},
            "missing_messages": {"json": {}},
            "not_json": {"content": b"not json", "headers": {"Content-Type": "application/json"}},
            "role_bot": {"json": {"messages": [{"role": "bot", "content": "q"}]}},
            "content_number": {"json": {"messages": [{"role": "user", "content": 3}]}},
            "too_many": {"json": {"messages": alternating(MAX + 1)}},
            "broken_order": {"json": {"messages": broken_order}},
            "blank_content": {"json": {"messages": [{"role": "user", "content": "   "}]}},
        }
        generator = FakeGenerator()
        async with self.client(generator) as c:
            for name, kwargs in cases.items():
                with self.subTest(name):
                    r = await c.post(URL, **kwargs)
                    self.assert_error(r, 400, "VALIDATION_ERROR")
        self.assertEqual(generator.calls, [])

    async def test_t15_domain_message_order(self):
        async with self.client() as c:
            r = await c.post(URL, json={"messages": [{"role": "assistant", "content": "secret-text"}]})
        self.assert_error(r, 400, "VALIDATION_ERROR")
        self.assertEqual(
            r.json()["message"],
            "대화는 user로 시작하고 끝나야 하며 user와 assistant가 번갈아 와야 합니다.",
        )
        self.assertNotIn("secret-text", r.text)

    async def test_t15_schema_message_has_location(self):
        async with self.client() as c:
            r = await c.post(URL, json={"messages": [{"role": "bot", "content": "q"}]})
        self.assertTrue(r.json()["message"].startswith("body.messages.0.role: "), r.json()["message"])

    async def test_t16_generation_error_is_502(self):
        error = AnswerGenerationError("답변을 생성하지 못했습니다. 잠시 후 다시 시도하세요.")
        with self.assertLogs("api.error_handlers", level="ERROR"):
            async with self.client(FakeGenerator(error=error)) as c:
                r = await c.post(URL, json={"messages": alternating(1)})
        self.assert_error(r, 502, "ANSWER_GENERATION_FAILED")
        self.assertEqual(r.json()["message"], "답변을 생성하지 못했습니다. 잠시 후 다시 시도하세요.")

    async def test_t17_unhandled_error_is_500_without_detail(self):
        with self.assertLogs("api.error_handlers", level="ERROR"):
            async with self.client(FakeGenerator(error=RuntimeError("raw-secret")), raise_app_exceptions=False) as c:
                r = await c.post(URL, json={"messages": alternating(1)})
        self.assert_error(r, 500, "INTERNAL_ERROR")
        self.assertNotIn("raw-secret", r.text)

    async def test_t18_get_is_method_not_allowed(self):
        async with self.client() as c:
            r = await c.get(URL)
        self.assert_error(r, 405, "METHOD_NOT_ALLOWED")
        self.assertIn("POST", r.headers.get("allow", ""))


class GeneratorWiringTest(unittest.TestCase):
    def settings(self, backend):
        return Settings(answer_backend=backend, max_messages=MAX)

    def test_mock_backend(self):
        self.assertIsInstance(create_answer_generator(self.settings("mock")), MockAnswerGenerator)

    def test_llm_backend_builds_without_network(self):
        env = {"OPENAI_CHAT_MODEL": "test-model", "OPENAI_API_KEY": "test-key-not-secret"}  # security: allow 테스트 더미 키, 네트워크 호출 없음
        with mock.patch.dict(os.environ, env):
            generator = create_answer_generator(self.settings("llm"))
        self.assertIsInstance(generator, LlmAnswerGenerator)
        self.assertEqual(generator.model.model_name, "test-model")
        self.assertEqual(generator.model.temperature, 0)

    def test_unknown_backend_fails_at_startup(self):
        with self.assertRaises(RuntimeError):
            create_app(self.settings("rag"))


if __name__ == "__main__":
    unittest.main()
