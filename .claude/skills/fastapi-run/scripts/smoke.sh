#!/usr/bin/env bash
# FastAPI 서비스(api/) smoke 검사 (fastapi-run 스킬)
#   BASE=http://127.0.0.1:8000 bash .claude/skills/fastapi-run/scripts/smoke.sh
# 환경 변수:
#   BASE          서버 주소 (기본 http://127.0.0.1:8000)
#   MAX_MESSAGES  서버의 API_MAX_MESSAGES 값 (기본 20). 초과 요청이 400인지 본다
#   CORS_ORIGIN   허용됐어야 하는 프론트 origin. 지정하면 preflight를 확인한다
# 서버는 ANSWER_BACKEND=mock으로 떠 있어야 한다 (LLM 호출·비용 없음).
# 결과: 항목마다 PASS / FAIL / INFO. FAIL이 하나라도 있으면 종료 코드 1.
set -u

BASE="${BASE:-http://127.0.0.1:8000}"
MAX_MESSAGES="${MAX_MESSAGES:-20}"
CORS_ORIGIN="${CORS_ORIGIN:-}"
CHAT="/api/v1/chat"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/api-smoke.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
FAILS=0

pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; FAILS=$((FAILS + 1)); }
info() { echo "INFO  $1"; }

# req METHOD PATH [BODY] → $TMP/body, 상태 코드를 stdout으로
req() {
  if [ $# -ge 3 ]; then
    curl -s -o "$TMP/body" -w '%{http_code}' -X "$1" -H 'Content-Type: application/json' --data "$3" "$BASE$2"
  else
    curl -s -o "$TMP/body" -w '%{http_code}' -X "$1" "$BASE$2"
  fi
}

# 공통 에러 형식 {"success": false, "error_code": str, "message": str}
error_shape_ok() {
  python3 - "$TMP/body" <<'PY'
import json, sys
try:
    b = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
ok = b.get("success") is False and isinstance(b.get("error_code"), str) and b["error_code"] and isinstance(b.get("message"), str)
sys.exit(0 if ok else 1)
PY
}

check_error() { # 설명 기대코드 실제코드
  if [ "$3" = "$2" ] && error_shape_ok; then
    pass "$1 → $3 $(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["error_code"])' "$TMP/body")"
  else
    fail "$1 → 기대 $2 + 공통 에러 형식, 실제 $3 $(head -c 200 "$TMP/body")"
  fi
}

# 1. health
code=$(req GET /health)
[ "$code" = "200" ] && pass "GET /health → 200" || fail "GET /health → 기대 200, 실제 $code"

# 2. 문서
code=$(req GET /openapi.json)
if [ "$code" != "200" ]; then
  fail "GET /openapi.json → 기대 200, 실제 $code"
  echo; echo "결과: FAIL $FAILS"; exit 1
fi
pass "GET /openapi.json → 200"
if ! python3 -c 'import json,sys; sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1]))["paths"] else 1)' "$TMP/body" "$CHAT"; then
  info "$CHAT 미구현 (openapi.json에 경로 없음). chat 검사를 건너뜀"
else
  # 3. 정상 질문
  code=$(req POST "$CHAT" '{"messages":[{"role":"user","content":"What type is Pikachu?"}]}')
  if [ "$code" = "200" ] && python3 - "$TMP/body" <<'PY'
import json, sys
b = json.load(open(sys.argv[1]))
ok = isinstance(b.get("answer"), str) and b["answer"] and isinstance(b.get("sources"), list) and b.get("mode") in {"mock", "llm", "rag"}
sys.exit(0 if ok else 1)
PY
  then
    pass "POST $CHAT 정상 질문 → 200 (mode=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["mode"])' "$TMP/body"))"
  else
    fail "POST $CHAT 정상 질문 → 기대 200 + answer/sources/mode, 실제 $code $(head -c 200 "$TMP/body")"
  fi

  # 4. 빈 대화
  code=$(req POST "$CHAT" '{"messages":[]}')
  check_error "POST $CHAT 빈 messages" 400 "$code"

  # 5. 메시지 수 초과
  many=$(python3 -c 'import json,sys;n=int(sys.argv[1])+1;print(json.dumps({"messages":[{"role":"user" if i%2==0 else "assistant","content":"hi"} for i in range(n-1)]+[{"role":"user","content":"hi"}]}))' "$MAX_MESSAGES")
  code=$(req POST "$CHAT" "$many")
  check_error "POST $CHAT 메시지 $((MAX_MESSAGES + 1))개" 400 "$code"

  # 6. 형식 오류 (JSON 아님)
  code=$(req POST "$CHAT" 'not-json')
  check_error "POST $CHAT 잘못된 JSON" 400 "$code"
fi

# 7. 없는 경로
code=$(req GET /no-such-path)
check_error "GET /no-such-path" 404 "$code"

# 8. CORS
if [ -n "$CORS_ORIGIN" ]; then
  allow=$(curl -s -o /dev/null -D - -X OPTIONS -H "Origin: $CORS_ORIGIN" -H 'Access-Control-Request-Method: POST' "$BASE$CHAT" | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')
  [ "$allow" = "$CORS_ORIGIN" ] && pass "CORS preflight 허용 origin → $allow" || fail "CORS preflight 허용 origin → 기대 $CORS_ORIGIN, 실제 '${allow}'"
  deny=$(curl -s -o /dev/null -D - -X OPTIONS -H "Origin: https://evil.example" -H 'Access-Control-Request-Method: POST' "$BASE$CHAT" | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')
  [ -z "$deny" ] && pass "CORS preflight 다른 origin → 허용 헤더 없음" || fail "CORS preflight 다른 origin → '${deny}' 허용됨"
else
  info "CORS_ORIGIN 미지정. CORS 검사를 건너뜀"
fi

echo
if [ "$FAILS" -gt 0 ]; then
  echo "결과: FAIL $FAILS"
  exit 1
fi
echo "결과: 모두 PASS"
