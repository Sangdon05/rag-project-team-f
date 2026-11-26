"""앱 조립: (settings 없을 때만) load_dotenv → Settings → 예외 미들웨어·CORS → 예외 핸들러 → 의존성 연결 → 라우터 등록."""

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat.presentation.router import router as chat_router
from api.container import wire_dependencies
from api.documents.presentation.router import router as documents_router
from api.error_handlers import UnhandledExceptionMiddleware, register_exception_handlers
from api.health.presentation.router import router as health_router
from api.shared.settings import Settings
from api.suggestion.presentation.router import router as suggestion_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """앱을 만든다. settings를 넘기면 .env를 읽지 않는다 (테스트가 개인 .env 영향을 막는다)."""
    if settings is None:
        load_dotenv()
        settings = Settings.from_env()
    app = FastAPI(title="Pokédex RAG API")
    # 나중에 add한 미들웨어가 바깥이다. 예외 미들웨어를 먼저 add해 CORS 안쪽에 둔다 (500에도 CORS 헤더).
    app.add_middleware(UnhandledExceptionMiddleware)
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
    app.include_router(documents_router)
    return app


app = create_app()
