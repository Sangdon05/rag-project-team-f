"""구현체 선택·생성과 provide_* 연결 (R5). 이 파일만 구현체를 고른다."""

from fastapi import FastAPI

from api.shared.settings import Settings
from api.suggestion.application.service import SuggestionService
from api.suggestion.infrastructure.fake_provider import FakeSuggestionProvider
from api.suggestion.presentation.dependencies import provide_suggestion_service

ANSWER_BACKENDS = ("mock", "llm")


def validate_answer_backend(settings: Settings) -> None:
    """ANSWER_BACKEND가 허용값 밖이면 앱 시작을 막는다. 생성기 연결은 chat 슬라이스에서 추가한다."""
    if settings.answer_backend not in ANSWER_BACKENDS:
        raise RuntimeError(
            f"알 수 없는 ANSWER_BACKEND: {settings.answer_backend!r} ({' | '.join(ANSWER_BACKENDS)})"
        )


def create_suggestion_service() -> SuggestionService:
    return SuggestionService(FakeSuggestionProvider())


def wire_dependencies(app: FastAPI, settings: Settings) -> None:
    validate_answer_backend(settings)
    suggestion_service = create_suggestion_service()   # 상태 없음: 앱당 하나
    app.dependency_overrides.update({
        provide_suggestion_service: lambda: suggestion_service,
    })
