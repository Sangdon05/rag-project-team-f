from collections.abc import Sequence

from api.chat.domain.answer import Answer
from api.chat.domain.conversation import Conversation, ConversationLimits
from api.chat.domain.generator import AnswerGenerator


class AskService:
    def __init__(self, generator: AnswerGenerator, limits: ConversationLimits) -> None:
        self.generator = generator
        self.limits = limits

    async def ask(self, raw: Sequence[tuple[str, str]]) -> Answer:
        conversation = Conversation.create(raw, self.limits)   # 규칙은 도메인 (R3)
        return await self.generator.generate(conversation)
