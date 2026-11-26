"""chat 설계안 8절 서비스 (T9, T10)."""

import unittest

from api.chat.application.service import AskService
from api.chat.domain.conversation import Conversation, ConversationLimits
from api.chat.domain.exceptions import AnswerGenerationError, InvalidConversationError
from api.tests.chat.fakes import FakeGenerator

LIMITS = ConversationLimits(max_messages=5)


class AskServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_t9_generator_receives_validated_conversation_once(self):
        generator = FakeGenerator()
        answer = await AskService(generator, LIMITS).ask([("user", " a "), ("assistant", "b"), ("user", " c ")])
        self.assertIs(answer, generator.answer)
        self.assertEqual(len(generator.calls), 1)
        conv = generator.calls[0]
        self.assertIsInstance(conv, Conversation)
        self.assertEqual(conv.question, "c")
        self.assertEqual(len(conv.history), 2)

    async def test_t10_invalid_conversation_skips_generator(self):
        generator = FakeGenerator()
        for raw in ([], [("assistant", "a")], [("user", " ")]):
            with self.subTest(raw=raw), self.assertRaises(InvalidConversationError):
                await AskService(generator, LIMITS).ask(raw)
        self.assertEqual(generator.calls, [])

    async def test_generation_error_propagates(self):
        generator = FakeGenerator(error=AnswerGenerationError("x"))
        with self.assertRaises(AnswerGenerationError):
            await AskService(generator, LIMITS).ask([("user", "q")])


if __name__ == "__main__":
    unittest.main()
