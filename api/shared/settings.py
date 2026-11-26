"""환경 변수 읽기 (R12). domain은 import하지 않는다.

값 검증: API_MAX_MESSAGES는 여기서, ANSWER_BACKEND 허용값은 container가 시작 시 검사한다.
"""

import os
from dataclasses import dataclass, field

DEFAULT_ANSWER_BACKEND = "mock"
DEFAULT_MAX_MESSAGES = 20
DEFAULT_DOCUMENTS_DIR = "data/synthetic/pilot"


def _parse_origins(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_max_messages(raw: str) -> int:
    try:
        value = int(raw.strip())
    except ValueError:
        raise ValueError("API_MAX_MESSAGES는 1 이상의 정수여야 합니다.") from None
    if value < 1:
        raise ValueError("API_MAX_MESSAGES는 1 이상의 정수여야 합니다.")
    return value


@dataclass(frozen=True)
class Settings:
    answer_backend: str = DEFAULT_ANSWER_BACKEND
    cors_origins: list[str] = field(default_factory=list)
    max_messages: int = DEFAULT_MAX_MESSAGES
    documents_dir: str = DEFAULT_DOCUMENTS_DIR

    @classmethod
    def from_env(cls) -> "Settings":
        """os.environ에서 읽는다. API_MAX_MESSAGES가 잘못되면 ValueError (앱 시작 실패)."""
        return cls(
            answer_backend=os.environ.get("ANSWER_BACKEND", "").strip() or DEFAULT_ANSWER_BACKEND,
            cors_origins=_parse_origins(os.environ.get("API_CORS_ORIGINS", "")),
            max_messages=_parse_max_messages(os.environ.get("API_MAX_MESSAGES", str(DEFAULT_MAX_MESSAGES))),
            documents_dir=os.environ.get("API_DOCUMENTS_DIR", "").strip() or DEFAULT_DOCUMENTS_DIR,
        )
