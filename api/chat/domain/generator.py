from abc import ABC, abstractmethod

from api.chat.domain.answer import Answer
from api.chat.domain.conversation import Conversation


class AnswerGenerator(ABC):
    """답변 생성기 포트. 계약 원본은 docs/references/api-rag-integration.md 2절."""

    @abstractmethod
    async def generate(self, conversation: Conversation) -> Answer: ...
