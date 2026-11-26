from api.chat.application.service import AskService


def provide_ask_service() -> AskService:
    """Depends 플레이스홀더. api/container.py의 wire_dependencies가 연결한다."""
    raise NotImplementedError("AskService 의존성이 연결되지 않았습니다.")
