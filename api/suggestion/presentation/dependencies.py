from api.suggestion.application.service import SuggestionService


def provide_suggestion_service() -> SuggestionService:
    """Depends 플레이스홀더. api/container.py의 wire_dependencies가 연결한다."""
    raise NotImplementedError("SuggestionService 의존성이 연결되지 않았습니다.")
