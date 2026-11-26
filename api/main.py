"""앱 조립: load_dotenv → Settings → CORS → 예외 핸들러 → 의존성 연결 → 라우터 등록."""

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat.presentation.router import router as chat_router
from api.container import wire_dependencies
from api.error_handlers import register_exception_handlers
from api.health.presentation.router import router as health_router
from api.shared.settings import Settings
from api.suggestion.presentation.router import router as suggestion_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """앱을 만든다. 테스트는 settings를 직접 넘겨 개인 .env 영향을 막는다."""
    load_dotenv()
    settings = settings or Settings.from_env()
    app = FastAPI(title="Pokédex RAG API")
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )
    register_exception_handlers(app)
    wire_dependencies(app, settings)
    app.include_router(health_router)
    app.include_router(suggestion_router)
    app.include_router(chat_router)
    return app


app = create_app()
