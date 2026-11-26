---
name: fastapi-run
description: Use when checking that a FastAPI service actually runs. Starts/stops uvicorn by PID file; the service injects app path and smoke script.
---

# fastapi-run

FastAPI(ASGI) 서버를 띄우고 끄는 **공통 절차**다. 어떤 앱을 띄울지, 어떤 설정으로 띄울지, 무엇을 확인할지는 서비스가 주입한다(4절).
명령은 저장소 루트에서 실행한다. 로그·PID 파일은 작업용 임시 폴더(`$TMPDIR`)에 둔다.

## 1. 준비

```bash
uv sync
uv run python -c "import fastapi, uvicorn"     # 실패하면 패키지 미설치
```

## 2. 실행·종료

```bash
export APP=<패키지>.main:app PORT=8000 LOG="$TMPDIR/server.log" PIDFILE="$TMPDIR/server.pid"
# 서비스 설정 환경 변수도 여기서 넘긴다 (서비스 규칙 스킬이 정한 값)
bash .claude/skills/fastapi-run/scripts/run_server.sh start
bash .claude/skills/fastapi-run/scripts/run_server.sh status
bash .claude/skills/fastapi-run/scripts/run_server.sh stop
```

- `start`는 `uv run uvicorn $APP`을 백그라운드로 띄우고 PID 파일을 남긴 뒤 `HEALTH_PATH`(기본 `/health`)가 200일 때까지 기다린다(기본 30초). 실패하면 로그 마지막 30줄을 보여 주고 종료 코드 1이다.
- `APP`이 없으면 종료 코드 2, 앱 모듈 파일이 없으면 종료 코드 3과 `[미구현]`이다.
- 포트를 다른 프로세스가 쓰고 있으면 실패한다. `PORT`만 바꾼다. 남의 프로세스를 끄지 않는다.
- 성공·실패와 관계없이 작업이 끝나면 `stop`으로 끄고 `status`로 확인한다. `pkill -f "uvicorn ..."`은 그 문자열이 든 현재 셸까지 죽일 수 있어 쓰지 않는다.
- 흔한 기동 실패: `ModuleNotFoundError` → 저장소 루트가 아닌 곳에서 실행했거나 패키지에 `__init__.py` 없음. 설정 오류 → 로그의 마지막 예외를 보고 서비스 설정 환경 변수를 확인한다.

## 3. 비용이 나가는 호출

외부 유료 API(LLM 등)를 부르는 설정으로 띄우는 일은 발주서에 명시된 경우에만 한다. 횟수 상한과 기본 설정은 서비스 규칙 스킬이 정하고, 실행 횟수를 보고서에 적는다.

## 4. 서비스가 주입하는 것

| 항목 | 방법 |
| --- | --- |
| 앱 경로 | `APP` |
| 기동 확인 경로 | `HEALTH_PATH` |
| 검증용 설정 (비용 없는 백엔드 등) | 환경 변수 |
| smoke 스크립트 | 서비스 규칙 스킬의 `scripts/` |

값은 서비스 규칙 스킬의 "실행 확인" 절에 둔다. 이 스킬은 어떤 서비스가 자기를 쓰는지 알지 않는다.

## 5. 보고 형식

| 항목 | 요청 | 기대 | 실제 | 결과 |
| --- | --- | --- | --- | --- |
| health | `GET /health` | 200 | 200 | PASS |

smoke 스크립트 출력을 그대로 붙이고, 서버를 껐는지(`status` 결과)도 적는다.
