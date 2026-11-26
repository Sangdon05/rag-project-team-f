#!/usr/bin/env python3
"""PR 전 보안 점검 (security-check 스킬).

사용:
    uv run python .claude/skills/security-check/scripts/check_security.py [--base origin/main] [--strict]

검사 대상
- 인덱스와 작업 트리: 각각의 파일 내용 독립 검사
- 브랜치 기록: base..HEAD 커밋에서 추가된 줄·파일 (지운 비밀도 push되면 남는다)
- 변경분: base 이후 추가된 줄 (코드 패턴)

ERROR: 비밀 노출, 커밋 금지 파일, .gitignore 누락. 반드시 고친다.
WARN : 위험할 수 있는 코드·설정. 고치거나 PR 본문에 사유를 남긴다.
--strict 는 WARN도 실패로 처리한다.

비밀 값과 Git 오류 출력은 표시하지 않는다.
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


class ScanFailure(Exception):
    pass


def git_bytes(*args: str, no_match_ok: bool = False) -> bytes:
    out = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=ROOT, capture_output=True)
    if out.returncode != 0 and not (no_match_ok and out.returncode == 1):
        raise ScanFailure("Git 명령 실패")
    return out.stdout


def git(*args: str, no_match_ok: bool = False) -> list[str]:
    # Git의 레코드 구분은 LF뿐이다. U+2028 등은 diff 내용으로 보존한다.
    text = git_bytes(*args, no_match_ok=no_match_ok).decode("utf-8", errors="replace")
    return text.removesuffix("\n").split("\n") if text else []


def git_paths(*args: str) -> list[str]:
    raw = git_bytes(*args)
    if not raw:
        return []
    if not raw.endswith(b"\0"):
        raise ScanFailure("Git 경로 형식 오류")
    try:
        paths = raw.decode("utf-8").split("\0")[:-1]
    except UnicodeDecodeError:
        raise ScanFailure("UTF-8이 아닌 Git 경로") from None
    # 인용되는 diff 헤더를 잘못 해석하지 않도록 지원하지 않는 이름은 실패 처리한다.
    for path in paths:
        validate_path(path)
    return paths


def validate_path(path: str) -> None:
    if (not path or path.startswith("/") or re.match(r"^[A-Za-z]:", path)
            or any(part in ("", ".", "..") for part in path.split("/"))
            or any(c.isspace() or c in '\\"' or ord(c) < 32 or ord(c) == 127 for c in path)):
        raise ScanFailure("지원하지 않는 Git 경로")


def git_files(*args: str) -> list[str]:
    return git_paths("ls-files", "-z", *args)


def allowed(line: str, marker: str) -> bool:
    return marker in line and bool(line.split(marker, 1)[1].strip())


def match_any(path: str, globs: list[str]) -> bool:
    return any(fnmatch(path, g) for g in globs)


def mask(value: str) -> str:
    return "***"


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
    files = set(git_files()) | set(git_files("--others", "--exclude-standard"))
    return sorted(f for f in files if f and (ROOT / f).is_file())


def index_blobs() -> dict[str, bytes]:
    """Read and validate every stage-0 index blob, independently of the tree."""
    raw = git_bytes("ls-files", "--stage", "-z")
    if raw and not raw.endswith(b"\0"):
        raise ScanFailure("인덱스 형식 오류")
    blobs = {}
    for record in raw.split(b"\0")[:-1]:
        try:
            meta, path_bytes = record.split(b"\t", 1)
            mode, oid, stage = meta.decode("ascii").split(" ")
            path = path_bytes.decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise ScanFailure("인덱스 형식 오류") from None
        validate_path(path)
        if (mode not in ("100644", "100755", "120000") or stage != "0"
                or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid) or path in blobs):
            raise ScanFailure("지원하지 않는 인덱스 항목")
        blobs[path] = git_bytes("cat-file", "blob", oid)
    return blobs


def text_blob(data: bytes) -> str | None:
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def merge_base(base: str) -> str:
    mb = git("merge-base", "--", base, "HEAD")
    if len(mb) != 1 or not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", mb[0]):
        raise ScanFailure("merge-base 확인 실패")
    return mb[0]


def added_lines(diff: list[str]) -> list[tuple[str, int, str]]:
    """unified diff(-U0) → [(path, new_lineno, text)]"""
    out, path, ln, in_hunk = [], None, 0, False
    for line in diff:
        if line.startswith("diff --git "):
            path, in_hunk = None, False
        elif not in_hunk and line.startswith("+++ "):
            if line == "+++ /dev/null":
                path = None
            elif line.startswith("+++ b/"):
                path = line[6:]
            else:
                raise ScanFailure("diff 경로 형식 오류")
        elif line.startswith("@@ "):
            m = re.search(r"\+(\d+)", line)
            if not m:
                raise ScanFailure("diff 형식 오류")
            ln, in_hunk = int(m.group(1)), True
        elif in_hunk and line.startswith("+"):
            if path is None:
                raise ScanFailure("diff 경로 누락")
            out.append((path, ln, line[1:]))
            ln += 1
        elif in_hunk and line.startswith(" "):
            ln += 1
    return out


def history_changes(mb: str) -> tuple[list[tuple[str, str, int, str]], set[str]]:
    lines, paths = [], set()
    for record in git("rev-list", "--parents", f"{mb}..HEAD", "--"):
        commit, *parents = record.split()
        if not parents:
            raise ScanFailure("부모 없는 커밋")
        for parent in parents:
            git_paths("diff", "--name-only", "--no-renames", "-z", parent, commit, "--")
            paths.update(git_paths("diff", "--name-only", "--diff-filter=A", "--no-renames", "-z", parent, commit, "--"))
            diff = git("diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames",
                       "--src-prefix=a/", "--dst-prefix=b/", parent, commit, "--")
            lines.extend((commit, path, ln, text) for path, ln, text in added_lines(diff))
    return lines, paths


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
        for i, line in enumerate(text.split("\n"), 1):
            for rid, val, level in find_secrets(line, rules):
                if level == "WARN" and allowed(line, marker):
                    continue
                found.add((rid, val))
                report(level, f"[secret:{rid}] {f}:{i}: {mask(val)}")
    return found


def check_secrets_index(blobs: dict[str, bytes], rules: dict) -> set[tuple[str, str]]:
    found = set()
    for path, data in blobs.items():
        text = text_blob(data)
        if text is None:
            continue
        for ln, line in enumerate(text.split("\n"), 1):
            for rid, val, level in find_secrets(line, rules):
                if level == "WARN" and allowed(line, rules["allow_marker"]):
                    continue
                found.add((rid, val))
                report(level, f"[secret:{rid}] 인덱스 {path}:{ln}: {mask(val)}")
    return found


def check_secrets_history(lines: list[tuple[str, str, int, str]], rules: dict) -> None:
    seen = set()
    for commit, path, _, text in lines:
        for rid, val, level in find_secrets(text, rules):
            if level != "ERROR" or (rid, val) in seen:
                continue
            seen.add((rid, val))
            errors.append(f"[secret:{rid}] 브랜치 기록 {path} (커밋 {commit[:12]}): "
                          f"{mask(val)} — push되면 기록에 남는다. 키를 폐기하고 기록을 다시 쓴다")


# 2. 커밋 금지 파일 ------------------------------------------------------------
def forbidden(path: str, rules: dict) -> str | None:
    for r in rules["forbidden_paths"]:
        if fnmatch(path, r["glob"]) or fnmatch(Path(path).name, r["glob"]):
            if path not in r.get("except", []):
                return r["why"]
    return None


def check_paths(files: list[str], historical_paths: set[str], rules: dict) -> None:
    for f in files:
        why = forbidden(f, rules)
        if why:
            errors.append(f"[file] {f}: 커밋 금지 ({why})")
    current = set(files)
    for f in sorted(historical_paths):
        if f not in current and (why := forbidden(f, rules)):
            errors.append(f"[file] 브랜치 기록 {f}: 커밋된 적 있음 ({why}) — 기록을 다시 쓴다")


def check_gitignore(rules: dict) -> None:
    for probe in rules["gitignore_probes"]:
        out = git("check-ignore", "-v", "--no-index", "--", probe["path"], no_match_ok=True)
        src = out[0].split(":", 1)[0] if out else ""
        # 개인용 .git/info/exclude, 전역 excludes는 팀원에게 적용되지 않으므로 .gitignore만 인정
        ignored = bool(out) and src.endswith(".gitignore") and not out[0].split("\t")[0].split(":")[-1].startswith("!")
        if probe["ignored"] and not ignored:
            errors.append(f"[gitignore] {probe['path']}: 저장소 .gitignore에서 무시되지 않음")
        if not probe["ignored"] and ignored:
            errors.append(f"[gitignore] {probe['path']}: 커밋돼야 하는데 무시됨")


# 3. 변경분: 코드·설정·크기·의존성 ------------------------------------------------
def has_db_target(text: str, pattern: str) -> bool:
    for match in re.finditer(pattern, text):
        if not match.group().endswith("://"):
            return True
        authority = re.match(r"[^\s/'\"?#(){}<>]+", text[match.end():])
        if authority and authority.group().rsplit("@", 1)[-1].split(":", 1)[0]:
            return True
    return False


def check_changes(mb: str, rules: dict, blobs: dict[str, bytes]) -> set[str]:
    marker = rules["allow_marker"]
    git_paths("diff", "--name-only", "--no-renames", "-z", mb, "--")
    diff = git("diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames",
               "--src-prefix=a/", "--dst-prefix=b/", mb, "--")
    lines = added_lines(diff)
    git_paths("diff", "--cached", "--name-only", "--no-renames", "-z", mb, "--")
    staged_diff = git("diff", "--cached", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames",
                      "--src-prefix=a/", "--dst-prefix=b/", mb, "--")
    lines.extend(added_lines(staged_diff))
    untracked = git_files("--others", "--exclude-standard")
    for f in untracked:
        text = read_text(f)
        if text is not None:
            lines += [(f, i, t) for i, t in enumerate(text.split("\n"), 1)]
    changed = ({p for p, _, _ in lines} | set(git_paths("diff", "--name-only", "--no-renames", "-z", mb, "--"))
               | set(git_paths("diff", "--cached", "--name-only", "--no-renames", "-z", mb, "--")) | set(untracked))

    for path, ln, text in dict.fromkeys(lines):
        if allowed(text, marker):
            continue
        if match_any(path, rules["code_globs"]) and not match_any(path, rules["code_skip"]):
            for p in rules["code_patterns"]:
                if (has_db_target(text, p["regex"]) if p["id"] == "hardcoded-db" else re.search(p["regex"], text)):
                    warns.append(f"[code:{p['id']}] {path}:{ln}: {p['why']}")
        cc = rules["claude_config"]
        if match_any(path, cc["globs"]):
            for p in cc["patterns"]:
                if re.search(p["regex"], text):
                    warns.append(f"[claude:{p['id']}] {path}:{ln}: {p['why']}")

    limit = rules["max_file_mb"] * 1024 * 1024
    for f in sorted(changed):
        p = ROOT / f
        sizes = [len(blobs[f])] if f in blobs else []
        if p.is_file():
            sizes.append(p.stat().st_size)
        if sizes and max(sizes) > limit:
            warns.append(f"[size] {f}: {max(sizes) // 1024 // 1024}MB > {rules['max_file_mb']}MB "
                         f"— 생성물이면 커밋하지 않고 스크립트로 재생성")
        if f.endswith(".ipynb"):
            versions = ([blobs[f]] if f in blobs else []) + ([p.read_bytes()] if p.is_file() else [])
            for version in versions:
                try:
                    nb = json.loads(version.decode("utf-8"))
                    if any(c.get("outputs") for c in nb.get("cells", [])):
                        warns.append(f"[notebook] {f}: 출력이 남아 있음 (환경 변수·응답 원문 노출 위험) — 출력 지우고 커밋")
                        break
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
    files = tree_files()
    blobs = index_blobs()
    history_lines, historical_paths = history_changes(mb)

    check_secrets_tree(files, rules)
    check_secrets_index(blobs, rules)
    check_secrets_history(history_lines, rules)
    check_paths(sorted(set(files) | set(blobs)), historical_paths, rules)
    check_gitignore(rules)
    changed = check_changes(mb, rules, blobs)

    def safe_print(text: str) -> None:
        # 진단 태그의 'secret:'은 비밀 할당문이 아니다.
        text = text.replace("[secret:", "[s_ecret:")
        for _, value, _ in sorted(find_secrets(text, rules), key=lambda hit: -len(hit[1])):
            text = text.replace(value, mask(value))
        print(text.replace("[s_ecret:", "[secret:"))

    safe_print(f"security-check: 트리 {len(files)}개, 인덱스 {len(blobs)}개, 변경 {len(changed)}개 (base={args.base})")
    for e in errors:
        safe_print("ERROR " + e)
    for w in warns:
        safe_print("WARN  " + w)
    print(f"결과: ERROR {len(errors)}, WARN {len(warns)}")
    return 1 if errors or (args.strict and warns) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ScanFailure, OSError):
        print("ERROR [git] 경로 또는 Git 명령을 확인하지 못해 보안 검사를 중단함", file=sys.stderr)
        sys.exit(1)
