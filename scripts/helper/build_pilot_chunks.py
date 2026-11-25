#!/usr/bin/env python3
"""파일럿 포켓몬 Markdown을 chunking 스킬의 제목 표대로 나눠 청크 JSON을 만든다.

템플릿 버전 (chunking 스킬 '템플릿 버전'). 파일은 data/synthetic/pilot/{v1,v2,v3a,v3b}/bulbasaur_red_blue.{md,json}:
- tpl3a (기본, 채택): tpl2 + 획득처 절 보강(버전별 장소·방법·레벨 표와 '얻는 방법' 요약 문장, encounters 데이터와
  줄 단위 대조). 최신본 data/synthetic/pilot/bulbasaur_red_blue.{md,json}은 v3a 파일의 바이트 사본이다 (LATEST).
- tpl3b (기각된 실험, REJECTED_TEMPLATES): tpl3a + 상성 요약 문장의 방향 구분. 파일럿 비교에서 기각돼 기본·최신본으로
  고르지 않으며 --template tpl3b --check로 v3b 재현 확인만 한다.
- tpl2: v2 기준선 재현용 (수정 금지). 내용이 드러나는 상성 제목, 상성 표준 용어 표·요약 문장, 장소 한국어명.
- tpl1: v1 기준선 재현용 (수정 금지).
v1·v2·v3a·v3b 폴더 파일은 모두 고정본이며 생성기는 그 JSON에 쓰지 않는다 (BASELINES).

입력: Markdown (수정하지 않는다), data/processed/*.json, data/source_manifest.json, scripts/gen1_battle/gen1_battle_rules.py
출력: 청크 JSON (임베딩·인덱싱은 하지 않는다)

사용법:
    uv run python scripts/helper/build_pilot_chunks.py --check             # tpl3a(v3a) 재현·최신본 사본 확인, 다르면 종료 코드 1
    uv run python scripts/helper/build_pilot_chunks.py --template tpl3b --check   # 기각된 실험 v3b 재현 확인 (명시할 때만)
    uv run python scripts/helper/build_pilot_chunks.py --template tpl2 --check   # 기준선 (출처 값 제외 비교)
    uv run python scripts/helper/build_pilot_chunks.py --template tpl1 --check
    uv run python scripts/helper/build_pilot_chunks.py --markdown 다른.md --output 다른.json

- 표준 라이브러리만 쓰고 네트워크를 쓰지 않는다. 실행 시각 같은 가변 값을 넣지 않는다.
- 청크 본문은 '머리말 한 줄 + 빈 줄 + Markdown 구간 본문'이다. 본문은 제목 줄을 빼고, 앞뒤 빈 줄을 지우고,
  제목을 뺀 자리에 생긴 연속 빈 줄을 하나로 줄인 것 외에는 Markdown 줄을 그대로 옮긴다.
- 표에 없는 제목, 빠진·중복·순서가 다른 제목, 이름·도감번호 불일치, 머신 절 유무 불일치, 표 값·요약 문장·장소명과
  정제 데이터·계산 규칙·장소 대응표의 불일치는 ChunkError로 멈춘다.
- 모든 sha256은 LF 바이트 기준이다. data/ 아래 JSON·Markdown은 .gitattributes(text eol=lf)로 LF로 고정되므로
  data/processed 파일의 sha256은 source_manifest.json 값을 쓰고 실제 파일 바이트와 일치하는지 확인한다.
  .gitattributes 대상이 아닌 계산 규칙·생성기(.py)의 sha256은 CRLF→LF 정규화 바이트(Git에 저장되는 형태) 기준이다.
- --check는 고정본 JSON과 바이트 단위로 비교하되, 고정 이후 바뀔 수밖에 없는 출처 기록(BASELINES[템플릿]의 키)은
  제외하고 저장본의 그 값이 기록된 기준선 값인지 따로 확인한다. tpl1·tpl2는 3곳(TPL1_VOLATILE: 생성기 자신의 sha256,
  source_manifest.json sha256, Markdown 경로), tpl3a·tpl3b는 생성기 sha256 한 곳이다. 고정본 JSON에는 쓰지 않으며,
  새 출력은 --output으로 다른 경로에 쓴다.
"""

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.gen1_battle.gen1_battle_rules import COMMIT, BattleRules  # noqa: E402

VERSION_GROUP = "red-blue"
GAMES = ["red", "blue"]
IN_GAME_METHODS = ("level-up", "machine")

MANIFEST_PATH = "data/source_manifest.json"
RULES_PATH = "scripts/gen1_battle/gen1_battle_rules.py"
GENERATOR_PATH = "scripts/helper/build_pilot_chunks.py"
LOCATION_NAMES_SOURCE_ID = "processed:location_names_ko_red_blue"
MARKDOWN_SOURCE_ID = "pilot_markdown:bulbasaur_red_blue"
RULES_SOURCE_ID = "code:gen1_battle_rules"
GENERATION_MODE = "markdown_section_split"
GENERATED_BY = "deterministic Python Markdown section splitter (verbatim section text + one-line prefix)"

# (제목 문자열, section 또는 상위 제목이면 None, 상위 제목 이름). 순서가 문서 순서다 (chunking 스킬 '청크 단위' 표).
# tpl2 제목의 {name}은 문서 # 제목(포켓몬 한국어명)으로, {name}{과/와}는 이름 + 조사(with_gwa_wa)로 채운다.
LAYOUTS = {
    "tpl1": [
        ("## 어떤 포켓몬인가요?", "profile", None),
        ("## 종족치", "stats", None),
        ("## 진화", "evolution", None),
        ("## 기술", None, None),
        ("### 레벨업으로 배우는 기술", "learnset_level", "기술"),
        ("### 기술머신·비전머신으로 배우는 기술", "learnset_machine", "기술"),
        ("### 머신은 어디서 얻나요?", "machine_acquisition", "기술"),
        ("## 타입 · 상성", None, None),
        ("### 자속 보정", "stab", "타입 · 상성"),
        ("### 공격할 때", "attack_matchup", "타입 · 상성"),
        ("### 공격받을 때", "defense_matchup", "타입 · 상성"),
        ("## 획득처", "encounter", None),
    ],
    "tpl2": [
        ("## 어떤 포켓몬인가요?", "profile", None),
        ("## 종족치", "stats", None),
        ("## 진화", "evolution", None),
        ("## 기술", None, None),
        ("### 레벨업으로 배우는 기술", "learnset_level", "기술"),
        ("### 기술머신·비전머신으로 배우는 기술", "learnset_machine", "기술"),
        ("### 머신은 어디서 얻나요?", "machine_acquisition", "기술"),
        ("## 타입 · 상성", None, None),
        ("### 자속 보정 (같은 타입 기술 1.5배)", "stab", "타입 · 상성"),
        ("### 공격 상성 ({name}{과/와} 같은 타입 기술이 잘 통하는 타입)", "attack_matchup", "타입 · 상성"),
        ("### 방어 상성 (약점과 저항)", "defense_matchup", "타입 · 상성"),
        ("## 획득처", "encounter", None),
    ],
}
# tpl3a·tpl3b는 제목 표가 tpl2와 같다 (바뀌는 것은 획득처 본문과 상성 요약 문장).
LAYOUTS["tpl3a"] = list(LAYOUTS["tpl2"])
LAYOUTS["tpl3b"] = list(LAYOUTS["tpl2"])
LAYOUT = LAYOUTS["tpl2"]
OPTIONAL_WITHOUT_MACHINES = "### 머신은 어디서 얻나요?"
PROFILE_TOPIC = "기본 정보"
PILOT_DIR = "data/synthetic/pilot"
TEMPLATES = {
    "tpl1": {"markdown": f"{PILOT_DIR}/v1/bulbasaur_red_blue.md",
             "output": f"{PILOT_DIR}/v1/bulbasaur_red_blue.json", "schema_version": 2},
    "tpl2": {"markdown": f"{PILOT_DIR}/v2/bulbasaur_red_blue.md",
             "output": f"{PILOT_DIR}/v2/bulbasaur_red_blue.json", "schema_version": 3},
    "tpl3a": {"markdown": f"{PILOT_DIR}/v3a/bulbasaur_red_blue.md",
              "output": f"{PILOT_DIR}/v3a/bulbasaur_red_blue.json", "schema_version": 3},
    "tpl3b": {"markdown": f"{PILOT_DIR}/v3b/bulbasaur_red_blue.md",
              "output": f"{PILOT_DIR}/v3b/bulbasaur_red_blue.json", "schema_version": 3},
}
DEFAULT_TEMPLATE = "tpl3a"
# 기각된 실험 템플릿: --template로 명시할 때만 재현 확인용으로 쓰고 기본·최신본으로 고르지 않는다 (chunking 스킬).
REJECTED_TEMPLATES = {
    "tpl3b": "상성 요약 방향 문장: 목표 질의 순위 변화 없음(각 3위), 기존 질의 2개 악화, Hit@5 25→24, MRR 0.765→0.755",
}
if DEFAULT_TEMPLATE in REJECTED_TEMPLATES:
    raise RuntimeError(f"기각된 템플릿은 기본 템플릿이 될 수 없다: {DEFAULT_TEMPLATE}")
# 최신본: 기본 템플릿 파일의 바이트 사본 (JSON 안의 Markdown 경로는 기본 템플릿 폴더를 가리킨다).
LATEST = {"markdown": f"{PILOT_DIR}/bulbasaur_red_blue.md", "output": f"{PILOT_DIR}/bulbasaur_red_blue.json"}
# 템플릿별 본문 규칙. encounter_v3: 획득처 표·요약(tpl3a~), matchup_direction: 상성 요약 방향 구분(tpl3b~).
FEATURES = {
    "tpl1": {"modern": False, "encounter_v3": False, "matchup_direction": False},
    "tpl2": {"modern": True, "encounter_v3": False, "matchup_direction": False},
    "tpl3a": {"modern": True, "encounter_v3": True, "matchup_direction": False},
    "tpl3b": {"modern": True, "encounter_v3": True, "matchup_direction": True},
}
# 고정본 JSON에 기록된 출처 값. 키가 비교에서 제외하는 필드다. 생성기·매니페스트·Markdown 위치는 고정 이후 바뀌었으므로
# 재생성 결과와 비교할 때 제외하고 이 값과 대조한다. tpl2(v2)의 Markdown 경로는 v2 당시 최신본 위치(지금은 tpl3a 사본)이며,
# 같은 바이트의 보존본이 v2/에 있다 (Markdown sha256은 비교 대상에 남는다).
TPL1_BASELINE = {
    "generator.sha256": "1580c6d18bec5b155107772e3383276fa3c888224d702138ff883c33a86de72d",
    "manifest.sha256": "e32d0e1851d6048b5b6d6231787fda6016cb8b02ddfbf757da84bbb76264f170",
    "source_files[pilot_markdown].path": "data/synthetic/pilot/bulbasaur_red_blue.md",
}
TPL2_BASELINE = {
    "generator.sha256": "37e8be1bed595638849da06cf00e82ed40ec013d71c4a7f8f90876959db2c6e4",
    "manifest.sha256": "2a78058bbe17b9331d5d13b4db07e56ca7d3565d08d65671f4c6c883eaf0ebbe",
    "source_files[pilot_markdown].path": "data/synthetic/pilot/bulbasaur_red_blue.md",
}
# v3a·v3b JSON은 파일럿 비교 당시 생성기로 만든 고정본이다. 기본 템플릿을 tpl3a로 되돌리며 생성기가 바뀌었으므로
# 생성기 sha256만 제외한다 (매니페스트 sha256·Markdown 경로는 그대로 비교한다).
TPL3_BASELINE = {
    "generator.sha256": "fdee159de1ccc943313d428a5d264b7914e481d199164f215b57e9d69f50a3e1",
}
TPL1_VOLATILE = tuple(TPL1_BASELINE)
BASELINES = {"tpl1": TPL1_BASELINE, "tpl2": TPL2_BASELINE,
             "tpl3a": dict(TPL3_BASELINE), "tpl3b": dict(TPL3_BASELINE)}

STAT_COLUMNS = {"HP": "hp", "공격": "attack", "방어": "defense", "스피드": "speed", "특수": "special"}
ACQUISITION_LABELS = {
    "reward_npc": "NPC 보상",
    "ground_item": "바닥 아이템",
    "shop": "상점",
    "game_corner_prize": "게임코너 경품 교환",
}
ENCOUNTER_LABELS = {"gift": "선물"}
# tpl3a 획득처 절 (chunking 스킬 '획득처 절'). encounters_red_blue.json의 method → 표의 방법 표기 (팀이 정한 번역).
# 정의되지 않은 method가 나오면 ChunkError로 멈춘다 (추측해서 표기하지 않는다).
ENCOUNTER_METHODS = {
    "walk": ("wild", "야생(풀숲·동굴)"),
    "old-rod": ("wild", "야생(낡은낚싯대 낚시)"),
    "good-rod": ("wild", "야생(좋은낚싯대 낚시)"),
    "super-rod": ("wild", "야생(대단한낚싯대 낚시)"),
    "surf": ("wild", "야생(파도타기)"),
    "static": ("wild", "야생(고정 출현)"),
    "pokeflute": ("wild", "야생(포켓몬 피리)"),
    "gift": ("gift", "선물"),
    "npc-trade": ("npc-trade", "NPC 교환"),
}
# 요약 문장에서 방법 묶음을 쓰는 순서와 동사구
ENCOUNTER_GROUPS = [("wild", "야생 포켓몬으로 만나는"), ("gift", "선물로 받는"), ("npc-trade", "NPC 교환으로 받는")]
ENCOUNTER_HEADER = ["버전", "장소", "방법", "레벨"]
ENCOUNTER_CONDITION_HEADER = "조건"
ENCOUNTER_SUMMARY_PLACES = 3  # 묶음마다 장소가 이보다 많으면 요약 문장에 장소 대신 개수를 쓴다 (장소는 표)
ENCOUNTER_PLACE_LINE = "장소는 한국어판 게임의 장소 이름입니다."
ENCOUNTER_SCOPE_LINE = "PokéAPI의 등장·획득 기록 기준이며, 기록이 없다고 해서 얻을 수 없다는 뜻은 아닙니다."
VERSION_LABELS = {"red": "Red", "blue": "Blue"}
NONE_CELL = "없음"
# tpl2 상성 표준 용어 (chunking 스킬 '상성 표준 용어')
ATTACK_TERMS = [(2, "효과가 굉장한"), (0.5, "효과가 별로인"), (0, "효과가 없는")]
ATTACK_HEADER = ["기술 타입"] + [f"{term}({factor}배) 상대 타입" for factor, term in ATTACK_TERMS]
DEFENSE_ROWS = [("약점", 4), ("약점", 2), ("저항", 0.5), ("저항", 0.25), ("무효", 0)]
DEFENSE_HEADER = ["구분", "상대 기술의 타입", "받는 피해"]
MATCHUP_TERMS = ("약점", "저항", "무효", "효과가 굉장한", "효과가 별로인", "효과가 없는", "강점")
FORBIDDEN_TERMS = ("강점",)

LIMITATIONS = [
    "원본 수집 스냅샷과 API는 필요하지 않으며 외부 출처 정보는 계보만 나타낸다.",
    "원본 수집일이 확인되지 않은 자료는 수집일을 추정하지 않는다.",
    "정적 표와 분류를 사용하며 게임 실행 검증이 아니다.",
    "청크 본문은 Markdown 구간을 그대로 옮긴 것이다. 생성기는 표의 값과 이름을 정제 데이터와 대조하지만 문장 전체의 사람 검토를 대신하지 않는다.",
    "모든 sha256은 LF 바이트 기준이다. data/processed 파일의 sha256은 source_manifest.json 값이며, 생성기가 .gitattributes(text eol=lf)로 LF 고정된 실제 파일 바이트와 일치함을 확인했다.",
    "Markdown, source_manifest.json은 LF 고정 파일 바이트, 계산 규칙과 생성기(.py)는 CRLF→LF 정규화 바이트(Git 저장 형태) 기준이다.",
    "인간 검토 전 색인 금지; 저작권 및 재배포 조건은 별도 확인.",
]
TPL2_LIMITATIONS = [
    "장소 한국어명은 location_names_ko_red_blue.json 대응표의 값이며 대응표는 사용자가 승인했다(approved, 홍련섬 결정 포함).",
]
TPL3_LIMITATIONS = [
    "획득처 절의 방법 표기(선물·NPC 교환·야생(…))와 조건 표기는 encounters_red_blue.json의 method·condition 값을 팀이 옮긴"
    " 표기이며 사람 검토 전이다. 출현 확률은 싣지 않는다.",
]
LOCALIZATION_NOTE = "한국어 명칭은 정제 데이터의 현재 명칭이며 영문판의 역사적 번역이 아니다."
TPL2_LOCALIZATION_NOTE = (LOCALIZATION_NOTE + " 장소명은 Red·Blue 한국어판이 없어 칸토가 나오는 한국어판 게임의 공식 명칭"
                          "(층·방·구역 수식어는 팀이 붙인 표기)을 대응표에서 가져왔다.")
TIMESTAMP_NOTE = "목록 작성 시각이며 원본 수집 시각이 아니다."
MARKDOWN_NOTES = [
    "청크 본문의 원문. 사람 검토 전 파일럿 초안이다.",
    "line_start·line_end는 1부터 세는 줄 번호이며 청크 ID에는 쓰지 않는다.",
]
RULES_NOTES = [
    "자속·상성 배율 계산 규칙. 명목 배율이며 실제 피해량이 아니다.",
    "피해 분류 출처 커밋은 파일의 COMMIT 값이다.",
]


class ChunkError(ValueError):
    """Markdown이 chunking 스킬 규칙이나 정제 데이터와 맞지 않는다."""


def lf_bytes(path):
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def sha256_lf(path):
    return hashlib.sha256(lf_bytes(path)).hexdigest()


def sha256_file(path):
    """LF로 고정된 data/ 파일의 실제 바이트 sha256 (verify_bundle()과 같은 기준)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(relpath):
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


def check_template(template):
    if template not in TEMPLATES:
        raise ChunkError(f"알 수 없는 템플릿: {template}")
    return template


NAME_PLACEHOLDER = "{name}"
JOSA_PLACEHOLDER = "{name}{과/와}"
# 조사를 고를 때 건너뛰는 이름 끝 기호 (니드런♀·니드런♂는 '니드런'으로 읽는다)
JOSA_IGNORED_SUFFIX = "♀♂"


def has_final_consonant(syllable):
    """한글 음절에 받침이 있는가. 한글 음절이 아니면 ChunkError."""
    code = ord(syllable) - 0xAC00
    if not 0 <= code <= 0x2BA3:
        raise ChunkError(f"조사를 정할 수 없는 글자: {syllable!r}")
    return code % 28 != 0


def with_josa(name, after_consonant, after_vowel):
    """이름 + 받침에 따른 조사. 마지막 한글 음절(끝의 ♀·♂ 제외)에 받침이 있으면 after_consonant, 없으면 after_vowel."""
    stem = name.rstrip(JOSA_IGNORED_SUFFIX) if isinstance(name, str) else ""
    if not stem:
        raise ChunkError(f"조사를 정할 수 없는 이름: {name!r}")
    return name + (after_consonant if has_final_consonant(stem[-1]) else after_vowel)


def with_gwa_wa(name):
    """이름 + 조사 '과/와'. 마지막 한글 음절(끝의 ♀·♂ 제외)에 받침이 있으면 '과', 없으면 '와'."""
    return with_josa(name, "과", "와")


def with_eul_reul(name):
    """이름 + 조사 '을/를' (with_gwa_wa와 같은 받침 규칙)."""
    return with_josa(name, "을", "를")


def with_i_ga(name):
    """이름 + 조사 '이/가' (with_gwa_wa와 같은 받침 규칙)."""
    return with_josa(name, "이", "가")


def layout_for(template, name):
    """템플릿 제목 표에 포켓몬명을 채운다. name이 '{name}'이면 자리표시자를 그대로 둔다."""
    if name == NAME_PLACEHOLDER:
        return list(LAYOUTS[template])
    filled = []
    for heading, section, parent in LAYOUTS[template]:
        heading = heading.replace(JOSA_PLACEHOLDER, with_gwa_wa(name)).replace(NAME_PLACEHOLDER, name)
        filled.append((heading, section, parent))
    return filled


def in_game_learnset(record):
    """Red·Blue 게임 안에서 배우는 learnset 기록 (level-up·machine)만 (원래 인덱스, 기록) 목록으로 준다."""
    return [
        (index, row)
        for index, row in enumerate(record["learnset"])
        if row["version_group"] == VERSION_GROUP and row["method"] in IN_GAME_METHODS
    ]


def topic_of(section, template=DEFAULT_TEMPLATE, name="{name}"):
    """머리말 주제. tpl1은 '상위 > 제목', tpl2는 제목 문자열만 쓴다. profile은 '기본 정보'."""
    if section == "profile":
        return PROFILE_TOPIC
    for heading, sec, parent in layout_for(check_template(template), name):
        if sec == section:
            title = heading.lstrip("#").strip()
            return f"{parent} > {title}" if parent and template == "tpl1" else title
    raise KeyError(section)


def prefix_of(record, number, section, template):
    if template == "tpl1":
        return f"{record['name_ko']} (도감번호 {number}, 영문 Red·Blue) — {topic_of(section, template, record['name_ko'])}"
    return f"{record['name_ko']} — {topic_of(section, template, record['name_ko'])}"


# ---------------------------------------------------------------- Markdown 분할


def find_headings(lines):
    headings = []
    in_code = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code and re.match(r"^#{1,6}(\s|$)", line.strip()):
            headings.append((index, line.strip()))
    if in_code:
        raise ChunkError("닫히지 않은 코드 블록")
    return headings


def split_markdown(md_text, pokemon_rows, template=DEFAULT_TEMPLATE):
    """Markdown을 제목 표대로 나눈다. 반환: (포켓몬 레코드, 도감번호 문자열, 청크 구간 목록)."""
    if "\r" in md_text.replace("\r\n", "\n"):
        raise ChunkError("단독 CR 줄바꿈")
    lines = md_text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    headings = find_headings(lines)
    h1 = [(i, t) for i, t in headings if re.match(r"^#(\s|$)", t)]
    if len(h1) != 1 or h1[0][0] != 0:
        raise ChunkError(f"# 제목은 첫 줄에 정확히 하나여야 한다: {h1}")
    name = h1[0][1][1:].strip()
    layout = layout_for(template, name)
    body_headings = headings[1:]
    known = {heading: (section, parent) for heading, section, parent in layout}
    first_section = next((i for i, t in body_headings), len(lines))
    profile_lines = lines[:first_section]
    numbers = [m.group(1) for line in profile_lines for m in [re.match(r"^- \*\*도감번호:\*\* (\d{3})$", line.strip())] if m]
    if len(numbers) != 1:
        raise ChunkError(f"도감번호 줄은 # 제목과 첫 ## 사이에 하나여야 한다: {numbers}")
    number = numbers[0]
    record = next((row for row in pokemon_rows if row["id"] == int(number)), None)
    if record is None or record["name_ko"] != name:
        raise ChunkError(f"이름·도감번호가 pokemon.json과 다르다: {name} {number}")

    for index, text in body_headings:
        if text not in known:
            raise ChunkError(f"표에 없는 제목 {index + 1}행: {text!r}")
    seen = [text for _, text in body_headings]
    duplicated = sorted({text for text in seen if seen.count(text) > 1})
    if duplicated:
        raise ChunkError(f"중복 제목: {duplicated}")

    has_machine = any(row["method"] == "machine" for _, row in in_game_learnset(record))
    expected = [h for h, _, _ in layout if has_machine or h != OPTIONAL_WITHOUT_MACHINES]
    if seen != expected:
        missing = [h for h in expected if h not in seen]
        unexpected = [h for h in seen if h not in expected]
        raise ChunkError(f"제목 구성·순서가 표와 다르다: 빠짐={missing} 예상밖={unexpected} 실제={seen}")

    starts = [("profile", 0)]
    pending_parent = None
    for index, text in body_headings:
        section, _ = known[text]
        if section is None:
            pending_parent = index
        elif section == "profile":
            continue
        else:
            starts.append((section, index if pending_parent is None else pending_parent))
            pending_parent = None
    if pending_parent is not None:
        raise ChunkError("하위 ### 제목이 없는 상위 제목")

    heading_index = {index for index, _ in headings}
    spans = []
    for position, (section, start) in enumerate(starts):
        end = starts[position + 1][1] - 1 if position + 1 < len(starts) else len(lines) - 1
        body = []
        for index in range(start, end + 1):
            if index in heading_index:
                continue
            line = lines[index]
            if not line.strip() and (not body or not body[-1].strip()):
                continue
            body.append(line)
        while body and not body[-1].strip():
            body.pop()
        if not body:
            raise ChunkError(f"본문이 없는 절: {section}")
        spans.append({
            "section": section,
            "line_start": start + 1,
            "line_end": end + 1,
            "headings": [lines[i].strip() for i in range(start, end + 1) if i in heading_index],
            "body": body,
        })
    return record, number, spans


# ---------------------------------------------------------------- 표 읽기와 데이터 대조


def parse_table(body, section):
    rows = [line.strip() for line in body if line.strip().startswith("|")]
    if len(rows) < 3:
        raise ChunkError(f"{section}: 표가 없다")
    cells = [[cell.strip() for cell in row.strip("|").split("|")] for row in rows]
    header, separator, data = cells[0], cells[1], cells[2:]
    if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
        raise ChunkError(f"{section}: 표 구분선이 아니다")
    if any(len(row) != len(header) for row in data):
        raise ChunkError(f"{section}: 표 열 수가 다르다")
    return header, data


def split_names(cell):
    return [part.strip() for part in cell.split(",") if part.strip()] if cell.strip() else []


def type_cell(cell, ctx, section):
    """표의 타입 칸을 (영문 타입 목록, 한국어 이름 목록)으로 읽는다. '없음'은 빈 목록이다."""
    if cell == NONE_CELL:
        return [], []
    names = split_names(cell)
    if not names or NONE_CELL in names:
        raise ChunkError(f"{section}: 빈 칸은 '{NONE_CELL}'으로 쓴다: {cell!r}")
    types = [ctx.type_by_ko.get(name) for name in names]
    if None in types or len(set(types)) != len(types):
        raise ChunkError(f"{section}: 알 수 없거나 중복된 타입: {cell!r}")
    return types, names


def number_value(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def parse_factor(cell, section):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)배", cell)
    if not match:
        raise ChunkError(f"{section}: 배율 형식이 아니다: {cell!r}")
    return number_value(match.group(1))


def summary_line(body, section):
    lines = [line for line in body if line.startswith("요약: ")]
    if len(lines) != 1:
        raise ChunkError(f"{section}: '요약: '으로 시작하는 요약 문장이 한 줄이어야 한다")
    return lines[0]


class Context:
    def __init__(self):
        self.manifest = load_json(MANIFEST_PATH)
        self.files = {entry["source_id"]: entry for entry in self.manifest["processed_files"]}
        for entry in self.files.values():
            if sha256_file(ROOT / entry["path"]) != entry["sha256"]:
                raise ChunkError(f"source_manifest.json 해시와 다르다: {entry['path']}")
        self.rules = BattleRules()  # verify_bundle()을 함께 실행한다
        self.pokemon = load_json("data/processed/pokemon.json")
        self.moves = load_json("data/processed/moves.json")
        self.types = load_json("data/processed/types.json")
        self.chart = load_json("data/processed/type_chart.json")
        self.classification = load_json("data/processed/red_blue_move_damage_classification.json")
        self.evolutions = load_json("data/processed/evolutions_red_blue.json")
        self.items = load_json("data/processed/evolution_items_red_blue.json")
        self.machines = load_json("data/processed/machines_red_blue.json")
        self.acquisition = load_json("data/processed/machine_acquisition_red_blue.json")
        self.encounters = load_json("data/processed/encounters_red_blue.json")
        self.location_names = load_json(self.files[LOCATION_NAMES_SOURCE_ID]["path"])
        self.pokemon_at = {row["id"]: i for i, row in enumerate(self.pokemon)}
        self.move_at = {row["id"]: i for i, row in enumerate(self.moves)}
        self.move_by_name = {row["name"]: row for row in self.moves}
        self.pokemon_by_name = {row["name"]: row for row in self.pokemon}
        self.type_at = {row["name"]: i for i, row in enumerate(self.types)}
        self.type_by_ko = {row["name_ko"]: row["name"] for row in self.types}
        self.class_at = {row["id"]: i for i, row in enumerate(self.classification["moves"])}
        self.evo_at = {row["id"]: i for i, row in enumerate(self.evolutions["records"])}
        self.item_at = {row["name"]: i for i, row in enumerate(self.items["items"])}
        self.machine_at = {row["code"]: i for i, row in enumerate(self.machines["machines"])}
        self.machine_by_move = {}
        for row in self.machines["machines"]:
            self.machine_by_move.setdefault(row["move"], []).append(row["code"])
        self.acq_at = {row["code"]: i for i, row in enumerate(self.acquisition["machines"])}
        self.encounter_at = {row["id"]: i for i, row in enumerate(self.encounters["pokemon"])}
        self.location_at = {row["id"]: i for i, row in enumerate(self.location_names["entries"])}

    # 근거 레코드 (source_manifest.json의 identity 규칙을 따른다)
    def rec_pokemon(self, pid):
        return {"identity_field": "id", "identity_value": pid, "pointer": f"/{self.pokemon_at[pid]}",
                "record_id": f"pokemon:{pid}", "source_id": "processed:pokemon"}

    def rec_learnset(self, pid, index):
        row = self.pokemon[self.pokemon_at[pid]]["learnset"][index]
        return {"expected_subrecord": {key: row[key] for key in ("level", "method", "move", "version_group")},
                "identity_field": "id", "identity_value": pid,
                "pointer": f"/{self.pokemon_at[pid]}/learnset/{index}", "record_id": f"pokemon:{pid}",
                "record_pointer": f"/{self.pokemon_at[pid]}", "source_id": "processed:pokemon"}

    def rec_move(self, move_id):
        return {"identity_field": "id", "identity_value": move_id, "pointer": f"/{self.move_at[move_id]}",
                "record_id": f"move:{move_id}", "source_id": "processed:moves"}

    def rec_class(self, move_id):
        return {"identity_field": "id", "identity_value": move_id, "pointer": f"/moves/{self.class_at[move_id]}",
                "record_id": f"move:{move_id}", "source_id": "processed:red_blue_move_damage_classification"}

    def rec_type(self, name):
        row = self.types[self.type_at[name]]
        return {"identity_field": "id", "identity_value": row["id"], "pointer": f"/{self.type_at[name]}",
                "record_id": f"type:{row['id']}", "source_id": "processed:types"}

    def rec_chart(self, attack, defense):
        return {"identity_value": self.chart[attack][defense], "pointer": f"/{attack}/{defense}",
                "record_id": f"type_matchup:{attack}:{defense}", "source_id": "processed:type_chart"}

    def rec_evolution(self, pid):
        return {"identity_field": "id", "identity_value": pid, "pointer": f"/records/{self.evo_at[pid]}",
                "record_id": f"pokemon:{pid}", "source_id": "processed:evolutions_red_blue"}

    def rec_item(self, name):
        return {"identity_field": "name", "identity_value": name, "pointer": f"/items/{self.item_at[name]}",
                "record_id": f"item:{name}", "source_id": "processed:evolution_items_red_blue"}

    def rec_machine(self, code):
        return {"identity_field": "code", "identity_value": code, "pointer": f"/machines/{self.machine_at[code]}",
                "record_id": f"machine:{code}", "source_id": "processed:machines_red_blue"}

    def rec_acquisition(self, code):
        return {"identity_field": "code", "identity_value": code, "pointer": f"/machines/{self.acq_at[code]}",
                "record_id": f"machine:{code}", "source_id": "processed:machine_acquisition_red_blue"}

    def rec_encounter(self, pid):
        return {"identity_field": "id", "identity_value": pid, "pointer": f"/pokemon/{self.encounter_at[pid]}",
                "record_id": f"pokemon:{pid}", "source_id": "processed:encounters_red_blue"}

    def rec_location(self, location_id):
        return {"identity_field": "id", "identity_value": location_id,
                "pointer": f"/entries/{self.location_at[location_id]}", "record_id": f"location_name:{location_id}",
                "source_id": LOCATION_NAMES_SOURCE_ID}

    def rec_rules(self, rule):
        return {"classification_source_commit": COMMIT, "record_id": "calc:gen1_battle_rules", "rule": rule,
                "sha256": sha256_lf(ROOT / RULES_PATH), "source_id": RULES_SOURCE_ID}

    def move_type(self, move):
        return move["values_by_version_group"][VERSION_GROUP]["type"]

    def type_ko(self, name):
        return self.types[self.type_at[name]]["name_ko"]

    def place(self, kind, identifier):
        """대응표의 한국어 장소명. name_ko가 null이면 식별자를 코드 표기로 쓴다. 반환: (표기, 대응표 ID)."""
        location_id = f"{kind}:{identifier}"
        if location_id not in self.location_at:
            raise ChunkError(f"장소 대응표에 없는 식별자: {location_id}")
        name_ko = self.location_names["entries"][self.location_at[location_id]]["name_ko"]
        return (name_ko if name_ko else f"`{identifier}`"), location_id


def evolution_family(ctx, pid):
    """evolves_from·evolves_to로 묶인 Red·Blue 진화 계통의 (포켓몬 ID 목록, 관계 목록)."""
    members, edges, queue = set(), {}, [pid]
    while queue:
        current = queue.pop()
        if current in members:
            continue
        members.add(current)
        record = ctx.evolutions["records"][ctx.evo_at[current]]
        for edge in record["evolves_from"] + record["evolves_to"]:
            edges[(edge["from_id"], edge["to_id"])] = edge
            queue.extend([edge["from_id"], edge["to_id"]])
    return sorted(members), [edges[key] for key in sorted(edges)]


def evolution_condition(ctx, edge):
    if edge["trigger"] == "level-up" and edge["min_level"] is not None:
        return f"레벨 {edge['min_level']}"
    if edge["trigger"] == "use-item" and edge["item"]:
        return ctx.items["items"][ctx.item_at[edge["item"]]]["name_ko"]
    if edge["trigger"] == "trade":
        return "통신 교환"
    raise ChunkError(f"진화 조건을 표기할 수 없다: {edge['from_id']}→{edge['to_id']}")


def attack_probe(ctx, attack):
    """계산 규칙 대조용: 해당 타입의 일반 피해 기술 하나. 없으면 None (예: 드래곤은 용의분노뿐이라 고정 피해)."""
    return next((m for m in ctx.moves if ctx.move_type(m) == attack
                 and ctx.classification["moves"][ctx.class_at[m["id"]]]["classification"] == "regular_damage"), None)


def check_attack_rules(ctx, pid, attack, defense_names):
    """해당 공격 타입의 단일 타입 상대 배율을 계산 규칙과 대조한다. 일반 피해 기술이 없어 대조하지 못하면 False."""
    probe = attack_probe(ctx, attack)
    if probe is None:
        return False
    for defense in defense_names:
        result = ctx.rules.calculate(version=VERSION_GROUP, user=pid, target=pid, move=probe["id"],
                                     target_types=[defense])
        if result["type_effectiveness"] != ctx.chart[attack][defense]:
            raise ChunkError(f"attack_matchup: 계산 규칙과 type_chart가 다르다 {attack}->{defense}")
    return True


def defense_rules_check(ctx, pid, own_types):
    """BattleRules로 공격 타입별 방어 배율을 계산해 type_chart 곱과 대조한다 (각 공격 타입의 일반 피해 기술로
    대상 포켓몬을 공격). 반환: 일반 피해 기술이 없어 대조하지 못한 공격 타입 목록."""
    unchecked = []
    for attack in sorted(ctx.chart):
        probe = attack_probe(ctx, attack)
        if probe is None:
            unchecked.append(attack)
            continue
        result = ctx.rules.calculate(version=VERSION_GROUP, user=pid, target=pid, move=probe["id"])
        expected = number_value(math.prod(ctx.chart[attack][t] for t in own_types))
        if result["type_effectiveness"] != expected:
            raise ChunkError(f"defense_matchup: 계산 규칙과 type_chart 곱이 다르다 {attack}")
    return unchecked


def attack_summary(rows_by_column, name=None, direction=False):
    """공격 상성 요약 문장. rows_by_column[i] = [(기술 타입 한국어, 한국어 타입 이름 목록), ...].
    direction(tpl3b)이면 앞에 '{name}이/가 상대에게 {타입} 타입 기술을 쓸 때의 상성입니다.'를 붙인다."""
    sentences = []
    for (factor, term), rows in zip(ATTACK_TERMS, rows_by_column):
        label = f"{term}({factor}배) 상대 타입은"
        if not any(names for _, names in rows):
            sentences.append(f"{label} 없습니다.")
        else:
            parts = ", ".join(f"{move_type} 기술이 {'·'.join(names) if names else NONE_CELL}" for move_type, names in rows)
            sentences.append(f"{label} {parts}입니다.")
    if direction:
        move_types = "·".join(move_type for move_type, _ in rows_by_column[0])
        sentences.insert(0, f"{with_i_ga(name)} 상대에게 {move_types} 타입 기술을 쓸 때의 상성입니다.")
    return "요약: " + " ".join(sentences)


def defense_summary(name, rows, direction=False):
    """방어 상성 요약 문장. rows = [(구분, 배율, 한국어 타입 이름 목록), ...] (DEFENSE_ROWS 순서).
    direction(tpl3b)이면 '{name}에게 효과가 굉장한(2배 이상) 기술 타입, 즉 약점'처럼 방어 방향을 밝히고
    '{name}을/를 상대할 때 유리한 기술 타입'(= 약점 타입) 문장을 붙인다."""
    def join(group):
        parts = [f"{'·'.join(names)}({factor}배)" for label, factor, names in rows if label == group and names]
        return ", ".join(parts) if parts else NONE_CELL
    immune = [names for label, _, names in rows if label == "무효"][0]
    tail = f"{'·'.join(immune)}입니다." if immune else "없습니다."
    if not direction:
        return f"요약: {name}의 약점은 {join('약점')}이고, 저항은 {join('저항')}이며, 무효(0배)인 타입은 {tail}"
    weak = [n for label, _, names in rows if label == "약점" for n in names]
    weak_text = f"약점은 {join('약점')}이고" if weak else "약점은 없고"
    resist_text = f"저항은 {join('저항')}이며" if any(names for label, _, names in rows if label == "저항") else "저항은 없으며"
    advantage = f"약점인 {'·'.join(weak)}입니다." if weak else "없습니다."
    return (f"요약: {with_i_ga(name)} 공격받을 때의 상성입니다. "
            f"{name}에게 효과가 굉장한(2배 이상) 기술 타입, 즉 {weak_text}, "
            f"{name}에게 효과가 별로인(0.5배 이하) 기술 타입, 즉 {resist_text}, "
            f"{name}에게 효과가 없는(0배) 기술 타입, 즉 무효는 {tail} "
            f"{with_eul_reul(name)} 상대할 때 유리한 기술 타입은 {advantage}")


# ---------------------------------------------------------------- tpl3a 획득처 절


def encounter_condition(ctx, value):
    """encounter condition 값의 본문 표기와 근거 레코드. 한국어 근거가 없는 값은 식별자를 코드 표기로 쓴다."""
    coins = re.fullmatch(r"coins-(\d+)", value)
    if coins:
        return f"코인 {int(coins.group(1))}개", []
    trade = re.fullmatch(r"trade-(.+)", value)
    if trade and trade.group(1) in ctx.pokemon_by_name:
        other = ctx.pokemon_by_name[trade.group(1)]
        return f"{with_gwa_wa(other['name_ko'])} 교환", [ctx.rec_pokemon(other["id"])]
    return f"`{value}`", []


def encounter_plan(ctx, pid):
    """encounters_red_blue.json → 획득처 표 행과 요약 문장 재료.

    표 행 키 = (location_area, method, condition 값들). 버전마다 같은 키의 레벨을 min_level 최솟값~max_level 최댓값으로
    합친다. 두 버전의 키·레벨 범위가 같으면 'Red·Blue' 한 행, 아니면 버전별 행이다. 행 순서는 Red 기록 순서, 그다음
    Blue에만 있는 키의 기록 순서다. 반환: dict(rows, by_version, records, location_ids, has_conditions)."""
    entry = ctx.encounters["pokemon"][ctx.encounter_at[pid]]
    order, levels = [], {version: {} for version in GAMES}
    for version in GAMES:
        for item in entry["versions"][version]["encounters"]:
            area = item["location_area"]["name"]
            for detail in item["version_detail"]["encounter_details"]:
                method = detail["method"]["name"]
                if method not in ENCOUNTER_METHODS:
                    raise ChunkError(f"encounter: 표기 규칙이 없는 획득 방법 {method} ({version} {area})")
                conditions = tuple(sorted(c["name"] for c in detail["condition_values"]))
                key = (area, method, conditions)
                low, high = detail["min_level"], detail["max_level"]
                if key in levels[version]:
                    old = levels[version][key]
                    low, high = min(low, old[0]), max(high, old[1])
                levels[version][key] = (low, high)
                if key not in order:
                    order.append(key)
    rows, location_ids, records = [], [], []
    places = {}
    for area, method, conditions in order:
        place, location_id = ctx.place("pokeapi_location_area", area)
        places[(area, method, conditions)] = place
        location_ids.append(location_id)
        present = [(v, levels[v][(area, method, conditions)]) for v in GAMES if (area, method, conditions) in levels[v]]
        if len(present) == 2 and present[0][1] == present[1][1]:
            present = [("·".join(VERSION_LABELS[v] for v in GAMES), present[0][1])]
        else:
            present = [(VERSION_LABELS[v], lv) for v, lv in present]
        texts = []
        for value in conditions:
            text, recs = encounter_condition(ctx, value)
            texts.append(text)
            records += recs
        for label, (low, high) in present:
            level = str(low) if low == high else f"{low}~{high}"
            rows.append([label, place, ENCOUNTER_METHODS[method][1], level, ", ".join(texts) if texts else NONE_CELL])
    by_version = {}
    for version in GAMES:
        groups = {}
        for key in order:
            if key in levels[version]:
                group = ENCOUNTER_METHODS[key[1]][0]
                names = groups.setdefault(group, [])
                if places[key] not in names:
                    names.append(places[key])
        by_version[version] = groups
    return {"rows": rows, "by_version": by_version, "records": records, "location_ids": location_ids,
            "has_conditions": any(key[2] for key in order)}


def encounter_clauses(groups):
    """한 버전의 요약 절 목록 [(주어부, '있'|'없')]. groups = {묶음: [장소, ...]}."""
    if not groups:
        return [("등장·획득 기록이", "없"), ("야생에서 만나는 기록도", "없")]
    clauses = []
    for group, verb in ENCOUNTER_GROUPS:
        names = groups.get(group)
        if names:
            where = "·".join(names) if len(names) <= ENCOUNTER_SUMMARY_PLACES else f"{len(names)}곳"
            clauses.append((f"{where}에서 {verb} 기록이", "있"))
    if "wild" not in groups:
        clauses.append(("야생에서 만나는 기록은", "없"))
    return clauses


def render_clauses(clauses):
    return ", ".join(f"{subject} {stem}{'습니다' if i == len(clauses) - 1 else '고'}"
                     for i, (subject, stem) in enumerate(clauses))


def encounter_summary(name, by_version):
    """획득처 요약 문장: '{name}을/를 얻는 방법(잡는 곳·받는 곳)과 장소입니다.' + 버전별 기록 문장."""
    red, blue = (encounter_clauses(by_version[v]) for v in GAMES)
    if red == blue:
        facts = f"Red와 Blue 모두 {render_clauses(red)}."
    else:
        facts = f"Red에서는 {render_clauses(red)}. Blue에서는 {render_clauses(blue)}."
    return f"요약: {with_eul_reul(name)} 얻는 방법(잡는 곳·받는 곳)과 장소입니다. {facts}"


def encounter_body(ctx, record):
    """tpl3a 획득처 절 본문 줄 (제목 제외). 생성기가 Markdown 본문과 줄 단위로 대조한다."""
    plan = encounter_plan(ctx, record["id"])
    lines = [encounter_summary(record["name_ko"], plan["by_version"]), ""]
    if plan["rows"]:
        header = ENCOUNTER_HEADER + ([ENCOUNTER_CONDITION_HEADER] if plan["has_conditions"] else [])
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for row in plan["rows"]:
            lines.append("| " + " | ".join(row[:len(header)]) + " |")
        lines += ["", f"{ENCOUNTER_PLACE_LINE} {ENCOUNTER_SCOPE_LINE}"]
    else:
        lines.append(ENCOUNTER_SCOPE_LINE)
    return lines, plan


def build_chunk_evidence(ctx, record, number, span, template=DEFAULT_TEMPLATE):
    """절마다 Markdown 값을 정제 데이터와 대조하고 (근거 레코드 목록, data 값 또는 None)을 돌려준다."""
    pid = record["id"]
    section, body = span["section"], span["body"]
    text = "\n".join(body)
    learnset = in_game_learnset(record)
    own_types = record["types_gen1"]
    records = [ctx.rec_pokemon(pid)]
    data = None
    features = FEATURES[check_template(template)]
    tpl2 = features["modern"]  # tpl2 이후 공통 규칙 (상성 표준 용어, 장소 한국어명)
    if tpl2:
        for term in FORBIDDEN_TERMS:
            if term in text:
                raise ChunkError(f"{section}: 쓰지 않는 상성 표현 '{term}'")

    if section == "profile":
        types_line = [line for line in body if line.startswith("- **타입:** ")]
        if types_line != [f"- **타입:** {' · '.join(ctx.type_ko(t) for t in own_types)}"]:
            raise ChunkError(f"profile: 타입 줄이 pokemon.json types_gen1과 다르다: {types_line}")
        records += [ctx.rec_type(t) for t in own_types]
        evo = ctx.evolutions["records"][ctx.evo_at[pid]]
        for edge in evo["evolves_from"] + evo["evolves_to"]:
            other = edge["to_id"] if edge["from_id"] == pid else edge["from_id"]
            if ctx.pokemon[ctx.pokemon_at[other]]["name_ko"] in text:
                records += [ctx.rec_evolution(pid), ctx.rec_pokemon(other)]
                if edge["item"]:
                    records.append(ctx.rec_item(edge["item"]))

    elif section == "stats":
        header, rows = parse_table(body, section)
        if len(rows) != 1 or [STAT_COLUMNS.get(h) for h in header] != list(record["stats_gen1"]):
            raise ChunkError("stats: 표 머리글·행 수가 다르다")
        values = dict(zip((STAT_COLUMNS[h] for h in header), (int(v) for v in rows[0])))
        if values != record["stats_gen1"]:
            raise ChunkError(f"stats: stats_gen1과 다르다: {values}")

    elif section == "evolution":
        members, edges = evolution_family(ctx, pid)
        for edge in edges:
            from_ko = ctx.pokemon[ctx.pokemon_at[edge["from_id"]]]["name_ko"]
            to_ko = ctx.pokemon[ctx.pokemon_at[edge["to_id"]]]["name_ko"]
            if f"{from_ko} ── {evolution_condition(ctx, edge)} ──▶ {to_ko}" not in text and \
                    f"── {evolution_condition(ctx, edge)} ──▶ {to_ko}" not in text:
                raise ChunkError(f"evolution: 진화 도식에 {from_ko}→{to_ko} 관계가 없다")
        records += [ctx.rec_evolution(m) for m in members]
        records += [ctx.rec_pokemon(m) for m in members if m != pid]
        records += [ctx.rec_item(edge["item"]) for edge in edges if edge["item"]]

    elif section == "learnset_level":
        header, rows = parse_table(body, section)
        if header != ["습득 레벨", "기술", "타입"]:
            raise ChunkError(f"learnset_level: 머리글이 다르다: {header}")
        expected = Counter()
        by_row = {}
        for index, row in learnset:
            if row["method"] != "level-up":
                continue
            move = ctx.move_by_name[row["move"]]
            key = (str(row["level"]), move["name_ko"], ctx.type_ko(ctx.move_type(move)))
            expected[key] += 1
            by_row[key] = (index, row, move)
        if Counter(tuple(r) for r in rows) != expected:
            raise ChunkError("learnset_level: 표가 Red·Blue 레벨업 기록과 다르다")
        data = []
        for row in rows:
            index, entry, move = by_row[tuple(row)]
            records += [ctx.rec_learnset(pid, index), ctx.rec_move(move["id"]), ctx.rec_type(ctx.move_type(move))]
            data.append({"level": entry["level"], "move_id": move["id"], "name": move["name"], "name_ko": move["name_ko"]})

    elif section == "learnset_machine":
        header, rows = parse_table(body, section)
        if header != ["머신", "기술", "타입"]:
            raise ChunkError(f"learnset_machine: 머리글이 다르다: {header}")
        expected = {}
        for index, row in learnset:
            if row["method"] != "machine":
                continue
            codes = ctx.machine_by_move.get(row["move"], [])
            if len(codes) != 1:
                raise ChunkError(f"learnset_machine: 머신 번호가 하나가 아니다: {row['move']} {codes}")
            move = ctx.move_by_name[row["move"]]
            expected[(codes[0], move["name_ko"], ctx.type_ko(ctx.move_type(move)))] = (index, move)
        if sorted(tuple(r) for r in rows) != sorted(expected) or len(rows) != len(expected):
            raise ChunkError("learnset_machine: 표가 Red·Blue 머신 기록과 다르다")
        data = []
        for row in rows:
            index, move = expected[tuple(row)]
            records += [ctx.rec_learnset(pid, index), ctx.rec_move(move["id"]), ctx.rec_machine(row[0]),
                        ctx.rec_type(ctx.move_type(move))]
            data.append({"code": row[0], "move_id": move["id"], "name": move["name"], "name_ko": move["name_ko"]})
        # 표 뒤 문단의 습득 건수·중복 기술 주장은 레벨업 기록까지 포함한 전체 습득 기록이 근거다.
        level_count = sum(1 for _, r in learnset if r["method"] == "level-up")
        machine_count = sum(1 for _, r in learnset if r["method"] == "machine")
        unique = len({r["move"] for _, r in learnset})
        for claim in (f"레벨업 {level_count}건", f"머신 {machine_count}건", f"{len(learnset)}건", f"기술은 {unique}개"):
            if claim not in text:
                raise ChunkError(f"learnset_machine: 습득 건수 문장이 데이터와 다르다 ({claim})")
        records += [ctx.rec_learnset(pid, index) for index, r in learnset if r["method"] == "level-up"]

    elif section == "machine_acquisition":
        header, rows = parse_table(body, section)
        if header != ["머신", "장소와 방법"]:
            raise ChunkError(f"machine_acquisition: 머리글이 다르다: {header}")
        machine_codes = {code for move in (r["move"] for _, r in learnset if r["method"] == "machine")
                         for code in ctx.machine_by_move[move]}
        if sorted(r[0] for r in rows) != sorted(machine_codes):
            raise ChunkError("machine_acquisition: 머신 목록이 머신 기술과 다르다")
        location_ids = []
        for code, cell in rows:
            locations = ctx.acquisition["machines"][ctx.acq_at[code]]["locations"]
            if tpl2:
                parts = []
                for loc in locations:
                    place, location_id = ctx.place("pokered_map", loc["map_id_raw"])
                    parts.append(f"{place} — {ACQUISITION_LABELS[loc['method']]}")
                    location_ids.append(location_id)
                expected = "; ".join(parts)
            else:
                expected = "; ".join(f"`{loc['map_id_raw']}` — {ACQUISITION_LABELS[loc['method']]}" for loc in locations)
            if cell != expected:
                raise ChunkError(f"machine_acquisition: {code} 획득 기록·장소명과 다르다: {cell!r} != {expected!r}")
            records.append(ctx.rec_acquisition(code))
        records += [ctx.rec_location(location_id) for location_id in sorted(set(location_ids))]

    elif section == "stab":
        examples = []
        for move in ctx.moves:
            entry = ctx.classification["moves"][ctx.class_at[move["id"]]]
            if ctx.move_type(move) in own_types and entry["classification"] == "regular_damage" and move["name_ko"] in text:
                examples.append(move)
        if sorted(ctx.move_type(m) for m in examples) != sorted(own_types):
            raise ChunkError(f"stab: 타입마다 일반 피해 예시 기술이 하나씩 있어야 한다: {[m['name'] for m in examples]}")
        records += [ctx.rec_type(t) for t in own_types]
        learnable = {r["move"]: index for index, r in learnset}
        for move in sorted(examples, key=lambda m: own_types.index(ctx.move_type(m))):
            result = ctx.rules.calculate(version=VERSION_GROUP, user=pid, target=pid, move=move["id"])
            if result["stab"] != 1.5:
                raise ChunkError(f"stab: {move['name']} 자속 보정이 1.5가 아니다")
            records += [ctx.rec_move(move["id"]), ctx.rec_class(move["id"])]
            if move["name"] in learnable:
                records.append(ctx.rec_learnset(pid, learnable[move["name"]]))
            elif "가정" not in text:
                raise ChunkError(f"stab: 배우지 않는 {move['name_ko']} 예시를 가정으로 표시하지 않았다")
        if "1.5배" not in text:
            raise ChunkError("stab: 1.5배 문장이 없다")
        if tpl2:
            mixed = [term for term in MATCHUP_TERMS if term in text]
            if mixed:
                raise ChunkError(f"stab: 자속 절에 상성 용어가 섞였다: {mixed}")
        records.append(ctx.rec_rules("stab = 1.5 if regular_damage move type in user types_gen1 else 1.0"))

    elif section == "attack_matchup":
        header, rows = parse_table(body, section)
        defense_names = sorted(ctx.chart)
        if not tpl2:
            if header != ["기술 타입", "효과가 좋은 상대 타입", "효과가 약한 상대 타입"]:
                raise ChunkError(f"attack_matchup: 머리글이 다르다: {header}")
            attack_types = [ctx.type_by_ko.get(row[0]) for row in rows]
            if attack_types != own_types:
                raise ChunkError(f"attack_matchup: 행이 포켓몬 타입과 다르다: {attack_types}")
            for (attack, (_, good, weak)) in zip(attack_types, rows):
                row = ctx.chart[attack]
                if any(row[t] == 0 for t in defense_names):
                    raise ChunkError(f"attack_matchup: {attack} 행에 0배 타입이 있어 표 형식으로 나타낼 수 없다")
                if {ctx.type_by_ko.get(n) for n in split_names(good)} != {t for t in defense_names if row[t] == 2} or \
                        {ctx.type_by_ko.get(n) for n in split_names(weak)} != {t for t in defense_names if row[t] == 0.5}:
                    raise ChunkError(f"attack_matchup: {attack} 행이 type_chart와 다르다")
                if not check_attack_rules(ctx, pid, attack, defense_names):
                    raise ChunkError(f"attack_matchup: {attack} 일반 피해 기술이 없어 계산 규칙과 대조할 수 없다")
        else:
            if header != ATTACK_HEADER:
                raise ChunkError(f"attack_matchup: 머리글이 상성 표준 용어와 다르다: {header}")
            attack_types = [ctx.type_by_ko.get(row[0]) for row in rows]
            if attack_types != own_types:
                raise ChunkError(f"attack_matchup: 행이 포켓몬 타입과 다르다: {attack_types}")
            columns, unchecked = [[] for _ in ATTACK_TERMS], []
            for attack, row in zip(attack_types, rows):
                for position, (factor, _) in enumerate(ATTACK_TERMS):
                    types, names = type_cell(row[position + 1], ctx, section)
                    if set(types) != {t for t in defense_names if ctx.chart[attack][t] == factor}:
                        raise ChunkError(f"attack_matchup: {attack} 행 {factor}배 칸이 type_chart와 다르다")
                    columns[position].append((row[0], names))
                if not check_attack_rules(ctx, pid, attack, defense_names):
                    unchecked.append(attack)
            expected_summary = attack_summary(columns, record["name_ko"], features["matchup_direction"])
            if summary_line(body, section) != expected_summary:
                raise ChunkError(f"attack_matchup: 요약 문장이 표와 다르다: 기대={expected_summary!r}")
        records += [ctx.rec_type(t) for t in sorted(ctx.type_at, key=ctx.type_at.get)]
        records += [ctx.rec_chart(a, d) for a in attack_types for d in defense_names]
        records.append(ctx.rec_rules("type_effectiveness = type_chart[move_type][defending_type] (single type)"))
        data = {"attack_type_factors_vs_single_type": {a: dict(sorted(ctx.chart[a].items())) for a in attack_types},
                "formula": "factor = type_chart[move_type][defending_type]; single defending type; nominal only"}
        if tpl2:
            data["calculator_unchecked_types"] = unchecked

    elif section == "defense_matchup":
        header, rows = parse_table(body, section)
        factors = {a: number_value(math.prod(ctx.chart[a][t] for t in own_types)) for a in sorted(ctx.chart)}
        if not tpl2:
            if header != ["상대 기술의 타입", "받는 피해"]:
                raise ChunkError(f"defense_matchup: 머리글이 다르다: {header}")
            listed = {}
            for names, factor in rows:
                for name in split_names(names):
                    if ctx.type_by_ko.get(name) is None or ctx.type_by_ko[name] in listed:
                        raise ChunkError(f"defense_matchup: 알 수 없거나 중복된 타입: {name}")
                    listed[ctx.type_by_ko[name]] = parse_factor(factor, section)
            for attack, factor in factors.items():
                if listed.get(attack, 1) != factor:
                    raise ChunkError(f"defense_matchup: {attack} 배율이 type_chart 곱과 다르다")
        else:
            if header != DEFENSE_HEADER:
                raise ChunkError(f"defense_matchup: 머리글이 상성 표준 용어와 다르다: {header}")
            if [(label, parse_factor(factor, section)) for label, _, factor in rows] != DEFENSE_ROWS:
                raise ChunkError(f"defense_matchup: 행은 {DEFENSE_ROWS} 순서의 구분·배율이어야 한다")
            unchecked = defense_rules_check(ctx, pid, own_types)
            summary_rows, listed = [], set()
            for (label, factor), (_, cell, _) in zip(DEFENSE_ROWS, rows):
                types, names = type_cell(cell, ctx, section)
                if set(types) != {a for a, f in factors.items() if f == factor}:
                    raise ChunkError(f"defense_matchup: {label} {factor}배 칸이 type_chart 곱과 다르다")
                listed |= set(types)
                summary_rows.append((label, factor, names))
            if any(f not in (4, 2, 1, 0.5, 0.25, 0) for f in factors.values()) or \
                    listed != {a for a, f in factors.items() if f != 1}:
                raise ChunkError("defense_matchup: 1배가 아닌 타입이 표에서 빠졌다")
            expected_summary = defense_summary(record["name_ko"], summary_rows, features["matchup_direction"])
            if summary_line(body, section) != expected_summary:
                raise ChunkError(f"defense_matchup: 요약 문장이 표와 다르다: 기대={expected_summary!r}")
        records += [ctx.rec_type(t) for t in sorted(ctx.type_at, key=ctx.type_at.get)]
        records += [ctx.rec_chart(a, d) for a in sorted(ctx.chart) for d in own_types]
        records.append(ctx.rec_rules("type_effectiveness = product of type_chart[move_type][t] for t in target types_gen1"))
        data = {"defense_factors": factors,
                "formula": "factor = " + " * ".join(f"type_chart[attack_type][{t}]" for t in own_types) + "; nominal only"}
        if tpl2:
            data["calculator_unchecked_types"] = unchecked

    elif section == "encounter" and features["encounter_v3"]:
        expected_body, plan = encounter_body(ctx, record)
        if body != expected_body:
            diff = [(i + 1, got, want) for i, (got, want) in enumerate(zip(body, expected_body)) if got != want]
            raise ChunkError(f"encounter: 본문이 encounters 데이터·장소 대응표로 만든 획득처 절과 다르다 "
                             f"(줄 수 {len(body)}/{len(expected_body)}, 첫 차이 {diff[:1]})")
        records.append(ctx.rec_encounter(pid))
        records += plan["records"]
        records += [ctx.rec_location(location_id) for location_id in sorted(set(plan["location_ids"]))]

    elif section == "encounter":
        encounter = ctx.encounters["pokemon"][ctx.encounter_at[pid]]
        found = False
        location_ids = []
        for version in GAMES:
            for item in encounter["versions"][version]["encounters"]:
                found = True
                area = item["location_area"]["name"]
                if tpl2:
                    place, location_id = ctx.place("pokeapi_location_area", area)
                    location_ids.append(location_id)
                    if not place.startswith("`") and area in text:
                        raise ChunkError(f"encounter: 한국어 장소명이 있는 식별자 {area}를 본문에 썼다")
                else:
                    place = f"`{area}`"
                methods = {d["method"]["name"] for d in item["version_detail"]["encounter_details"]}
                if place not in text or any(ENCOUNTER_LABELS.get(m, "\0") not in text for m in methods):
                    raise ChunkError(f"encounter: {version} {area}({place}) {sorted(methods)} 기록이 본문에 없다")
        if not found and "기록이 없" not in text:
            raise ChunkError("encounter: 기록이 없다는 문장이 없다")
        records.append(ctx.rec_encounter(pid))
        records += [ctx.rec_location(location_id) for location_id in sorted(set(location_ids))]

    return records, data


def dedupe(records):
    seen, result = set(), []
    for record in records:
        key = json.dumps(record, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


# ---------------------------------------------------------------- 문서 조립


def relpath(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def build_document(md_text=None, template=DEFAULT_TEMPLATE, markdown_path=None):
    """Markdown → 청크 문서. md_text가 없으면 템플릿 기본 Markdown을 읽는다. markdown_path는 기록할 경로다."""
    check_template(template)
    ctx = Context()
    if markdown_path is None:
        markdown_path = TEMPLATES[template]["markdown"]
    markdown_path = relpath(ROOT / markdown_path)
    if md_text is None:
        md_text = (ROOT / markdown_path).read_text(encoding="utf-8")
    record, number, spans = split_markdown(md_text, ctx.pokemon, template)
    pid = record["id"]
    doc_id = f"pokemon:{pid}"
    chunks = []
    for span in spans:
        section = span["section"]
        evidence, data = build_chunk_evidence(ctx, record, number, span, template)
        markdown_record = {"headings": span["headings"], "line_end": span["line_end"],
                           "line_start": span["line_start"], "record_id": f"markdown_section:{section}",
                           "source_id": MARKDOWN_SOURCE_ID}
        chunk = {
            "chunk_id": f"{doc_id}#{section}",
            "content": prefix_of(record, number, section, template) + "\n\n" + "\n".join(span["body"]),
            "doc_id": doc_id,
            "games": list(GAMES),
            "generation_mode": GENERATION_MODE,
            "needs_human_review": True,
            "review_status": "pending",
            "section": section,
            "source_records": dedupe([markdown_record] + evidence),
            "version_group": VERSION_GROUP,
        }
        if data is not None:
            chunk["data"] = data
        chunks.append(chunk)

    ids = [chunk["chunk_id"] for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ChunkError(f"청크 ID 중복: {ids}")

    markdown_sha = hashlib.sha256(md_text.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    used = sorted({r["source_id"] for chunk in chunks for r in chunk["source_records"]})
    source_files = []
    for source_id in used:
        if source_id == MARKDOWN_SOURCE_ID:
            path, notes, refs, digest = markdown_path, MARKDOWN_NOTES, [], markdown_sha
        elif source_id == RULES_SOURCE_ID:
            path, notes, refs, digest = RULES_PATH, RULES_NOTES, ["pokered_pinned"], sha256_lf(ROOT / RULES_PATH)
        else:
            entry = ctx.files[source_id]
            path, notes, refs, digest = entry["path"], entry["notes"], entry["source_refs"], entry["sha256"]
        source_files.append({"notes": list(notes), "path": path, "sha256": digest,
                             "source_id": source_id, "source_refs": list(refs)})
    source_files.sort(key=lambda entry: entry["path"])
    lineage = {ref: ctx.manifest["sources"][ref] for entry in source_files for ref in entry["source_refs"]}
    for text in json.dumps(source_files, ensure_ascii=False), json.dumps(lineage, ensure_ascii=False):
        if "pokeapi/" in text:
            raise ChunkError("개인 폴더 경로(pokeapi/)를 참조하지 않는다")

    rules_sha = sha256_lf(ROOT / RULES_PATH)
    document = {
        "chunk_ids": ids,
        "chunks": chunks,
        "doc_id": doc_id,
        "game_language": "English",
        "games": list(GAMES),
        "generated_by": GENERATED_BY,
        "generation_mode": GENERATION_MODE,
        "generator": {"formula_version": f"{RULES_PATH} sha256:{rules_sha}", "path": GENERATOR_PATH,
                      "sha256": sha256_lf(ROOT / GENERATOR_PATH)},
        "index_eligible": False,
        "limitations": list(LIMITATIONS) + (list(TPL2_LIMITATIONS) if FEATURES[template]["modern"] else [])
        + (list(TPL3_LIMITATIONS) if FEATURES[template]["encounter_v3"] else []),
        "localization_note": TPL2_LOCALIZATION_NOTE if FEATURES[template]["modern"] else LOCALIZATION_NOTE,
        "manifest": {"generated_at_utc": ctx.manifest["generated_at_utc"], "path": MANIFEST_PATH,
                     "sha256": sha256_file(ROOT / MANIFEST_PATH), "timestamp_note": TIMESTAMP_NOTE},
        "needs_human_review": True,
        "pokemon_id": pid,
        "review_status": "pending",
        "schema_version": TEMPLATES[template]["schema_version"],
        "source_files": source_files,
        "source_lineage": dict(sorted(lineage.items())),
        "title": f"{record['name_ko']} Red/Blue 설명 파일럿",
        "version_group": VERSION_GROUP,
    }
    if template != "tpl1":
        document["template_version"] = template
    return document


def render(document):
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def volatile_values(document, keys=TPL1_VOLATILE):
    """고정본 비교에서 제외하는 출처 값 (keys 순서, 기본 TPL1_VOLATILE)."""
    markdown = [e["path"] for e in document["source_files"] if e["source_id"] == MARKDOWN_SOURCE_ID]
    values = {"generator.sha256": document["generator"]["sha256"], "manifest.sha256": document["manifest"]["sha256"],
              "source_files[pilot_markdown].path": markdown[0] if markdown else None}
    return {key: values[key] for key in keys}


def without_volatile(document, keys=TPL1_VOLATILE):
    document = copy.deepcopy(document)
    if "generator.sha256" in keys:
        document["generator"]["sha256"] = None
    if "manifest.sha256" in keys:
        document["manifest"]["sha256"] = None
    if "source_files[pilot_markdown].path" in keys:
        for entry in document["source_files"]:
            if entry["source_id"] == MARKDOWN_SOURCE_ID:
                entry["path"] = None
    return document


def compare_baseline(document, saved_text, template):
    """고정본 템플릿(BASELINES) 재생성 결과와 저장본 비교. 반환: (같은지, 설명)."""
    baseline = BASELINES[template]
    keys = tuple(baseline)
    saved = json.loads(saved_text)
    if render(saved) != saved_text:
        return False, "저장본이 render() 형식이 아니다"
    if volatile_values(saved, keys) != baseline:
        return False, f"저장본의 출처 값이 {template} 기준선과 다르다: {volatile_values(saved, keys)}"
    if render(without_volatile(document, keys)) != render(without_volatile(saved, keys)):
        return False, "제외 필드 밖에서 다르다"
    differs = [key for key, value in volatile_values(document, keys).items() if value != baseline[key]]
    return True, f"제외 필드({template} 기준선 값 확인): " + ", ".join(keys) + f"; 현재 값이 다른 필드: {differs}"


def compare_tpl1(document, saved_text):
    """tpl1 재생성 결과와 v1 저장본 비교. 반환: (같은지, 설명)."""
    return compare_baseline(document, saved_text, "tpl1")


def latest_copy_status():
    """최신본(LATEST)이 기본 템플릿 저장본 Markdown·JSON의 바이트 사본이고 기각된 템플릿이 아닌가. 반환: (같은지, 설명)."""
    paths = TEMPLATES[DEFAULT_TEMPLATE]
    problems = []
    for kind in ("markdown", "output"):
        latest = ROOT / LATEST[kind]
        if not latest.exists() or latest.read_bytes() != (ROOT / paths[kind]).read_bytes():
            problems.append(LATEST[kind])
    if not problems:
        version = json.loads((ROOT / LATEST["output"]).read_text(encoding="utf-8")).get("template_version")
        if version != DEFAULT_TEMPLATE or version in REJECTED_TEMPLATES:
            problems.append(f"template_version={version}")
    return not problems, ("최신본 사본 같음" if not problems else f"최신본 사본이 {DEFAULT_TEMPLATE} 파일과 다르다: {problems}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="파일럿 Markdown → 청크 JSON (chunking 스킬 제목 표)")
    parser.add_argument("--template", choices=sorted(TEMPLATES), default=DEFAULT_TEMPLATE,
                        help=f"청크 템플릿 버전 (기본 {DEFAULT_TEMPLATE}, tpl1·tpl2는 기준선 재현, "
                             f"기각된 실험 {', '.join(sorted(REJECTED_TEMPLATES))}는 명시할 때만 재현 확인)")
    parser.add_argument("--markdown", type=Path, help="입력 Markdown (기본: 템플릿별 경로)")
    parser.add_argument("--output", type=Path, help="출력 JSON (기본: 템플릿별 경로)")
    parser.add_argument("--check", action="store_true", help="쓰지 않고 출력 파일과 같은지만 확인한다")
    args = parser.parse_args(argv)
    paths = TEMPLATES[args.template]
    markdown = args.markdown or ROOT / paths["markdown"]
    output = args.output or ROOT / paths["output"]
    try:
        document = build_document(Path(markdown).read_text(encoding="utf-8"), args.template, markdown)
    except ChunkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    text = render(document)
    data = text.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    current = Path(output).read_bytes().replace(b"\r\n", b"\n") if Path(output).exists() else b""
    if args.check:
        default_paths = not args.markdown and not args.output
        frozen_output = Path(output).resolve() == (ROOT / paths["output"]).resolve()
        if args.template in BASELINES and frozen_output:
            same, detail = (compare_baseline(document, current.decode("utf-8"), args.template) if current
                            else (False, "저장본 없음"))
            details = [detail]
        else:
            same, details = current == data, []
        if args.template == DEFAULT_TEMPLATE and default_paths:
            latest_same, latest_detail = latest_copy_status()
            same = same and latest_same
            details.append(latest_detail)
        if args.template in REJECTED_TEMPLATES:
            details.append(f"기각된 실험 템플릿: {REJECTED_TEMPLATES[args.template]}")
        detail = f" ({'; '.join(details)})" if details else ""
        print(("same" if same else "differs") + f" template={args.template} sha256={digest}{detail}")
        return 0 if same else 1
    frozen = {(ROOT / TEMPLATES[t]["output"]).resolve(): t for t in BASELINES}
    if Path(output).resolve() in frozen:
        print(f"error: {frozen[Path(output).resolve()]} 기준선 JSON은 수정하지 않는다 (--check로 비교하거나 다른 --output을 쓴다)",
              file=sys.stderr)
        return 2
    if Path(output).resolve() in {(ROOT / LATEST[kind]).resolve() for kind in LATEST}:
        print("error: 최신본은 기본 템플릿 저장본의 바이트 사본으로만 만든다 (다른 --output을 쓴다)", file=sys.stderr)
        return 2
    Path(output).write_bytes(data)
    print(f"wrote {output} template={args.template} chunks={len(document['chunks'])} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
