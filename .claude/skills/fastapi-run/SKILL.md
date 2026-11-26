---
name: fastapi-run
description: Use when checking that api/ actually runs. Starts/stops uvicorn by PID file and runs the smoke script against it.
---

# fastapi-run

`api/` 서버를 띄우고 실제 응답을 확인한다. DB를 쓰지 않으므로 docker는 필요 없다.
명령은 모두 저장소 루트에서 실행한다. 로그·PID 파일은 작업용 임시 폴더(`$TMPDIR`)에 둔다.

## 1. 준비

```bash
uv sync
uv run python -c "import fastapi, uvicorn, api.main"   # 실패하면 미구현 또는 패키지 미설치
```

- 검증은 `ANSWER_BACKEND=mock`으로 한다(스크립트 기본값). LLM 비용이 나가지 않고 키가 없어도 된다.
- `ANSWER_BACKEND=llm` 확인은 발주서에 명시된 경우에만 한다. 호출은 1~2회로 끝내고 보고서에 횟수를 적는다.

## 2. 서버 실행·종료

```bash
export PORT=8000 LOG="$TMPDIR/api.log" PIDFILE="$TMPDIR/api.pid"
export API_CORS_ORIGINS=http://localhost:5173        # CORS를 확인하려면
bash .claude/skills/fastapi-run/scripts/run_server.sh start
bash .claude/skills/fastapi-run/scripts/run_server.sh status
bash .claude/skills/fastapi-run/scripts/run_server.sh stop
```

- `start`는 `uv run uvicorn api.main:app`을 백그라운드로 띄우고 PID 파일을 남긴 뒤 `/health`가 200일 때까지 기다린다(기본 30초). 실패하면 로그 마지막 30줄을 보여 주고 종료 코드 1이다.
- `api/main.py`가 없으면 종료 코드 3과 `[미구현]`을 낸다.
- 포트를 다른 프로세스가 쓰고 있으면 실패한다. `PORT`만 바꾼다. 남의 프로세스를 끄지 않는다.
- 성공·실패와 관계없이 작업이 끝나면 `stop`으로 끈다. `pkill -f "uvicorn ..."`은 그 문자열이 든 현재 셸까지 죽일 수 있어 쓰지 않는다.
- 흔한 기동 실패: `ModuleNotFoundError: api` → 저장소 루트가 아닌 곳에서 실행했거나 `api/__init__.py` 없음. `RuntimeError: 알 수 없는 ANSWER_BACKEND` → 환경 변수 값 확인.

## 3. smoke 검사

```bash
BASE=http://127.0.0.1:$PORT CORS_ORIGIN=http://localhost:5173 \
  bash .claude/skills/fastapi-run/scripts/smoke.sh
```

| 항목 | 기대 |
| --- | --- |
| `GET /health` | 200 |
| `GET /openapi.json` | 200. `/api/v1/chat`이 없으면 chat 항목은 INFO(미구현)로 건너뜀 |
| `POST /api/v1/chat` 정상 질문 | 200, `answer`(문자열), `sources`(목록), `mode`(mock\|llm\|rag) |
| 빈 `messages` | 400 + 공통 에러 형식 |
| 메시지 `MAX_MESSAGES + 1`개 | 400 + 공통 에러 형식 (서버의 `API_MAX_MESSAGES`와 같은 값을 `MAX_MESSAGES`로 넘긴다. 기본 20) |
| JSON이 아닌 본문 | 400 + 공통 에러 형식 |
| 없는 경로 | 404 + 공통 에러 형식 |
| CORS (`CORS_ORIGIN` 지정 시) | 허용 origin은 같은 값이 돌아오고, 다른 origin은 허용 헤더가 없음 |

공통 에러 형식은 `{"success": false, "error_code": "...", "message": "..."}`다(R7). FAIL이 하나라도 있으면 종료 코드 1이다.
smoke가 다루지 않는 엔드포인트는 설계안의 명세대로 `curl`로 직접 확인하고 같은 표 형식으로 적는다.

## 4. 보고 형식

| 항목 | 요청 | 기대 | 실제 | 결과 |
| --- | --- | --- | --- | --- |
| health | `GET /health` | 200 | 200 | PASS |

스크립트 출력은 그대로 붙이고, 서버를 껐는지(`status` 결과)도 적는다.
