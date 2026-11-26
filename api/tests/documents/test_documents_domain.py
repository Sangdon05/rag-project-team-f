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
        for raw in ("001", "151"):
            with self.subTest(raw=raw):
                self.assertEqual(SourceRefId.create(raw).value, raw)

    def test_d2_invalid_ids(self):
        invalid = (
            "", "1", "01", "0001", "00a", "..", "001.md", "001_이상해씨",
            " 001", "001\n", "١٢٣", "0/1", "0\\1", "%31",
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(InvalidSourceRefIdError) as ctx:
                SourceRefId.create(raw)
            self.assertEqual(ctx.exception.error_code, "VALIDATION_ERROR")
            self.assertEqual(ctx.exception.status_code, 400)
            self.assertEqual(ctx.exception.message, "source_ref_id는 도감번호 3자리(예: 001)여야 합니다.")

    def test_d2_non_string_rejected(self):
        for raw in (1, None, b"001"):
            with self.subTest(raw=raw), self.assertRaises(InvalidSourceRefIdError):
                SourceRefId.create(raw)

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
        (self.base / "001_x.md").write_bytes(raw)
        text = await FileDocumentStore(self.base).get("001")
        self.assertEqual(text, raw.decode("utf-8"))
        self.assertIn("\r\n", text)

    async def test_d3_empty_file_allowed(self):
        (self.base / "005_e.md").write_bytes(b"")
        self.assertEqual(await FileDocumentStore(self.base).get("005"), "")

    async def test_d4_missing_file_is_not_found(self):
        (self.base / "0010_x.md").write_bytes(b"prefix-only")
        (self.base / "001.md").write_bytes(b"no-underscore")
        (self.base / "001_x.txt").write_bytes(b"wrong-ext")
        store = FileDocumentStore(self.base)
        for doc_id in ("002", "001"):
            with self.subTest(doc_id=doc_id), self.assertRaises(DocumentNotFoundError):
                await store.get(doc_id)

    async def test_d5_source_errors_hide_paths(self):
        (self.base / "003_z.md").mkdir()
        (self.base / "006_bad.md").write_bytes(b"\xff\xfe\xfa")
        (self.base / "004_a.md").write_bytes(b"a")
        (self.base / "004_b.md").write_bytes(b"b")
        cases = {
            "base_dir 없음": (FileDocumentStore(self.base / "missing"), "001"),
            "003_z.md가 폴더": (FileDocumentStore(self.base), "003"),
            "잘못된 UTF-8": (FileDocumentStore(self.base), "006"),
            "같은 번호 파일 둘": (FileDocumentStore(self.base), "004"),
        }
        for name, (store, doc_id) in cases.items():
            with self.subTest(name), self.assertLogs("api.documents.infrastructure.file_store", "WARNING") as logs:
                with self.assertRaises(DocumentSourceError) as ctx:
                    await store.get(doc_id)
            self.assertEqual(ctx.exception.message, "문서를 읽지 못했습니다. 잠시 후 다시 시도하세요.")
            self.assertNotIn(self.tmp.name, ctx.exception.message)
            self.assertNotIn(".md", ctx.exception.message)
            self.assertNotIn(self.tmp.name, "\n".join(logs.output))

    async def test_base_dir_is_file_is_source_error(self):
        f = self.base / "file"
        f.write_text("x")
        with self.assertLogs("api.documents.infrastructure.file_store", "WARNING"):
            with self.assertRaises(DocumentSourceError):
                await FileDocumentStore(f).get("001")

    async def test_store_does_not_modify_files(self):
        (self.base / "001_x.md").write_bytes(b"abc")
        await FileDocumentStore(self.base).get("001")
        self.assertEqual(sorted(p.name for p in self.base.iterdir()), ["001_x.md"])
        self.assertEqual((self.base / "001_x.md").read_bytes(), b"abc")


class DocumentServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_document(self):
        store = FakeDocumentStore(markdown="# md")
        doc = await DocumentService(store).get("001")
        self.assertEqual(doc, Document(SourceRefId("001"), "# md"))
        self.assertEqual(store.calls, ["001"])

    async def test_d6_invalid_id_does_not_call_store(self):
        store = FakeDocumentStore()
        for raw in ("..", "001.md", "", "1", "0001"):
            with self.subTest(raw=raw), self.assertRaises(InvalidSourceRefIdError):
                await DocumentService(store).get(raw)
        self.assertEqual(store.calls, [])


if __name__ == "__main__":
    unittest.main()
