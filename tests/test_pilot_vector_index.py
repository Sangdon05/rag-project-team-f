"""scripts/helper/pilot_vector_index.py의 네트워크 없는 부분을 검사한다 (DB·API 호출 없음).

컬렉션 이름 가드, 레코드 id·해시 계산, 증분 sync 분류, 질의 파일 로딩, 원본 결과 JSON 형식.
"""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "helper" / "pilot_vector_index.py"
CHUNKS = ROOT / "data" / "synthetic" / "pilot" / "v2" / "bulbasaur_red_blue.json"  # test-pilot-v2-te3s-tpl2에 임베딩된 판
V1_CHUNKS = ROOT / "data" / "synthetic" / "pilot" / "v1" / "bulbasaur_red_blue.json"
V3A_CHUNKS = ROOT / "data" / "synthetic" / "pilot" / "v3a" / "bulbasaur_red_blue.json"
V3B_CHUNKS = ROOT / "data" / "synthetic" / "pilot" / "v3b" / "bulbasaur_red_blue.json"
# 보존 대상 기존 테스트 컬렉션과 그 행의 (schema_version, template_version)
EXISTING = {"test-pilot-v1-te3s-tpl1": {(2, None)}, "test-pilot-v2-te3s-tpl2": {(3, "tpl2")}}
NEW = {"test-pilot-v3a-te3s-tpl3a": V3A_CHUNKS, "test-pilot-v3b-te3s-tpl3b": V3B_CHUNKS}
MODEL = "test-embedding-model"  # 실제 모델명이 아닌 고정 문자열 (해시 계산 확인용)


def load_module():
    spec = importlib.util.spec_from_file_location("pilot_vector_index", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class PilotVectorIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()
        cls.doc = load(CHUNKS)
        cls.pokemon = load(ROOT / "data" / "processed" / "pokemon.json")
        cls.types = [t["name"] for t in load(ROOT / "data" / "processed" / "types.json")]

    def rows(self, collection="test-x", doc=None):
        return self.mod.build_rows(doc or self.doc, "data/synthetic/pilot/bulbasaur_red_blue.json", collection, MODEL,
                                   self.pokemon, self.types)

    # ------------------------------------------------------------ 컬렉션 이름 가드

    def test_collection_guard(self):
        self.assertEqual(self.mod.check_writable_collection("test-pilot-v2-te3s-tpl2"), "test-pilot-v2-te3s-tpl2")
        for bad in ("v1-te3s-tpl1", "langchain", "pilot-test-x", "Test-x", "test-", "", None, " test-x"):
            with self.subTest(bad):
                with self.assertRaises(self.mod.GuardError):
                    self.mod.check_writable_collection(bad)
        with self.assertRaises(self.mod.GuardError):
            self.mod.check_writable_collection("test-same", official="test-same")

    def test_sync_compatibility_guard(self):
        v1, v2 = load(V1_CHUNKS), self.doc
        self.assertEqual(self.mod.check_sync_compatibility("test-pilot-v2-te3s-tpl2", v2, set()), (3, "tpl2"))
        self.assertEqual(self.mod.check_sync_compatibility("test-pilot-v2-te3s-tpl2", v2, {(3, "tpl2")}), (3, "tpl2"))
        self.assertEqual(self.mod.check_sync_compatibility("test-pilot-v1-te3s-tpl1", v1, {(2, None)}), (2, "tpl1"))
        self.assertEqual(self.mod.check_sync_compatibility("test-other", v2, set()), (3, "tpl2"))
        bad = (("test-pilot-v1-te3s-tpl1", v2, {(2, None)}),   # v1 기준선 컬렉션에 tpl2 청크
               ("test-pilot-v1-te3s-tpl1", v2, set()),           # 이름의 템플릿이 다르다
               ("test-other", v2, {(2, None)}),                  # 기존 행 버전이 다르다
               ("test-pilot-v2-te3s-tpl2", v1, set()))
        for collection, doc, stored in bad:
            with self.subTest(collection=collection, stored=stored):
                with self.assertRaises(self.mod.GuardError):
                    self.mod.check_sync_compatibility(collection, doc, stored)

    def test_new_templates_cannot_be_synced_into_existing_collections(self):
        # 쓰기 없이 가드만 호출한다: tpl3a·tpl3b 청크는 v1·v2 컬렉션 이름·기존 행 버전과 맞지 않아 거부된다.
        for path in NEW.values():
            doc = load(path)
            for collection, stored in EXISTING.items():
                for versions in (stored, set()):
                    with self.subTest(chunks=doc["template_version"], collection=collection, stored=versions):
                        with self.assertRaises(self.mod.GuardError):
                            self.mod.check_sync_compatibility(collection, doc, versions)
        # 새 컬렉션은 자기 템플릿 청크만 받는다
        for collection, path in NEW.items():
            doc = load(path)
            self.assertEqual(self.mod.check_writable_collection(collection), collection)
            self.assertEqual(self.mod.check_sync_compatibility(collection, doc, set()), (3, doc["template_version"]))
            self.assertEqual(self.mod.check_sync_compatibility(collection, doc, {(3, doc["template_version"])}),
                             (3, doc["template_version"]))
        with self.assertRaises(self.mod.GuardError):
            self.mod.check_sync_compatibility("test-pilot-v3a-te3s-tpl3a", load(V3B_CHUNKS), set())
        with self.assertRaises(self.mod.GuardError):
            self.mod.check_sync_compatibility("test-pilot-v3b-te3s-tpl3b", load(V3A_CHUNKS), set())

    def test_new_template_rows(self):
        for collection, path in NEW.items():
            doc = load(path)
            rows = self.rows(collection, doc)
            self.assertEqual([r["id"] for r in rows], [f"{collection}:{c}" for c in doc["chunk_ids"]])
            self.assertEqual({r["meta"]["template_version"] for r in rows}, {doc["template_version"]})
            self.assertEqual({r["meta"]["heading"] for r in rows if r["meta"]["section"] == "encounter"}, {"획득처"})
            self.assertEqual(len(self.mod.classify(rows, {})["embed"]), 10)

    def test_main_refuses_writes_to_non_test_collection(self):
        # 가드는 .env·DB·API보다 먼저 실행되어 종료 코드 2로 멈춘다.
        for argv in (["--sync", "--chunks", str(CHUNKS), "--collection", "v2-te3s-tpl2"],
                     ["--drop", "--collection", "v1-te3s-tpl1", "--yes"],
                     ["--drop", "--collection", "test-pilot-v2-te3s-tpl2"]):  # --yes 없음
            with self.subTest(argv):
                self.assertEqual(self.mod.main(argv), 2)

    # ------------------------------------------------------------ 레코드 id·해시

    def test_record_id_and_hashes(self):
        self.assertEqual(self.mod.record_id("test-c", "pokemon:1#stats"), "test-c:pokemon:1#stats")
        with self.assertRaises(ValueError):
            self.mod.record_id("", "pokemon:1#stats")
        expected = hashlib.sha256(f"{MODEL}|본문".encode("utf-8")).hexdigest()
        self.assertEqual(self.mod.content_hash(MODEL, "본문"), expected)
        self.assertNotEqual(self.mod.content_hash("other-model", "본문"), expected)
        meta = {"b": 1, "a": "가", "content_hash": "x", "meta_hash": "y"}
        self.assertEqual(self.mod.meta_hash(meta), self.mod.meta_hash({"a": "가", "b": 1}))
        self.assertNotEqual(self.mod.meta_hash(meta), self.mod.meta_hash({"a": "가", "b": 2}))

    def test_build_rows(self):
        rows = self.rows("test-pilot-v2-te3s-tpl2")
        self.assertEqual([r["id"] for r in rows], [f"test-pilot-v2-te3s-tpl2:{c}" for c in self.doc["chunk_ids"]])
        for row, chunk in zip(rows, self.doc["chunks"]):
            meta = row["meta"]
            self.assertEqual(row["text"], chunk["content"])  # 접두어 없음
            self.assertEqual(meta["content_hash"], self.mod.content_hash(MODEL, chunk["content"]))
            self.assertEqual(meta["meta_hash"], self.mod.meta_hash(meta))
            self.assertEqual((meta["chunk_id"], meta["section"]), (chunk["chunk_id"], chunk["section"]))
            self.assertEqual(meta["index_version"], "test-pilot-v2-te3s-tpl2")
            self.assertTrue(meta["test_only"])
            self.assertTrue(meta["type_grass"] and meta["type_poison"] and not meta["type_fire"])
        headings = {r["meta"]["section"]: r["meta"]["heading"] for r in rows}
        self.assertEqual(headings["profile"], "기본 정보")
        self.assertEqual(headings["attack_matchup"], "공격 상성 (이상해씨와 같은 타입 기술이 잘 통하는 타입)")
        self.assertEqual(headings["defense_matchup"], "방어 상성 (약점과 저항)")
        # 같은 입력이면 해시가 같다 (재실행 시 embedded=0의 전제)
        self.assertEqual([r["meta"] for r in rows], [r["meta"] for r in self.rows("test-pilot-v2-te3s-tpl2")])

    def test_source_ref_id_is_pokedex_number(self):
        # 기본 파일럿(schema_version 3)과 보존 판 모두 도감번호 3자리이며 URL path에 그대로 넣을 수 있다
        current = ROOT / "data" / "synthetic" / "pilot" / "bulbasaur_red_blue.json"
        for path in (current, CHUNKS, V1_CHUNKS, V3A_CHUNKS, V3B_CHUNKS):
            doc = load(path)
            rows = self.rows("test-x", doc)
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertEqual(len(rows), 10)
                self.assertEqual([r["meta"]["source_ref_id"] for r in rows], ["001"] * 10)
                for r in rows:
                    self.assertEqual(r["meta"]["source_ref_id"], f"{r['meta']['pokemon_id']:03d}")
                    self.assertTrue(r["meta"]["source_path"].endswith(".md"))  # source_path 메타데이터는 그대로
        self.assertEqual(load(current)["schema_version"], 3)
        # chunk_id·document_id 규칙은 그대로다
        rows = self.rows("test-x", load(current))
        self.assertEqual([r["meta"]["chunk_id"] for r in rows], load(current)["chunk_ids"])
        self.assertEqual({r["meta"]["document_id"] for r in rows}, {c["doc_id"] for c in load(current)["chunks"]})

    def test_source_ref_id_of(self):
        for pid, expected in ((1, "001"), (9, "009"), (10, "010"), (99, "099"), (100, "100"), (151, "151")):
            self.assertEqual(self.mod.source_ref_id_of(pid), expected)
        for bad in (0, 152, -1, "1", "001", 1.0, None, True):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.mod.source_ref_id_of(bad)
        # 청크 문서의 pokemon_id가 범위 밖·정수 아님·없음이면 조용히 넘기지 않는다
        for bad in (0, 152, "1", None):
            doc = json.loads(json.dumps(self.doc))
            doc["pokemon_id"] = bad
            with self.subTest(doc_pokemon_id=bad):
                with self.assertRaises(ValueError):
                    self.rows("test-x", doc)
        doc = json.loads(json.dumps(self.doc))
        del doc["pokemon_id"]
        with self.assertRaises(ValueError):
            self.rows("test-x", doc)

    def test_source_path_requires_single_markdown(self):
        def with_sources(files):
            doc = json.loads(json.dumps(self.doc))
            doc["source_files"] = files
            return doc

        md = {"source_id": "pilot_markdown:x", "path": "data/synthetic/pilot/bulbasaur_red_blue.md"}
        other = [f for f in self.doc["source_files"] if not f["source_id"].startswith("pilot_markdown:")]
        bad_docs = {"no_markdown": other,
                    "two_markdown": other + [md, dict(md, path="data/synthetic/pilot/ivysaur_red_blue.md")],
                    "not_md": other + [dict(md, path="data/synthetic/pilot/bulbasaur_red_blue.json")],
                    "empty_path": other + [dict(md, path="")]}
        for label, files in bad_docs.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    self.rows("test-x", with_sources(files))

    def test_classify(self):
        rows = self.rows()
        stored = {r["id"]: (r["meta"]["content_hash"], r["meta"]["meta_hash"]) for r in rows}
        plan = self.mod.classify(rows, {})
        self.assertEqual((len(plan["embed"]), len(plan["meta_only"]), len(plan["unchanged"]), plan["delete"]),
                         (10, 0, 0, []))
        plan = self.mod.classify(rows, stored)
        self.assertEqual((len(plan["embed"]), len(plan["meta_only"]), len(plan["unchanged"]), plan["delete"]),
                         (0, 0, 10, []))
        first, second = rows[0]["id"], rows[1]["id"]
        changed = dict(stored, **{first: ("other", stored[first][1]), second: (stored[second][0], "other"),
                                  "test-x:gone": ("a", "b")})
        plan = self.mod.classify(rows, changed)
        self.assertEqual([r["id"] for r in plan["embed"]], [first])
        self.assertEqual([r["id"] for r in plan["meta_only"]], [second])
        self.assertEqual(len(plan["unchanged"]), 8)
        self.assertEqual(plan["delete"], ["test-x:gone"])

    # ------------------------------------------------------------ 질의 파일·결과 형식

    def test_load_queries_returns_only_qid_and_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "q.json"
            path.write_text(json.dumps({"queries": [
                {"qid": "q1", "query": "가", "tag": "t", "expected_sections": ["stats"]},
                {"qid": "q2", "query": "나", "expected_sections": []}]}, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(self.mod.load_queries(path), [{"qid": "q1", "query": "가"}, {"qid": "q2", "query": "나"}])
            path.write_text(json.dumps({"queries": [{"qid": "q1", "query": "가"}, {"qid": "q1", "query": "나"}]}),
                            encoding="utf-8")
            with self.assertRaises(ValueError):
                self.mod.load_queries(path)

    def test_run_queries_and_document_format(self):
        metas = [{"chunk_id": "pokemon:1#stats", "section": "stats", "heading": "종족치"},
                 {"chunk_id": "pokemon:1#profile", "section": "profile"}]

        class FakeAPIError(Exception):
            status_code = 429

        def fake_search(query, k):
            if query == "실패":
                raise FakeAPIError("secret-looking message is not recorded")
            return [(m, 0.1234567 * (i + 1)) for i, m in enumerate(metas[:k])]

        calls = []

        def counted(query, k):
            calls.append(query)
            return fake_search(query, k)

        queries = [{"qid": "a", "query": "종족치"}, {"qid": "b", "query": "실패"}, {"qid": "c", "query": "기본"}]
        results = self.mod.run_queries(queries, counted, 5)
        self.assertEqual(calls, ["종족치", "실패", "기본"])  # 재시도 없음, 순서 유지
        self.assertEqual([r["qid"] for r in results], ["a", "b", "c"])
        ok, failed = results[0], results[1]
        self.assertEqual(set(ok), {"qid", "query", "seconds", "error", "n_results", "results"})
        self.assertIsNone(ok["error"])
        self.assertEqual(ok["results"][0], {"rank": 1, "chunk_id": "pokemon:1#stats", "section": "stats",
                                            "heading": "종족치", "distance": 0.123457})
        self.assertIsNone(ok["results"][1]["heading"])  # heading이 없는 기존 컬렉션 행
        self.assertEqual(failed["error"], {"type": "FakeAPIError", "status_code": 429})
        self.assertEqual((failed["results"], failed["n_results"]), ([], 0))
        self.assertNotIn("secret", json.dumps(results))

        doc = self.mod.run_document(collection="test-c", model=MODEL, k=5,
                                    query_file={"path": "eval/q.json", "sha256": "a" * 64},
                                    chunk_file={"path": "data/x.json", "sha256": "b" * 64},
                                    started_at="2026-01-01T00:00:00+00:00", results=results,
                                    api={"embed_requests": 3}, collection_rows=10)
        for key in ("collection", "embed_model", "k", "filter", "query_file", "chunk_file", "started_at_utc",
                    "manifest_run_id", "n_queries", "n_errors", "results"):
            self.assertIn(key, doc)
        self.assertEqual((doc["n_queries"], doc["n_errors"], doc["filter"], doc["scoring"]), (3, 1, None, None))
        text = json.dumps(doc, ensure_ascii=False)
        for forbidden in ("expected", "hit@", "mrr", "\"hit\"", "correct"):
            self.assertNotIn(forbidden, text.lower())
        json.loads(text)

    def test_heading_fallback_for_v1_prefix(self):
        v1 = load(V1_CHUNKS)
        rows = self.rows("test-x", v1)
        # tpl1 머리말은 '이상해씨 (도감번호 001, 영문 Red·Blue) — 상위 > 제목' 형식이며 주제 부분을 제목으로 쓴다
        self.assertEqual({r["meta"]["template_version"] for r in rows}, {"tpl1"})
        self.assertTrue(all(r["meta"]["heading"] for r in rows))


if __name__ == "__main__":
    unittest.main()
