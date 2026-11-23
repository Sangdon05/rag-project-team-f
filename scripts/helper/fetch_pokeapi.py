#!/usr/bin/env python3
"""PokeAPI에서 포켓몬 데이터를 받아 datas/pokeapi/{번호}.json 으로 저장한다.

사용법:
    python3 scripts/helper/fetch_pokeapi.py                 # 1~151 전체
    python3 scripts/helper/fetch_pokeapi.py --start 1 --end 10
    python3 scripts/helper/fetch_pokeapi.py --force         # 이미 받은 파일도 다시 받기

표준 라이브러리만 사용한다 (추가 설치 불필요).
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://pokeapi.co/api/v2/pokemon/{id}"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "datas" / "pokeapi"
RATE_LIMIT_SEC = 0.5  # 호출 간 최소 간격
MAX_RETRIES = 3
TIMEOUT_SEC = 30
USER_AGENT = "rag-project-team-f/1.0 (pokeapi fetcher)"


def fetch_pokemon(pokemon_id: int) -> dict:
    """한 마리 조회. 429/5xx/네트워크 오류는 지수 백오프로 재시도."""
    url = API_URL.format(id=pokemon_id)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 404:
                raise  # 재시도 의미 없음
            if e.code != 429 and e.code < 500:
                raise
            wait = int(e.headers.get("Retry-After", 0) or 0) or 2 ** attempt
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            wait = 2 ** attempt
        print(f"  [{pokemon_id}] 재시도 {attempt}/{MAX_RETRIES} ({last_err}), {wait}s 대기", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"{pokemon_id}번 조회 실패: {last_err}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PokeAPI 포켓몬 데이터 JSON 저장")
    parser.add_argument("--start", type=int, default=1, help="시작 번호 (기본 1)")
    parser.add_argument("--end", type=int, default=151, help="끝 번호, 포함 (기본 151)")
    parser.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ok, skipped, failed = 0, 0, []
    last_call = 0.0

    for pid in range(args.start, args.end + 1):
        out_path = OUTPUT_DIR / f"{pid}.json"
        if out_path.exists() and not args.force:
            skipped += 1
            continue

        # 레이트 제한: 직전 호출로부터 최소 RATE_LIMIT_SEC 간격 유지
        elapsed = time.monotonic() - last_call
        if elapsed < RATE_LIMIT_SEC:
            time.sleep(RATE_LIMIT_SEC - elapsed)
        last_call = time.monotonic()

        try:
            data = fetch_pokemon(pid)
        except Exception as e:  # noqa: BLE001
            print(f"[{pid}] 실패: {e}", file=sys.stderr)
            failed.append(pid)
            continue

        tmp_path = out_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(out_path)  # 원자적 저장 (중단 시 깨진 파일 방지)
        ok += 1
        print(f"[{pid}] {data.get('name')} 저장 -> {out_path.relative_to(PROJECT_ROOT)}")

    print(f"\n완료: 저장 {ok}, 건너뜀 {skipped}, 실패 {len(failed)}")
    if failed:
        print(f"실패 번호: {failed}  (다시 실행하면 실패분만 재시도)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
