"""Adapt the stateless Solar service to the team's answer port."""

import re

from api.chat.domain.answer import Answer, AnswerMode, EmbeddingInfo, Source
from api.chat.domain.exceptions import AnswerGenerationError, InvalidConversationError
from api.chat.domain.generator import AnswerGenerator


def _source_id(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{3}", value):
        return value
    match = re.fullmatch(r"pokemon:([1-9][0-9]{0,2})", value) if isinstance(value, str) else None
    if match and 1 <= int(match[1]) <= 151:
        return f"{int(match[1]):03d}"
    raise ValueError("invalid source identifier")


class RagAnswerGenerator(AnswerGenerator):
    def __init__(self, service_factory, runner):
        self._service_factory = service_factory
        self._runner = runner

    async def generate(self, conversation):
        from solar_handoff.src.conversation import ConversationInputError

        messages = [{"role": message.role.value, "content": message.content}
                    for message in conversation.messages]
        try:
            payload = await self._runner(lambda: self._service_factory().answer(messages))
            if (not isinstance(payload, dict) or payload.get("mode") != "rag"
                    or not isinstance(payload.get("answer"), str)
                    or not isinstance(payload.get("sources"), list)):
                raise ValueError("invalid RAG payload")
            sources = []
            for row in payload["sources"]:
                if (not isinstance(row, dict) or type(row.get("ref")) is not int or row["ref"] < 1
                        or not isinstance(row.get("chunk_id"), str) or not row["chunk_id"]):
                    raise ValueError("invalid RAG source")
                source_id = row.get("source_ref_id", row.get("document_id"))
                sources.append(Source(row["ref"], row["chunk_id"], _source_id(source_id)))
            embedding = None
            if "embedding" in payload:
                metadata = payload["embedding"]
                if not isinstance(metadata, dict):
                    raise ValueError("invalid RAG embedding metadata")
                embedding = EmbeddingInfo(metadata.get("query_model"), metadata.get("document_model"))
            return Answer(payload["answer"], AnswerMode.RAG, tuple(sources), embedding)
        except ConversationInputError:
            raise InvalidConversationError("대화 내용 또는 질문의 길이를 확인해 주세요.") from None
        except Exception:
            raise AnswerGenerationError("답변을 생성하지 못했습니다. 잠시 후 다시 시도하세요.") from None
