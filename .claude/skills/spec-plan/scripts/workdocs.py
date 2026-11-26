#!/usr/bin/env python3
"""스펙·계획 문서 생성, 검사, 병렬 단계 계산, 승인, 보관 (stdlib만 사용).

    uv run python .claude/skills/spec-plan/scripts/workdocs.py new spec <name> --title "..."
    uv run python .claude/skills/spec-plan/scripts/workdocs.py new plan <name> --spec <spec-id> --title "..."
    uv run python .claude/skills/spec-plan/scripts/workdocs.py check [--strict]
    uv run python .claude/skills/spec-plan/scripts/workdocs.py waves <plan-id>
    uv run python .claude/skills/spec-plan/scripts/workdocs.py approve spec <id> --by <사용자> | approve plan <id> [--by 디렉터]
    uv run python .claude/skills/spec-plan/scripts/workdocs.py start <plan-id>
    uv run python .claude/skills/spec-plan/scripts/workdocs.py archive <spec-id> [--dry-run]
    uv run python .claude/skills/spec-plan/scripts/workdocs.py cancel spec|plan <id> --reason "..." [--dry-run]
    uv run python .claude/skills/spec-plan/scripts/workdocs.py list [--archived]

목록(인덱스) 파일은 만들지 않는다. 활성 폴더 자체가 진행 중 목록이고, 끝난 문서는 보관 폴더로 옮긴다.

규칙 원본은 같은 스킬의 SKILL.md와 references/completion-criteria.md다.
"""
from __future__ import annotations

import argparse
import hashlib
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("WORKDOCS_ROOT") or SKILL.parents[2])

ACTIVE = {"spec": "docs/specs", "plan": "docs/plans"}
ARCHIVE = {"spec": "docs/archives/specs", "plan": "docs/archives/plans"}
STATUSES = {
    "spec": ["draft", "clarifying", "approved", "done", "cancelled"],
    "plan": ["draft", "approved", "in_progress", "done", "cancelled"],
}
CLOSED = {"done", "cancelled"}
REQUIRED = {
    "spec": ["type", "id", "title", "status", "owner", "created", "updated",
             "approved_by", "approved_at", "completed_at", "archived_at"],
    "plan": ["type", "id", "title", "status", "owner", "spec", "created", "updated",
             "approved_by", "approved_at", "completed_at", "archived_at", "base_commit"],
}
NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TASK_STATUSES = {"todo", "doing", "done", "blocked", "cancelled"}
HUMAN_ASSIGNEES = {"오케스트레이터", "디렉터", "팀원", "사용자"}  # 에이전트가 아닌 담당
DIRECTORS = {"오케스트레이터", "디렉터"}  # 계획 승인·작업 판단 (HITL 아님)
VERDICTS = {"pass", "fail", "waived"}
METHODS = ("명령", "파일", "사람", "보고")
VAGUE = ["적절", "충분", "잘 ", "깔끔", "가능한 한", "가급적", "최대한", "등등", "원활"]

errors: list[str] = []
warns: list[str] = []


# ── 파일·frontmatter ──────────────────────────────────────────────────────
def today() -> str:
    return os.environ.get("WORKDOCS_TODAY") or dt.date.today().isoformat()


def split_frontmatter(text: str) -> tuple[list[str], str]:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return [], text
    return m.group(1).splitlines(), text[m.end():]


def parse_fm(lines: list[str]) -> dict:
    fm: dict = {}
    cur = None
    for line in lines:
        if re.match(r"^\s+- ", line) and cur:
            if not isinstance(fm.get(cur), list):
                fm[cur] = []
            fm[cur].append(line.split("- ", 1)[1].strip())
        elif ":" in line:
            cur, val = (s.strip() for s in line.split(":", 1))
            if val.startswith("[") and val.endswith("]"):
                fm[cur] = [v.strip() for v in val[1:-1].split(",") if v.strip()]
            else:
                fm[cur] = val
    return fm


def set_fm(text: str, updates: dict) -> str:
    lines, body = split_frontmatter(text)
    keys = [l.split(":", 1)[0].strip() for l in lines]
    for k, v in updates.items():
        line = f"{k}: {v}".rstrip()
        if k in keys:
            lines[keys.index(k)] = line
        else:
            lines.append(line)
            keys.append(k)
    return "---\n" + "\n".join(lines) + "\n---\n" + body


class Doc:
    def __init__(self, path: Path):
        self.path = path
        self.rel = path.relative_to(ROOT).as_posix()
        self.text = path.read_text(encoding="utf-8")
        lines, self.body = split_frontmatter(self.text)
        self.fm = parse_fm(lines)
        self.type = self.fm.get("type", "")
        self.id = self.fm.get("id", "")
        self.status = self.fm.get("status", "")
        self.archived = self.rel.startswith("docs/archives/")

    def save(self, updates: dict) -> None:
        self.text = set_fm(self.text, updates)
        self.path.write_text(self.text, encoding="utf-8")
        self.fm.update(updates)
        self.status = self.fm.get("status", "")


INDEX_NAMES = {"readme.md", "index.md", "_index.md"}


def is_index_name(name: str) -> bool:
    return name.lower() in INDEX_NAMES


def stray_files() -> list[str]:
    """문서 폴더 안의 인덱스 파일과 하위 폴더 (이 폴더들에는 문서만 둔다)."""
    out = []
    for folder in [*ACTIVE.values(), "docs/archives", *ARCHIVE.values()]:
        d = ROOT / folder
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            rel = p.relative_to(ROOT).as_posix()
            if p.is_file() and is_index_name(p.name):
                out.append(rel)
            elif p.is_dir() and p.relative_to(ROOT).as_posix() not in ARCHIVE.values():
                out.append(rel + "/")
    return out


def all_docs() -> list[Doc]:
    out = []
    for folder in list(ACTIVE.values()) + list(ARCHIVE.values()):
        d = ROOT / folder
        if d.is_dir():
            out += [Doc(p) for p in sorted(d.glob("*.md")) if not is_index_name(p.name)]
    return out


def find(docs: list[Doc], doc_id: str, kind: str) -> Doc | None:
    """id는 종류(spec·plan) 안에서 유일하다. 스펙과 계획은 같은 이름을 쓸 수 있다."""
    return next((d for d in docs if d.type == kind and (d.id == doc_id or d.path.stem == doc_id)), None)


# ── 본문 표 ───────────────────────────────────────────────────────────────
def tables(body: str) -> list[list[list[str]]]:
    """코드 블록 밖의 Markdown 표를 [행[셀]] 목록으로 (헤더 포함, 구분선 제외)."""
    out, cur, fence = [], [], False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
        if not fence and line.strip().startswith("|"):
            inner = re.sub(r"^\||(?<!\\)\|$", "", line.strip())
            cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", inner)]
            if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                cur.append(cells)
            continue
        if cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def table(body: str, *header: str) -> list[dict]:
    for t in tables(body):
        if [h for h in t[0][: len(header)]] == list(header):
            return [dict(zip(t[0], row + [""] * (len(t[0]) - len(row)))) for row in t[1:]]
    return []


def ids(cell: str, prefix: str) -> list[str]:
    return re.findall(rf"\b{prefix}-\d+\b", cell)


def spec_parts(doc: Doc) -> dict:
    return {
        "req": table(doc.body, "ID", "요구사항"),
        "ac": table(doc.body, "ID", "기준"),
        "q": table(doc.body, "ID", "질문"),
        "decisions": table(doc.body, "날짜", "결정"),
    }


def plan_parts(doc: Doc) -> dict:
    return {"tasks": table(doc.body, "ID", "작업"), "verdict": table(doc.body, "AC", "결과"),
            "decisions": table(doc.body, "날짜", "결정")}


def agent_names() -> set[str]:
    return {p.stem for p in (ROOT / ".claude/agents").glob("*.md")}


def read_only_agents() -> set[str]:
    """frontmatter tools에 Write·Edit이 없는 에이전트 (산출물 파일을 쓰지 않는다)."""
    out = set()
    for p in (ROOT / ".claude/agents").glob("*.md"):
        tools = parse_fm(split_frontmatter(p.read_text(encoding="utf-8"))[0]).get("tools", "")
        tools = ",".join(tools) if isinstance(tools, list) else tools
        if tools and not re.search(r"\b(Write|Edit)\b", tools):
            out.add(p.stem)
    return out


def contract_hash(d: "Doc") -> str:
    """승인 대상: 스펙은 요구사항·완료 기준 표, 계획은 작업의 ID·작업·담당·선행·산출물·완료 기준(상태 제외)."""
    if d.type == "spec":
        p = spec_parts(d)
        rows = [[r.get(k, "") for k in ("ID", "요구사항", "구분")] for r in p["req"]]
        rows += [[a.get(k, "") for k in ("ID", "기준", "확인 방법", "기대 결과", "요구사항")] for a in p["ac"]]
    else:
        rows = [[t.get(k, "") for k in ("ID", "작업", "담당", "선행", "산출물", "완료 기준")]
                for t in plan_parts(d)["tasks"]]
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()[:12]


def body_hash(text: str) -> str:
    lines, body = split_frontmatter(text)
    keep = [l for l in lines if not l.startswith("archived_hash:")]
    return hashlib.sha256(("\n".join(keep) + body).encode("utf-8")).hexdigest()[:12]


def decision_rows(d: "Doc") -> list[dict]:
    return table(d.body, "날짜", "결정")


def is_person(name: str) -> bool:
    """스펙 결정자는 사람이어야 한다: 에이전트·오케스트레이터·디렉터가 아니면 사람으로 본다."""
    name = name.strip()
    return bool(name) and not any(r in name for r in DIRECTORS) and not any(a in name for a in agent_names())


def paths_in(cell: str) -> list[str]:
    return [p.rstrip("/") for p in re.findall(r"`([^`]+)`", cell)]


# ── 병렬 단계 ─────────────────────────────────────────────────────────────
def waves(tasks: list[dict], where: str) -> list[list[str]]:
    live = {t["ID"]: t for t in tasks if t.get("상태") != "cancelled"}
    deps = {i: [d for d in ids(t.get("선행", ""), "T") if d in live] for i, t in live.items()}
    done: set[str] = set()
    out: list[list[str]] = []
    while len(done) < len(live):
        layer = sorted((i for i in live if i not in done and set(deps[i]) <= done),
                       key=lambda x: int(x.split("-")[1]))
        if not layer:
            errors.append(f"[plan] {where}: 선행 관계에 순환이 있음 ({sorted(set(live) - done)})")
            return out
        out.append(layer)
        done |= set(layer)
    for n, layer in enumerate(out, 1):
        for i, a in enumerate(layer):
            for b in layer[i + 1:]:
                for pa in paths_in(live[a].get("산출물", "")):
                    for pb in paths_in(live[b].get("산출물", "")):
                        if pa == pb or pa.startswith(pb + "/") or pb.startswith(pa + "/"):
                            errors.append(f"[plan] {where}: 단계 {n}의 {a}·{b}가 같은 산출물 `{pa}`·`{pb}`을 씀 "
                                          "— 선행 관계를 넣어 순서를 정한다")
    return out


# ── 검사 ─────────────────────────────────────────────────────────────────
def check_doc(d: Doc, docs: list[Doc]) -> None:
    where = d.rel
    if not NAME_RE.match(d.path.stem):
        errors.append(f"[name] {where}: 파일 이름이 YYYY-MM-DD-{{kebab-case}}.md 형식이 아님")
    folder = d.path.parent.relative_to(ROOT).as_posix()
    want_type = {f: t for t, f in [*ACTIVE.items(), *ARCHIVE.items()]}.get(folder, "")
    if d.type not in STATUSES:
        errors.append(f"[frontmatter] {where}: type='{d.type}' (spec | plan)")
        return
    if d.type != want_type:
        errors.append(f"[location] {where}: type={d.type} 문서가 {folder}에 있음")
    for k in REQUIRED[d.type]:
        if k not in d.fm:
            errors.append(f"[frontmatter] {where}: '{k}' 없음")
    if d.id != d.path.stem:
        errors.append(f"[frontmatter] {where}: id='{d.id}' ≠ 파일 이름 '{d.path.stem}'")
    if d.status not in STATUSES[d.type]:
        errors.append(f"[frontmatter] {where}: status='{d.status}' ({' | '.join(STATUSES[d.type])})")
    for k in ("created", "updated", "approved_at", "completed_at", "archived_at"):
        v = d.fm.get(k)
        if v and not (isinstance(v, str) and DATE_RE.match(v)):
            errors.append(f"[frontmatter] {where}: {k}='{v}' (YYYY-MM-DD)")
    if isinstance(d.fm.get("created"), str) and not d.path.stem.startswith(d.fm["created"]):
        warns.append(f"[name] {where}: 파일 이름 날짜와 created({d.fm['created']})가 다름")
    if d.archived and d.status not in CLOSED:
        errors.append(f"[location] {where}: 보관 폴더에는 done·cancelled만 둔다 (status={d.status})")
    if not d.archived and d.status in CLOSED:
        errors.append(f"[location] {where}: status={d.status} 문서는 보관해야 함 (archive / cancel 명령)")
    if d.archived and not (d.fm.get("archived_at") and (d.status == "cancelled" or d.fm.get("completed_at"))):
        errors.append(f"[frontmatter] {where}: 보관 문서는 completed_at·archived_at을 채운다")
    if d.status == "cancelled" and not d.fm.get("cancel_reason"):
        errors.append(f"[frontmatter] {where}: cancelled 문서는 cancel_reason이 필요")
    if d.status not in ("draft", "clarifying", "cancelled"):
        if not (d.fm.get("approved_by") and d.fm.get("approved_at")):
            errors.append(f"[approval] {where}: status={d.status}이면 approved_by·approved_at이 필요")
        if "{{" in d.body:
            errors.append(f"[template] {where}: 채우지 않은 {{{{...}}}} 자리표시가 남음")
        if d.fm.get("approved_hash") != contract_hash(d):
            what = "요구사항·완료 기준" if d.type == "spec" else "작업 분해(상태 제외)"
            errors.append(f"[approval] {where}: 승인 후 {what}이 바뀜 (approved_hash 불일치) — "
                          "변경 이력을 남기고 사용자 재승인(approve)을 받는다")
    if d.archived and d.fm.get("archived_hash") != body_hash(d.text):
        errors.append(f"[archive] {where}: 보관 후 내용이 바뀜 (archived_hash 불일치) — 보관 문서는 고치지 않는다")
    n_warn = len(warns)
    (check_spec if d.type == "spec" else check_plan)(d, docs)
    if d.archived:  # 보관 문서는 고칠 수 없으므로 WARN을 남기지 않는다
        del warns[n_warn:]


def check_spec(d: Doc, docs: list[Doc]) -> None:
    where, p = d.rel, spec_parts(d)
    reqs = {r["ID"]: r for r in p["req"] if r["ID"].startswith("REQ-")}
    acs = {a["ID"]: a for a in p["ac"] if a["ID"].startswith("AC-")}
    if d.status in ("draft", "clarifying"):
        return
    if not reqs or not acs:
        errors.append(f"[spec] {where}: 요구사항(REQ-n)·완료 기준(AC-n) 표가 비어 있음")
    for q in p["q"]:
        if q.get("상태") != "resolved" and q["ID"].startswith("Q-"):
            errors.append(f"[spec] {where}: {q['ID']}가 resolved가 아님 — 미결 사항이 남으면 승인하지 않는다")
        elif q["ID"].startswith("Q-") and not q.get("결정"):
            errors.append(f"[spec] {where}: {q['ID']} 결정 칸이 비어 있음")
    covered = set()
    for a in acs.values():
        refs = ids(a.get("요구사항", ""), "REQ")
        covered |= set(refs)
        if not refs:
            errors.append(f"[ac] {where}: {a['ID']}가 요구사항을 가리키지 않음")
        for r in refs:
            if r not in reqs:
                errors.append(f"[ac] {where}: {a['ID']}가 없는 {r}를 가리킴")
        if not a.get("확인 방법") or not a.get("기대 결과"):
            errors.append(f"[ac] {where}: {a['ID']} 확인 방법·기대 결과가 비어 있음")
        elif not re.match(rf"^({'|'.join(METHODS)})\s*:", a["확인 방법"]):
            errors.append(f"[ac] {where}: {a['ID']} 확인 방법은 '명령:'·'파일:'·'사람:'·'보고:'로 시작한다")
        text = f"{a.get('기준', '')} {a.get('기대 결과', '')}"
        for w in VAGUE:
            if w in text:
                warns.append(f"[ac] {where}: {a['ID']}에 판정이 모호한 표현 '{w.strip()}'")
    for r, row in reqs.items():
        if row.get("구분") == "필수" and r not in covered:
            errors.append(f"[ac] {where}: 필수 {r}에 완료 기준이 없음")
    plans = [x for x in docs if x.type == "plan" and x.fm.get("spec") == d.id]
    if d.status == "done":
        for x in plans:
            if x.status not in CLOSED:
                errors.append(f"[spec] {where}: done인데 계획 {x.id}가 {x.status}")
        if not any(x.status == "done" for x in plans):
            errors.append(f"[spec] {where}: done인데 완료된 계획이 없음")


def check_plan(d: Doc, docs: list[Doc]) -> None:
    where, p = d.rel, plan_parts(d)
    spec = find(docs, d.fm.get("spec", ""), "spec")
    if not spec:
        errors.append(f"[plan] {where}: spec='{d.fm.get('spec')}' 스펙 문서가 없음")
        return
    if d.status in ("approved", "in_progress", "done") and spec.status not in ("approved", "done"):
        errors.append(f"[plan] {where}: 스펙 {spec.id}가 승인 전({spec.status})인데 계획이 {d.status}")
    spec_acs = {a["ID"] for a in spec_parts(spec)["ac"] if a["ID"].startswith("AC-")}
    tasks = [t for t in p["tasks"] if t["ID"].startswith("T-")]
    if d.status == "draft" and not tasks:
        return
    seen, valid_assignees, covered = set(), agent_names() | HUMAN_ASSIGNEES, set()
    readonly = read_only_agents()
    for t in tasks:
        i = t["ID"]
        if i in seen:
            errors.append(f"[plan] {where}: 작업 ID {i} 중복")
        seen.add(i)
        if t.get("담당") not in valid_assignees:
            errors.append(f"[plan] {where}: {i} 담당 '{t.get('담당')}'는 에이전트·오케스트레이터·팀원·사용자가 아님")
        if t.get("상태") not in TASK_STATUSES:
            errors.append(f"[plan] {where}: {i} 상태 '{t.get('상태')}' ({' | '.join(sorted(TASK_STATUSES))})")
        refs = ids(t.get("완료 기준", ""), "AC")
        covered |= set(refs)
        if not refs and not t.get("완료 기준", "").startswith("지원:"):
            errors.append(f"[plan] {where}: {i} 완료 기준이 AC-n도 '지원: 조건'도 아님")
        for r in refs:
            if r not in spec_acs:
                errors.append(f"[plan] {where}: {i}가 스펙에 없는 {r}를 가리킴")
        for dep in ids(t.get("선행", ""), "T"):
            if dep not in {x["ID"] for x in tasks}:
                errors.append(f"[plan] {where}: {i} 선행 {dep}가 없음")
        if not paths_in(t.get("산출물", "")) and t.get("담당") not in HUMAN_ASSIGNEES | readonly:
            warns.append(f"[plan] {where}: {i} 산출물 경로가 없음 (백틱 경로) — 병렬 충돌을 검사할 수 없음")
    waves(tasks, where)
    missing = spec_acs - covered
    if missing:
        (errors if d.status != "draft" else warns).append(
            f"[plan] {where}: 스펙 완료 기준 {sorted(missing)}을 맡은 작업이 없음")
    if d.status == "done":
        check_plan_done(d, spec, tasks, p["verdict"], spec_acs)


def method_of(spec: Doc, ac: str) -> str:
    row = next((a for a in spec_parts(spec)["ac"] if a["ID"] == ac), {})
    return row.get("확인 방법", "").split(":", 1)[0].strip()


def check_plan_done(d: Doc, spec: Doc, tasks: list[dict], verdict: list[dict], spec_acs: set[str]) -> None:
    where = d.rel
    for t in tasks:
        if t.get("상태") not in ("done", "cancelled"):
            errors.append(f"[done] {where}: {t['ID']} 상태가 {t.get('상태')}")
    # 작업을 cancelled로 바꿔도 그 AC는 빠지지 않는다: 스펙의 모든 AC를 판정한다
    rows = {v["AC"]: v for v in verdict if v["AC"].startswith("AC-")}
    decisions = spec_parts(spec)["decisions"]
    for ac in sorted(spec_acs, key=lambda x: int(x.split("-")[1])):
        v = rows.get(ac)
        if not v:
            errors.append(f"[done] {where}: 완료 판정 표에 {ac}가 없음")
            continue
        if v.get("결과") not in ("pass", "waived"):
            errors.append(f"[done] {where}: {ac} 결과 '{v.get('결과')}' — pass 또는 waived여야 완료")
        if not v.get("근거") or not v.get("확인자"):
            errors.append(f"[done] {where}: {ac} 근거·확인자가 비어 있음")
        if v.get("결과") == "waived" and not any(
                ac in ids(r.get("결정", ""), "AC") and is_person(r.get("결정자", "")) for r in decisions):
            errors.append(f"[done] {where}: {ac} waived인데 스펙 결정 기록에 사람(결정자)의 결정이 없음")
        confirmer = v.get("확인자", "")
        assignees = {t.get("담당", "") for t in tasks if ac in ids(t.get("완료 기준", ""), "AC")}
        for a in assignees - {"사용자", "팀원"}:
            if a and a in confirmer:
                if a in DIRECTORS and method_of(spec, ac) == "명령":
                    continue  # 결정적 명령은 오케스트레이터가 다시 실행해 확인할 수 있다
                errors.append(f"[done] {where}: {ac} 확인자 '{confirmer}'에 수행 담당 '{a}'가 들어 있음")


def run_check(strict: bool) -> int:
    docs = all_docs()
    seen: dict[tuple[str, str], str] = {}
    for d in docs:
        if (d.type, d.id) in seen:
            errors.append(f"[frontmatter] {d.rel}: {d.type} id '{d.id}'가 {seen[(d.type, d.id)]}와 중복")
        seen[(d.type, d.id)] = d.rel
        check_doc(d, docs)
    for rel in stray_files():
        errors.append(f"[index] {rel}: 스펙·계획 폴더에 인덱스 파일·하위 폴더를 두지 않는다 — 목록은 `workdocs.py list`")
    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    print(f"\n루트 {ROOT}\n문서 {len(docs)}개, ERROR {len(errors)}, WARN {len(warns)}")
    return 1 if errors or (strict and warns) else 0


# ── 이동과 링크 갱신 ──────────────────────────────────────────────────────
LINK_RE = re.compile(r"(\]\()([^)\s#]+)((?:#[^)]*)?\))")


def repo_md() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        return [ROOT / f for f in out if (ROOT / f).exists()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [p for p in ROOT.rglob("*.md") if ".git" not in p.parts]


def relink(text: str, src_dir: Path, mapping: dict[Path, Path], new_dir: Path | None = None) -> str:
    """src_dir 기준 상대 링크 중 mapping의 옛 경로를 새 경로로. new_dir이면 모든 상대 링크를 new_dir 기준으로."""
    def sub(m: re.Match) -> str:
        link = m.group(2)
        if re.match(r"^[a-z]+:", link) or link.startswith("/"):
            return m.group(0)
        target = Path(os.path.normpath(src_dir / link))
        target = mapping.get(target, target)
        base = new_dir or src_dir
        if target == Path(os.path.normpath(src_dir / link)) and new_dir is None:
            return m.group(0)
        return m.group(1) + Path(os.path.relpath(target, base)).as_posix() + m.group(3)
    return LINK_RE.sub(sub, text)


def move_docs(moves: list[tuple[Doc, dict]], dry: bool) -> None:
    mapping = {}
    for d, _ in moves:
        dest = ROOT / ARCHIVE[d.type] / d.path.name
        if dest.exists():
            sys.exit(f"중단: {dest.relative_to(ROOT)}가 이미 있음")
        mapping[d.path] = dest
    for d, upd in moves:
        print(f"{'(dry-run) ' if dry else ''}{d.rel} → {mapping[d.path].relative_to(ROOT).as_posix()}  {upd}")
    if dry:
        return
    for d, upd in moves:
        d.save(upd)
    for f in repo_md():
        if f in mapping:
            continue
        text = f.read_text(encoding="utf-8")
        new = relink(text, f.parent, mapping)
        if new != text:
            f.write_text(new, encoding="utf-8")
            print(f"링크 갱신 {f.relative_to(ROOT).as_posix()}")
    tracked = set(subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split())
    for old, new in mapping.items():
        text = relink(old.read_text(encoding="utf-8"), old.parent, mapping, new_dir=new.parent)
        text = set_fm(text, {"archived_hash": body_hash(text)})
        old.write_text(text, encoding="utf-8")
        new.parent.mkdir(parents=True, exist_ok=True)
        if old.relative_to(ROOT).as_posix() in tracked:
            subprocess.run(["git", "mv", str(old), str(new)], cwd=ROOT, check=True)
        else:
            shutil.move(old, new)


# ── 명령 ─────────────────────────────────────────────────────────────────
def cmd_new(a) -> int:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", a.name):
        sys.exit("이름은 영문 소문자·숫자 kebab-case (예: chunk-schema-contract)")
    date = today()
    doc_id = f"{date}-{a.name}"
    dest = ROOT / ACTIVE[a.kind] / f"{doc_id}.md"
    docs = all_docs()
    if dest.exists() or find(docs, doc_id, a.kind):
        sys.exit(f"중단: {doc_id}가 이미 있음")
    values = {"id": doc_id, "title": a.title, "date": date}
    if a.kind == "plan":
        spec = find(docs, a.spec or "", "spec")
        if not spec:
            sys.exit(f"중단: 스펙 '{a.spec}'이 없음")
        if spec.status not in ("approved",):
            sys.exit(f"중단: 스펙 {spec.id}가 approved가 아님 ({spec.status}) — HITL로 미결 사항을 먼저 해결한다")
        rel = Path(os.path.relpath(spec.path, dest.parent)).as_posix()
        head = "-"
        for ref in ("origin/main", "main", "HEAD"):
            r = subprocess.run(["git", "rev-parse", "--short", ref], cwd=ROOT, capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                head = r.stdout.strip()
                break
        values |= {"spec_id": spec.id, "spec_link": f"[{spec.id}]({rel})", "base_commit": head}
    text = (SKILL / "templates" / f"{a.kind}.md").read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(dest.relative_to(ROOT).as_posix())
    return 0


def cmd_waves(a) -> int:
    d = find(all_docs(), a.id, "plan")
    if not d:
        sys.exit(f"계획 '{a.id}'이 없음")
    tasks = [t for t in plan_parts(d)["tasks"] if t["ID"].startswith("T-")]
    by_id = {t["ID"]: t for t in tasks}
    for n, layer in enumerate(waves(tasks, d.rel), 1):
        print(f"단계 {n}: " + ", ".join(f"{i}({by_id[i].get('담당')})" for i in layer))
    for e in errors:
        print("ERROR", e)
    return 1 if errors else 0


def cmd_approve(a) -> int:
    docs = all_docs()
    d = find(docs, a.id, a.kind)
    if not d or d.archived:
        sys.exit(f"활성 {a.kind} '{a.id}'가 없음")
    if not a.by:
        if a.kind == "spec":
            sys.exit("중단: 스펙 승인은 --by <사용자>가 필요하다")
        a.by = "오케스트레이터"
    allowed = {"spec": ("draft", "clarifying"), "plan": ("draft", "approved", "in_progress")}[a.kind]
    if d.status not in allowed:
        sys.exit(f"중단: {d.id}는 {d.status} — 승인된 스펙을 바꿨다면 status를 clarifying으로 되돌리고 "
                 "변경 이력을 쓴 뒤 다시 승인한다")
    if a.kind == "spec":  # HITL은 스펙에만: 사람의 승인 행이 있어야 한다
        if not is_person(a.by):
            sys.exit(f"중단: --by '{a.by}'는 사람이 아님. 스펙 승인은 사용자·팀원만 한다")
        if not any("승인" in r.get("결정", "") and r.get("결정자", "").strip() == a.by for r in decision_rows(d)):
            sys.exit(f"중단: {d.rel} 결정 기록에 '{a.by}'의 승인 행이 없음 "
                     f"(| 날짜 | ... 승인 | {a.by} | 근거 |). 사용자 확인을 받은 뒤 기록한다")
    elif a.by in agent_names():
        sys.exit(f"중단: --by '{a.by}'는 하위 에이전트. 계획은 오케스트레이터·디렉터가 승인한다")
    status = "approved" if d.status in ("draft", "clarifying", "approved") else d.status
    upd = {"status": status, "approved_by": a.by, "approved_at": today(), "updated": today()}
    original = d.text
    d.save(upd)
    d.save({"approved_hash": contract_hash(d)})
    errors.clear()
    check_doc(d, all_docs())
    if errors:
        d.path.write_text(original, encoding="utf-8")
        for e in errors:
            print("ERROR", e)
        print("승인하지 않음 (파일 원상 복구)")
        return 1
    print(f"{d.rel}: approved by {a.by}")
    return 0


def cmd_list(a) -> int:
    """frontmatter로 목록을 출력한다 (파일로 쓰지 않는다)."""
    docs = all_docs()
    for kind in ("spec", "plan"):
        rows = [d for d in docs if d.type == kind and d.archived == a.archived]
        print(f"[{kind}] {len(rows)}개")
        for d in rows:
            link = d.fm.get("spec", "") if kind == "plan" else ", ".join(
                x.id for x in docs if x.type == "plan" and x.fm.get("spec") == d.id)
            date = d.fm.get("archived_at") if a.archived else d.fm.get("updated")
            print(f"  {d.id}  {d.status}  {date}  {d.fm.get('title', '')}" + (f"  ↔ {link}" if link else ""))
    return 0


def cmd_start(a) -> int:
    d = find(all_docs(), a.id, "plan")
    if not d or d.archived:
        sys.exit(f"활성 계획 '{a.id}'가 없음")
    if d.status != "approved":
        sys.exit(f"중단: {d.id}는 {d.status} — 사용자 승인(approved) 뒤에 발주를 시작한다")
    d.save({"status": "in_progress", "updated": today()})
    print(f"{d.rel}: in_progress")
    return 0


def cmd_archive(a) -> int:
    docs = all_docs()
    spec = find(docs, a.id, "spec")
    if not spec or spec.archived:
        sys.exit(f"활성 스펙 '{a.id}'가 없음 (계획만 따로 보관하려면 cancel)")
    plans = [x for x in docs if x.type == "plan" and x.fm.get("spec") == spec.id and not x.archived]
    d_ = today()
    moves = [(p, {"status": "done", "completed_at": p.fm.get("completed_at") or d_, "archived_at": d_, "updated": d_})
             if p.status != "cancelled" else (p, {"archived_at": d_, "updated": d_}) for p in plans]
    moves.append((spec, {"status": "done", "completed_at": spec.fm.get("completed_at") or d_,
                         "archived_at": d_, "updated": d_}))
    # 이동 후 상태로 미리 검사
    snapshot = {d.path: d.text for d, _ in moves}
    for d, upd in moves:
        d.text = set_fm(d.text, upd)
        d.fm.update(upd)
        d.status = d.fm["status"]
        d.archived = True
    errors.clear()
    for d, _ in moves:
        check_doc(d, docs)
    errors[:] = [e for e in errors if not e.startswith(("[location]", "[archive]"))
                 and "completed_at·archived_at" not in e]
    for d, _ in moves:
        d.text = snapshot[d.path]
        d.archived = False
    if errors:
        for e in errors:
            print("ERROR", e)
        print("보관하지 않음: 완료 기준을 충족하지 않았다")
        return 1
    move_docs(moves, a.dry_run)
    return 0


def cmd_cancel(a) -> int:
    docs = all_docs()
    d = find(docs, a.id, a.kind)
    if not d or d.archived:
        sys.exit(f"활성 {a.kind} '{a.id}'가 없음")
    d_ = today()
    upd = {"status": "cancelled", "cancel_reason": a.reason, "archived_at": d_, "updated": d_}
    if d.type == "spec" and not any("취소" in r.get("결정", "") and is_person(r.get("결정자", ""))
                                    for r in decision_rows(d)):
        sys.exit(f"중단: 스펙 취소는 사용자 결정이 필요하다. {d.rel} 결정 기록에 사람의 취소 결정 행을 쓴 뒤 실행한다")
    targets = [d]
    if d.type == "spec":
        targets += [x for x in docs if x.type == "plan" and x.fm.get("spec") == d.id and not x.archived]
    moves = []
    for t in targets:
        if t.type == "plan" and t.status == "done":
            sys.exit(f"중단: 계획 {t.id}는 done이다. 스펙을 완료 처리(archive)할지 먼저 정한다")
        moves.append((t, dict(upd)))
    move_docs(moves, a.dry_run)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("new"); p.add_argument("kind", choices=["spec", "plan"]); p.add_argument("name")
    p.add_argument("--title", required=True); p.add_argument("--spec")
    p = sp.add_parser("check"); p.add_argument("--strict", action="store_true")
    p = sp.add_parser("waves"); p.add_argument("id")
    p = sp.add_parser("approve"); p.add_argument("kind", choices=["spec", "plan"]); p.add_argument("id")
    p.add_argument("--by", help="스펙: 승인한 사용자(필수). 계획: 기본 오케스트레이터")
    p = sp.add_parser("start"); p.add_argument("id")
    p = sp.add_parser("archive"); p.add_argument("id"); p.add_argument("--dry-run", action="store_true")
    p = sp.add_parser("cancel"); p.add_argument("kind", choices=["spec", "plan"]); p.add_argument("id"); p.add_argument("--reason", required=True)
    p.add_argument("--dry-run", action="store_true")
    p = sp.add_parser("list"); p.add_argument("--archived", action="store_true")
    a = ap.parse_args()
    if a.cmd == "check":
        return run_check(a.strict)
    if a.cmd == "list":
        return cmd_list(a)
    return {"new": cmd_new, "waves": cmd_waves, "approve": cmd_approve, "start": cmd_start,
            "archive": cmd_archive, "cancel": cmd_cancel}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
