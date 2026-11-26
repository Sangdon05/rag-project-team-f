"""고정 응답 생성기. 평가셋 정답을 넣지 않는다 (R16). 프론트 연동 확인용."""

from api.chat.domain.answer import Answer, AnswerMode
from api.chat.domain.conversation import Conversation
from api.chat.domain.generator import AnswerGenerator

MOCK_TEXT = "[mock] 아직 RAG가 연결되지 않아 고정 응답을 돌려줍니다. 받은 질문: {question}"
QUESTION_PREVIEW_CHARS = 100


class MockAnswerGenerator(AnswerGenerator):
    async def generate(self, conversation: Conversation) -> Answer:
        question = conversation.question[:QUESTION_PREVIEW_CHARS]
        return Answer(text=MOCK_TEXT.format(question=question), mode=AnswerMode.MOCK)
