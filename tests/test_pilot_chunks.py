"""파일럿 청크 JSON을 생성기·Markdown·정제 데이터와 대조한다 (네트워크 없음).

- tpl3a: data/synthetic/pilot/v3a/bulbasaur_red_blue.{md,json} (채택·기본 양식 = tpl2 + 획득처 보강, 최신본 data/synthetic/pilot/ 사본)
- tpl3b: data/synthetic/pilot/v3b/bulbasaur_red_blue.{md,json} (기각된 실험 = tpl3a + 상성 방향 문장, 명시 재현만)
- tpl2: data/synthetic/pilot/v2/bulbasaur_red_blue.{md,json} (v2 기준선, 수정 금지)
- tpl1: data/synthetic/pilot/v1/bulbasaur_red_blue.{md,json} (v1 기준선, 수정 금지)

PilotChunksTest는 v2(tpl2) 기준선의 회귀 검사, CurrentTemplatesTest(test_pilot_chunks_v3.py)는 tpl3a·tpl3b 검사다.
"""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "helper" / "build_pilot_chunks.py"
PILOT = ROOT / "data" / "synthetic" / "pilot"
OUTPUT = PILOT / "v2" / "bulbasaur_red_blue.json"
MARKDOWN = PILOT / "v2" / "bulbasaur_red_blue.md"
# v2 기준선 파일의 LF 바이트 sha256 (test-pilot-v2-te3s-tpl2 컬렉션에 임베딩된 판, v2 당시 최신본의 바이트 사본)
V2_SHA256 = {
    MARKDOWN: "1796ddd296b8bb8df9c1f672f7caca75e10973dead37e835f8a3dc1a4f6ade7f",
    OUTPUT: "bf10f43e6dc021001bea9fad85b35d1c48278ba0d776ec7efd77d8e40e258be4",
}
V1_OUTPUT = ROOT / "data" / "synthetic" / "pilot" / "v1" / "bulbasaur_red_blue.json"
V1_MARKDOWN = ROOT / "data" / "synthetic" / "pilot" / "v1" / "bulbasaur_red_blue.md"
# v1 기준선 파일의 LF 바이트 sha256 (test-pilot-v1-te3s-tpl1 컬렉션에 임베딩된 판)
V1_SHA256 = {
    V1_MARKDOWN: "2dee4dc602fa35173f1c6c9cc3b7dffbeafd7bb30fdf3505d0f7e34de6295bcb",
    V1_OUTPUT: "24797e23223f5bba21df07e6a5d9b17df738ce5e7e6167a5075ee36f909503ce",
}

TOP_LEVEL_KEYS = {
    "chunk_ids", "chunks", "doc_id", "game_language", "games", "generated_by", "generation_mode", "generator",
    "index_eligible", "limitations", "localization_note", "manifest", "needs_human_review", "pokemon_id",
    "review_status", "schema_version", "source_files", "source_lineage", "title", "version_group",
}
CHUNK_KEYS = {
    "chunk_id", "content", "doc_id", "games", "generation_mode", "needs_human_review", "review_status",
    "section", "source_records", "version_group",
}
SECTIONS = [
    "profile", "stats", "evolution", "learnset_level", "learnset_machine", "machine_acquisition",
    "stab", "attack_matchup", "defense_matchup", "encounter",
]
DATA_SECTIONS = {"learnset_level", "learnset_machine", "attack_matchup", "defense_matchup"}
LOCATION_SOURCE = "processed:location_names_ko_red_blue"


def load_generator():
    spec = importlib.util.spec_from_file_location("build_pilot_chunks", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lf_sha(path):
    """.gitattributes 대상이 아닌 코드(.py)의 Git 저장 형태(LF) 바이트 sha256."""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def file_sha(path):
    """.gitattributes로 LF 고정된 data/ 파일의 실제 바이트 sha256."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_pointer(doc, pointer):
    node = doc
    for part in pointer.lstrip("/").split("/") if pointer else []:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def read_lines(path):
    lines = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


class PilotChunksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = load_generator()
        cls.saved_text = OUTPUT.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
        cls.doc = json.loads(cls.saved_text)
        cls.chunks = {chunk["section"]: chunk for chunk in cls.doc["chunks"]}
        cls.md_lines = read_lines(MARKDOWN)
        cls.manifest = json.loads((ROOT / "data" / "source_manifest.json").read_text(encoding="utf-8"))
        cls.manifest_files = {entry["source_id"]: entry for entry in cls.manifest["processed_files"]}
        cls.files = {entry["source_id"]: entry for entry in cls.doc["source_files"]}
        cls.loaded = {}

    def source(self, source_id):
        if source_id not in self.loaded:
            self.loaded[source_id] = json.loads((ROOT / self.files[source_id]["path"]).read_text(encoding="utf-8"))
        return self.loaded[source_id]

    def pointers(self, section, source_id):
        return {r["pointer"] for r in self.chunks[section]["source_records"] if r["source_id"] == source_id}

    # ------------------------------------------------------------ 재생성·결정성

    def test_v2_baseline_files_unchanged(self):
        for path, digest in V2_SHA256.items():
            self.assertEqual(file_sha(path), digest, path)

    def test_tpl2_regenerates_v2_baseline(self):
        document = self.gen.build_document(template="tpl2")
        same, detail = self.gen.compare_baseline(document, self.saved_text, "tpl2")
        self.assertTrue(same, detail)
        # 청크 본문·ID·근거는 바이트 단위로 같다. 차이는 TPL1_VOLATILE 세 곳뿐이다.
        self.assertEqual(json.dumps(document["chunks"], ensure_ascii=False, sort_keys=True),
                         json.dumps(self.doc["chunks"], ensure_ascii=False, sort_keys=True))
        self.assertEqual(self.gen.volatile_values(self.doc), self.gen.TPL2_BASELINE)
        self.assertEqual(set(self.gen.TPL2_BASELINE), set(self.gen.TPL1_VOLATILE))
        self.assertEqual(self.gen.main(["--template", "tpl2", "--check"]), 0)

    def test_tpl2_baseline_output_is_not_overwritten(self):
        self.assertEqual(self.gen.main(["--template", "tpl2"]), 2)
        self.assertEqual(file_sha(OUTPUT), V2_SHA256[OUTPUT])

    def test_regeneration_is_deterministic(self):
        first = hashlib.sha256(self.gen.render(self.gen.build_document(template="tpl2")).encode("utf-8")).hexdigest()
        second = hashlib.sha256(self.gen.render(self.gen.build_document(template="tpl2")).encode("utf-8")).hexdigest()
        self.assertEqual(first, second)

    # ------------------------------------------------------------ v1 기준선 (tpl1)

    def test_v1_baseline_files_unchanged(self):
        for path, digest in V1_SHA256.items():
            self.assertEqual(file_sha(path), digest, path)

    def test_tpl1_regenerates_v1_baseline(self):
        saved = V1_OUTPUT.read_bytes().decode("utf-8")
        document = self.gen.build_document(template="tpl1")
        same, detail = self.gen.compare_tpl1(document, saved)
        self.assertTrue(same, detail)
        v1 = json.loads(saved)
        # 청크 본문·ID·근거는 바이트 단위로 같다. 차이는 TPL1_VOLATILE 세 곳뿐이다.
        self.assertEqual(json.dumps(document["chunks"], ensure_ascii=False, sort_keys=True),
                         json.dumps(v1["chunks"], ensure_ascii=False, sort_keys=True))
        self.assertEqual(self.gen.volatile_values(v1), self.gen.TPL1_BASELINE)
        self.assertEqual(set(self.gen.TPL1_VOLATILE), set(self.gen.TPL1_BASELINE))
        self.assertNotIn("template_version", document)
        self.assertEqual(document["schema_version"], 2)

    def test_tpl1_rejects_broken_v1_markdown(self):
        md = V1_MARKDOWN.read_text(encoding="utf-8")
        broken = {
            "missing_heading": md.replace("### 공격할 때\n", ""),
            "tpl2_heading_in_tpl1": md.replace("### 공격받을 때", "### 방어 상성 (약점과 저항)"),
            "wrong_map_id": md.replace("`SilphCo7F`", "`SilphCo8F`"),
        }
        for label, text in broken.items():
            self.assertNotEqual(text, md, label)
            with self.subTest(label):
                with self.assertRaises(self.gen.ChunkError):
                    self.gen.build_document(text, template="tpl1")

    def test_tpl1_baseline_output_is_not_overwritten(self):
        self.assertEqual(self.gen.main(["--template", "tpl1"]), 2)
        self.assertEqual(file_sha(V1_OUTPUT), V1_SHA256[V1_OUTPUT])

    # ------------------------------------------------------------ 구조·ID

    def test_structure_and_flags(self):
        self.assertEqual(set(self.doc), TOP_LEVEL_KEYS | {"template_version"})
        self.assertEqual(self.doc["template_version"], "tpl2")
        for chunk in self.doc["chunks"]:
            expected = CHUNK_KEYS | ({"data"} if chunk["section"] in DATA_SECTIONS else set())
            self.assertEqual(set(chunk), expected, chunk["chunk_id"])
            self.assertEqual((chunk["review_status"], chunk["needs_human_review"]), ("pending", True))
            self.assertEqual(chunk["doc_id"], self.doc["doc_id"])
        self.assertEqual(self.doc["schema_version"], 3)
        self.assertEqual(self.doc["doc_id"], "pokemon:1")
        self.assertEqual(self.doc["pokemon_id"], 1)
        self.assertEqual((self.doc["review_status"], self.doc["needs_human_review"], self.doc["index_eligible"]),
                         ("pending", True, False))
        self.assertEqual(self.doc["generator"]["path"], "scripts/helper/build_pilot_chunks.py")
        # 기준선 출처 값 (생성기는 v2 이후 바뀌었다. compare_baseline이 제외 필드로 다룬다)
        self.assertEqual(self.doc["generator"]["sha256"], self.gen.TPL2_BASELINE["generator.sha256"])
        self.assertEqual(self.doc["manifest"]["generated_at_utc"], self.manifest["generated_at_utc"])
        self.assertEqual(self.doc["manifest"]["sha256"], file_sha(ROOT / "data" / "source_manifest.json"))
        self.assertNotIn("pokeapi/", json.dumps({k: v for k, v in self.doc.items() if k != "chunks"}, ensure_ascii=False))

    def test_chunk_ids(self):
        ids = [chunk["chunk_id"] for chunk in self.doc["chunks"]]
        self.assertEqual(ids, [f"pokemon:1#{section}" for section in SECTIONS])
        self.assertEqual(self.doc["chunk_ids"], ids)
        self.assertEqual(len(ids), len(set(ids)))

    # ------------------------------------------------------------ Markdown 대응

    def test_chunks_cover_markdown_lines_once(self):
        owner = {}
        previous_end = 0
        for chunk in self.doc["chunks"]:
            md = [r for r in chunk["source_records"] if r["source_id"] == "pilot_markdown:bulbasaur_red_blue"]
            self.assertEqual(len(md), 1, chunk["chunk_id"])
            start, end = md[0]["line_start"], md[0]["line_end"]
            self.assertEqual(start, previous_end + 1, chunk["chunk_id"])
            previous_end = end
            span = self.md_lines[start - 1:end]
            headings = [line.strip() for line in span if line.startswith("#")]
            self.assertEqual(md[0]["headings"], headings, chunk["chunk_id"])
            for number in range(start, end + 1):
                if self.md_lines[number - 1].strip():
                    self.assertNotIn(number, owner)
                    owner[number] = chunk["chunk_id"]
            # 본문 = 머리말 한 줄 + 빈 줄 + 제목을 뺀 구간 줄 (빈 줄만 정리)
            head, _, body = chunk["content"].partition("\n\n")
            self.assertEqual(head, f"이상해씨 — {self.gen.topic_of(chunk['section'], 'tpl2', '이상해씨')}")
            self.assertNotIn("도감번호", head)
            self.assertNotIn("Red", head)
            expected_lines = [line for line in span if line.strip() and not line.startswith("#")]
            self.assertEqual([line for line in body.split("\n") if line.strip()], expected_lines, chunk["chunk_id"])
            self.assertNotIn("\n\n\n", chunk["content"])
        self.assertEqual(previous_end, len(self.md_lines))
        nonblank = {i + 1 for i, line in enumerate(self.md_lines) if line.strip()}
        self.assertEqual(set(owner), nonblank)

    def test_prefix_topics(self):
        heads = {c["section"]: c["content"].split("\n", 1)[0] for c in self.doc["chunks"]}
        self.assertEqual(heads["profile"], "이상해씨 — 기본 정보")
        self.assertEqual(heads["stab"], "이상해씨 — 자속 보정 (같은 타입 기술 1.5배)")
        self.assertEqual(heads["attack_matchup"], "이상해씨 — 공격 상성 (이상해씨와 같은 타입 기술이 잘 통하는 타입)")
        self.assertEqual(heads["defense_matchup"], "이상해씨 — 방어 상성 (약점과 저항)")
        self.assertEqual(len(set(heads.values())), len(heads))

    def test_matchup_terms_and_places(self):
        content = {c["section"]: c["content"] for c in self.doc["chunks"]}
        for term in ("효과가 굉장한", "효과가 별로인", "효과가 없는"):
            self.assertIn(term, content["attack_matchup"])
        for term in ("약점", "저항", "무효"):
            self.assertIn(term, content["defense_matchup"])
        for term in ("약점", "저항", "무효", "효과가 굉장한"):
            self.assertNotIn(term, content["stab"])
        self.assertNotIn("강점", "\n".join(content.values()))
        self.assertIn("태초마을", content["encounter"])
        self.assertNotIn("pallet-town", content["encounter"])
        self.assertNotIn("`", content["machine_acquisition"])
        self.assertIn("실프주식회사 7층", content["machine_acquisition"])

    def test_broken_markdown_is_rejected(self):
        md = MARKDOWN.read_text(encoding="utf-8").replace("\r\n", "\n")
        machine_cut = md.split("### 머신은 어디서 얻나요?")[0] + "## 타입 · 상성" + md.split("## 타입 · 상성")[1]
        stats_old, stats_new = "| 45 | 49 | 49 | 45 | 65 |", "| 45 | 49 | 49 | 45 | 66 |"
        attack_heading = "### 공격 상성 (이상해씨와 같은 타입 기술이 잘 통하는 타입)"
        broken = {
            # 제목
            "missing_heading": md.replace(attack_heading + "\n", ""),
            "missing_defense_heading": md.replace("### 방어 상성 (약점과 저항)\n", ""),
            "old_tpl1_heading": md.replace(attack_heading, "### 공격할 때"),
            "old_tpl2_attack_heading": md.replace(attack_heading, "### 공격 상성 (이상해씨의 기술이 잘 통하는 타입)"),
            "wrong_josa": md.replace(attack_heading, "### 공격 상성 (이상해씨과 같은 타입 기술이 잘 통하는 타입)"),
            "unknown_heading": md.replace("## 획득처", "## 획득 장소"),
            "duplicate_heading": md + "\n## 종족치\n\nx\n",
            "reordered": md.replace("## 종족치", "## TMP").replace("## 진화", "## 종족치").replace("## TMP", "## 진화"),
            "h4_heading": md.replace("### 자속 보정 (같은 타입 기술 1.5배)\n",
                                     "### 자속 보정 (같은 타입 기술 1.5배)\n\n#### 예시\n"),
            "machine_section_dropped": machine_cut,
            "name_mismatch": md.replace("# 이상해씨", "# 이상해풀", 1),
            "number_mismatch": md.replace("**도감번호:** 001", "**도감번호:** 002"),
            "unclosed_code_block": md.replace("```text", "```text\n```text", 1),
            # 정제 데이터 값
            "stats_value_changed": md.replace(stats_old, stats_new),
            "move_row_removed": md.replace("| 7 | 씨뿌리기 | 풀 |\n", ""),
            # 상성 용어 누락
            "attack_term_missing": md.replace("| 효과가 굉장한(2배) 상대 타입 |", "| 효과가 좋은(2배) 상대 타입 |"),
            "attack_zero_column_dropped": md.replace(" | 효과가 없는(0배) 상대 타입 |", " |")
                                            .replace("|---|---|---|---|", "|---|---|---|")
                                            .replace("드래곤 | 없음 |", "드래곤 |")
                                            .replace("고스트 | 없음 |", "고스트 |"),
            "attack_none_cell_blank": md.replace("드래곤 | 없음 |", "드래곤 |  |"),
            "defense_term_missing": md.replace("| 약점 | 벌레 | 4배 |", "| 취약 | 벌레 | 4배 |"),
            "defense_immune_row_dropped": md.replace("| 무효 | 없음 | 0배 |\n", ""),
            "summary_missing": md.replace("요약: 이상해씨의 약점은", "이상해씨의 약점은"),
            "summary_term_changed": md.replace("요약: 이상해씨의 약점은", "요약: 이상해씨의 취약점은"),
            "strength_word": md.replace("독 타입 공격 행은", "강점: 독 타입 공격 행은"),
            "stab_mixes_matchup_terms": md.replace("자속 보정을 받아 기본 배율에", "자속 보정을 받아 약점과 무관하게 기본 배율에"),
            # 잘못된 배율
            "defense_factor_wrong": md.replace("| 약점 | 벌레 | 4배 |", "| 약점 | 벌레 | 2배 |"),
            "defense_type_moved": md.replace("| 저항 | 풀 | 0.25배 |", "| 저항 | 풀, 노말 | 0.25배 |"),
            "attack_type_moved": md.replace("| 풀 | 물, 땅, 바위 |", "| 풀 | 물, 땅 |"),
            "summary_factor_wrong": md.replace("벌레(4배), 비행", "벌레(2배), 비행"),
            # 대응표와 다른 장소명
            "place_name_changed": md.replace("상트앙느호 선장실", "상트안느호 선장실"),
            "place_identifier_left": md.replace("| TM03 | 실프주식회사 7층 —", "| TM03 | `SilphCo7F` —"),
            "encounter_identifier_left": md.replace("Red와 Blue 모두 태초마을에서", "Red와 Blue 모두 `pallet-town-area`(태초마을)에서"),
            "encounter_place_changed": md.replace("Red와 Blue 모두 태초마을에서", "Red와 Blue 모두 상록시티에서"),
        }
        for label, text in broken.items():
            self.assertNotEqual(text, md, label)
            with self.subTest(label):
                with self.assertRaises(self.gen.ChunkError):
                    self.gen.build_document(text, template="tpl2")

    # ------------------------------------------------------------ 근거 연결

    def test_source_files_hashes(self):
        for source_id, entry in self.files.items():
            path = ROOT / entry["path"]
            if source_id == "pilot_markdown:bulbasaur_red_blue":
                # v2 당시 최신본 경로가 기록돼 있다. 같은 바이트의 보존본은 v2/에 있다.
                self.assertEqual(entry["sha256"], file_sha(MARKDOWN), source_id)
            elif source_id in self.manifest_files:
                self.assertEqual(entry["sha256"], self.manifest_files[source_id]["sha256"], source_id)
                self.assertEqual(entry["sha256"], file_sha(path), source_id)
            elif entry["path"].startswith("data/"):
                self.assertEqual(entry["sha256"], file_sha(path), source_id)
            else:
                self.assertEqual(entry["sha256"], lf_sha(path), source_id)
        used = {r["source_id"] for chunk in self.doc["chunks"] for r in chunk["source_records"]}
        self.assertEqual(used, set(self.files))
        refs = {ref for entry in self.doc["source_files"] for ref in entry["source_refs"]}
        self.assertEqual(set(self.doc["source_lineage"]), refs)
        self.assertEqual(self.files["pilot_markdown:bulbasaur_red_blue"]["path"], "data/synthetic/pilot/bulbasaur_red_blue.md")

    def test_source_records_resolve(self):
        rules_sha = lf_sha(ROOT / "scripts" / "gen1_battle" / "gen1_battle_rules.py")
        for chunk in self.doc["chunks"]:
            for record in chunk["source_records"]:
                source_id = record["source_id"]
                with self.subTest(chunk=chunk["chunk_id"], record=record["record_id"], pointer=record.get("pointer")):
                    if source_id == "pilot_markdown:bulbasaur_red_blue":
                        continue  # test_chunks_cover_markdown_lines_once
                    if source_id == "code:gen1_battle_rules":
                        self.assertEqual(record["sha256"], rules_sha)
                        self.assertEqual(self.files[source_id]["sha256"], rules_sha)
                        continue
                    doc = self.source(source_id)
                    scheme = self.manifest_files[source_id]["identity"]["scheme"]
                    if source_id == "processed:type_chart":
                        attack, defense = record["pointer"].strip("/").split("/")
                        self.assertEqual(resolve_pointer(doc, record["pointer"]), record["identity_value"])
                        self.assertEqual(record["record_id"], scheme.format(attack_type=attack, defense_type=defense))
                        continue
                    field = record["identity_field"]
                    self.assertEqual(field, self.manifest_files[source_id]["identity"]["identity_field"])
                    target = resolve_pointer(doc, record.get("record_pointer", record["pointer"]))
                    self.assertEqual(target[field], record["identity_value"])
                    self.assertEqual(record["record_id"], scheme.format(**{field: record["identity_value"]}))
                    if "expected_subrecord" in record:
                        sub = resolve_pointer(doc, record["pointer"])
                        self.assertEqual({k: sub[k] for k in record["expected_subrecord"]}, record["expected_subrecord"])
                        self.assertTrue(record["pointer"].startswith(record["record_pointer"] + "/learnset/"))

    def test_required_evidence(self):
        p = "processed:pokemon"
        self.assertEqual(self.pointers("evolution", "processed:evolutions_red_blue"), {"/records/0", "/records/1", "/records/2"})
        self.assertEqual(self.pointers("evolution", p), {"/0", "/1", "/2"})
        chart = "processed:type_chart"
        types = [t["name"] for t in self.source("processed:types")]
        self.assertEqual(self.pointers("attack_matchup", chart), {f"/{a}/{d}" for a in ("grass", "poison") for d in types})
        self.assertEqual(self.pointers("defense_matchup", chart), {f"/{a}/{d}" for a in types for d in ("grass", "poison")})
        moves = self.source("processed:moves")
        stab_moves = {moves[int(ptr.strip("/"))]["name"] for ptr in self.pointers("stab", "processed:moves")}
        self.assertEqual(stab_moves, {"vine-whip", "poison-sting"})
        self.assertEqual(len(self.pointers("stab", "processed:red_blue_move_damage_classification")), 2)
        for section in ("stab", "attack_matchup", "defense_matchup"):
            rules = [r for r in self.chunks[section]["source_records"] if r["source_id"] == "code:gen1_battle_rules"]
            self.assertEqual(len(rules), 1, section)
        self.assertEqual(self.pointers("encounter", "processed:encounters_red_blue"), {"/pokemon/0"})
        self.assertEqual(len(self.pointers("machine_acquisition", "processed:machine_acquisition_red_blue")), 15)
        self.assertEqual(len(self.pointers("learnset_machine", "processed:machines_red_blue")), 15)
        self.assertEqual(len(self.pointers("learnset_machine", "processed:moves")), 15)
        self.assertEqual(len(self.pointers("learnset_level", "processed:moves")), 9)
        # 장소명이 들어간 청크는 대응표 레코드를 근거로 연결한다 (머신 15개의 획득 지도 16곳, 획득처 1곳).
        table = self.source(LOCATION_SOURCE)["entries"]
        acquisition = self.source("processed:machine_acquisition_red_blue")["machines"]
        codes = {r["identity_value"] for r in self.chunks["machine_acquisition"]["source_records"]
                 if r["source_id"] == "processed:machine_acquisition_red_blue"}
        maps = {f"pokered_map:{loc['map_id_raw']}" for m in acquisition if m["code"] in codes for loc in m["locations"]}
        linked = {r["identity_value"] for r in self.chunks["machine_acquisition"]["source_records"]
                  if r["source_id"] == LOCATION_SOURCE}
        self.assertEqual(linked, maps)
        self.assertEqual(len(linked), 16)
        for location_id in linked:
            name_ko = next(e["name_ko"] for e in table if e["id"] == location_id)
            self.assertIn(name_ko, self.chunks["machine_acquisition"]["content"])
        self.assertEqual({r["identity_value"] for r in self.chunks["encounter"]["source_records"]
                          if r["source_id"] == LOCATION_SOURCE}, {"pokeapi_location_area:pallet-town-area"})
        for section in set(SECTIONS) - {"machine_acquisition", "encounter"}:
            self.assertFalse(self.pointers(section, LOCATION_SOURCE), section)
        # 기술 표의 근거는 Red·Blue level-up·machine 기록만이다 (learnset_machine은 건수 문장 때문에 24건 전체).
        for section, count in (("learnset_level", 9), ("learnset_machine", 24)):
            subs = [r["expected_subrecord"] for r in self.chunks[section]["source_records"] if "expected_subrecord" in r]
            self.assertEqual(len(subs), count, section)
            for sub in subs:
                self.assertEqual(sub["version_group"], "red-blue")
                self.assertIn(sub["method"], ("level-up", "machine"))
        for chunk in self.doc["chunks"]:
            self.assertIn("/0", {r["pointer"] for r in chunk["source_records"] if r["source_id"] == p}, chunk["chunk_id"])

    # ------------------------------------------------------------ 공격 상성 제목의 조사 '과/와'

    def test_josa_gwa_wa(self):
        pokemon = json.loads((ROOT / "data" / "processed" / "pokemon.json").read_text(encoding="utf-8"))
        names = {row["name_ko"] for row in pokemon}
        # 받침 없음 → '와', 받침 있음 → '과'. 모두 pokemon.json에 있는 실제 이름이다.
        cases = {"이상해씨": "이상해씨와", "피카츄": "피카츄와", "꼬부기": "꼬부기와", "디그다": "디그다와",
                 "리자몽": "리자몽과", "이상해꽃": "이상해꽃과", "고라파덕": "고라파덕과", "롱스톤": "롱스톤과",
                 "버터플": "버터플과", "니드런♀": "니드런♀과", "니드런♂": "니드런♂과"}
        for name, expected in cases.items():
            with self.subTest(name):
                self.assertIn(name, names)
                self.assertEqual(self.gen.with_gwa_wa(name), expected)
        for name in names:  # 151마리 모두 조사를 정할 수 있다
            self.assertIn(self.gen.with_gwa_wa(name)[-1], "과와")
        for bad in ("Pikachu", "♀", ""):
            with self.assertRaises(self.gen.ChunkError):
                self.gen.with_gwa_wa(bad)

    def test_attack_heading_uses_josa(self):
        for name, expected in (("이상해씨", "이상해씨와"), ("리자몽", "리자몽과"), ("피카츄", "피카츄와")):
            headings = {section: heading for heading, section, _ in self.gen.layout_for("tpl2", name)}
            self.assertEqual(headings["attack_matchup"], f"### 공격 상성 ({expected} 같은 타입 기술이 잘 통하는 타입)")
            self.assertEqual(self.gen.topic_of("attack_matchup", "tpl2", name),
                             f"공격 상성 ({expected} 같은 타입 기술이 잘 통하는 타입)")
        tpl1 = {section: heading for heading, section, _ in self.gen.layout_for("tpl1", "리자몽")}
        self.assertEqual(tpl1["attack_matchup"], "### 공격할 때")
        self.assertIn("{name}{과/와}", self.gen.topic_of("attack_matchup", "tpl2"))

    def test_in_game_learnset_excludes_non_game_method(self):
        pokemon = json.loads((ROOT / "data" / "processed" / "pokemon.json").read_text(encoding="utf-8"))
        pikachu = next(row for row in pokemon if row["id"] == 25)
        raw = [r for r in pikachu["learnset"] if r["version_group"] == "red-blue" and r["method"] == "stadium-surfing-pikachu"]
        self.assertEqual([r["move"] for r in raw], ["surf"])
        kept = [row for _, row in self.gen.in_game_learnset(pikachu)]
        self.assertTrue(kept)
        self.assertFalse([r for r in kept if r["method"] not in ("level-up", "machine")])
        self.assertNotIn("surf", {r["move"] for r in kept})


if __name__ == "__main__":
    unittest.main()
