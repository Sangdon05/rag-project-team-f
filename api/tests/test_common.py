"""공통 테스트 (health 설계안 0.6, C1~C6)."""

import os
import unittest
from unittest import mock

from api.main import create_app
from api.shared.exceptions import InvalidInputError, NotFoundError, UpstreamError
from api.shared.settings import Settings
from api.tests.support import CORS_ORIGIN, SETTINGS, client_for, make_app


class ErrorShapeTest(unittest.IsolatedAsyncioTestCase):
    def assert_error(self, r, status, code):
        body = r.json()
        self.assertEqual(r.status_code, status)
        self.assertEqual(set(body), {"success", "error_code", "message"})
        self.assertIs(body["success"], False)
        self.assertEqual(body["error_code"], code)
        self.assertIsInstance(body["message"], str)
        self.assertNotIn("detail", body)

    async def test_c1_unknown_path_is_not_found(self):
        async with client_for(make_app()) as c:
            r = await c.get("/no-such-path")
        self.assert_error(r, 404, "NOT_FOUND")

    async def test_c2_wrong_method_is_method_not_allowed(self):
        async with client_for(make_app()) as c:
            r = await c.delete("/health")
        self.assert_error(r, 405, "METHOD_NOT_ALLOWED")
        self.assertIn("GET", r.headers.get("allow", ""))

    async def test_c3_unhandled_exception_hides_detail(self):
        app = make_app()

        async def boom():
            raise RuntimeError("sk-secret /Users/x")

        app.add_api_route("/boom", boom)
        with self.assertLogs("api.error_handlers", level="ERROR"):
            async with client_for(app, raise_app_exceptions=False) as c:
                r = await c.get("/boom")
        self.assert_error(r, 500, "INTERNAL_ERROR")
        for leaked in ("sk-secret", "Traceback", "/Users/x"):
            self.assertNotIn(leaked, r.text)

    async def test_c3_unhandled_exception_keeps_cors_header(self):
        # 처리 못 한 예외 미들웨어가 CORS 안쪽에 있어 500에도 허용 헤더가 붙는다 (health 설계안 0.4)
        app = make_app()

        async def boom():
            raise RuntimeError("secret-detail /Users/x")

        app.add_api_route("/boom", boom)
        with self.assertLogs("api.error_handlers", level="ERROR"):
            async with client_for(app, raise_app_exceptions=False) as c:
                r = await c.get("/boom", headers={"Origin": CORS_ORIGIN})
        self.assert_error(r, 500, "INTERNAL_ERROR")
        self.assertEqual(r.json()["message"], "서버 내부 오류가 발생했습니다.")
        self.assertEqual(r.headers.get("access-control-allow-origin"), CORS_ORIGIN)
        for leaked in ("secret-detail", "Traceback", "/Users/x"):
            self.assertNotIn(leaked, r.text)

    async def test_unhandled_exception_without_cors(self):
        app = create_app(Settings(answer_backend="mock", cors_origins=[], max_messages=20))

        async def boom():
            raise RuntimeError("secret-detail")

        app.add_api_route("/boom", boom)
        with self.assertLogs("api.error_handlers", level="ERROR"):
            async with client_for(app, raise_app_exceptions=False) as c:
                r = await c.get("/boom", headers={"Origin": CORS_ORIGIN})
        self.assert_error(r, 500, "INTERNAL_ERROR")
        self.assertNotIn("access-control-allow-origin", r.headers)

    async def test_api_error_subclasses_map_to_their_codes(self):
        app = make_app()
        cases = {
            "/invalid": (InvalidInputError("잘못된 입력입니다."), 400, "VALIDATION_ERROR"),
            "/missing": (NotFoundError("없습니다."), 404, "NOT_FOUND"),
            "/upstream": (UpstreamError("외부 오류입니다."), 502, "UPSTREAM_ERROR"),
        }
        for path, (exc, _, _) in cases.items():
            async def raiser(exc=exc):
                raise exc

            app.add_api_route(path, raiser)
        async with client_for(app) as c:
            for path, (exc, status, code) in cases.items():
                with self.subTest(path=path):
                    r = await c.get(path)
                    self.assert_error(r, status, code)
                    self.assertEqual(r.json()["message"], exc.message)

    async def test_c4_cors_preflight_allows_only_configured_origin(self):
        async with client_for(make_app()) as c:
            ok = await c.options("/health", headers={"Origin": CORS_ORIGIN, "Access-Control-Request-Method": "GET"})
            bad = await c.options("/health", headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "GET"})
        self.assertEqual(ok.headers.get("access-control-allow-origin"), CORS_ORIGIN)
        self.assertNotIn("access-control-allow-origin", bad.headers)

    async def test_no_cors_middleware_when_origins_empty(self):
        app = create_app(Settings(answer_backend="mock", cors_origins=[], max_messages=20))
        async with client_for(app) as c:
            r = await c.get("/health", headers={"Origin": CORS_ORIGIN})
        self.assertNotIn("access-control-allow-origin", r.headers)


class SettingsTest(unittest.TestCase):
    def from_env(self, **env):
        with mock.patch.dict(os.environ, env, clear=True):
            return Settings.from_env()

    def test_defaults(self):
        s = self.from_env()
        self.assertEqual(
            (s.answer_backend, s.cors_origins, s.max_messages, s.documents_dir),
            ("mock", [], 20, "data/synthetic/pilot"),
        )

    def test_reads_values_and_splits_origins(self):
        s = self.from_env(
            ANSWER_BACKEND="llm",
            API_CORS_ORIGINS=" http://a.test , ,http://b.test,",
            API_MAX_MESSAGES="5",
            API_DOCUMENTS_DIR="docs/x",
        )
        self.assertEqual(
            (s.answer_backend, s.cors_origins, s.max_messages, s.documents_dir),
            ("llm", ["http://a.test", "http://b.test"], 5, "docs/x"),
        )

    def test_c5_invalid_max_messages_fails(self):
        for raw in ("abc", "0", "-1", ""):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.from_env(API_MAX_MESSAGES=raw)


class StartupTest(unittest.TestCase):
    def test_c6_unknown_answer_backend_fails_at_startup(self):
        with self.assertRaises(RuntimeError):
            create_app(Settings(answer_backend="unknown", cors_origins=[], max_messages=20))

    def test_known_backends_start(self):
        # llm 분기는 ChatOpenAI를 만들기만 한다 (네트워크 호출 없음). 가짜 키·모델명으로 고정한다.
        env = {"OPENAI_CHAT_MODEL": "test-model", "OPENAI_API_KEY": "test-key-not-secret"}  # security: allow 테스트 더미 키, 네트워크 호출 없음
        for backend in ("mock", "llm"):
            with self.subTest(backend=backend), mock.patch.dict(os.environ, env):
                create_app(Settings(answer_backend=backend, cors_origins=[], max_messages=20))

    def test_settings_given_skips_dotenv(self):
        with mock.patch("api.main.load_dotenv") as load, mock.patch.object(Settings, "from_env") as from_env:
            create_app(SETTINGS)
        load.assert_not_called()
        from_env.assert_not_called()

    def test_settings_none_loads_dotenv_then_env(self):
        with mock.patch("api.main.load_dotenv") as load, mock.patch.object(
            Settings, "from_env", return_value=SETTINGS
        ) as from_env:
            create_app()
        load.assert_called_once_with()
        from_env.assert_called_once_with()

    def test_openapi_lists_routes(self):
        paths = make_app(SETTINGS).openapi()["paths"]
        self.assertIn("/health", paths)
        self.assertIn("/api/v1/suggestion", paths)
        self.assertIn("/api/v1/chat", paths)
        self.assertIn("/api/v1/documents/{source_ref_id}", paths)


if __name__ == "__main__":
    unittest.main()
