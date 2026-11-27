#!/usr/bin/env python3
"""프론트 API 주소를 환경 변수에서 읽어 frontend/runtime-config.mjs를 만든다.

입력: 환경 변수 FRONTEND_API_BASE_URL (예: http://15.164.172.89). 브라우저가 호출할 API origin이다.
출력: frontend/runtime-config.mjs (git 무시). 값이 비어 있으면 파일을 지우고, 프론트는
      neo-config.mjs의 기본값(http://127.0.0.1:8000)을 쓴다.

정적 프론트는 .env를 읽을 수 없으므로 서버 시작 전에 이 스크립트를 실행한다.
값은 브라우저에 공개되므로 http(s) origin만 허용한다(경로·쿼리·계정 정보 금지).

    uv run --env-file .env python scripts/frontend/write_runtime_config.py
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ENV_NAME = "FRONTEND_API_BASE_URL"
OUTPUT = Path(__file__).resolve().parents[2] / "frontend" / "runtime-config.mjs"


def normalize_origin(value: str) -> str:
    """http(s) origin만 받아 끝의 '/'를 뗀 값을 돌려준다. 형식이 틀리면 ValueError."""
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"{ENV_NAME}는 http(s)://호스트[:포트] 형식이어야 합니다")
    if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ValueError(f"{ENV_NAME}에는 경로·쿼리·계정 정보를 넣지 않습니다")
    parts.port  # 잘못된 포트면 ValueError
    return f"{parts.scheme}://{parts.netloc}"


def render(origin: str) -> str:
    return (
        f"// 자동 생성 파일: scripts/frontend/write_runtime_config.py ({ENV_NAME}). 직접 고치지 않는다.\n"
        f"export const API_BASE_URL = {json.dumps(origin)};\n"
    )


def write(value: str | None, output: Path = OUTPUT) -> str | None:
    """값이 있으면 파일을 쓰고 origin을, 없으면 파일을 지우고 None을 돌려준다."""
    if not value or not value.strip():
        output.unlink(missing_ok=True)
        return None
    origin = normalize_origin(value)
    output.write_text(render(origin), encoding="utf-8")
    return origin


def main() -> int:
    try:
        origin = write(os.environ.get(ENV_NAME))
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    if origin is None:
        print(f"{ENV_NAME} 없음: {OUTPUT.name} 삭제, 기본 주소 사용")
    else:
        print(f"{OUTPUT.name} 작성: API_BASE_URL={origin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
