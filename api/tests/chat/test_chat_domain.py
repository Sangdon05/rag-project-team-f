"""chat 설계안 8절 도메인 (T1~T8)."""

import unittest

from api.chat.domain.answer import Answer, AnswerMode, Source
from api.chat.domain.conversation import (
    COUNT_MESSAGE,
    EMPTY_CONTENT_MESSAGE,
    ORDER_MESSAGE,
    Conversation,
    ConversationLimits,
    Message,
    Role,
)
from api.chat.domain.exceptions import AnswerGenerationError, InvalidConversationError

LIMITS = ConversationLimits(max_messages=5)


def alternating(n, content="q"):
    return [("user" if i % 2 == 0 else "assistant", content) for i in range(n)]


class ConversationCreateTest(unittest.TestCase):
    def test_t1_single_user_message(self):
        conv = Conversation.create([("user", "  파이리 타입?  ")], LIMITS)
        self.assertEqual(conv.question, "파이리 타입?")
        self.assertEqual(conv.history, ())
        self.assertEqual(conv.messages, (Message(Role.USER, "파이리 타입?"),))

    def test_t1_three_messages(self):
        conv = Conversation.create([("user", " a "), ("assistant", "\tb\n"), ("user", " c")], LIMITS)
        self.assertEqual(conv.question, "c")
        self.assertEqual(conv.history, (Message(Role.USER, "a"), Message(Role.ASSISTANT, "b")))
        self.assertIsInstance(conv.messages[1].role, Role)

    def test_t2_count_out_of_range(self):
        for raw in ([], alternating(LIMITS.max_messages + 2)):
            with self.subTest(n=len(raw)), self.assertRaises(InvalidConversationError) as ctx:
                Conversation.create(raw, LIMITS)
            self.assertEqual(ctx.exception.message, COUNT_MESSAGE.format(max=5))
            self.assertEqual(ctx.exception.error_code, "VALIDATION_ERROR")

    def test_t2_max_plus_one_even_count(self):
        with self.assertRaises(InvalidConversationError) as ctx:
            Conversation.create(alternating(LIMITS.max_messages + 1), LIMITS)
        self.assertEqual(ctx.exception.message, COUNT_MESSAGE.format(max=5))

    def test_max_messages_is_allowed(self):
        conv = Conversation.create(alternating(LIMITS.max_messages), LIMITS)
        self.assertEqual(len(conv.messages), 5)

    def test_t3_order_violations(self):
        cases = {
            "starts_with_assistant": [("assistant", "a"), ("user", "q")],
            "ends_with_assistant": [("user", "q"), ("assistant", "a")],
            "user_user": [("user", "q"), ("user", "q2"), ("user", "q3")],
            "unknown_role": [("bot", "q")],
        }
        for name, raw in cases.items():
            with self.subTest(name), self.assertRaises(InvalidConversationError) as ctx:
                Conversation.create(raw, LIMITS)
            self.assertEqual(ctx.exception.message, ORDER_MESSAGE)

    def test_non_string_role_is_invalid_conversation(self):
        # 스키마를 거치지 않은 호출(설계안 4.2): 해시 불가·비문자열 role도 TypeError가 아니라 400
        cases = {
            "list_role": [(["user"], "q")],
            "dict_role": [({"role": "user"}, "q")],
            "set_role": [({"user"}, "q")],
            "int_role": [(1, "q")],
            "none_role": [(None, "q")],
            "bytes_role": [(b"user", "q")],
            "unhashable_later": [("user", "q"), (["assistant"], "a"), ("user", "q")],
        }
        for name, raw in cases.items():
            with self.subTest(name), self.assertRaises(InvalidConversationError) as ctx:
                Conversation.create(raw, LIMITS)
            self.assertEqual(ctx.exception.message, ORDER_MESSAGE)
            self.assertEqual(ctx.exception.error_code, "VALIDATION_ERROR")

    def test_t4_blank_content(self):
        for raw in ([("user", "   ")], [("user", "q"), ("assistant", " "), ("user", "q")]):
            with self.subTest(raw=raw), self.assertRaises(InvalidConversationError) as ctx:
                Conversation.create(raw, LIMITS)
            self.assertEqual(ctx.exception.message, EMPTY_CONTENT_MESSAGE)

    def test_t5_count_checked_before_blank_content(self):
        raw = alternating(LIMITS.max_messages + 2)
        raw[0] = ("user", "  ")
        with self.assertRaises(InvalidConversationError) as ctx:
            Conversation.create(raw, LIMITS)
        self.assertEqual(ctx.exception.message, COUNT_MESSAGE.format(max=5))

    def test_t6_order_checked_before_blank_content(self):
        with self.assertRaises(InvalidConversationError) as ctx:
            Conversation.create([("assistant", " "), ("user", "q")], LIMITS)
        self.assertEqual(ctx.exception.message, ORDER_MESSAGE)

    def test_error_message_has_no_request_content(self):
        with self.assertRaises(InvalidConversationError) as ctx:
            Conversation.create([("assistant", "secret-content")], LIMITS)
        self.assertNotIn("secret-content", ctx.exception.message)


class AnswerTest(unittest.TestCase):
    def test_t7_blank_answer_is_generation_error(self):
        with self.assertRaises(AnswerGenerationError) as ctx:
            Answer(text=" ", mode=AnswerMode.MOCK)
        self.assertEqual((ctx.exception.status_code, ctx.exception.error_code), (502, "ANSWER_GENERATION_FAILED"))

    def test_t8_sources_kept_as_is(self):
        sources = tuple(Source(ref=3 - i % 3, chunk_id=f"c{i}", source_ref_id=f"doc_{i}") for i in range(30))
        answer = Answer(text="t [3]", mode=AnswerMode.RAG, sources=sources)
        self.assertEqual(answer.sources, sources)
        self.assertEqual(len(answer.sources), 30)
        self.assertEqual(answer.sources[0].ref, 3)

    def test_default_sources_empty(self):
        self.assertEqual(Answer(text="t", mode=AnswerMode.LLM).sources, ())


if __name__ == "__main__":
    unittest.main()
