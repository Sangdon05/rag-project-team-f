"""The RAG boundary uses fakes; never calls a provider or database."""
import unittest
from unittest.mock import patch

from api.chat.domain.answer import AnswerMode
from api.chat.domain.conversation import Conversation, ConversationLimits
from api.chat.domain.exceptions import AnswerGenerationError, InvalidConversationError
from api.chat.infrastructure.rag_generator import RagAnswerGenerator
from solar_handoff.src.conversation import ConversationInputError


CONV = Conversation.create([("user", "first"), ("assistant", "previous"), ("user", "followup")], ConversationLimits(5))


async def direct_runner(call):
    return call()


class FakeService:
    def __init__(self, payload=None, error=None):
        self.payload, self.error, self.calls = payload, error, []

    def answer(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.payload


class RagGeneratorTest(unittest.IsolatedAsyncioTestCase):
    async def test_full_history_and_numbered_sources_preserved(self):
        payload = {"mode": "rag", "answer": "answer [2] [1]", "sources": [
            {"ref": 2, "chunk_id": "pokemon:7#learnset_level", "source_ref_id": "pokemon:7"},
            {"ref": 1, "chunk_id": "pokemon:95#profile", "source_ref_id": "095"}]}
        service = FakeService(payload)
        result = await RagAnswerGenerator(lambda: service, direct_runner).generate(CONV)
        self.assertEqual(service.calls, [[{"role": "user", "content": "first"},
                                       {"role": "assistant", "content": "previous"},
                                       {"role": "user", "content": "followup"}]])
        self.assertEqual((result.text, result.mode), (payload["answer"], AnswerMode.RAG))
        self.assertEqual([(s.ref, s.source_ref_id) for s in result.sources], [(2, "007"), (1, "095")])

    async def test_document_id_fallback(self):
        service = FakeService({"mode": "rag", "answer": "answer [1]", "sources": [
            {"ref": 1, "chunk_id": "pokemon:1#profile", "document_id": "pokemon:1"}]})
        result = await RagAnswerGenerator(lambda: service, direct_runner).generate(CONV)
        self.assertEqual(result.sources[0].source_ref_id, "001")

    async def test_insufficient_evidence_is_success_without_sources(self):
        service = FakeService({"mode": "rag", "answer": "확인할 수 없습니다.", "sources": []})
        result = await RagAnswerGenerator(lambda: service, direct_runner).generate(CONV)
        self.assertEqual(result.sources, ())

    async def test_bad_source_and_mode_rejected_without_fallback(self):
        for source in ("../007", "pokemon:0", "pokemon:152", 7, "7"):
            with self.subTest(source=source):
                service = FakeService({"mode": "rag", "answer": "answer", "sources": [
                    {"ref": 1, "chunk_id": "pokemon:7#profile", "source_ref_id": source}]})
                with self.assertRaises(AnswerGenerationError):
                    await RagAnswerGenerator(lambda: service, direct_runner).generate(CONV)
                self.assertEqual(len(service.calls), 1)
        service = FakeService({"mode": "llm", "answer": "answer", "sources": []})
        with self.assertRaises(AnswerGenerationError):
            await RagAnswerGenerator(lambda: service, direct_runner).generate(CONV)

    async def test_input_error_is_400_and_provider_error_is_redacted_502_once(self):
        for error, expected in ((ConversationInputError("private"), InvalidConversationError),
                                (TimeoutError("private"), AnswerGenerationError)):
            service = FakeService(error=error)
            with self.assertRaises(expected) as caught:
                await RagAnswerGenerator(lambda: service, direct_runner).generate(CONV)
            self.assertNotIn("private", caught.exception.message)
            self.assertEqual(len(service.calls), 1)

    async def test_mock_wiring_does_not_construct_solar_service(self):
        from api.container import create_answer_generator
        from api.shared.settings import Settings
        from api.chat.infrastructure.mock_generator import MockAnswerGenerator
        with patch("solar_handoff.src.conversation.create_service", side_effect=AssertionError("not needed")):
            self.assertIsInstance(create_answer_generator(Settings(answer_backend="mock")), MockAnswerGenerator)
