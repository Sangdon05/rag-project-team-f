"""chat 테스트용 fake 생성기. 실제 LLM·네트워크를 부르지 않는다 (R15)."""

from api.chat.domain.answer import Answer, AnswerMode
from api.chat.domain.generator import AnswerGenerator


class FakeGenerator(AnswerGenerator):
    def __init__(self, answer: Answer | None = None, error: Exception | None = None) -> None:
        self.answer = answer or Answer(text="fake", mode=AnswerMode.MOCK)
        self.error = error
        self.calls = []

    async def generate(self, conversation):
        self.calls.append(conversation)
        if self.error is not None:
            raise self.error
        return self.answer
