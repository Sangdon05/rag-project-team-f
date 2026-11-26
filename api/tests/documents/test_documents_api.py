"""documents 설계안 8절 API (D7~D12)."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from api.documents.application.service import DocumentService
from api.documents.domain.exceptions import DocumentSourceError
from api.documents.presentation.dependencies import provide_document_service
from api.tests.documents.fakes import FakeDocumentStore
from api.tests.support import CORS_ORIGIN, SETTINGS, client_for, make_app

URL = "/api/v1/documents"
PILOT_ID = "bulbasaur_red_blue"
PILOT_FILE = Path("data/synthetic/pilot") / f"{PILOT_ID}.md"


class DocumentsApiTest(unittest.IsolatedAsyncioTestCase):
    def client(self, store=None, settings=SETTINGS, raise_app_exceptions=True):
        app = make_app(settings)
        if store is not None:
            service = DocumentService(store)
            app.dependency_overrides[provide_document_service] = lambda: service
        return client_for(app, raise_app_exceptions=raise_app_exceptions)

    def assert_error(self, r, status, code):
        body = r.json()
        self.assertEqual(r.status_code, status, r.text)
        self.assertEqual(set(body), {"success", "error_code", "message"})
        self.assertEqual((body["success"], body["error_code"]), (False, code))

    async def test_d7_pilot_document(self):
        self.assertEqual(SETTINGS.documents_dir, "data/synthetic/pilot")
        async with self.client() as c:
            r = await c.get(f"{URL}/{PILOT_ID}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIs(body["success"], True)
        self.assertEqual(body["data"]["source_ref_id"], PILOT_ID)
        self.assertEqual(body["data"]["markdown"], PILOT_FILE.read_bytes().decode("utf-8"))

    async def test_d7_temp_dir_markdown_is_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = "# t\r\n<b>raw</b>  \r\n"
            Path(tmp, "t-1.md").write_bytes(raw.encode("utf-8"))
            async with self.client(settings=replace(SETTINGS, documents_dir=tmp)) as c:
                r = await c.get(f"{URL}/t-1")
        self.assertEqual(r.json(), {"success": True, "data": {"source_ref_id": "t-1", "markdown": raw}})

    async def test_d8_invalid_id_is_validation_error(self):
        async with self.client() as c:
            for path in (f"{URL}/a.md", f"{URL}/%2E%2E", f"{URL}/a%20b", f"{URL}/{PILOT_ID}.md"):
                with self.subTest(path=path):
                    r = await c.get(path)
                    self.assert_error(r, 400, "VALIDATION_ERROR")
                    self.assertEqual(r.json()["message"], "source_ref_id는 영문, 숫자, '_', '-'만 쓸 수 있습니다.")

    async def test_d9_missing_document(self):
        async with self.client() as c:
            r = await c.get(f"{URL}/no_such_doc")
        self.assert_error(r, 404, "DOCUMENT_NOT_FOUND")
        self.assertEqual(r.json()["message"], "문서를 찾을 수 없습니다.")

    async def test_d10_slash_or_empty_id_does_not_match_route(self):
        async with self.client() as c:
            for path in (f"{URL}/a/b", f"{URL}/a%2Fb", f"{URL}/"):
                with self.subTest(path=path):
                    self.assert_error(await c.get(path), 404, "NOT_FOUND")

    async def test_d11_source_failure_fake(self):
        async with self.client(FakeDocumentStore(error=DocumentSourceError())) as c:
            r = await c.get(f"{URL}/x")
        self.assert_error(r, 502, "DOCUMENT_SOURCE_FAILED")

    async def test_d11_missing_documents_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp, "nope"))
            with self.assertLogs("api.documents.infrastructure.file_store", "WARNING"):
                async with self.client(settings=replace(SETTINGS, documents_dir=missing)) as c:
                    r = await c.get(f"{URL}/{PILOT_ID}")
        self.assert_error(r, 502, "DOCUMENT_SOURCE_FAILED")
        self.assertNotIn(tmp, r.text)

    async def test_d12_unhandled_error_hides_detail_and_keeps_cors(self):
        store = FakeDocumentStore(error=RuntimeError("/abs/secret"))
        with self.assertLogs("api.error_handlers", level="ERROR"):
            async with self.client(store, raise_app_exceptions=False) as c:
                r = await c.get(f"{URL}/x", headers={"Origin": CORS_ORIGIN})
        self.assert_error(r, 500, "INTERNAL_ERROR")
        self.assertNotIn("/abs/secret", r.text)
        self.assertEqual(r.headers.get("access-control-allow-origin"), CORS_ORIGIN)

    async def test_post_is_method_not_allowed(self):
        async with self.client() as c:
            r = await c.post(f"{URL}/{PILOT_ID}")
        self.assert_error(r, 405, "METHOD_NOT_ALLOWED")
        self.assertIn("GET", r.headers.get("allow", ""))


if __name__ == "__main__":
    unittest.main()
