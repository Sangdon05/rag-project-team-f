#!/usr/bin/env python3
"""Extract answer-free planning inputs and check candidate structure (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
VERSION = "question-design-v2"
SEED_IDS = tuple(f"P{persona}-{n:02}" for persona in range(1, 4) for n in range(1, 4))
PROFILE_ROWS = ("연령·성별", "포켓몬과의 접점", "게임 경험", "이미 아는 것", "어려운 것", "이용 동기", "검색 입력 방식", "필요한 도움", "답변 방식", "도달 목표")
SCENARIO_ROWS = ("게임·장면", "상대", "내 후보·현재 기술", "공통 상태", "추가 조건", "비교 기준")
CANDIDATE_FIELDS = {"candidate_id", "seed_id", "persona_id", "scenario_id", "information_need_id", "relation", "question", "changed_conditions", "missing_inputs", "review_status"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def section(text: str, heading: str) -> str:
    """Only an exact heading can open a section; a peer/parent heading closes it."""
    lines = text.splitlines()
    matches = [i for i, line in enumerate(lines) if line == heading]
    require(len(matches) == 1, f"Expected one source heading: {heading}")
    start = matches[0] + 1
    level = len(heading) - len(heading.lstrip("#"))
    end = next((i for i in range(start, len(lines)) if re.match(rf"^#{{1,{level}}} ", lines[i])), len(lines))
    return "\n".join(lines[start:end])


def table_rows(text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        require(cells[0] not in rows, "Duplicate source table row")
        rows[cells[0]] = cells[1:]
    return rows


def build_packet(text: str) -> dict:
    scope_rows = [line for line in text.splitlines() if line.startswith("| 대상 게임·데이터 |")]
    require(len(scope_rows) == 1 and all(value in scope_rows[0] for value in ("Red/Blue", "151종", "165개", "15개")), "Source data scope changed; review mapping")
    profiles = table_rows(section(text, "## 2. 사용자 페르소나"))
    require(len(profiles.get("항목", [])) == 3, "Expected three persona columns")
    require(all(profiles["항목"][i].startswith(f"P{i + 1} ") for i in range(3)), "Persona columns changed")
    require(all(len(profiles.get(row, [])) == 3 and all(profiles[row]) for row in PROFILE_ROWS), "Persona fields missing or empty")
    personas = [{"persona_id": f"P{i + 1}", "label": profiles["항목"][i],
                 "profile": {row: profiles[row][i] for row in PROFILE_ROWS}} for i in range(3)]

    rows = table_rows(section(text, "### S01 — 동일 조건 비교를 위한 가상 상황"))
    require(all(len(rows.get(row, [])) == 1 and bool(rows[row][0]) for row in SCENARIO_ROWS), "Scenario fields missing or empty")
    scenario = {row: rows[row][0] for row in SCENARIO_ROWS}
    require(scenario["게임·장면"] == "Red/Blue, 싱글 배틀 전 준비", "Source game or scene changed; review scope")
    scenarios = {"S01": {"conditions": scenario}}
    seeds = []
    for seed_id in SEED_IDS:
        card = section(text, f"### {seed_id}")
        questions = [line[2:].strip() for line in card.splitlines() if line.startswith("> ")]
        require(len(questions) == 1 and bool(questions[0]), f"Expected one original question: {seed_id}")
        scenario_id = "S01"
        if seed_id == "P3-02":
            source_conditions = table_rows(card).get("상황·추가 확인", [])
            require(len(source_conditions) == 1 and source_conditions[0].startswith("S01-B:"), "S01-B input missing")
            scenarios["S01-B"] = {"base_scenario": "S01", "changed_input": source_conditions[0]}
            scenario_id = "S01-B"
        seeds.append({"seed_id": seed_id, "persona_id": seed_id[:2],
                      "scenario_id": scenario_id, "question": questions[0]})
    return {"schema_version": VERSION, "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "source": "docs/problem.md", "scope": {"game": "Red/Blue", "pokemon_count": 151,
            "scene": "싱글 배틀 전 도감 탐색", "personas_are": "설계 가설"},
            "personas": personas, "scenarios": scenarios, "seeds": seeds}


def string_list(value: object, field: str) -> None:
    require(isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value), f"{field}: expected nonempty strings in an array")


def check_candidates(packet: dict, output: dict) -> dict:
    require(isinstance(output, dict), "Output must be an object")
    require(set(output) == {"schema_version", "source_sha256", "candidates"}, "Unexpected or missing output fields")
    require(output["schema_version"] == packet["schema_version"] == VERSION, "Schema version mismatch")
    require(output["source_sha256"] == packet["source_sha256"], "Source hash mismatch")
    candidates = output["candidates"]
    require(isinstance(candidates, list) and bool(candidates), "Candidates must be a nonempty array")
    seeds = {seed["seed_id"]: seed for seed in packet["seeds"]}
    ids: set[str] = set()
    questions: set[tuple[str, str, str]] = set()
    counts = {f"P{i}": 0 for i in range(1, 4)}
    for item in candidates:
        require(isinstance(item, dict) and set(item) == CANDIDATE_FIELDS, "Unexpected or missing candidate fields; answer/evidence fields are not allowed")
        require(all(isinstance(item[key], str) and item[key].strip() for key in CANDIDATE_FIELDS - {"changed_conditions", "missing_inputs"}), "Candidate text fields must be nonempty strings")
        cid = item["candidate_id"]
        require(re.fullmatch(r"Q\d{2,4}", cid) is not None and cid not in ids, "Invalid or duplicate candidate_id")
        ids.add(cid)
        require(item["seed_id"] in seeds, "Unknown seed_id")
        seed = seeds[item["seed_id"]]
        require(item["persona_id"] == seed["persona_id"], "Persona differs from seed")
        require(item["scenario_id"] in packet["scenarios"], "Unknown scenario_id")
        require(item["review_status"] == "draft", "Only draft candidates are allowed")
        relation = item["relation"]
        require(relation in {"paraphrase", "condition_change", "new_need"}, "Unknown relation")
        string_list(item["changed_conditions"], "changed_conditions")
        string_list(item["missing_inputs"], "missing_inputs")
        if relation == "condition_change":
            require(bool(item["changed_conditions"]), "Condition change must be explicit")
        else:
            require(not item["changed_conditions"], "Only condition_change may change conditions")
            require(item["scenario_id"] == seed["scenario_id"], "Scenario changed without condition_change")
        if relation == "new_need":
            require(re.fullmatch(r"N-[A-Z0-9-]+", item["information_need_id"]) is not None, "New information need requires an N- ID")
        else:
            require(item["information_need_id"] == seed["seed_id"], "Information need must stay connected to seed")
        normalized = " ".join(item["question"].split()).casefold()
        require(normalized != " ".join(seed["question"].split()).casefold(), "Candidate merely repeats seed")
        # Semantic equivalence and contradictory prose still need an independent human review.
        key = (item["persona_id"], item["scenario_id"], normalized)
        require(key not in questions, "Duplicate question text")
        questions.add(key)
        counts[item["persona_id"]] += 1
    return {"structural_check": "pass", "candidate_count": len(candidates), "persona_counts": counts,
            "meaning_review": "pending", "answerability_review": "pending", "official_evalset": False}


def run_path(value: str) -> Path:
    path = Path(value)
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    boundary = (ROOT / "runs/question-design").resolve()
    require(boundary.is_relative_to(ROOT.resolve()), "Run directory resolves outside repository")
    require(resolved.is_relative_to(boundary) and resolved != boundary, "Input/output must be inside runs/question-design/")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--output", required=True)
    check = commands.add_parser("check")
    check.add_argument("--input", required=True)
    check.add_argument("--candidates", required=True)
    args = parser.parse_args()
    try:
        source = (ROOT / "docs/problem.md").read_text(encoding="utf-8")
        packet = build_packet(source)
        if args.command == "prepare":
            target = run_path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as handle:
                json.dump(packet, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            print(json.dumps({"prepared": target.relative_to(ROOT).as_posix(), "source_sha256": packet["source_sha256"], "personas": len(packet["personas"]), "seeds": len(packet["seeds"])}, ensure_ascii=False))
        else:
            provided = json.loads(run_path(args.input).read_text(encoding="utf-8"))
            require(provided == packet, "Packet is stale or changed; prepare from current source")
            output = json.loads(run_path(args.candidates).read_text(encoding="utf-8"))
            print(json.dumps(check_candidates(packet, output), ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
