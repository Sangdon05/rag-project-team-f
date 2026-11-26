#!/usr/bin/env python3
"""문서 동기화 검사 (doc-sync 스킬).

사용:
    uv run python .claude/skills/doc-sync/scripts/check_docs.py [--base origin/main] [--strict]

ERROR: 구조가 깨짐 (링크, 등록, 값 불일치, 고아 문서, 금지어). 반드시 고친다.
WARN : 함께 바뀌어야 할 수 있는 문서가 이번 변경에 없음. 확인 후 고치거나 PR에 사유를 남긴다.
--strict 는 WARN도 실패로 처리한다.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[4]
MAP = Path(__file__).resolve().parents[1] / "doc-map.json"

errors: list[str] = []
warns: list[str] = []
historical_unresolved: list[str] = []
historical_resolved: list[str] = []


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return [l for l in out.stdout.splitlines() if l]


def read(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def match_any(path: str, globs: list[str]) -> bool:
    return any(fnmatch(path, g) for g in globs)


def repo_files() -> list[str]:
    files = set(git("ls-files")) | set(git("ls-files", "--others", "--exclude-standard"))
    return sorted(f for f in files if (ROOT / f).exists())


def md_links(rel: str) -> list[str]:
    links = re.findall(r"\]\(([^)\s#]+)(?:#[^)]*)?\)", read(rel))
    return [l for l in links if not re.match(r"^[a-z]+:", l)]


def resolve(rel: str, link: str) -> str:
    return (Path(rel).parent / link).as_posix() if not link.startswith("/") else link.lstrip("/")


def normpath(p: str) -> str:
    import os.path
    return os.path.normpath(p).replace("\\", "/")


# 1. 링크 ---------------------------------------------------------------
def historical_allowance(cfg: dict) -> Counter[tuple[str, str]]:
    """승인된 정확한 보고서 경로/링크 쌍만 인스턴스별로 허용한다."""
    allowed: Counter[tuple[str, str]] = Counter()
    report_root = (ROOT / "solar_handoff/reports").resolve()
    if not report_root.is_relative_to(ROOT.resolve()):
        errors.append("[historical-link] 보고서 디렉터리가 저장소 밖을 가리킴")
        return allowed
    entries = cfg.get("historical_missing_links", [])
    if not isinstance(entries, list):
        errors.append("[historical-link] 예외 목록은 배열이어야 함")
        return allowed
    for entry in entries:
        if not isinstance(entry, list) or len(entry) != 2 or not all(isinstance(x, str) and x for x in entry):
            errors.append(f"[historical-link] 잘못된 예외 항목: {entry!r}")
            continue
        report, link = entry
        path = PurePosixPath(report)
        if ("\\" in report or path.is_absolute() or path.as_posix() != report
                or any(part in (".", "..") or ":" in part for part in report.split("/"))
                or not report.startswith("solar_handoff/reports/") or not report.endswith(".md")
                or not (ROOT / report).resolve().is_relative_to(report_root)):
            errors.append(f"[historical-link] 허용되지 않는 보고서 경로: {report!r}")
            continue
        allowed[(report, link)] += 1
    return allowed


def check_links(files: list[str], cfg: dict) -> None:
    remaining = historical_allowance(cfg)
    for f in files:
        if not f.endswith(".md"):
            continue
        for link in md_links(f):
            target = normpath(resolve(f, link))
            exists = (ROOT / target).exists()
            pair = (f, link)
            # 링크별 허용 개수보다 새로 추가된 동일 링크도 예외로 삼지 않는다.
            approved = remaining[pair] > 0 and (ROOT / f).resolve().is_relative_to(
                (ROOT / "solar_handoff/reports").resolve()
            )
            if approved:
                remaining[pair] -= 1
                if exists:
                    historical_resolved.append(f"{f}: {link}")
                else:
                    historical_unresolved.append(f"{f}: {link}")
            elif not exists:
                errors.append(f"[link] {f}: 깨진 링크 {link}")


# 2. 고아 문서 (허브에서 파일 링크로 도달 불가) ------------------------------
def check_orphans(files: list[str], cfg: dict) -> None:
    seen, stack = set(), list(cfg["hubs"])
    while stack:
        f = stack.pop()
        if f in seen or not (ROOT / f).is_file():
            continue
        seen.add(f)
        if f.endswith(".md"):
            stack += [normpath(resolve(f, l)) for l in md_links(f)]
    for f in files:
        if f.endswith(".md") and match_any(f, cfg["orphan_scope"]) and f not in seen:
            errors.append(f"[orphan] {f}: AGENTS.md/README.md에서 링크로 도달할 수 없음")


# 3. 스킬·에이전트 등록 -----------------------------------------------------
def frontmatter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    fm, cur = {}, None
    for line in m.group(1).splitlines():
        if re.match(r"^\s+- ", line) and cur:
            fm.setdefault(cur, []).append(line.split("- ", 1)[1].strip())
        elif ":" in line:
            cur, val = (s.strip() for s in line.split(":", 1))
            fm[cur] = val if val else []
    return fm


def table_rows(text: str) -> dict[str, list[str]]:
    """'| [name](path) | col2 | ...' -> {name: [col2, ...]}"""
    rows = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*\[([^\]]+)\]\([^)]*\)\s*\|(.*)\|\s*$", line)
        if m:
            rows[m.group(1)] = [c.strip() for c in m.group(2).split("|")]
    return rows


def check_registry(cfg: dict) -> None:
    reg = cfg["registries"]
    skills = {p.parent.name: frontmatter(p.read_text(encoding="utf-8"))
              for p in sorted((ROOT / ".claude/skills").glob("*/SKILL.md"))}
    agents = {p.stem: frontmatter(p.read_text(encoding="utf-8"))
              for p in sorted((ROOT / ".claude/agents").glob("*.md"))}

    for name, fm in {**{f"skill:{k}": v for k, v in skills.items()},
                     **{f"agent:{k}": v for k, v in agents.items()}}.items():
        kind, n = name.split(":")
        if fm.get("name") != n:
            errors.append(f"[frontmatter] {kind} {n}: name='{fm.get('name')}' (경로와 불일치)")
        if not fm.get("description"):
            errors.append(f"[frontmatter] {kind} {n}: description 없음")

    # 스킬 사용처 (에이전트 frontmatter 기준)
    used_by: dict[str, set[str]] = {s: set() for s in skills}
    for a, fm in agents.items():
        for s in fm.get("skills", []) or []:
            if s not in skills:
                errors.append(f"[registry] agent {a}: 없는 스킬 '{s}' 참조")
            else:
                used_by[s].add(a)
    for s in reg.get("orchestrator_skills", []):
        if s in used_by:
            used_by[s].add("오케스트레이터")

    # 스킬 README: 모든 스킬 등재 + 사용 에이전트 일치
    rows = table_rows(read(reg["skills_readme"]))
    for s in skills:
        if s not in rows:
            errors.append(f"[registry] {reg['skills_readme']}: 스킬 '{s}' 누락")
            continue
        listed = {x.strip() for x in rows[s][0].split(",") if x.strip()}
        if listed != used_by[s]:
            errors.append(f"[registry] {reg['skills_readme']}: '{s}' 사용 에이전트 {sorted(listed)} "
                          f"≠ 실제 {sorted(used_by[s])}")
    for s in rows:
        if s not in skills:
            errors.append(f"[registry] {reg['skills_readme']}: 존재하지 않는 스킬 '{s}' 등재")

    # 에이전트 README·AGENTS.md: 모든 에이전트 등재 + 스킬 목록 일치
    for doc in (reg["agents_readme"], reg["agents_hub"]):
        rows = table_rows(read(doc))
        for a, fm in agents.items():
            if a not in rows:
                errors.append(f"[registry] {doc}: 에이전트 '{a}' 누락")
                continue
            want = set(fm.get("skills", []) or [])
            got = next((set(x.strip() for x in c.split(",")) for c in rows[a] if set(x.strip() for x in c.split(",")) & (set(skills) | want)), set())
            if got != want:
                errors.append(f"[registry] {doc}: '{a}' 스킬 {sorted(got)} ≠ frontmatter {sorted(want)}")
        for a in rows:
            if a not in agents:
                errors.append(f"[registry] {doc}: 존재하지 않는 에이전트 '{a}' 등재")


# 4. 값 미러 ---------------------------------------------------------------
def env_values(rel: str) -> dict[str, str]:
    vals = {}
    for line in read(rel).splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line.strip())
        if m:
            vals[m.group(1)] = m.group(2).strip()
    return vals


def check_mirrors(cfg: dict) -> None:
    for m in cfg["mirrors"]:
        src = m["source"]
        if "key" in src:
            value = env_values(src["file"]).get(src["key"], "")
            label = f"{src['file']}:{src['key']}"
        else:
            value = read(src["file"]).strip()
            label = src["file"]
        if not value:
            errors.append(f"[mirror] {label}: 값 없음")
            continue
        for doc in m["in"]:
            if value not in read(doc):
                errors.append(f"[mirror] {doc}: {label} 값 '{value}'이 없음 (예전 값이 남았는지 확인)")

    # 포트: compose 기본값 / .env.example / DATABASE_URL
    env = env_values(".env.example")
    compose = re.search(r"POSTGRES_PORT:-(\d+)", read("docker-compose.yml"))
    url = re.search(r":(\d+)/", env.get("DATABASE_URL", ""))
    ports = {"docker-compose.yml": compose and compose.group(1),
             ".env.example POSTGRES_PORT": env.get("POSTGRES_PORT"),
             ".env.example DATABASE_URL": url and url.group(1)}
    if len(set(ports.values())) != 1:
        errors.append(f"[mirror] 포트 불일치: {ports}")

    pyver = read(".python-version").strip()
    if pyver and f">={pyver}" not in read("pyproject.toml"):
        errors.append(f"[mirror] pyproject.toml requires-python이 .python-version({pyver})과 다름")


def check_env_docs(cfg: dict) -> None:
    keys = env_values(cfg["env_docs"]["source"])
    for doc in cfg["env_docs"]["in"]:
        text = read(doc)
        tokens = set(re.findall(r"`([A-Z][A-Z0-9_]*\*?)`", text))
        prefixes = [t[:-1] for t in tokens if t.endswith("*")]
        for k in keys:
            if k not in tokens and not any(k.startswith(p) for p in prefixes):
                errors.append(f"[env] {doc}: 환경 변수 {k} 설명 없음")
        for t in tokens:
            if not t.endswith("*") and re.fullmatch(r"(OPENAI|POSTGRES|PGVECTOR|DATABASE)_[A-Z_]+|DATABASE_URL", t) and t not in keys:
                errors.append(f"[env] {doc}: .env.example에 없는 변수 {t} 설명 (삭제·이름 변경 반영 안 됨)")


def check_deps_docs(cfg: dict) -> None:
    py = read(cfg["deps_docs"]["source"])
    block = re.search(r"dependencies\s*=\s*\[(.*?)\]", py, re.S)
    names = [re.split(r"[\[<>=!~ ;]", d)[0].lower()
             for d in re.findall(r'"([^"]+)"', block.group(1) if block else "")]
    for doc in cfg["deps_docs"]["in"]:
        text = read(doc).lower()
        for n in names:
            if n not in text:
                errors.append(f"[deps] {doc}: 패키지 {n} 설명 없음")


# 5. 금지어 ---------------------------------------------------------------
def check_forbidden(files: list[str], cfg: dict) -> None:
    for rule in cfg["forbidden"]:
        for f in files:
            if match_any(f, rule["in"]) and f.endswith((".md", ".json", ".yml", ".yaml", ".py")) \
                    and not f.startswith(".claude/skills/doc-sync/") and not match_any(f, rule.get("skip", [])):
                for i, line in enumerate(read(f).splitlines(), 1):
                    if rule["pattern"] in line:
                        errors.append(f"[forbidden] {f}:{i}: '{rule['pattern']}' — {rule['why']}")


# 6. 변경 연동 (diff 기반) ------------------------------------------------------
def changed_files(base: str) -> set[str]:
    mb = git("merge-base", base, "HEAD")
    changed = set(git("diff", "--name-only", f"{mb[0]}..HEAD")) if mb else set()
    changed |= set(git("diff", "--name-only", "HEAD"))
    changed |= set(git("ls-files", "--others", "--exclude-standard"))
    return changed


def check_coupling(cfg: dict, base: str) -> set[str]:
    changed = changed_files(base)
    for rule in cfg["coupling"]:
        hits = sorted(f for f in changed if match_any(f, rule["when"]))
        if not hits:
            continue
        for doc in rule["review"]:
            if doc not in changed and doc not in hits:
                warns.append(f"[coupling] {', '.join(hits)} 변경 → {doc} 미변경 ({rule['why']})")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(MAP.read_text(encoding="utf-8"))
    files = repo_files()
    check_links(files, cfg)
    check_orphans(files, cfg)
    check_registry(cfg)
    check_mirrors(cfg)
    check_env_docs(cfg)
    check_deps_docs(cfg)
    check_forbidden(files, cfg)
    changed = check_coupling(cfg, args.base)

    print(f"doc-sync: 변경 파일 {len(changed)}개 (base={args.base})")
    for item in historical_unresolved:
        print(f"INFO [historical-link] 의도적 미포함, 링크 미해결: {item}")
    for item in historical_resolved:
        print(f"INFO [historical-link] 해결됨: {item}")
    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    print(f"결과: ERROR {len(errors)}, WARN {len(warns)}, "
          f"의도적 미포함 링크 미해결 {len(historical_unresolved)}, 해결 {len(historical_resolved)}")
    return 1 if errors or (args.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
