"""검색 없이 LLM이 답하는 생성기. RAG 연결 전 임시 모드 (mode=llm, sources 없음)."""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from api.chat.domain.answer import GENERATION_FAILED_MESSAGE, Answer, AnswerMode
from api.chat.domain.conversation import Conversation, Role
from api.chat.domain.exceptions import AnswerGenerationError
from api.chat.domain.generator import AnswerGenerator

logger = logging.getLogger(__name__)

# 임시 프롬프트. RAG 프롬프트는 rag-developer 담당이며 여기로 옮겨 오지 않는다.
SYSTEM_PROMPT = (
    "You are a Pokédex assistant for English Pokémon Red and Blue (the original 151 Pokémon). "
    "Answer only with Red/Blue values and never mention values from other generations. "
    "You have no reference documents, so if you are not sure, say that you cannot confirm it. "
    "Reply in the same language as the user."
)


class LlmAnswerGenerator(AnswerGenerator):
    def __init__(self, model: BaseChatModel) -> None:   # 모델은 container가 넣는다 (R4)
        self.model = model

    def _to_messages(self, conversation: Conversation) -> list[BaseMessage]:
        messages: list[BaseMessage] = [SystemMessage(SYSTEM_PROMPT)]
        for message in conversation.history:
            cls = HumanMessage if message.role == Role.USER else AIMessage
            messages.append(cls(message.content))
        messages.append(HumanMessage(conversation.question))
        return messages

    async def generate(self, conversation: Conversation) -> Answer:
        try:
            reply = await self.model.ainvoke(self._to_messages(conversation))
        except Exception as exc:
            logger.warning("LLM 호출 실패: %s", type(exc).__name__)   # 원문·키를 남기지 않는다
            raise AnswerGenerationError(GENERATION_FAILED_MESSAGE) from exc
        text = reply.content if isinstance(reply.content, str) else ""
        if not text.strip():
            logger.warning("LLM 빈 응답")
            raise AnswerGenerationError(GENERATION_FAILED_MESSAGE)
        return Answer(text=text, mode=AnswerMode.LLM)
