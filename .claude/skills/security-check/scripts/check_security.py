#!/usr/bin/env python3
"""PR 전 보안 점검 (security-check 스킬).

사용:
    uv run python .claude/skills/security-check/scripts/check_security.py [--base origin/main] [--strict]

검사 대상
- 작업 트리: 커밋될 수 있는 파일 전체 (tracked + ignore되지 않은 untracked)
- 브랜치 기록: base..HEAD 커밋에서 추가된 줄·파일 (지운 비밀도 push되면 남는다)
- 변경분: base 이후 추가된 줄 (코드 패턴)

ERROR: 비밀 노출, 커밋 금지 파일, .gitignore 누락. 반드시 고친다.
WARN : 위험할 수 있는 코드·설정. 고치거나 PR 본문에 사유를 남긴다.
--strict 는 WARN도 실패로 처리한다.

비밀 값은 출력하지 않는다 (앞 4자만 표시).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RULES = Path(__file__).resolve().parents[1] / "rules.json"

errors: list[str] = []
warns: list[str] = []


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.splitlines()


def match_any(path: str, globs: list[str]) -> bool:
    return any(fnmatch(path, g) for g in globs)


def mask(value: str) -> str:
    return value[:4] + "***" if len(value) > 4 else "***"


def read_text(rel: str) -> str | None:
    p = ROOT / rel
    if not p.is_file():
        return None
    data = p.read_bytes()
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


# 대상 수집 ------------------------------------------------------------------
def tree_files() -> list[str]:
    files = set(git("ls-files")) | set(git("ls-files", "--others", "--exclude-standard"))
    return sorted(f for f in files if f and (ROOT / f).is_file())


def merge_base(base: str) -> str | None:
    mb = git("merge-base", base, "HEAD")
    return mb[0] if mb else None


def added_lines(diff: list[str]) -> list[tuple[str, int, str]]:
    """unified diff(-U0) → [(path, new_lineno, text)]"""
    out, path, ln = [], None, 0
    for line in diff:
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            ln = int(m.group(1)) if m else 0
        elif line.startswith("+") and path:
            out.append((path, ln, line[1:]))
            ln += 1
    return out


# 1. 비밀 ------------------------------------------------------------------
def find_secrets(text: str, rules: dict) -> list[tuple[str, str, str]]:
    """한 줄에서 (rule_id, value, level) 목록"""
    hits = []
    for p in rules["secret_patterns"]:
        for m in re.finditer(p["regex"], text):
            hits.append((p["id"], m.group(0), "ERROR"))
    db = rules["db_url"]
    for m in re.finditer(db["regex"], text):
        pw = m.group(1)
        if pw not in db["allowed_passwords"] and not pw.startswith(("$", "{", "<")):
            hits.append(("db-password", pw, "ERROR"))
    asg = rules["assignment"]
    strong = [v for _, v, _ in hits]
    for m in re.finditer(asg["regex"], text):
        val = m.group(1)
        if any(val in s or s in val for s in strong):
            continue  # 이미 ERROR로 잡힌 값
        if not val.startswith(tuple(asg["ignore_value_prefixes"])) and "(" not in val:
            hits.append(("secret-assignment", val, "WARN"))
    return hits


def report(level: str, msg: str) -> None:
    (errors if level == "ERROR" else warns).append(msg)


def check_secrets_tree(files: list[str], rules: dict) -> set[tuple[str, str]]:
    found = set()
    marker = rules["allow_marker"]
    for f in files:
        text = read_text(f)
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if marker in line:
                continue
            for rid, val, level in find_secrets(line, rules):
                found.add((rid, val))
                report(level, f"[secret:{rid}] {f}:{i}: {mask(val)}")
    return found


def check_secrets_history(mb: str | None, rules: dict, in_tree: set[tuple[str, str]]) -> None:
    if not mb:
        return
    diff = git("log", "-p", "-U0", "--no-color", "--format=", f"{mb}..HEAD")
    marker = rules["allow_marker"]
    seen = set()
    for path, _, text in added_lines(diff):
        if marker in text:
            continue
        for rid, val, level in find_secrets(text, rules):
            if level != "ERROR" or (rid, val) in in_tree or (rid, val) in seen:
                continue
            seen.add((rid, val))
            commits = git("log", "--format=%h", "-S", val, f"{mb}..HEAD")
            errors.append(f"[secret:{rid}] 브랜치 기록 {path} (커밋 {', '.join(commits) or '?'}): "
                          f"{mask(val)} — 트리에서는 지워졌지만 push되면 남는다. 키를 폐기하고 기록을 다시 쓴다")


# 2. 커밋 금지 파일 ------------------------------------------------------------
def forbidden(path: str, rules: dict) -> str | None:
    for r in rules["forbidden_paths"]:
        if fnmatch(path, r["glob"]) or fnmatch(Path(path).name, r["glob"]):
            if path not in r.get("except", []):
                return r["why"]
    return None


def check_paths(files: list[str], mb: str | None, rules: dict) -> None:
    for f in files:
        why = forbidden(f, rules)
        if why:
            errors.append(f"[file] {f}: 커밋 금지 ({why})")
    if mb:
        current = set(files)
        for f in set(git("log", "--format=", "--name-only", "--diff-filter=A", f"{mb}..HEAD")):
            if f and f not in current and (why := forbidden(f, rules)):
                errors.append(f"[file] 브랜치 기록 {f}: 커밋된 적 있음 ({why}) — 기록을 다시 쓴다")


def check_gitignore(rules: dict) -> None:
    for probe in rules["gitignore_probes"]:
        out = git("check-ignore", "-v", "--no-index", probe["path"])
        src = out[0].split(":", 1)[0] if out else ""
        # 개인용 .git/info/exclude, 전역 excludes는 팀원에게 적용되지 않으므로 .gitignore만 인정
        ignored = bool(out) and src.endswith(".gitignore") and not out[0].split("\t")[0].split(":")[-1].startswith("!")
        if probe["ignored"] and not ignored:
            errors.append(f"[gitignore] {probe['path']}: 저장소 .gitignore에서 무시되지 않음")
        if not probe["ignored"] and ignored:
            errors.append(f"[gitignore] {probe['path']}: 커밋돼야 하는데 무시됨")


# 3. 변경분: 코드·설정·크기·의존성 ------------------------------------------------
def check_changes(mb: str | None, rules: dict) -> set[str]:
    marker = rules["allow_marker"]
    diff = git("diff", "-U0", "--no-color", mb) if mb else []
    lines = added_lines(diff)
    untracked = git("ls-files", "--others", "--exclude-standard")
    for f in untracked:
        text = read_text(f)
        if text is not None:
            lines += [(f, i, t) for i, t in enumerate(text.splitlines(), 1)]
    changed = {p for p, _, _ in lines} | set(git("diff", "--name-only", mb) if mb else []) | set(untracked)

    for path, ln, text in lines:
        if marker in text:
            continue
        if match_any(path, rules["code_globs"]) and not match_any(path, rules["code_skip"]):
            for p in rules["code_patterns"]:
                if re.search(p["regex"], text):
                    warns.append(f"[code:{p['id']}] {path}:{ln}: {p['why']}")
        cc = rules["claude_config"]
        if match_any(path, cc["globs"]):
            for p in cc["patterns"]:
                if re.search(p["regex"], text):
                    warns.append(f"[claude:{p['id']}] {path}:{ln}: {p['why']}")

    limit = rules["max_file_mb"] * 1024 * 1024
    for f in sorted(changed):
        p = ROOT / f
        if p.is_file() and p.stat().st_size > limit:
            warns.append(f"[size] {f}: {p.stat().st_size // 1024 // 1024}MB > {rules['max_file_mb']}MB "
                         f"— 생성물이면 커밋하지 않고 스크립트로 재생성")
        if f.endswith(".ipynb") and p.is_file():
            try:
                nb = json.loads(p.read_text(encoding="utf-8"))
                if any(c.get("outputs") for c in nb.get("cells", [])):
                    warns.append(f"[notebook] {f}: 출력이 남아 있음 (환경 변수·응답 원문 노출 위험) — 출력 지우고 커밋")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

    if "pyproject.toml" in changed and "uv.lock" not in changed:
        warns.append("[deps] pyproject.toml만 바뀌고 uv.lock은 그대로 — uv add/remove로 관리한다")
    for f in changed:
        if re.search(r"(^|/)requirements[^/]*\.txt$", f):
            warns.append(f"[deps] {f}: 패키지는 uv(pyproject.toml, uv.lock)로만 관리한다")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    rules = json.loads(RULES.read_text(encoding="utf-8"))
    mb = merge_base(args.base)
    if not mb:
        warns.append(f"[base] {args.base}와 merge-base 없음 — 브랜치 기록·변경분 검사 생략 (git fetch 확인)")
    files = tree_files()

    in_tree = check_secrets_tree(files, rules)
    check_secrets_history(mb, rules, in_tree)
    check_paths(files, mb, rules)
    check_gitignore(rules)
    changed = check_changes(mb, rules)

    print(f"security-check: 트리 {len(files)}개, 변경 {len(changed)}개 (base={args.base})")
    for e in errors:
        print("ERROR", e)
    for w in warns:
        print("WARN ", w)
    print(f"결과: ERROR {len(errors)}, WARN {len(warns)}")
    return 1 if errors or (args.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
