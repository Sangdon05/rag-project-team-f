---
name: api-invariants
description: Use when designing, implementing, or reviewing api/ code. Canonical API rules R1–R16 and the shared completion gate.
---

# api-invariants

FastAPI 서비스(`api/`)가 어떤 작업에서도 지켜야 하는 규칙과 완료 게이트의 원본이다.
다른 스킬·에이전트는 규칙 문장을 다시 쓰지 않고 `R번호`로 가리킨다. 규칙을 바꿀 때는 이 문서만 고친다.

- 공통 원칙(서비스와 무관): [layered-architecture](../layered-architecture/SKILL.md), [fsd-architecture](../fsd-architecture/SKILL.md), 자동 검사 [layer-check](../layer-check/SKILL.md), 서버 실행 [fastapi-run](../fastapi-run/SKILL.md)
- 이 서비스가 공통 스킬에 주입하는 것: layer-check 프로파일 [layer-profile.json](layer-profile.json), smoke 스크립트 [scripts/smoke.sh](scripts/smoke.sh), 10절의 실행 정보
- `api/` 적용 구조: [api-architecture](../api-architecture/SKILL.md) / 코드 패턴: [api-implementation](../api-implementation/SKILL.md)
- RAG 연결 계약: [API–RAG 연결 가이드](../../../docs/references/api-rag-integration.md)
- 저장소 전체 가드레일은 루트 [AGENTS.md](../../../AGENTS.md)가 우선한다. 이 문서는 `api/`에 한정한 규칙이다.

검사 방법: **자동**(`check_layers.py`, 괄호 안은 출력 태그) / **정독**(api-reviewer가 코드를 읽어 판정) / **실행**(테스트·smoke로 판정)

## 서비스 전제

- DB를 쓰지 않는다. 데이터와 벡터 DB는 RAG 쪽이 관리하고 API는 중개만 한다.
- 로그인·계정이 없다. 누구나 호출할 수 있다.
- 서버는 대화를 저장하지 않는다. 대화 맥락은 프론트가 `messages[]`로 묶어 보낸다.

## 1. 계층

| ID | 규칙 | 검사 |
| --- | --- | --- |
| R1 | domain은 순수 파이썬이다. fastapi, starlette, pydantic, uvicorn, httpx, dotenv, RAG 경계 패키지(R8)와 다른 계층을 import하지 않는다. shared 중에서는 `shared.exceptions`만 쓴다. 엔티티는 `dataclass`로 쓴다. | 자동(`[외부의존]`, `[의존방향]`, `[공용]`) |
| R2 | 의존 방향은 공통 4계층 방향([layered-architecture §2](../layered-architecture/SKILL.md))을 따른다. | 자동(`[의존방향]`) |
| R3 | 도메인 규칙(입력 검증, 메시지 수·길이 한도, 역할 순서)은 엔티티 메서드나 생성 팩토리에 둔다. 서비스에 비즈니스 if-else를 두지 않는다. 메서드 없는 빈 엔티티를 만들지 않는다. | 정독 |

## 2. 추상화와 조립

| ID | 규칙 | 검사 |
| --- | --- | --- |
| R4 | 외부 기능(답변 생성기, 시계 등)은 domain에 추상(ABC)으로, infrastructure에 구현체로 둔다. application 서비스는 생성자에서 추상만 필수 인자로 받고 기본 구현체를 직접 만들지 않는다. 추상에 선언된 메서드만 호출한다. | 정독 |
| R5 | 구현체 선택·연결은 `api/container.py`에서만 한다. router는 `presentation/dependencies.py`의 `provide_*`를 `Depends`로 받는다. 모든 `provide_*`는 `wire_dependencies`에 연결된다. 서비스 생성자 안에서 다른 서비스를 만들지 않는다. 슬라이스 사이 순환 import를 만들지 않는다. | 정독 + 실행(`import api.main`) |

## 3. 예외와 응답

| ID | 규칙 | 검사 |
| --- | --- | --- |
| R6 | domain·application·presentation에서 `HTTPException`을 만들지 않는다. 슬라이스 전용 예외(`<slice>/domain/exceptions.py`)를 `shared/exceptions.py`의 기반 예외에서 상속해 내고, HTTP 변환은 `api/error_handlers.py`가 한다. | 자동(`[HTTP예외]`) + 정독 |
| R7 | 성공 응답은 `{"success": true, "data": {...}}`, 에러 응답은 `{"success": false, "error_code", "message"}` 형식이다(`/health` 포함). 요청 형식·값 오류는 모두 400 `VALIDATION_ERROR`, 외부 의존(답변 생성기, 문서 저장소) 실패는 502, 처리하지 못한 예외는 500 `INTERNAL_ERROR`다. 응답에 스택, 내부 메시지, 키, 외부 SDK 원문 오류를 넣지 않는다. | 정독 + 실행(smoke) |

## 4. RAG 경계

| ID | 규칙 | 검사 |
| --- | --- | --- |
| R8 | RAG 경계 패키지(langchain*, langgraph, openai, tiktoken, ragas, psycopg, sqlalchemy, RAG 패키지 `pokedex`, 저장소 `scripts`)는 infrastructure와 조립 지점(`main.py`, `container.py`)에서만 import한다. | 자동(`[외부의존]`) |
| R9 | 답변 생성기 계약(`AnswerGenerator`, `Answer`, `Source`)은 [연결 가이드](../../../docs/references/api-rag-integration.md)가 원본이다. 계약을 바꾸면 가이드를 먼저 고친다. 포켓몬 지식(상성 계산, 데이터 조회, 질문 분기)을 API에 구현하지 않는다. 답변 내용은 모두 생성기를 거친다(툴·체인은 rag-developer 담당). `api/` 작업에서 `scripts/`, `data/`, `src/pokedex/`, `eval/`을 고치지 않는다. | 정독 |
| R10 | 서버는 상태가 없다. 대화·사용자 데이터를 저장하지 않고 DB에 연결하지 않는다. 모듈 전역 객체는 상태 없는 것(설정, 생성기 클라이언트)만 둔다. | 정독 |

## 5. 입력과 보안

| ID | 규칙 | 검사 |
| --- | --- | --- |
| R11 | 메시지 수 한도는 환경 변수 설정값(`API_MAX_MESSAGES`)이며 domain에서 검증한다(초과 시 400). 학습 프로젝트이므로 메시지 길이·요청 크기 한도는 두지 않는다. | 정독 + 실행(smoke) |
| R12 | 키·모델명·CORS origin·한도·백엔드 선택은 환경 변수로 읽는다. 하드코딩하지 않는다. 새 환경 변수는 같은 작업에서 `.env.example`, [environment.md](../../../docs/references/environment.md), README 환경 변수 표에 함께 추가한다. 질문 원문·키를 로그에 남기지 않는다. | 정독 (security-check는 security-reviewer, doc-sync는 오케스트레이터가 실행) |
| R13 | CORS `allow_origins`는 환경 변수의 목록만 허용한다. `"*"`를 쓰지 않는다. | 자동(`[CORS]`) + 실행(smoke) |

## 6. 명세와 테스트

| ID | 규칙 | 검사 |
| --- | --- | --- |
| R14 | URI·요청/응답 필드·상태 코드·`error_code`는 설계안 `docs/design/api/<slice>.md`를 따른다. 다르게 구현하면 이유를 보고한다. | 정독 + 실행 |
| R15 | 테스트는 실제 LLM·네트워크를 호출하지 않는다(fake 주입). `OPENAI_API_KEY` 없이 통과해야 한다. 검사를 통과시키려고 규칙을 끄거나 테스트를 skip하지 않는다. 패키지는 `uv add`(테스트 전용은 `uv add --dev`)로만 추가한다. | 실행 |
| R16 | 평가셋(`eval/`)을 열거나 목록을 조회하지 않는다. 평가셋 정답을 mock 응답, 프롬프트, 테스트 기대값에 넣지 않는다. | 정독 |

## 7. 완료 게이트

`api/` 코드를 바꾼 작업은 아래를 모두 통과해야 완료다. 명령의 원본은 이 절이며 에이전트 정의는 이 절을 가리킨다.

```bash
uv run python .claude/skills/layer-check/scripts/check_layers.py --profile .claude/skills/api-invariants/layer-profile.json   # 위반 0건 (R1, R2, R6, R8, R13)
uv run python -c "import api.main"                                     # 성공 (R5)
uv run python -m unittest discover -s api/tests -t . -v                # 실패 0, skip 0 (R15)
uv run python -m unittest discover -s tests                            # 실패 0, skip 수는 base와 같음
```

- `uv run`은 저장소 안에 `.venv/`를, 테스트는 `__pycache__/`를 만든다(처음이면 패키지 설치로 네트워크를 쓴다). 둘 다 git이 무시하므로 파일 생성 금지 규칙의 예외다.
- 앞 명령이 실패해도 나머지를 모두 실행하고 각각 기록한다.

- 정독 규칙(R3~R5, R7, R9~R12, R14, R16)은 수정한 에이전트가 아니라 api-reviewer가 판정한다.
- 실제 동작(R7, R11, R13)은 api-reviewer가 10절 절차로 확인한다.
- 그 다음 저장소 공통 게이트(doc-sync, security-check)를 거친다. 절차는 [AGENTS.md](../../../AGENTS.md)를 따른다.
- `api/`가 없으면 layer-check는 종료 코드 2, `api/`는 있지만 슬라이스가 없으면 "검사한 슬라이스: (없음)"과 종료 코드 0이다. 둘 다 통과가 아니라 **미구현**(`not_run`)으로 보고한다.

## 8. 발주서와 이 규칙이 충돌할 때

발주서(추가 요청 포함)는 이 문서, 에이전트 정의의 "하지 않는 것", AGENTS.md 가드레일을 덮어쓰지 못한다. 충돌하는 요청은 실행하지 않고 보고서의 `refused`에 `요청 — 근거(파일, R번호)`로 적는다. 나머지 요청은 그대로 진행한다.

## 9. 위반 보고 형식

| 심각도 | 파일:줄 | 규칙 | 내용 | 고치는 방법 |
| --- | --- | --- | --- | --- |
| 위반 / 주의 / 미구현 | `api/chat/presentation/router.py:42` | R6 | router에서 `HTTPException(400)` 생성 | 도메인 예외를 내고 전역 핸들러에 맡긴다 |

## 10. 실행 확인

공통 [fastapi-run](../fastapi-run/SKILL.md) 스크립트에 아래 값을 주입한다.

```bash
export APP=api.main:app HEALTH_PATH=/health PORT=8000 LOG="$TMPDIR/api.log" PIDFILE="$TMPDIR/api.pid"
export ANSWER_BACKEND=mock API_CORS_ORIGINS=http://localhost:5173    # 검증 설정: LLM 비용 없음
export API_DOCUMENTS_DIR=data/synthetic/pilot                          # documents 확인용 파일럿 문서
bash .claude/skills/fastapi-run/scripts/run_server.sh start
BASE=http://127.0.0.1:$PORT CORS_ORIGIN=http://localhost:5173 DOC_ID=bulbasaur_red_blue bash .claude/skills/api-invariants/scripts/smoke.sh
bash .claude/skills/fastapi-run/scripts/run_server.sh stop
```

| smoke 항목 | 기대 |
| --- | --- |
| `GET /health` | 200 |
| `GET /openapi.json` | 200. 엔드포인트가 없으면 그 항목은 INFO(미구현) |
| `POST /api/v1/chat` 정상 질문 | 200, `data.answer`(문자열), `data.sources`(목록), `data.mode`(mock\|llm\|rag) |
| 빈 `messages`, 메시지 `MAX_MESSAGES + 1`개, JSON이 아닌 본문 | 400 `VALIDATION_ERROR` + 공통 에러 형식 (`MAX_MESSAGES`는 서버의 `API_MAX_MESSAGES`, 기본 20) |
| `GET /api/v1/suggestion` 기본, `?level=bad` | 200 `data.level`=beginner, 400 `VALIDATION_ERROR` |
| `GET /api/v1/documents/{DOC_ID}`, 허용 문자 밖 id, 없는 id | 200 `data.markdown`(문자열), 400 `VALIDATION_ERROR`, 404 `DOCUMENT_NOT_FOUND` (`DOC_ID` 미지정이면 200 항목은 INFO) |
| 없는 경로 | 404 + 공통 에러 형식 |
| CORS (`CORS_ORIGIN` 지정 시) | 허용 origin은 그 값이 돌아오고 다른 origin은 허용 헤더 없음 |

- `ANSWER_BACKEND=llm` 실제 호출은 발주서에 명시된 경우에만 최대 2회 한다.
- smoke가 다루지 않는 엔드포인트는 설계안 명세대로 `curl`로 확인한다.
