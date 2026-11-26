"""documents 설계안 8절 도메인·구현체·서비스 (D1~D6)."""

import tempfile
import unittest
from pathlib import Path

from api.documents.application.service import DocumentService
from api.documents.domain.document import Document, SourceRefId
from api.documents.domain.exceptions import (
    DocumentNotFoundError,
    DocumentSourceError,
    InvalidSourceRefIdError,
)
from api.documents.infrastructure.file_store import FileDocumentStore
from api.tests.documents.fakes import FakeDocumentStore


class SourceRefIdTest(unittest.TestCase):
    def test_d1_valid_ids(self):
        for raw in ("bulbasaur_red_blue", "A-1_b"):
            with self.subTest(raw=raw):
                self.assertEqual(SourceRefId.create(raw).value, raw)

    def test_d2_invalid_ids(self):
        for raw in ("", "..", "a.md", "a/b", "a b", "이상해씨", "a\n", "a%2F", "a\\b", " a", "١٢"):
            with self.subTest(raw=raw), self.assertRaises(InvalidSourceRefIdError) as ctx:
                SourceRefId.create(raw)
            self.assertEqual(ctx.exception.error_code, "VALIDATION_ERROR")
            self.assertEqual(ctx.exception.status_code, 400)

    def test_exception_codes(self):
        self.assertEqual((DocumentNotFoundError.status_code, DocumentNotFoundError.error_code), (404, "DOCUMENT_NOT_FOUND"))
        self.assertEqual((DocumentSourceError.status_code, DocumentSourceError.error_code), (502, "DOCUMENT_SOURCE_FAILED"))


class FileDocumentStoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    async def test_d3_returns_bytes_decoded_as_is(self):
        raw = "# 제목\r\n\r\n본문 끝 공백   \r\nlast line  ".encode("utf-8")
        (self.base / "x.md").write_bytes(raw)
        text = await FileDocumentStore(self.base).get("x")
        self.assertEqual(text, raw.decode("utf-8"))
        self.assertIn("\r\n", text)

    async def test_d3_empty_file_allowed(self):
        (self.base / "e.md").write_bytes(b"")
        self.assertEqual(await FileDocumentStore(self.base).get("e"), "")

    async def test_d4_missing_file_is_not_found(self):
        with self.assertRaises(DocumentNotFoundError):
            await FileDocumentStore(self.base).get("y")

    async def test_d5_source_errors_hide_paths(self):
        (self.base / "z.md").mkdir()
        (self.base / "bad.md").write_bytes(b"\xff\xfe\xfa")
        cases = {
            "base_dir 없음": (FileDocumentStore(self.base / "missing"), "x"),
            "z.md가 폴더": (FileDocumentStore(self.base), "z"),
            "잘못된 UTF-8": (FileDocumentStore(self.base), "bad"),
        }
        for name, (store, doc_id) in cases.items():
            with self.subTest(name), self.assertLogs("api.documents.infrastructure.file_store", "WARNING") as logs:
                with self.assertRaises(DocumentSourceError) as ctx:
                    await store.get(doc_id)
            self.assertNotIn(self.tmp.name, ctx.exception.message)
            self.assertNotIn(".md", ctx.exception.message)
            self.assertNotIn(self.tmp.name, "\n".join(logs.output))

    async def test_base_dir_is_file_is_source_error(self):
        f = self.base / "file"
        f.write_text("x")
        with self.assertLogs("api.documents.infrastructure.file_store", "WARNING"):
            with self.assertRaises(DocumentSourceError):
                await FileDocumentStore(f).get("x")

    async def test_store_does_not_modify_files(self):
        (self.base / "x.md").write_bytes(b"abc")
        await FileDocumentStore(self.base).get("x")
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["x.md"])
        self.assertEqual((self.base / "x.md").read_bytes(), b"abc")


class DocumentServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_document(self):
        store = FakeDocumentStore(markdown="# md")
        doc = await DocumentService(store).get("bulbasaur_red_blue")
        self.assertEqual(doc, Document(SourceRefId("bulbasaur_red_blue"), "# md"))
        self.assertEqual(store.calls, ["bulbasaur_red_blue"])

    async def test_d6_invalid_id_does_not_call_store(self):
        store = FakeDocumentStore()
        for raw in ("..", "a.md", ""):
            with self.subTest(raw=raw), self.assertRaises(InvalidSourceRefIdError):
                await DocumentService(store).get(raw)
        self.assertEqual(store.calls, [])


if __name__ == "__main__":
    unittest.main()
