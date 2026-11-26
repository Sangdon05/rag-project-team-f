"""구현체 선택·생성과 provide_* 연결 (R5). 이 파일만 구현체를 고른다."""

import os

from fastapi import FastAPI

from api.chat.application.service import AskService
from api.chat.domain.conversation import ConversationLimits
from api.chat.domain.generator import AnswerGenerator
from api.chat.infrastructure.llm_generator import LlmAnswerGenerator
from api.chat.infrastructure.mock_generator import MockAnswerGenerator
from api.chat.presentation.dependencies import provide_ask_service
from api.shared.settings import Settings
from api.suggestion.application.service import SuggestionService
from api.suggestion.infrastructure.fake_provider import FakeSuggestionProvider
from api.suggestion.presentation.dependencies import provide_suggestion_service

ANSWER_BACKENDS = ("mock", "llm")


def validate_answer_backend(settings: Settings) -> None:
    """ANSWER_BACKEND가 허용값 밖이면 앱 시작을 막는다."""
    if settings.answer_backend not in ANSWER_BACKENDS:
        raise RuntimeError(
            f"알 수 없는 ANSWER_BACKEND: {settings.answer_backend!r} ({' | '.join(ANSWER_BACKENDS)})"
        )


def create_answer_generator(settings: Settings) -> AnswerGenerator:
    validate_answer_backend(settings)
    if settings.answer_backend == "llm":
        from langchain_openai import ChatOpenAI   # llm 모드에서만 키·모델명이 필요하다

        return LlmAnswerGenerator(ChatOpenAI(model=os.environ["OPENAI_CHAT_MODEL"], temperature=0))
    return MockAnswerGenerator()


def create_ask_service(settings: Settings) -> AskService:
    return AskService(create_answer_generator(settings), ConversationLimits(settings.max_messages))


def create_suggestion_service() -> SuggestionService:
    return SuggestionService(FakeSuggestionProvider())


def wire_dependencies(app: FastAPI, settings: Settings) -> None:
    ask_service = create_ask_service(settings)          # 상태 없음: 앱당 하나
    suggestion_service = create_suggestion_service()
    app.dependency_overrides.update({
        provide_ask_service: lambda: ask_service,
        provide_suggestion_service: lambda: suggestion_service,
    })
