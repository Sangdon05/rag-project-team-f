"""tpl3a(획득처 보강)·tpl3b(상성 방향 구분) 파일럿 청크를 생성기·Markdown·정제 데이터와 대조한다 (네트워크 없음).

- tpl3a (채택, 기본): data/synthetic/pilot/v3a/bulbasaur_red_blue.{md,json} = v2 + 획득처 절 보강
- tpl3b (기각된 실험): data/synthetic/pilot/v3b/bulbasaur_red_blue.{md,json} = tpl3a + 공격·방어 상성 요약 방향 구분.
  --template tpl3b로 명시할 때만 재현 확인하며 기본·최신본으로 고르지 않는다.
- 최신본 data/synthetic/pilot/bulbasaur_red_blue.{md,json}은 v3a의 바이트 사본이다.
- v3a·v3b JSON은 고정본이다. 생성기 sha256만 기준선 값(TPL3_BASELINE)으로 따로 확인하고 나머지는 바이트 비교한다.
획득처·상성 요약 규칙은 151마리 공통 규칙이므로 이상해씨 밖의 종(야생 다수·기록 없음·한 버전 전용·교환·코인)도 검사한다.
"""
import copy
import importlib.util
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "helper" / "build_pilot_chunks.py"
PILOT = ROOT / "data" / "synthetic" / "pilot"
FILES = {t: (PILOT / v / "bulbasaur_red_blue.md", PILOT / v / "bulbasaur_red_blue.json")
         for t, v in (("tpl2", "v2"), ("tpl3a", "v3a"), ("tpl3b", "v3b"))}
LATEST = (PILOT / "bulbasaur_red_blue.md", PILOT / "bulbasaur_red_blue.json")
SECTIONS = [
    "profile", "stats", "evolution", "learnset_level", "learnset_machine", "machine_acquisition",
    "stab", "attack_matchup", "defense_matchup", "encounter",
]
LOCATION_SOURCE = "processed:location_names_ko_red_blue"


def load_generator():
    spec = importlib.util.spec_from_file_location("build_pilot_chunks_v3", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_lines(path):
    lines = Path(path).read_bytes().decode("utf-8").split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def section_lines(lines):
    """Markdown 줄을 '## '·'### ' 제목별 구간으로 나눈다 (코드 블록 안 제외). {제목: [줄]}."""
    out, current, in_code = {}, "#", False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
        if not in_code and line.startswith("#"):
            current = line
        out.setdefault(current, []).append(line)
    return out


class CurrentTemplatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = load_generator()
        cls.ctx = cls.gen.Context()
        cls.docs = {t: json.loads(FILES[t][1].read_bytes().decode("utf-8")) for t in FILES}
        cls.chunks = {t: {c["section"]: c for c in doc["chunks"]} for t, doc in cls.docs.items()}

    def pokemon(self, pid):
        return self.ctx.pokemon[self.ctx.pokemon_at[pid]]

    # ------------------------------------------------------------ 재생성·최신본

    def test_saved_json_equals_regeneration(self):
        for template in ("tpl3a", "tpl3b"):
            with self.subTest(template):
                document = self.gen.build_document(template=template)
                saved_text = FILES[template][1].read_bytes().decode("utf-8")
                same, detail = self.gen.compare_baseline(document, saved_text, template)
                self.assertTrue(same, detail)
                # 고정본과 다른 곳은 생성기 sha256 하나뿐이다 (매니페스트 sha256·Markdown 경로·청크는 바이트 동일).
                self.assertEqual(self.gen.BASELINES[template], self.gen.TPL3_BASELINE)
                self.assertEqual(list(self.gen.TPL3_BASELINE), ["generator.sha256"])
                self.assertEqual(self.docs[template]["generator"]["sha256"], self.gen.TPL3_BASELINE["generator.sha256"])
                patched = copy.deepcopy(document)
                patched["generator"]["sha256"] = self.gen.TPL3_BASELINE["generator.sha256"]
                self.assertEqual(saved_text, self.gen.render(patched))
                self.assertEqual(self.gen.render(document), self.gen.render(self.gen.build_document(template=template)))
                self.assertEqual((document["template_version"], document["schema_version"]), (template, 3))
                self.assertEqual(document["chunk_ids"], [f"pokemon:1#{s}" for s in SECTIONS])
                self.assertEqual(self.gen.main(["--template", template, "--check"]), 0)

    def test_latest_is_byte_copy_of_v3a(self):
        self.assertEqual(self.gen.DEFAULT_TEMPLATE, "tpl3a")
        for latest, saved in zip(LATEST, FILES["tpl3a"]):
            self.assertEqual(latest.read_bytes(), saved.read_bytes(), latest)
        latest_doc = json.loads(LATEST[1].read_bytes().decode("utf-8"))
        self.assertEqual(latest_doc["template_version"], "tpl3a")
        self.assertEqual([e["path"] for e in latest_doc["source_files"] if e["source_id"] == "pilot_markdown:bulbasaur_red_blue"],
                         ["data/synthetic/pilot/v3a/bulbasaur_red_blue.md"])
        self.assertEqual(self.gen.latest_copy_status(), (True, "최신본 사본 같음"))
        self.assertEqual(self.gen.main(["--check"]), 0)
        self.assertEqual(self.gen.build_document()["template_version"], "tpl3a")

    def test_tpl3b_is_rejected_and_explicit_only(self):
        self.assertIn("tpl3b", self.gen.REJECTED_TEMPLATES)
        self.assertNotIn(self.gen.DEFAULT_TEMPLATE, self.gen.REJECTED_TEMPLATES)
        for latest, saved in zip(LATEST, FILES["tpl3b"]):
            self.assertNotEqual(latest.read_bytes(), saved.read_bytes(), latest)
        # 명시하면 v3b 재현 확인은 된다.
        self.assertEqual(self.gen.main(["--template", "tpl3b", "--check"]), 0)
        # 최신본이 v3b 사본이면 기본 --check가 실패한다 (최신본 위치를 v3b로 바꿔 흉내 낸다).
        original = self.gen.LATEST
        try:
            self.gen.LATEST = {"markdown": str(FILES["tpl3b"][0].relative_to(ROOT).as_posix()),
                               "output": str(FILES["tpl3b"][1].relative_to(ROOT).as_posix())}
            same, detail = self.gen.latest_copy_status()
            self.assertFalse(same, detail)
        finally:
            self.gen.LATEST = original

    def test_chunks_cover_markdown_lines_once(self):
        for template in ("tpl3a", "tpl3b"):
            md_lines = read_lines(FILES[template][0])
            previous_end, owner = 0, {}
            for chunk in self.docs[template]["chunks"]:
                [md] = [r for r in chunk["source_records"] if r["source_id"] == "pilot_markdown:bulbasaur_red_blue"]
                self.assertEqual(md["line_start"], previous_end + 1)
                previous_end = md["line_end"]
                span = md_lines[md["line_start"] - 1:md["line_end"]]
                head, _, body = chunk["content"].partition("\n\n")
                self.assertEqual(head, f"이상해씨 — {self.gen.topic_of(chunk['section'], template, '이상해씨')}")
                self.assertEqual([x for x in body.split("\n") if x.strip()],
                                 [x for x in span if x.strip() and not x.startswith("#")], chunk["chunk_id"])
                for number in range(md["line_start"], md["line_end"] + 1):
                    if md_lines[number - 1].strip():
                        self.assertNotIn(number, owner)
                        owner[number] = chunk["chunk_id"]
            self.assertEqual(previous_end, len(md_lines))
            self.assertEqual(set(owner), {i + 1 for i, x in enumerate(md_lines) if x.strip()})

    # ------------------------------------------------------------ 변수 분리: v2 → A → B

    def test_markdown_diff_is_isolated(self):
        v2, a, b = (section_lines(read_lines(FILES[t][0])) for t in ("tpl2", "tpl3a", "tpl3b"))
        self.assertEqual(list(v2), list(a))  # 제목 문자열·순서 동일 (획득처 제목 유지)
        self.assertEqual(list(a), list(b))
        self.assertEqual([h for h in v2 if v2[h] != a[h]], ["## 획득처"])
        self.assertEqual([h for h in a if a[h] != b[h]],
                         ["### 공격 상성 (이상해씨와 같은 타입 기술이 잘 통하는 타입)", "### 방어 상성 (약점과 저항)"])
        for heading in [h for h in a if a[h] != b[h]]:
            changed = [(x, y) for x, y in zip(a[heading], b[heading]) if x != y]
            self.assertEqual(len(a[heading]), len(b[heading]))
            self.assertEqual(len(changed), 1)
            self.assertTrue(all(x.startswith("요약: ") and y.startswith("요약: ") for x, y in changed))

    def test_chunk_diff_is_isolated(self):
        v2, a, b = (self.chunks[t] for t in ("tpl2", "tpl3a", "tpl3b"))
        self.assertEqual([s for s in SECTIONS if v2[s] != a[s]], ["encounter"])
        self.assertEqual([s for s in SECTIONS if a[s] != b[s]], ["attack_matchup", "defense_matchup"])
        for section in ("attack_matchup", "defense_matchup"):
            self.assertEqual(a[section]["source_records"], b[section]["source_records"])
            self.assertEqual(a[section]["data"], b[section]["data"])
        self.assertEqual(a["encounter"], b["encounter"])

    # ------------------------------------------------------------ (A) 획득처 절

    def test_bulbasaur_encounter_chunk(self):
        content = self.chunks["tpl3a"]["encounter"]["content"]
        self.assertTrue(content.startswith("이상해씨 — 획득처\n\n요약: 이상해씨를 얻는 방법(잡는 곳·받는 곳)과 장소입니다."))
        for text in ("태초마을", "| Red·Blue | 태초마을 | 선물 | 5 |", "야생에서 만나는 기록은 없습니다",
                     "기록이 없다고 해서 얻을 수 없다는 뜻은 아닙니다"):
            self.assertIn(text, content)
        self.assertNotIn("pallet-town", content)
        records = self.chunks["tpl3a"]["encounter"]["source_records"]
        self.assertEqual({r["pointer"] for r in records if r["source_id"] == "processed:encounters_red_blue"}, {"/pokemon/0"})
        self.assertEqual({r["identity_value"] for r in records if r["source_id"] == LOCATION_SOURCE},
                         {"pokeapi_location_area:pallet-town-area"})

    def test_encounter_rules_for_other_species(self):
        cases = {
            2: ["Red와 Blue 모두 등장·획득 기록이 없고, 야생에서 만나는 기록도 없습니다."],   # 기록 없음
            16: ["Red와 Blue 모두 14곳에서 야생 포켓몬으로 만나는 기록이 있습니다.", "| Red·Blue | 1번도로 | 야생(풀숲·동굴) | 2~5 |"],
            23: ["Red에서는 6곳에서 야생 포켓몬으로 만나는 기록이 있습니다.",
                 "Blue에서는 등장·획득 기록이 없고, 야생에서 만나는 기록도 없습니다.", "| Red | 4번도로 | 야생(풀숲·동굴) | 6~12 |"],
            27: ["Red에서는 등장·획득 기록이 없고", "Blue에서는 6곳에서 야생 포켓몬으로 만나는 기록이 있습니다."],
            83: ["갈색시티에서 NPC 교환으로 받는 기록이 있고, 야생에서 만나는 기록은 없습니다.",
                 "| 버전 | 장소 | 방법 | 레벨 | 조건 |", "| Red·Blue | 갈색시티 | NPC 교환 | 3~100 | 깨비참과 교환 |"],
            137: ["| Red | 무지개 게임코너 교환소 | 선물 | 26 | 코인 9999개 |", "| Blue | 무지개 게임코너 교환소 | 선물 | 18 | 코인 6500개 |"],
            138: ["| `item-helix-fossil` |"],  # 한국어 근거가 없는 조건은 식별자 코드 표기
            143: ["12번도로·16번도로에서 야생 포켓몬으로 만나는 기록이 있습니다.", "야생(포켓몬 피리)"],
        }
        for pid, expected in cases.items():
            with self.subTest(pid):
                record = self.pokemon(pid)
                lines, plan = self.gen.encounter_body(self.ctx, record)
                text = "\n".join(lines)
                self.assertTrue(lines[0].startswith(f"요약: {self.gen.with_eul_reul(record['name_ko'])} 얻는 방법(잡는 곳·받는 곳)과 장소입니다. "))
                self.assertEqual(lines[-1].endswith(self.gen.ENCOUNTER_SCOPE_LINE), True)
                self.assertEqual(sum(1 for x in lines if x.startswith("요약: ")), 1)
                for piece in expected:
                    self.assertIn(piece, text)
                if pid == 2:
                    self.assertFalse(any(x.startswith("|") for x in lines))
                self.assertNotIn("-area", text)

    def test_encounter_body_for_all_151(self):
        """151마리 모두 규칙대로 절을 만들 수 있고, 표 행이 encounters 기록(버전·장소·방법·레벨)과 같다."""
        entry_by_id = {row["id"]: row for row in self.ctx.encounters["pokemon"]}
        self.assertEqual(sorted(entry_by_id), list(range(1, 152)))
        for pid in range(1, 152):
            record = self.pokemon(pid)
            lines, plan = self.gen.encounter_body(self.ctx, record)
            expected = set()
            for version in self.gen.GAMES:
                for item in entry_by_id[pid]["versions"][version]["encounters"]:
                    place, _ = self.ctx.place("pokeapi_location_area", item["location_area"]["name"])
                    for d in item["version_detail"]["encounter_details"]:
                        expected.add((version, place, self.gen.ENCOUNTER_METHODS[d["method"]["name"]][1]))
            got = set()
            for label, place, method, level, _ in plan["rows"]:
                for version in self.gen.GAMES:
                    if self.gen.VERSION_LABELS[version] in label.split("·"):
                        got.add((version, place, method))
            self.assertEqual(got, expected, pid)
            has_wild = {v: any(self.gen.ENCOUNTER_METHODS[d["method"]["name"]][0] == "wild"
                               for item in entry_by_id[pid]["versions"][v]["encounters"]
                               for d in item["version_detail"]["encounter_details"]) for v in self.gen.GAMES}
            if not any(has_wild.values()):
                self.assertRegex(lines[0], "야생에서 만나는 기록[은도] 없습니다")

    def test_encounter_section_is_checked_against_data(self):
        md = FILES["tpl3a"][0].read_bytes().decode("utf-8")
        v2_md = FILES["tpl2"][0].read_bytes().decode("utf-8")
        broken = {
            "level_changed": md.replace("| Red·Blue | 태초마을 | 선물 | 5 |", "| Red·Blue | 태초마을 | 선물 | 6 |"),
            "place_changed": md.replace("| Red·Blue | 태초마을 |", "| Red·Blue | 상록시티 |"),
            "identifier_left": md.replace("| Red·Blue | 태초마을 |", "| Red·Blue | `pallet-town-area` |"),
            "method_changed": md.replace("| 태초마을 | 선물 |", "| 태초마을 | NPC 교환 |"),
            "version_split": md.replace("| Red·Blue | 태초마을 |", "| Red | 태초마을 |"),
            "row_removed": md.replace("| Red·Blue | 태초마을 | 선물 | 5 |\n", ""),
            "summary_missing": md.replace("요약: 이상해씨를 얻는", "이상해씨를 얻는"),
            "wild_sentence_dropped": md.replace(", 야생에서 만나는 기록은 없습니다.", "."),
            "scope_note_dropped": md.replace(" PokéAPI의 등장·획득 기록 기준이며, 기록이 없다고 해서 얻을 수 없다는 뜻은 아닙니다.", ""),
            "new_fact_added": md + "\n\n이상해씨는 오박사에게서 받습니다.",
            "wrong_josa": md.replace("요약: 이상해씨를 얻는", "요약: 이상해씨을 얻는"),
        }
        for label, text in broken.items():
            self.assertNotEqual(text, md, label)
            with self.subTest(label):
                with self.assertRaises(self.gen.ChunkError):
                    self.gen.build_document(text, template="tpl3a")
        with self.assertRaises(self.gen.ChunkError):  # v2 획득처 문장은 tpl3a 규칙이 아니다
            self.gen.build_document(v2_md, template="tpl3a")

    def test_unknown_encounter_method_is_rejected(self):
        ctx = copy.copy(self.ctx)
        ctx.encounters = copy.deepcopy(self.ctx.encounters)
        detail = ctx.encounters["pokemon"][0]["versions"]["red"]["encounters"][0]["version_detail"]["encounter_details"][0]
        detail["method"]["name"] = "headbutt"
        with self.assertRaises(self.gen.ChunkError):
            self.gen.encounter_body(ctx, self.pokemon(1))

    # ------------------------------------------------------------ (B) 상성 방향 구분 (기각된 실험 tpl3b 재현 검사)

    def test_josa_eul_reul_i_ga(self):
        names = {row["name_ko"] for row in self.ctx.pokemon}
        cases = {"이상해씨": ("이상해씨를", "이상해씨가"), "피카츄": ("피카츄를", "피카츄가"), "리자몽": ("리자몽을", "리자몽이"),
                 "이상해꽃": ("이상해꽃을", "이상해꽃이"), "롱스톤": ("롱스톤을", "롱스톤이"), "꼬부기": ("꼬부기를", "꼬부기가"),
                 "니드런♀": ("니드런♀을", "니드런♀이"), "니드런♂": ("니드런♂을", "니드런♂이"), "뮤": ("뮤를", "뮤가")}
        for name, (eul, i) in cases.items():
            with self.subTest(name):
                self.assertIn(name, names)
                self.assertEqual(self.gen.with_eul_reul(name), eul)
                self.assertEqual(self.gen.with_i_ga(name), i)
        for name in names:  # 151마리 모두 조사를 정할 수 있고 세 조사가 같은 받침 판단을 쓴다
            batchim = self.gen.with_gwa_wa(name).endswith("과")
            self.assertEqual(self.gen.with_eul_reul(name).endswith("을"), batchim, name)
            self.assertEqual(self.gen.with_i_ga(name).endswith("이"), batchim, name)
        for bad in ("Pikachu", "♀", "", None):
            for fn in (self.gen.with_eul_reul, self.gen.with_i_ga):
                with self.assertRaises(self.gen.ChunkError):
                    fn(bad)

    def test_bulbasaur_direction_summaries(self):
        attack = [x for x in self.chunks["tpl3b"]["attack_matchup"]["content"].split("\n") if x.startswith("요약: ")]
        defense = [x for x in self.chunks["tpl3b"]["defense_matchup"]["content"].split("\n") if x.startswith("요약: ")]
        self.assertEqual(len(attack), 1)
        self.assertEqual(len(defense), 1)
        self.assertTrue(attack[0].startswith("요약: 이상해씨가 상대에게 풀·독 타입 기술을 쓸 때의 상성입니다. 효과가 굉장한(2배) 상대 타입은"))
        for piece in ("요약: 이상해씨가 공격받을 때의 상성입니다.",
                      "이상해씨에게 효과가 굉장한(2배 이상) 기술 타입, 즉 약점은 벌레(4배), 비행·불꽃·에스퍼·얼음(2배)이고",
                      "이상해씨에게 효과가 별로인(0.5배 이하) 기술 타입, 즉 저항은 격투·물·전기(0.5배), 풀(0.25배)이며",
                      "이상해씨에게 효과가 없는(0배) 기술 타입, 즉 무효는 없습니다.",
                      "이상해씨를 상대할 때 유리한 기술 타입은 약점인 벌레·비행·불꽃·에스퍼·얼음입니다."):
            self.assertIn(piece, defense[0])
        # 공격 요약의 v2 부분은 그대로다
        v2_attack = [x for x in self.chunks["tpl2"]["attack_matchup"]["content"].split("\n") if x.startswith("요약: ")][0]
        self.assertTrue(attack[0].endswith(v2_attack[len("요약: "):]))

    def defense_rows(self, pid):
        """type_chart 곱으로 DEFENSE_ROWS 순서의 (구분, 배율, 한국어 타입 목록)을 만들고 BattleRules와 대조한다."""
        own = self.pokemon(pid)["types_gen1"]
        factors = {a: self.gen.number_value(math.prod(self.ctx.chart[a][t] for t in own)) for a in sorted(self.ctx.chart)}
        self.gen.defense_rules_check(self.ctx, pid, own)  # BattleRules 계산과 type_chart 곱이 다르면 ChunkError
        order = [row["name"] for row in self.ctx.types]
        return [(label, factor, [self.ctx.type_ko(a) for a in order if factors.get(a) == factor])
                for label, factor in self.gen.DEFENSE_ROWS]

    def test_direction_summaries_for_other_species(self):
        cases = {
            6: ("리자몽이 공격받을 때의 상성입니다.", "즉 약점은 바위(4배)"),
            92: ("고오스가 공격받을 때의 상성입니다.", "즉 무효는 노말·격투입니다."),
            50: ("디그다가 공격받을 때의 상성입니다.", "즉 무효는 전기입니다."),
            29: ("니드런♀이 공격받을 때의 상성입니다.", "니드런♀을 상대할 때 유리한 기술 타입은 약점인"),
        }
        for pid, pieces in cases.items():
            with self.subTest(pid):
                name = self.pokemon(pid)["name_ko"]
                rows = self.defense_rows(pid)
                summary = self.gen.defense_summary(name, rows, True)
                weak = [n for label, _, names in rows if label == "약점" for n in names]
                expected_advantage = f"{self.gen.with_eul_reul(name)} 상대할 때 유리한 기술 타입은 약점인 {'·'.join(weak)}입니다."
                self.assertTrue(summary.endswith(expected_advantage), summary)
                self.assertIn(pieces[0], summary)
                self.assertIn(pieces[1], summary)
                self.assertIn(f"{name}에게 효과가 굉장한(2배 이상) 기술 타입, 즉 약점은", summary)
                self.assertEqual(self.gen.defense_summary(name, rows), self.gen.defense_summary(name, rows, False))
        # 약점이 없을 때의 문장
        none_rows = [(label, factor, []) for label, factor in self.gen.DEFENSE_ROWS]
        summary = self.gen.defense_summary("리자몽", none_rows, True)
        self.assertIn("즉 약점은 없고", summary)
        self.assertIn("즉 저항은 없으며", summary)
        self.assertTrue(summary.endswith("리자몽을 상대할 때 유리한 기술 타입은 없습니다."))
        # 공격 요약 방향 문장 (조사 이/가)
        columns = [[("불꽃", ["풀"]), ("비행", ["풀"])], [("불꽃", []), ("비행", [])], [("불꽃", []), ("비행", [])]]
        self.assertTrue(self.gen.attack_summary(columns, "리자몽", True)
                        .startswith("요약: 리자몽이 상대에게 불꽃·비행 타입 기술을 쓸 때의 상성입니다. 효과가 굉장한(2배) 상대 타입은"))

    def test_direction_summary_is_checked(self):
        md = FILES["tpl3b"][0].read_bytes().decode("utf-8")
        a_md = FILES["tpl3a"][0].read_bytes().decode("utf-8")
        broken = {
            "defense_direction_dropped": md.replace("요약: 이상해씨가 공격받을 때의 상성입니다. ", "요약: "),
            "defense_advantage_dropped": md.replace(" 이상해씨를 상대할 때 유리한 기술 타입은 약점인 벌레·비행·불꽃·에스퍼·얼음입니다.", ""),
            "defense_advantage_wrong": md.replace("약점인 벌레·비행·불꽃·에스퍼·얼음입니다.", "약점인 벌레·비행·불꽃·에스퍼입니다."),
            "defense_factor_wrong": md.replace("즉 약점은 벌레(4배)", "즉 약점은 벌레(2배)"),
            "defense_josa_wrong": md.replace("요약: 이상해씨가 공격받을", "요약: 이상해씨이 공격받을"),
            "attack_direction_dropped": md.replace("요약: 이상해씨가 상대에게 풀·독 타입 기술을 쓸 때의 상성입니다. ", "요약: "),
            "attack_types_wrong": md.replace("상대에게 풀·독 타입 기술을", "상대에게 풀 타입 기술을"),
        }
        for label, text in broken.items():
            self.assertNotEqual(text, md, label)
            with self.subTest(label):
                with self.assertRaises(self.gen.ChunkError):
                    self.gen.build_document(text, template="tpl3b")
        with self.assertRaises(self.gen.ChunkError):  # tpl3a 요약 문장은 tpl3b 규칙이 아니다
            self.gen.build_document(a_md, template="tpl3b")
        with self.assertRaises(self.gen.ChunkError):  # tpl3b 요약 문장은 tpl3a 규칙이 아니다
            self.gen.build_document(md, template="tpl3a")

    def test_baseline_outputs_are_not_overwritten(self):
        for template in ("tpl1", "tpl2", "tpl3a", "tpl3b"):
            before = FILES.get(template, (None, PILOT / "v1" / "bulbasaur_red_blue.json"))[1].read_bytes()
            self.assertEqual(self.gen.main(["--template", template]), 2)
            self.assertEqual(FILES.get(template, (None, PILOT / "v1" / "bulbasaur_red_blue.json"))[1].read_bytes(), before)
        before = [p.read_bytes() for p in LATEST]
        self.assertEqual(self.gen.main([]), 2)  # 기본(tpl3a) 쓰기도 고정본 v3a를 덮어쓰지 않는다
        self.assertEqual(self.gen.main(["--output", str(LATEST[1])]), 2)  # 최신본은 사본으로만 만든다
        self.assertEqual([p.read_bytes() for p in LATEST], before)


if __name__ == "__main__":
    unittest.main()
