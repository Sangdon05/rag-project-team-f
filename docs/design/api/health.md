# health 설계안

상태: 검토 중

입력 원본: [API 엔드포인트 계획](../../plans/2026-11-26-api-endpoints.md) 2절 결정, 3절 확정 규격. 규칙 번호(R*)는 [api-invariants](../../../.claude/skills/api-invariants/SKILL.md)를 가리킨다.

이 문서는 health 슬라이스와 함께 **모든 슬라이스가 쓰는 공통 사항**(0절)을 정의한다. 다른 설계안은 0절을 링크하고 다시 쓰지 않는다.

## 0. 공통

### 0.1 응답 형식 (R7)

| 구분 | 본문 |
| --- | --- |
| 성공 | `{"success": true, "data": {...}}` |
| 실패 | `{"success": false, "error_code": "<CODE>", "message": "<사람이 읽는 문장>"}` |

- `/health`를 포함한 모든 엔드포인트가 이 형식이다.
- 실패 본문에 스택, 내부 예외 메시지, 키, 외부 SDK 원문 오류, 요청 원문 값을 넣지 않는다.

### 0.2 공통 상태 코드

| HTTP | `error_code` | 조건 | 발생 지점 |
| --- | --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 요청 형식·값 오류(잘못된 JSON, 필수 필드 누락, 타입·허용값 위반, 도메인 입력 규칙 위반) | `RequestValidationError`, `InvalidInputError` 하위 예외 |
| 404 | `NOT_FOUND` | 라우트에 매칭되지 않는 경로 | `StarletteHTTPException(404)` |
| 405 | `METHOD_NOT_ALLOWED` | 경로는 있으나 허용하지 않는 메서드 | `StarletteHTTPException(405)` |
| 500 | `INTERNAL_ERROR` | 처리하지 못한 예외 | `Exception` |

- 슬라이스 전용 400 코드는 두지 않는다. 400은 모두 `VALIDATION_ERROR`다(계획 2절).
- 슬라이스 전용 404·502 코드(`DOCUMENT_NOT_FOUND`, `ANSWER_GENERATION_FAILED`, `DOCUMENT_SOURCE_FAILED`)는 각 설계안에 있다.

### 0.3 공용 파일 (`api/shared/`, 조립 파일)

| 파일 | 내용 | import 허용 |
| --- | --- | --- |
| `api/shared/exceptions.py` | 기반 예외 (아래 표). 순수 파이썬 | 모든 계층(domain은 이 모듈만, R1) |
| `api/shared/responses.py` | `SuccessResponse[T]`(`success: Literal[True] = True`, `data: T`), `ErrorResponse`(`success: Literal[False] = False`, `error_code: str`, `message: str`, OpenAPI 문서·핸들러용) | presentation, `error_handlers.py` |
| `api/shared/settings.py` | `Settings`(frozen dataclass) + `Settings.from_env()` | presentation, 조립 파일 (domain 금지) |
| `api/error_handlers.py` | `register_exception_handlers(app)` (0.4) | 조립 파일 |
| `api/container.py` | `wire_dependencies(app, settings)`: 슬라이스별 구현체 선택·생성, `provide_*` 연결 | — |
| `api/main.py` | `create_app(settings=None)`: settings가 없을 때만 `load_dotenv` → `Settings.from_env()` (settings를 넘기면 `.env`를 읽지 않는다) → 예외 핸들러·500 미들웨어 → CORS(나중에 add한 미들웨어가 바깥이므로 500 미들웨어가 CORS 안쪽에 온다) → `wire_dependencies` → 라우터 등록. 모듈 수준 `app = create_app()` | — |

기반 예외 (`api/shared/exceptions.py`):

| 클래스 | `status_code` | `error_code` | 쓰임 |
| --- | --- | --- | --- |
| `ApiError(Exception)` | 500 | `INTERNAL_ERROR` | 기반. 생성자 `message: str`(사용자에게 보여도 되는 문장만) |
| `InvalidInputError(ApiError)` | 400 | `VALIDATION_ERROR` | 도메인 입력 규칙 위반. 하위 클래스는 `error_code`를 바꾸지 않는다 |
| `NotFoundError(ApiError)` | 404 | `NOT_FOUND` | 대상 없음. 하위 클래스가 `error_code`를 구체화할 수 있다 |
| `UpstreamError(ApiError)` | 502 | `UPSTREAM_ERROR` | 외부 의존(답변 생성기, 문서 저장소) 실패. 하위 클래스가 `error_code`를 구체화한다 |

### 0.4 예외 → HTTP 매핑 (`api/error_handlers.py`)

| 예외 | 상태 | `error_code` | `message` |
| --- | --- | --- | --- |
| `ApiError`와 하위 클래스 | 클래스의 `status_code` | 클래스의 `error_code` | 예외의 `message` |
| `RequestValidationError` (스키마 위반, 잘못된 JSON, query 허용값 위반) | 400 | `VALIDATION_ERROR` | 첫 오류의 `필드 경로: 오류 설명`(pydantic `loc`·`msg`만. `input` 값은 넣지 않는다) |
| `StarletteHTTPException` 404 | 404 | `NOT_FOUND` | `요청한 경로를 찾을 수 없습니다.` |
| `StarletteHTTPException` 405 | 405 | `METHOD_NOT_ALLOWED` | `허용하지 않는 메서드입니다.` (예외의 `headers`(`Allow`)는 응답에 유지) |
| `StarletteHTTPException` 그 밖의 코드 | 해당 코드 | `HTTP_ERROR` | 고정 문구 |
| `Exception` (처리 못 한 예외) | 500 | `INTERNAL_ERROR` | `서버 내부 오류가 발생했습니다.` 원문은 `logger.exception`으로만 남긴다 |

- 처리 못 한 예외의 500 응답에도 CORS 헤더가 붙어야 프론트가 `error_code`를 읽는다. Starlette의 `Exception` 핸들러는 CORS 미들웨어 바깥에서 돌므로, CORS 안쪽에 예외를 잡아 같은 500 응답을 만드는 HTTP 미들웨어를 둔다(오케스트레이터 결정, PR ③ 리뷰 지적).
- 핸들러는 `fastapi.exceptions.RequestValidationError`와 `starlette.exceptions.HTTPException`에 등록한다(FastAPI `HTTPException`이 아니라 Starlette 쪽이어야 라우팅 404·405를 받는다).
- 내장 `ValueError`·`LookupError`를 핸들러에 등록하지 않는다(layer-check `[넓은예외]`).
- domain·application·presentation은 `HTTPException`을 만들지 않는다(R6).

### 0.5 환경 변수 (`Settings`)

| 변수 | 기본값 | `Settings` 필드 | 쓰는 슬라이스 | 잘못된 값 |
| --- | --- | --- | --- | --- |
| `ANSWER_BACKEND` | `mock` | `answer_backend` | chat | `mock`·`llm` 밖이면 앱 시작 실패 (container) |
| `API_CORS_ORIGINS` | (빈 값) | `cors_origins: list[str]` (쉼표 구분, 앞뒤 공백 제거, 빈 항목 제외) | 공통 | 비어 있으면 CORS 미들웨어를 붙이지 않는다. `*`를 쓰지 않는다(R13) |
| `API_MAX_MESSAGES` | `20` | `max_messages: int` | chat | 정수가 아니거나 1 미만이면 앱 시작 실패 |
| `API_DOCUMENTS_DIR` | `data/synthetic/pilot` | `documents_dir: str` | documents | 시작 시 검사하지 않는다(요청 시 [documents](documents.md) 규칙) |
| `OPENAI_CHAT_MODEL`, `OPENAI_API_KEY` | (기존 값) | — (container가 `llm` 분기에서만 읽음) | chat | `mock`이면 읽지 않는다 |

- CORS: `allow_origins=settings.cors_origins`, `allow_methods=["GET", "POST"]`, `allow_headers=["Content-Type"]`.
- 요청 크기·타임아웃·호출 횟수 제한은 두지 않는다(계획 머리말, R11).

### 0.6 공통 테스트 (`api/tests/test_common.py`)

| # | 시나리오 | 기대 |
| --- | --- | --- |
| C1 | `GET /no-such-path` | 404, `{"success": false, "error_code": "NOT_FOUND", "message": ...}`, `detail` 키 없음 |
| C2 | `DELETE /health` | 405, `error_code` `METHOD_NOT_ALLOWED` |
| C3 | 테스트용 라우트가 `RuntimeError("sk-secret /Users/x")`를 던짐 (`raise_app_exceptions=False`) | 500, `INTERNAL_ERROR`, 본문에 `sk-secret`·`Traceback`·경로 없음 |
| C4 | 허용 origin으로 `OPTIONS` preflight | `access-control-allow-origin`이 그 origin. 다른 origin은 헤더 없음 |
| C5 | `Settings.from_env()`: `API_MAX_MESSAGES=abc`, `0` | 예외 (앱 시작 실패) |
| C6 | `ANSWER_BACKEND=unknown`으로 `create_app` | 시작 시 예외 |

테스트는 항상 `create_app(SETTINGS)`로 설정을 직접 넘긴다(개인 `.env` 영향 차단).

## 1. 목적과 범위

서버가 떠 있는지만 알려 준다. 외부 호출(LLM, 파일, 네트워크)이 없으며 `OPENAI_API_KEY`가 없어도 200이다.

## 2. 용어

| 코드 이름 | 뜻 |
| --- | --- |
| `HealthData` | `data` 스키마. `status: Literal["ok"]` |

## 3. 도메인

없음. 규칙이 없으므로 presentation만 둔다([fsd-architecture §2-5](../../../.claude/skills/fsd-architecture/SKILL.md)).

## 4. 포트와 구현체

없음.

## 5. 유스케이스

없음. router가 고정 값을 돌려준다.

## 6. 엔드포인트 명세

### `GET /health`

| 항목 | 값 |
| --- | --- |
| 요청 | 파라미터·본문 없음 |
| 성공 | 200 `{"success": true, "data": {"status": "ok"}}` |
| `response_model` | `SuccessResponse[HealthData]` |

응답 `data`:

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `status` | string (`"ok"`) | 예 | 항상 `ok` |

에러: 0.2 공통(405 등)만 해당. 슬라이스 전용 에러 없음.

파일 배치:

```text
api/health/
  __init__.py
  presentation/
    __init__.py
    schemas.py     HealthData
    router.py      APIRouter(tags=["health"]), GET /health  (prefix 없음)
```

## 7. 설정

없음. 0.5의 공통 설정만 쓴다.

## 8. 테스트 시나리오 (`api/tests/health/`)

| # | 시나리오 | 기대 |
| --- | --- | --- |
| H1 | `GET /health` (`Settings(answer_backend="mock", ...)`, `OPENAI_API_KEY` 없음) | 200, 본문이 정확히 `{"success": true, "data": {"status": "ok"}}` |
| H2 | `POST /health` | 405 `METHOD_NOT_ALLOWED` 공통 에러 형식 |

공통 테스트는 0.6.

## 9. 변경 제안 (설계안 밖 파일)

| 파일 | 제안 |
| --- | --- |
| `pyproject.toml` | `fastapi`·`uvicorn` 미설치(`uv run --no-sync python -c "import fastapi"` → `ModuleNotFoundError`). PR ③ 구현 시 api-implementer가 `uv add fastapi uvicorn`으로 추가([api-implementation](../../../.claude/skills/api-implementation/SKILL.md) "시작 전" 3) |
| `.env.example`, `docs/references/environment.md`, `README.md` | `ANSWER_BACKEND`, `API_CORS_ORIGINS`, `API_MAX_MESSAGES`(PR ③), `API_DOCUMENTS_DIR`(PR ⑤)가 아직 없음(`grep -n "API_\|ANSWER" .env.example` → `OPENAI_API_KEY`만). 해당 PR에서 함께 추가(R12) |
| `.claude/skills/api-architecture/SKILL.md` §3 | 폴더 트리에 `shared/responses.py`, `suggestion/`, `documents/` 슬라이스 추가. §2 "외부 의존은 답변 생성기 포트 하나"를 "답변 생성기·문서 저장소·추천 질문 제공자"로 갱신 |

## 10. 질문

| 질문 | 임시 기본값 |
| --- | --- |
| 405·404 외 Starlette HTTP 예외의 `error_code` | `HTTP_ERROR` (api-implementation 스킬 표를 따름) |
| `/health`를 OpenAPI 문서에 노출할지 | 노출 (기본값 유지) |
