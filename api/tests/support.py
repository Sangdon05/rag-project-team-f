"""api 테스트 공용 도우미. 실제 LLM·네트워크를 부르지 않는다 (R15)."""

import httpx

from api.main import create_app
from api.shared.settings import Settings

CORS_ORIGIN = "http://localhost:5173"
SETTINGS = Settings(
    answer_backend="mock",
    cors_origins=[CORS_ORIGIN],
    max_messages=20,
    documents_dir="data/synthetic/pilot",
)


def make_app(settings: Settings = SETTINGS):
    """항상 설정을 직접 넘긴다 (개인 .env 영향 차단). 모듈 수준 app은 쓰지 않는다."""
    return create_app(settings)


def client_for(app, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return httpx.AsyncClient(transport=transport, base_url="http://test")
