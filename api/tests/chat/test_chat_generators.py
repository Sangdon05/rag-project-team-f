"""chat 설계안 8절 어댑터 (T11, T12) + mock 생성기. fake 모델만 쓴다 (R15)."""

import unittest

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from api.chat.domain.answer import AnswerMode
from api.chat.domain.conversation import Conversation, ConversationLimits
from api.chat.domain.exceptions import AnswerGenerationError
from api.chat.infrastructure.llm_generator import LlmAnswerGenerator
from api.chat.infrastructure.mock_generator import MockAnswerGenerator

LIMITS = ConversationLimits(max_messages=5)
CONV = Conversation.create([("user", "q1"), ("assistant", "a1"), ("user", "q2")], LIMITS)


class BrokenModel(FakeListChatModel):
    async def ainvoke(self, *args, **kwargs):
        raise TimeoutError("network down sk-secret")


class RecordingModel(FakeListChatModel):
    seen: list = []

    async def ainvoke(self, messages, *args, **kwargs):
        self.seen.append(messages)
        return await super().ainvoke(messages, *args, **kwargs)


class LlmGeneratorTest(unittest.IsolatedAsyncioTestCase):
    async def test_t11_returns_llm_mode_without_sources(self):
        answer = await LlmAnswerGenerator(FakeListChatModel(responses=["hello"])).generate(CONV)
        self.assertEqual((answer.text, answer.mode, answer.sources), ("hello", AnswerMode.LLM, ()))

    async def test_messages_sent_to_model(self):
        model = RecordingModel(responses=["ok"], seen=[])
        await LlmAnswerGenerator(model).generate(CONV)
        sent = model.seen[0]
        self.assertEqual([type(m) for m in sent], [SystemMessage, HumanMessage, AIMessage, HumanMessage])
        self.assertEqual([m.content for m in sent[1:]], ["q1", "a1", "q2"])

    async def test_t12_sdk_error_becomes_domain_error_without_detail(self):
        with self.assertLogs("api.chat.infrastructure.llm_generator", level="WARNING") as logs:
            with self.assertRaises(AnswerGenerationError) as ctx:
                await LlmAnswerGenerator(BrokenModel(responses=["x"])).generate(CONV)
        self.assertNotIn("sk-secret", ctx.exception.message)
        self.assertNotIn("sk-secret", "\n".join(logs.output))
        self.assertEqual(ctx.exception.error_code, "ANSWER_GENERATION_FAILED")

    async def test_blank_reply_is_generation_error(self):
        with self.assertLogs("api.chat.infrastructure.llm_generator", level="WARNING"):
            with self.assertRaises(AnswerGenerationError):
                await LlmAnswerGenerator(FakeListChatModel(responses=["   "])).generate(CONV)


class MockGeneratorTest(unittest.IsolatedAsyncioTestCase):
    async def test_mock_answer_contains_question_prefix(self):
        long_q = "가" * 150
        answer = await MockAnswerGenerator().generate(Conversation.create([("user", long_q)], LIMITS))
        self.assertEqual((answer.mode, answer.sources), (AnswerMode.MOCK, ()))
        self.assertIn("가" * 100, answer.text)
        self.assertNotIn("가" * 101, answer.text)


if __name__ == "__main__":
    unittest.main()
