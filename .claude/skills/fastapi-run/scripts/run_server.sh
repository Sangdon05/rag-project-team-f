#!/usr/bin/env bash
# FastAPI 서비스(api/) 실행 래퍼 (fastapi-run 스킬)
#   run_server.sh start   uvicorn을 백그라운드로 띄우고 /health가 응답할 때까지 대기
#   run_server.sh stop    PID 파일의 서버(와 자식 프로세스)만 종료
#   run_server.sh status  실행 여부 확인
# 환경 변수: PORT(기본 8000), LOG, PIDFILE, WAIT_SECONDS(기본 30),
#            ANSWER_BACKEND(기본 mock — 검증 중 LLM 비용이 나가지 않게)
# DB를 쓰지 않으므로 docker는 띄우지 않는다.
set -u

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PORT="${PORT:-8000}"
TMP="${TMPDIR:-/tmp}"
LOG="${LOG:-$TMP/pokedex-api-$PORT.log}"
PIDFILE="${PIDFILE:-$TMP/pokedex-api-$PORT.pid}"
WAIT_SECONDS="${WAIT_SECONDS:-30}"
BASE="http://127.0.0.1:$PORT"
export ANSWER_BACKEND="${ANSWER_BACKEND:-mock}"

is_running() {
  [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

wait_until() { # 설명 명령...
  local what=$1; shift
  for _ in $(seq "$WAIT_SECONDS"); do
    if "$@" >/dev/null 2>&1; then return 0; fi
    is_running || break
    sleep 1
  done
  echo "[실패] $what: ${WAIT_SECONDS}초 안에 준비되지 않음" >&2
  return 1
}

cmd_start() {
  if is_running; then
    echo "이미 실행 중입니다 (PID $(cat "$PIDFILE"), $BASE)"
    return 0
  fi
  if curl -s -o /dev/null "$BASE/"; then
    echo "[실패] 포트 $PORT를 다른 프로세스가 쓰고 있습니다. PORT를 바꾸세요." >&2
    exit 1
  fi
  if [ ! -f "$ROOT/api/main.py" ]; then
    echo "[미구현] api/main.py가 없습니다. 실행할 서비스가 아직 없습니다." >&2
    exit 3
  fi
  cd "$ROOT" || exit 1
  nohup uv run uvicorn api.main:app --port "$PORT" > "$LOG" 2>&1 &
  echo $! > "$PIDFILE"
  if wait_until "서버 기동" curl -sf "$BASE/health"; then
    echo "서버 실행 중: $BASE (PID $(cat "$PIDFILE"), ANSWER_BACKEND=$ANSWER_BACKEND, 로그 $LOG)"
  else
    echo "--- 로그 마지막 30줄 ($LOG) ---" >&2
    tail -30 "$LOG" >&2
    cmd_stop >/dev/null
    exit 1
  fi
}

cmd_stop() {
  if ! [ -f "$PIDFILE" ]; then
    echo "PID 파일이 없습니다 ($PIDFILE). 실행 중인 서버가 없습니다."
    return 0
  fi
  local pid; pid="$(cat "$PIDFILE")"
  # uv run → python(uvicorn) 자식까지 끈다. pkill -f는 이 명령을 실행한 셸까지 죽일 수 있어 쓰지 않는다.
  pkill -TERM -P "$pid" 2>/dev/null
  kill -TERM "$pid" 2>/dev/null
  for _ in $(seq 10); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  if kill -0 "$pid" 2>/dev/null; then
    pkill -KILL -P "$pid" 2>/dev/null
    kill -KILL "$pid" 2>/dev/null
  fi
  rm -f "$PIDFILE"
  echo "서버 종료 (PID $pid)"
}

cmd_status() {
  if is_running; then
    echo "실행 중: $BASE (PID $(cat "$PIDFILE"), 로그 $LOG)"
  else
    echo "실행 중이 아님"
    return 1
  fi
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  *) echo "사용법: $0 start|stop|status" >&2; exit 2 ;;
esac
