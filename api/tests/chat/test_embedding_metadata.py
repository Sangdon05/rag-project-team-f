"""Optional display metadata crosses the real adapter and HTTP schema without inference."""

import os
import unittest
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from api.chat.application.service import AskService
from api.chat.domain.answer import Answer, AnswerMode, EmbeddingInfo
from api.chat.domain.conversation import Conversation, ConversationLimits
from api.chat.domain.exceptions import AnswerGenerationError
from api.chat.infrastructure.llm_generator import LlmAnswerGenerator
from api.chat.infrastructure.mock_generator import MockAnswerGenerator
from api.chat.infrastructure.rag_generator import RagAnswerGenerator
from api.chat.presentation.dependencies import provide_ask_service
from api.tests.chat.fakes import FakeGenerator
from api.tests.chat.test_rag_generator import FakeService, direct_runner
from api.tests.support import client_for, make_app


MODELS = {"query_model": "provider/query-v1", "document_model": "provider/document-v2"}
MESSAGES = [{"role": "user", "content": "first"},
            {"role": "assistant", "content": "previous"},
            {"role": "user", "content": "followup"}]
CONVERSATION = Conversation.create([(row["role"], row["content"]) for row in MESSAGES], ConversationLimits(5))


def rag_payload():
    return {"answer": "Answer [2] [1]", "mode": "rag", "sources": [
        {"ref": 2, "chunk_id": "pokemon:7#profile", "source_ref_id": "pokemon:7"},
        {"ref": 1, "chunk_id": "pokemon:95#profile", "source_ref_id": "095"}]}


def malformed_metadata():
    return [None, [], "model", {}, {"query_model": "q"}, {"document_model": "d"},
            *[{**MODELS, field: value}
              for field in MODELS
              for value in (None, 7, "", "   ", "m" * 201,
                            "m" + chr(0), "m\n", "m" + chr(127), "m" + chr(133),
                            "m" + chr(0x202E), "m" + chr(0xD800))]]


class EmbeddingInfoTest(unittest.TestCase):
    def test_valid_models_preserved_and_existing_answer_defaults_to_absence(self):
        metadata = EmbeddingInfo(**MODELS)
        answer = Answer("answer", AnswerMode.RAG, embedding=metadata)
        self.assertEqual((answer.embedding.query_model, answer.embedding.document_model),
                         (MODELS["query_model"], MODELS["document_model"]))
        self.assertIsNone(Answer("legacy", AnswerMode.RAG).embedding)
        self.assertEqual(EmbeddingInfo("q" * 200, "d" * 200).query_model, "q" * 200)

    def test_non_rag_answer_cannot_claim_embedding_metadata(self):
        for mode in (AnswerMode.MOCK, AnswerMode.LLM):
            with self.subTest(mode=mode), self.assertRaises(AnswerGenerationError) as caught:
                Answer("answer", mode, embedding=EmbeddingInfo(**MODELS))
            self.assertEqual((caught.exception.status_code, caught.exception.error_code),
                             (502, "ANSWER_GENERATION_FAILED"))

    def test_invalid_model_ids_raise_only_redacted_generation_error(self):
        for field in MODELS:
            for value in (None, 7, "", "   ", "x" * 201, "raw-private\n", "raw-private\x00",
                          "raw-private" + chr(0x202E)):
                with self.subTest(field=field, value=repr(value)):
                    with self.assertRaises(AnswerGenerationError) as caught:
                        EmbeddingInfo(**{**MODELS, field: value})
                    self.assertNotIn("raw-private", caught.exception.message)
                    self.assertEqual(caught.exception.status_code, 502)
        with self.assertRaises(AnswerGenerationError):
            Answer("answer", AnswerMode.RAG, embedding=MODELS)


class EmbeddingMetadataApiTest(unittest.IsolatedAsyncioTestCase):
    def client(self, generator):
        app = make_app()
        service = AskService(generator, ConversationLimits(5))
        app.dependency_overrides[provide_ask_service] = lambda: service
        return client_for(app)

    async def test_actual_adapter_to_http_preserves_both_models_history_and_sources(self):
        payload = {**rag_payload(), "embedding": MODELS.copy()}
        service = FakeService(payload)
        generator = RagAnswerGenerator(lambda: service, direct_runner)
        async with self.client(generator) as client:
            response = await client.post("/api/v1/chat", json={"messages": MESSAGES})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "data": {
            "answer": payload["answer"], "mode": "rag", "embedding": MODELS,
            "sources": [{"ref": 2, "chunk_id": "pokemon:7#profile", "source_ref_id": "007"},
                        {"ref": 1, "chunk_id": "pokemon:95#profile", "source_ref_id": "095"}]}})
        self.assertEqual(service.calls, [MESSAGES])
        self.assertEqual(payload["embedding"], MODELS)

    async def test_legacy_rag_mock_llm_have_exact_original_three_fields(self):
        service = FakeService(rag_payload())
        generators = [RagAnswerGenerator(lambda: service, direct_runner),
                      MockAnswerGenerator(),
                      LlmAnswerGenerator(FakeListChatModel(responses=["llm answer"])),
                      FakeGenerator(Answer("legacy RAG", AnswerMode.RAG))]
        for generator in generators:
            with self.subTest(generator=type(generator).__name__):
                async with self.client(generator) as client:
                    response = await client.post("/api/v1/chat", json={"messages": MESSAGES})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(set(response.json()["data"]), {"answer", "mode", "sources"})

    async def test_every_malformed_provided_metadata_is_one_redacted_502_without_fallback(self):
        for index, metadata in enumerate(malformed_metadata()):
            with self.subTest(case=index):
                service = FakeService({**rag_payload(), "embedding": metadata})
                generator = RagAnswerGenerator(lambda: service, direct_runner)
                with self.assertLogs("api.error_handlers", level="ERROR"):
                    async with self.client(generator) as client:
                        response = await client.post("/api/v1/chat", json={"messages": MESSAGES})
                self.assertEqual(response.status_code, 502)
                self.assertEqual(response.json(), {
                    "success": False, "error_code": "ANSWER_GENERATION_FAILED",
                    "message": "답변을 생성하지 못했습니다. 잠시 후 다시 시도하세요."})
                self.assertEqual(service.calls, [MESSAGES])

    async def test_adapter_without_embedding_does_not_add_metadata(self):
        service = FakeService(rag_payload())
        with patch.dict(os.environ, {"UPSTAGE_QUERY_MODEL": "unverified-query-setting",
                                    "UPSTAGE_EMBEDDING_MODEL": "unverified-document-setting",
                                    "OPENAI_CHAT_MODEL": "unrelated-answer-setting"}):
            result = await RagAnswerGenerator(lambda: service, direct_runner).generate(CONVERSATION)
        self.assertIsNone(result.embedding)
        self.assertEqual(service.calls, [MESSAGES])


if __name__ == "__main__":
    unittest.main()
