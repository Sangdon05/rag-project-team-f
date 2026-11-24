#!/usr/bin/env python3
"""평가셋 해시 잠금.

평가셋(eval/dev.json, eval/test.json)은 사용자만 작성·수정한다.
사용자가 평가셋을 확정하면 lock으로 해시를 기록하고, 평가 실행 전에는 항상 verify로 확인한다.

    # 사용자 전용: 평가셋 확정 (label은 평가셋 파일의 "version" 값을 쓴다)
    uv run python scripts/eval/evalset_lock.py lock --split dev --chunks data/chunks/chunks.jsonl
    uv run python scripts/eval/evalset_lock.py lock --split test --chunks data/chunks/chunks.jsonl

    # 누구나: 실행 전 확인 (불일치 시 exit 1)
    uv run python scripts/eval/evalset_lock.py verify --split dev
    uv run python scripts/eval/evalset_lock.py verify --split test --chunks data/chunks/chunks.jsonl

--chunks: 잠금 시점의 청크 파일 해시도 기록한다. verify 때 청크가 바뀌었으면
근거 매핑(allowed_evidence의 chunk_id)이 낡았을 수 있으므로 실패로 처리한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "eval"
LOCK = EVAL / "LOCK.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_lock() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.exists() else {}


def splits(arg: str) -> list[str]:
    return ["dev", "test"] if arg == "all" else [arg]


def cmd_lock(args) -> int:
    lock = load_lock()
    for s in splits(args.split):
        f = EVAL / f"{s}.json"
        if not f.exists():
            print(f"ERROR {f.relative_to(ROOT)} 없음")
            return 1
        try:
            version = json.loads(f.read_text(encoding="utf-8")).get("version")
        except (json.JSONDecodeError, AttributeError):
            print(f"ERROR {f.relative_to(ROOT)}: JSON 객체가 아니다 (형식: {{\"version\": ..., \"items\": [...]}})")
            return 1
        if not version:
            print(f"ERROR {f.relative_to(ROOT)}: \"version\" 값이 없다. 평가셋 파일에 버전을 적은 뒤 잠근다")
            return 1
        if args.label and args.label != version:
            print(f"ERROR --label {args.label} 이 파일의 version {version} 과 다르다. 평가셋 버전은 파일의 version 하나만 쓴다")
            return 1
        entry = {
            "file": f"eval/{s}.json",
            "sha256": sha256(f),
            "label": version,
            "locked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if args.chunks:
            c = ROOT / args.chunks
            entry["chunks"] = {"file": args.chunks, "sha256": sha256(c)}
        lock[s] = entry
        print(f"locked {entry['file']} {entry['sha256'][:12]} label={version}")
    LOCK.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def cmd_verify(args) -> int:
    lock, ok = load_lock(), True
    for s in splits(args.split):
        f = EVAL / f"{s}.json"
        entry = lock.get(s)
        if not entry:
            print(f"ERROR {s}: 잠금 기록 없음. 사용자가 lock을 실행해야 한다")
            ok = False
            continue
        if not f.exists():
            print(f"ERROR {entry['file']} 없음")
            ok = False
            continue
        cur = sha256(f)
        if cur != entry["sha256"]:
            print(f"ERROR {entry['file']} 해시 불일치: 잠금 {entry['sha256'][:12]} / 현재 {cur[:12]}. "
                  "평가셋이 잠금 이후 바뀌었다. 사용자가 확인 후 다시 lock해야 한다")
            ok = False
            continue
        if args.chunks:
            c = ROOT / args.chunks
            locked = entry.get("chunks")
            if not locked:
                print(f"ERROR {s}: 청크 해시가 잠금에 없음. 근거 매핑 기준을 알 수 없다")
                ok = False
                continue
            if not c.exists() or sha256(c) != locked["sha256"]:
                print(f"ERROR {s}: 청크가 잠금 이후 바뀌었다 ({args.chunks}). "
                      "근거 매핑이 낡았을 수 있으므로 사용자가 매핑 확인 후 다시 lock해야 한다")
                ok = False
                continue
        print(f"ok {entry['file']} {cur[:12]} label={entry['label']}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("lock", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--split", choices=["dev", "test", "all"], required=True)
        p.add_argument("--chunks", help="청크 파일 경로 (근거 매핑 기준)")
        if name == "lock":
            p.add_argument("--label", help="생략 가능. 주면 평가셋 파일의 version과 같아야 한다")
    args = ap.parse_args()
    return cmd_lock(args) if args.cmd == "lock" else cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
