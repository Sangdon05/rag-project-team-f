---
name: api-implementation
description: Use when writing or fixing api/ code. Per-layer code patterns for slices, errors, settings, generators, and tests.
---

# api-implementation

`api/` 슬라이스 코드를 계층별로 쓰는 패턴이다. 규칙 원본은 [api-invariants](../api-invariants/SKILL.md), 배치는 [api-architecture](../api-architecture/SKILL.md), 공통 원칙은 [layered-architecture](../layered-architecture/SKILL.md)다.
테스트 작성법은 [references/testing.md](references/testing.md)를 본다.

아래 코드는 chat 슬라이스 기준 예시다. 임시 작업 트리에서 그대로 만들어 layer-check 위반 0건, unittest 12개 통과, smoke 전부 PASS를 확인한 구성이다.
실제 코드가 생기면 그 코드가 정답 예시가 된다. 이 문서와 실제 코드가 다르면 api-reviewer 판정을 받아 둘 중 하나를 고치고, 이 문서를 실제 코드에 맞춘다.

## 시작 전

1. `git fetch`로 main을 반영한다. remote가 없거나 fetch가 실패하면 그 사실을 보고서 `open_issues`에 적고 로컬 코드 기준으로 진행한다.
2. 대상 설계안 `docs/design/api/<slice>.md`를 읽는다. 설계안이 없으면 아무것도 바꾸지 않고(패키지 추가 포함) `blocked`로 보고한다. 이 스킬의 예시 코드는 설계안을 대신하지 않는다. `상태: 검토 중` 이상이면 구현할 수 있고, `초안`이면 발주서에 명시된 경우에만 구현한다.
3. 패키지가 없으면 `uv add fastapi uvicorn`으로 추가한다(이 서비스의 첫 구현 작업에서 한 번). 테스트용 HTTP 클라이언트 `httpx`와 fake 모델(`langchain_core`)은 이미 설치돼 있다. `pyproject.toml`을 손으로 고치지 않는다.
4. `api/shared/`, `api/error_handlers.py`, `api/main.py`, `api/container.py`가 없으면 첫 슬라이스 작업에서 만든다(발주서에 없어도 된다). 이미 있으면 맡은 슬라이스 연결 외의 수정은 발주서에 있을 때만 한다.
5. 새 환경 변수를 쓰면 같은 작업에서 `.env.example`, `docs/references/environment.md`, README 환경 변수 표를 함께 고친다(R12). 이 서비스의 기본 변수:

   | 변수 | 기본값 | 뜻 |
   | --- | --- | --- |
   | `ANSWER_BACKEND` | `mock` | 답변 생성기 선택 `mock` \| `llm` \| `rag` |
   | `API_CORS_ORIGINS` | (빈 값) | 허용할 프론트 origin, 쉼표 구분 |
   | `API_MAX_MESSAGES` | `20` | 요청당 메시지 수 상한 (메시지 길이 한도는 두지 않는다, R11) |
   | `API_DOCUMENTS_DIR` | `solar_handoff/documents` | documents 슬라이스가 읽는 원문 Markdown 폴더 |

   모델명은 기존 `OPENAI_CHAT_MODEL`을 그대로 쓴다.

## 구현 순서

shared(처음 한 번) → domain → infrastructure → application → presentation(schemas → dependencies → router) → `container.py` → `main.py` 등록 → 테스트

import는 항상 `api.`로 시작하는 절대 경로로 쓴다. 새 폴더에는 `__init__.py`를 만든다.

## shared

```python
# api/shared/exceptions.py — 순수 파이썬. domain도 import한다
class ApiError(Exception):
    status_code = 500
    error_code = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidInputError(ApiError):   # 400
    status_code = 400
    error_code = "VALIDATION_ERROR"


class NotFoundError(ApiError):       # 404
    status_code = 404
    error_code = "NOT_FOUND"


class UpstreamError(ApiError):       # 502 답변 생성기 등 외부 의존 실패
    status_code = 502
    error_code = "UPSTREAM_ERROR"
```

```python
# api/shared/responses.py — 성공 응답 형식 (R7). presentation만 import한다
class SuccessResponse(BaseModel, Generic[T]):
    success: Literal[True] = True
    data: T
```

- router는 `SuccessResponse[XxxData]`를 `response_model`로 쓰고 `SuccessResponse(data=...)`를 돌려준다. `/health`도 같은 형식이다.

- `api/shared/settings.py`는 `os.environ`에서 위 변수를 읽어 frozen `Settings` dataclass를 만든다(`Settings.from_env()`). pydantic-settings는 쓰지 않는다(설치돼 있지 않다).
- `api/error_handlers.py`의 `register_exception_handlers(app)`가 네 가지를 공통 형식으로 바꾼다.

  | 예외 | 상태 | `error_code` |
  | --- | --- | --- |
  | `ApiError`와 하위 클래스 | 클래스의 `status_code` | 클래스의 `error_code` |
  | `RequestValidationError` (스키마 위반, 잘못된 JSON) | 400 | `VALIDATION_ERROR`, 메시지는 `필드: 오류` |
  | `StarletteHTTPException` (없는 경로 등 프레임워크 내부) | 해당 코드 | 404 `NOT_FOUND`, 405 `METHOD_NOT_ALLOWED`, 그 외 `HTTP_ERROR` |
  | `Exception` (처리 못 한 예외) | 500 | `INTERNAL_ERROR`, 고정 문구. 원문은 `logger.exception`으로만 |

  내장 `ValueError`·`LookupError`를 핸들러에 등록하지 않는다. 라이브러리 버그가 4xx로 숨는다(layer-check `[넓은예외]`).

## domain

```python
# api/chat/domain/exceptions.py
from api.shared.exceptions import InvalidInputError, UpstreamError


class InvalidConversationError(InvalidInputError):
    pass                                       # 빈 대화, 역할·순서 오류, 메시지 수 초과 (R11). error_code는 VALIDATION_ERROR 그대로 (R7)


class AnswerGenerationError(UpstreamError):
    error_code = "ANSWER_GENERATION_FAILED"    # 502
```

```python
# api/chat/domain/conversation.py (요지)
@dataclass(frozen=True)
class ConversationLimits:
    max_messages: int


@dataclass(frozen=True)
class Conversation:
    messages: tuple[Message, ...]

    @classmethod
    def create(cls, raw: list[tuple[str, str]], limits: ConversationLimits) -> "Conversation":
        # 빈 대화 / 수 초과 / 알 수 없는 role / 빈 메시지 / 첫·마지막이 user가 아님 / 교대 깨짐 → 슬라이스 예외
        ...

    @property
    def question(self) -> str:          # 마지막 user 메시지
        return self.messages[-1].content
```

- `Answer(text, mode, sources=(), embedding=None)`과 `Source(ref, chunk_id, source_ref_id)`는 frozen dataclass, `AnswerMode`는 `StrEnum`(`mock`, `llm`, `rag`)이다. 빈 답변은 `__post_init__`에서 막는다. `embedding`은 RAG가 실제 질의·문서 임베딩 모델 정보를 제공할 때만 채운다.
- 포트 `AnswerGenerator.generate(conversation) -> Answer`는 [api-architecture §5](../api-architecture/SKILL.md)와 [연결 가이드](../../../docs/references/api-rag-integration.md)를 따른다.

## infrastructure

```python
# api/chat/infrastructure/mock_generator.py
# 평가셋 정답을 넣지 않는다 (R16). 프론트 연동 확인용 고정 문구만 쓴다.
MOCK_TEXT = "[mock] 아직 RAG가 연결되지 않아 고정 응답을 돌려줍니다. 받은 질문: {question}"


class MockAnswerGenerator(AnswerGenerator):
    async def generate(self, conversation: Conversation) -> Answer:
        return Answer(text=MOCK_TEXT.format(question=conversation.question[:100]), mode=AnswerMode.MOCK)
```

```python
# api/chat/infrastructure/llm_generator.py (요지)
class LlmAnswerGenerator(AnswerGenerator):
    """검색 없이 LLM이 답하는 임시 모드 (mode=llm, sources=[])."""

    def __init__(self, model: BaseChatModel) -> None:   # 모델은 container가 넣는다. 테스트는 fake
        self.model = model

    async def generate(self, conversation: Conversation) -> Answer:
        messages = [SystemMessage(SYSTEM_PROMPT), *대화를 HumanMessage/AIMessage로]
        try:
            reply = await self.model.ainvoke(messages)
        except Exception as exc:
            logger.warning("LLM 호출 실패: %s", type(exc).__name__)   # 원문·키를 남기지 않는다
            raise AnswerGenerationError("답변을 생성하지 못했습니다. 잠시 후 다시 시도하세요.") from exc
        ...
        return Answer(text=text, mode=AnswerMode.LLM)
```

- `SYSTEM_PROMPT`는 짧게 둔다: 영문 Red·Blue 151마리 기준, 다른 세대 값을 말하지 않음, 근거 문서가 없으니 확실하지 않으면 확인할 수 없다고 답함, 사용자 언어로 답함. 이 프롬프트는 `llm` 모드에만 쓴다. RAG 프롬프트는 rag-developer 담당이며 이 파일로 옮겨 오지 않는다.
- 생성기 안에서 `ChatOpenAI`를 만들지 않는다. 생성자로 받는다(R4).

## application

```python
class AskService:
    def __init__(self, generator: AnswerGenerator, limits: ConversationLimits) -> None:
        self.generator = generator
        self.limits = limits

    async def ask(self, raw: list[tuple[str, str]]) -> Answer:
        conversation = Conversation.create(raw, self.limits)   # 규칙은 도메인에서 (R3)
        return await self.generator.generate(conversation)
```

## presentation

- `schemas.py`: `ChatRequest(messages: list[MessageIn])`, `MessageIn.role`은 `Literal["user", "assistant"]`. `ChatData(answer, mode, sources, embedding=None)`와 `from_domain(answer)`, 응답 모델은 `SuccessResponse[ChatData]`. 필드마다 `Field(..., description=...)`를 쓴다.
- 질의 임베딩을 호출하지 않는 등 실제 사용 정보가 없으면 HTTP 응답에서 `embedding`을 생략한다. `sources`는 비어 있어도 목록으로 반환한다. 기술 분류 근거(`move:{id}`)는 답변 본문에 표시하고, 번호 출처(`sources`)는 인용한 포켓몬 청크만 가리킨다. 세부 계약은 [API–RAG 연결 가이드](../../../docs/references/api-rag-integration.md)를 따른다.
- 스키마는 형식만 본다(타입, 필수 여부, role 값). 메시지 수·순서 같은 규칙은 도메인이 본다. 둘 다 400 `VALIDATION_ERROR`다(R7).
- `dependencies.py`: `provide_ask_service()` 플레이스홀더([layered-architecture §4.3](../layered-architecture/SKILL.md)).
- `router.py`:

```python
router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=SuccessResponse[ChatData], response_model_exclude_none=True)
async def chat(body: ChatRequest, service: Annotated[AskService, Depends(provide_ask_service)]) -> SuccessResponse[ChatData]:
    answer = await service.ask(body.to_raw())
    return SuccessResponse(data=ChatData.from_domain(answer))
```

- router에서 `try/except`로 예외를 바꾸지 않는다(R6).
- health는 `GET /health` → `{"success": true, "data": {"status": "ok"}}`만 둔다. 외부 호출을 하지 않는다(LLM 키가 없어도 200).

## 조립

```python
# api/container.py (요지)
def create_answer_generator(settings: Settings) -> AnswerGenerator:
    validate_answer_backend(settings)  # mock | llm | rag 외의 값은 시작 시 거부
    if settings.answer_backend == "rag":
        from starlette.concurrency import run_in_threadpool
        from api.chat.infrastructure.rag_generator import RagAnswerGenerator
        from solar_handoff.src.conversation import create_service

        return RagAnswerGenerator(create_service, run_in_threadpool)
    if settings.answer_backend == "llm":
        from langchain_openai import ChatOpenAI
        return LlmAnswerGenerator(ChatOpenAI(model=os.environ["OPENAI_CHAT_MODEL"], temperature=0,
                                               reasoning_effort=os.environ.get("OPENAI_REASONING_EFFORT", "low")))
    return MockAnswerGenerator()


def wire_dependencies(app: FastAPI, settings: Settings) -> None:
    service = AskService(generator=create_answer_generator(settings),
                         limits=ConversationLimits(settings.max_messages))
    app.dependency_overrides.update({provide_ask_service: lambda: service})
```

```python
# api/main.py (요지)
def create_app(settings: Settings | None = None) -> FastAPI:
    load_dotenv()
    settings = settings or Settings.from_env()
    app = FastAPI(title="Pokédex RAG API")
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                           allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    register_exception_handlers(app)
    wire_dependencies(app, settings)
    app.include_router(health_router)
    app.include_router(chat_router)
    return app


app = create_app()
```

## 완료와 보고

- [api-invariants §7](../api-invariants/SKILL.md)의 게이트 명령을 모두 실행하고 출력을 보고서에 붙인다.
- 서버를 띄워 확인하고 싶으면 [api-invariants §10](../api-invariants/SKILL.md)을 따르고, 끝나면 반드시 끈다.
- 설계안과 다르게 구현한 점, 모듈 밖에서 바꾼 파일(`pyproject.toml`, `uv.lock`, `.env.example`, 문서)은 보고서에 따로 적는다.
