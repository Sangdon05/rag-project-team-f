#!/usr/bin/env bash
# api/ 서비스 smoke 검사 (api-invariants 스킬). 서버 기동·종료는 공통 fastapi-run 스킬로 한다.
#   BASE=http://127.0.0.1:8000 bash .claude/skills/api-invariants/scripts/smoke.sh
# 환경 변수:
#   BASE          서버 주소 (기본 http://127.0.0.1:8000)
#   MAX_MESSAGES  서버의 API_MAX_MESSAGES 값 (기본 20). 초과 요청이 400인지 본다
#   CORS_ORIGIN   허용됐어야 하는 프론트 origin. 지정하면 preflight를 확인한다
#   DOC_ID        서버의 API_DOCUMENTS_DIR에 있는 문서 id. 지정하면 documents 정상 조회를 확인한다
# 서버는 ANSWER_BACKEND=mock으로 떠 있어야 한다 (LLM 호출·비용 없음).
# 성공 응답은 {"success": true, "data": {...}}, 에러 응답은 {"success": false, "error_code", "message"}다 (R7).
# 결과: 항목마다 PASS / FAIL / INFO. FAIL이 하나라도 있으면 종료 코드 1.
set -u

BASE="${BASE:-http://127.0.0.1:8000}"
MAX_MESSAGES="${MAX_MESSAGES:-20}"
CORS_ORIGIN="${CORS_ORIGIN:-}"
DOC_ID="${DOC_ID:-}"
CHAT="/api/v1/chat"
SUGGESTION="/api/v1/suggestion"
DOCUMENTS="/api/v1/documents"
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

# 공통 에러 형식 {"success": false, "error_code": str, "message": str}. 둘째 인자가 있으면 error_code도 비교한다
error_shape_ok() {
  python3 - "$TMP/body" "${1:-}" <<'PY'
import json, sys
try:
    b = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
ok = b.get("success") is False and isinstance(b.get("error_code"), str) and b["error_code"] and isinstance(b.get("message"), str)
if ok and sys.argv[2]:
    ok = b["error_code"] == sys.argv[2]
sys.exit(0 if ok else 1)
PY
}

check_error() { # 설명 기대코드 실제코드 [기대error_code]
  if [ "$3" = "$2" ] && error_shape_ok "${4:-}"; then
    pass "$1 → $3 $(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["error_code"])' "$TMP/body")"
  else
    fail "$1 → 기대 $2 ${4:-} + 공통 에러 형식, 실제 $3 $(head -c 200 "$TMP/body")"
  fi
}

# data_ok 파이썬식 — 성공 형식이고 식이 참인지 (d = data, env = 환경 변수). 식은 이 스크립트의 고정 문자열만 쓴다
data_ok() {
  python3 - "$TMP/body" "$1" <<'PY'
import json, os, sys
try:
    b = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
d = b.get("data")
ok = b.get("success") is True and isinstance(d, dict) and eval(sys.argv[2], {}, {"d": d, "env": os.environ})
sys.exit(0 if ok else 1)
PY
}

# 1. health
code=$(req GET /health)
if [ "$code" = "200" ] && data_ok 'True'; then
  pass "GET /health → 200"
else
  fail "GET /health → 기대 200 + 성공 형식, 실제 $code $(head -c 200 "$TMP/body")"
fi

# 2. 문서
code=$(req GET /openapi.json)
if [ "$code" != "200" ]; then
  fail "GET /openapi.json → 기대 200, 실제 $code"
  echo; echo "결과: FAIL $FAILS"; exit 1
fi
pass "GET /openapi.json → 200"
cp "$TMP/body" "$TMP/openapi"
has_path() { python3 -c 'import json,sys; sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1]))["paths"] else 1)' "$TMP/openapi" "$1"; }

# 3. chat
if ! has_path "$CHAT"; then
  info "$CHAT 미구현 (openapi.json에 경로 없음). chat 검사를 건너뜀"
else
  code=$(req POST "$CHAT" '{"messages":[{"role":"user","content":"What type is Pikachu?"}]}')
  if [ "$code" = "200" ] && data_ok 'isinstance(d.get("answer"), str) and d["answer"] and isinstance(d.get("sources"), list) and d.get("mode") in {"mock", "llm", "rag"}'; then
    pass "POST $CHAT 정상 질문 → 200 (mode=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["data"]["mode"])' "$TMP/body"))"
  else
    fail "POST $CHAT 정상 질문 → 기대 200 + data.answer/sources/mode, 실제 $code $(head -c 200 "$TMP/body")"
  fi

  code=$(req POST "$CHAT" '{"messages":[]}')
  check_error "POST $CHAT 빈 messages" 400 "$code" VALIDATION_ERROR

  # 교대 순서를 지키면서 MAX_MESSAGES + 1개를 만든다 (개수 초과만으로 400이 나야 한다)
  many=$(python3 -c 'import json,sys
n = int(sys.argv[1]) + 1
if n % 2 == 0:
    n += 1   # 첫·마지막이 user가 되도록 홀수 개
print(json.dumps({"messages": [{"role": "user" if i % 2 == 0 else "assistant", "content": "hi"} for i in range(n)]}))' "$MAX_MESSAGES")
  code=$(req POST "$CHAT" "$many")
  check_error "POST $CHAT 메시지 ${MAX_MESSAGES}개 초과" 400 "$code" VALIDATION_ERROR

  code=$(req POST "$CHAT" 'not-json')
  check_error "POST $CHAT 잘못된 JSON" 400 "$code" VALIDATION_ERROR
fi

# 4. suggestion
if ! has_path "$SUGGESTION"; then
  info "$SUGGESTION 미구현 (openapi.json에 경로 없음). suggestion 검사를 건너뜀"
else
  code=$(req GET "$SUGGESTION")
  if [ "$code" = "200" ] && data_ok 'd.get("level") == "beginner" and isinstance(d.get("suggestions"), list)'; then
    pass "GET $SUGGESTION 기본 등급 → 200 (level=beginner)"
  else
    fail "GET $SUGGESTION 기본 등급 → 기대 200 + data.level=beginner, 실제 $code $(head -c 200 "$TMP/body")"
  fi
  code=$(req GET "$SUGGESTION?level=bad")
  check_error "GET $SUGGESTION?level=bad" 400 "$code" VALIDATION_ERROR
fi

# 5. documents
if ! has_path "$DOCUMENTS/{source_ref_id}"; then
  info "$DOCUMENTS/{source_ref_id} 미구현 (openapi.json에 경로 없음). documents 검사를 건너뜀"
else
  if [ -n "$DOC_ID" ]; then
    code=$(req GET "$DOCUMENTS/$DOC_ID")
    if [ "$code" = "200" ] && DOC_ID="$DOC_ID" data_ok 'd.get("source_ref_id") == env["DOC_ID"] and isinstance(d.get("markdown"), str) and d["markdown"]'; then
      pass "GET $DOCUMENTS/$DOC_ID → 200"
    else
      fail "GET $DOCUMENTS/$DOC_ID → 기대 200 + data.markdown, 실제 $code $(head -c 200 "$TMP/body")"
    fi
  else
    info "DOC_ID 미지정. documents 정상 조회 검사를 건너뜀"
  fi
  code=$(req GET "$DOCUMENTS/bad.id")
  check_error "GET $DOCUMENTS/bad.id (허용 문자 밖)" 400 "$code" VALIDATION_ERROR
  code=$(req GET "$DOCUMENTS/no_such_document_zz")
  check_error "GET $DOCUMENTS/no_such_document_zz" 404 "$code" DOCUMENT_NOT_FOUND
fi

# 6. 없는 경로
code=$(req GET /no-such-path)
check_error "GET /no-such-path" 404 "$code" NOT_FOUND

# 7. CORS
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
