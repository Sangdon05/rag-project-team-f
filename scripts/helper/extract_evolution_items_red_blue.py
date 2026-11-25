#!/usr/bin/env python3
"""Red·Blue 아이템 진화에 쓰이는 돌의 한국어·영어 이름을 PokeAPI /item에서 보강한다.

입력 data/processed/evolutions_red_blue.json의 use-item 진화 관계에서 아이템 목록과
사용처를 자동으로 뽑고, 아이템마다 https://pokeapi.co/api/v2/item/{name}/ 을 조회해
data/processed/evolution_items_red_blue.json 을 만든다 (HASHES 대상 아님).

사용법:
    uv run python scripts/helper/extract_evolution_items_red_blue.py
    uv run python scripts/helper/extract_evolution_items_red_blue.py --output 다른/경로.json

- 표준 라이브러리만 사용한다. 호출 간격 0.5초 이상, 429/5xx/네트워크 오류는 지수 백오프로 재시도한다.
- 출력은 결정적이다. 실행 시각 같은 가변 값을 넣지 않고 정렬·키 순서를 고정한다.
- 원본 API 응답은 저장하지 않는다. 라이브 API 값이 바뀌면 다시 실행한 결과도 달라질 수 있다.
- 한국어 이름은 API 값을 그대로 쓴다 (띄어쓰기 등 변형 없음). 없으면 null.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "evolutions_red_blue.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "evolution_items_red_blue.json"
API_URL = "https://pokeapi.co/api/v2/item/{name}/"
RATE_LIMIT_SEC = 0.5  # 호출 간 최소 간격
MAX_RETRIES = 4
TIMEOUT_SEC = 30
USER_AGENT = "rag-project-team-f/1.0 (pokeapi fetcher)"
USE_ITEM_TRIGGER = "use-item"


def collect_item_usages(evolutions: dict) -> dict:
    """evolves_to의 use-item 관계를 아이템별 사용처 목록으로 모은다.

    반환: {item_name: [{from_id, from_name, to_id, to_name, evolution_pointer}, ...]}
    같은 관계가 evolves_from 쪽에도 있으므로 evolves_to만 기준으로 하고 중복을 거부한다.
    """
    usages: dict = {}
    seen = set()
    for rec_index, record in enumerate(evolutions["records"]):
        for edge_index, edge in enumerate(record["evolves_to"]):
            if edge.get("trigger") != USE_ITEM_TRIGGER:
                continue
            item = edge.get("item")
            if not isinstance(item, str) or not item:
                raise ValueError(f"use-item 관계에 item 식별자가 없음: {edge.get('from_id')}->{edge.get('to_id')}")
            if edge["from_id"] != record["id"]:
                raise ValueError(f"evolves_to의 from_id가 레코드 id와 다름: /records/{rec_index}")
            key = (edge["from_id"], edge["to_id"])
            if key in seen:
                raise ValueError(f"중복 진화 관계: {key}")
            seen.add(key)
            usages.setdefault(item, []).append({
                "from_id": edge["from_id"],
                "from_name": edge["from_name"],
                "to_id": edge["to_id"],
                "to_name": edge["to_name"],
                "evolution_pointer": f"/records/{rec_index}/evolves_to/{edge_index}",
            })
    for item_usages in usages.values():
        item_usages.sort(key=lambda u: (u["from_id"], u["to_id"]))
    return usages


def fetch_json(url: str) -> dict:
    """URL 하나 조회. 429/5xx/네트워크 오류는 지수 백오프로 재시도 (fetch_pokeapi.py와 같은 정책)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code != 429 and e.code < 500:
                raise  # 404 등은 재시도 의미 없음
            wait = int(e.headers.get("Retry-After", 0) or 0) or 2 ** attempt
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            wait = 2 ** attempt
        print(f"  [{url}] 재시도 {attempt}/{MAX_RETRIES} ({last_err}), {wait}s 대기", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError(f"조회 실패: {url}: {last_err}")


def localized_name(names: list, language: str):
    """names에서 해당 언어 이름을 그대로 돌려준다. 없으면 None, 서로 다른 값이 여럿이면 오류."""
    values = {n["name"] for n in names if n.get("language", {}).get("name") == language}
    if len(values) > 1:
        raise ValueError(f"{language} 이름이 여러 개: {sorted(values)}")
    return values.pop() if values else None


def build_item_record(item_name: str, payload: dict, usages: list, source_url: str) -> dict:
    if payload.get("name") != item_name:
        raise ValueError(f"응답 name 불일치: 요청 {item_name}, 응답 {payload.get('name')}")
    name_en = localized_name(payload.get("names", []), "en")
    if not name_en:
        raise ValueError(f"{item_name}: 영문 이름 없음")
    return {
        "id": payload["id"],
        "name": item_name,
        "name_en": name_en,
        "name_ko": localized_name(payload.get("names", []), "ko"),
        "source_url": source_url,
        "used_in": usages,
    }


def build_output(evolutions: dict, items: list) -> dict:
    return {
        "scope": evolutions["scope"],
        "version_group": evolutions["version_group"],
        "description": "evolutions_red_blue.json의 use-item 진화에 쓰이는 아이템의 PokeAPI id와 영어·한국어 이름, 사용처.",
        "input": "data/processed/evolutions_red_blue.json",
        "selection": "records[].evolves_to[] 중 trigger가 use-item인 관계의 item",
        "source": "https://pokeapi.co/api/v2/item/{name}/",
        "name_note": "name_en·name_ko는 PokeAPI names의 en·ko 값 그대로다. 현재 API 이름이며 영문 원판의 역사적 번역이 아니다. 값이 없으면 null.",
        "snapshot_note": "원본 API 응답은 보존하지 않는다. 같은 입력이라도 API 값이 바뀌면 재생성 결과가 달라질 수 있다.",
        "item_count": len(items),
        "usage_count": sum(len(i["used_in"]) for i in items),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="진화 아이템 이름 보강 (PokeAPI /item)")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="출력 JSON 경로")
    args = parser.parse_args()

    evolutions = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    usages = collect_item_usages(evolutions)
    if not usages:
        print("use-item 진화 관계가 없음", file=sys.stderr)
        return 1

    items = []
    last_call = 0.0
    for item_name in sorted(usages):
        elapsed = time.monotonic() - last_call
        if elapsed < RATE_LIMIT_SEC:
            time.sleep(RATE_LIMIT_SEC - elapsed)
        last_call = time.monotonic()
        url = API_URL.format(name=item_name)
        payload = fetch_json(url)
        items.append(build_item_record(item_name, payload, usages[item_name], url))
        print(f"[{item_name}] id={payload['id']} ko={items[-1]['name_ko']!r}")
    items.sort(key=lambda i: (i["id"], i["name"]))

    text = json.dumps(build_output(evolutions, items), ensure_ascii=False, indent=2) + "\n"
    out_path = args.output.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_name(out_path.name + ".tmp")
    tmp_path.write_bytes(text.encode("utf-8"))  # 줄바꿈 LF 고정
    tmp_path.replace(out_path)  # 원자적 저장
    print(f"저장: {out_path} (아이템 {len(items)}, 사용처 {sum(len(i['used_in']) for i in items)})")
    missing_ko = [i["name"] for i in items if i["name_ko"] is None]
    if missing_ko:
        print(f"경고: 한국어 이름 없음 {missing_ko}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
