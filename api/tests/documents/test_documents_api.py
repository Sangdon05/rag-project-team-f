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
DEX_ID = "001"
DOCUMENTS_DIR = Path("solar_handoff/documents")


def _dex_file(dex_id: str) -> Path:
    # 한글 파일명의 NFC/NFD 차이를 피하려고 번호 접두어로만 찾는다(읽기만).
    matches = sorted(DOCUMENTS_DIR.glob(f"{dex_id}_*.md"))
    assert len(matches) == 1, matches
    return matches[0]


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

    async def test_d7_solar_handoff_document(self):
        self.assertEqual(SETTINGS.documents_dir, "solar_handoff/documents")
        path = _dex_file(DEX_ID)
        self.assertTrue(path.name.startswith("001_"))
        async with self.client() as c:
            r = await c.get(f"{URL}/{DEX_ID}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIs(body["success"], True)
        self.assertEqual(body["data"]["source_ref_id"], DEX_ID)
        self.assertEqual(body["data"]["markdown"], path.read_bytes().decode("utf-8"))

    async def test_d7_temp_dir_markdown_is_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = "# t\r\n<b>raw</b>  \r\n"
            Path(tmp, "025_x.md").write_bytes(raw.encode("utf-8"))
            async with self.client(settings=replace(SETTINGS, documents_dir=tmp)) as c:
                r = await c.get(f"{URL}/025")
        self.assertEqual(r.json(), {"success": True, "data": {"source_ref_id": "025", "markdown": raw}})

    async def test_d8_invalid_id_is_validation_error(self):
        async with self.client() as c:
            for path in (f"{URL}/1", f"{URL}/001.md", f"{URL}/%2E%2E", f"{URL}/0001", f"{URL}/a%20b"):
                with self.subTest(path=path):
                    r = await c.get(path)
                    self.assert_error(r, 400, "VALIDATION_ERROR")
                    self.assertEqual(r.json()["message"], "source_ref_id는 도감번호 3자리(예: 001)여야 합니다.")

    async def test_d9_missing_document(self):
        async with self.client() as c:
            r = await c.get(f"{URL}/999")
        self.assert_error(r, 404, "DOCUMENT_NOT_FOUND")
        self.assertEqual(r.json()["message"], "문서를 찾을 수 없습니다.")

    async def test_d10_slash_or_empty_id_does_not_match_route(self):
        async with self.client() as c:
            for path in (f"{URL}/a/b", f"{URL}/a%2Fb", f"{URL}/"):
                with self.subTest(path=path):
                    self.assert_error(await c.get(path), 404, "NOT_FOUND")

    async def test_d11_source_failure_fake(self):
        async with self.client(FakeDocumentStore(error=DocumentSourceError())) as c:
            r = await c.get(f"{URL}/{DEX_ID}")
        self.assert_error(r, 502, "DOCUMENT_SOURCE_FAILED")

    async def test_d11_missing_documents_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp, "nope"))
            with self.assertLogs("api.documents.infrastructure.file_store", "WARNING"):
                async with self.client(settings=replace(SETTINGS, documents_dir=missing)) as c:
                    r = await c.get(f"{URL}/{DEX_ID}")
        self.assert_error(r, 502, "DOCUMENT_SOURCE_FAILED")
        self.assertNotIn(tmp, r.text)

    async def test_d12_unhandled_error_hides_detail_and_keeps_cors(self):
        store = FakeDocumentStore(error=RuntimeError("/abs/secret"))
        with self.assertLogs("api.error_handlers", level="ERROR"):
            async with self.client(store, raise_app_exceptions=False) as c:
                r = await c.get(f"{URL}/{DEX_ID}", headers={"Origin": CORS_ORIGIN})
        self.assert_error(r, 500, "INTERNAL_ERROR")
        self.assertNotIn("/abs/secret", r.text)
        self.assertEqual(r.headers.get("access-control-allow-origin"), CORS_ORIGIN)

    async def test_openapi_path_param_description(self):
        async with self.client() as c:
            r = await c.get("/openapi.json")
        params = r.json()["paths"][f"{URL}/{{source_ref_id}}"]["get"]["parameters"]
        param = next(p for p in params if p["name"] == "source_ref_id")
        self.assertEqual(param["description"], "chat sources[].source_ref_id 값. 도감번호 3자리 [0-9]{3} (예: 001)")

    async def test_post_is_method_not_allowed(self):
        async with self.client() as c:
            r = await c.post(f"{URL}/{DEX_ID}")
        self.assert_error(r, 405, "METHOD_NOT_ALLOWED")
        self.assertIn("GET", r.headers.get("allow", ""))


if __name__ == "__main__":
    unittest.main()
