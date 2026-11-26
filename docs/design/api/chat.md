# chat 설계안

상태: 검토 중

입력 원본: [API 엔드포인트 스펙](../../archives/specs/2026-11-26-api-endpoints.md) 3절 요구사항, `POST /api/v1/chat`. 생성기 계약 원본: [API–RAG 연결 가이드](../../references/api-rag-integration.md) 2절(R9). 응답 형식·공통 에러·기반 예외·설정은 [health 설계안 0절(공통)](health.md#0-공통)을 따른다.

## 1. 목적과 범위

프론트가 보낸 대화 전체(`messages[]`)를 검증해 답변 생성기에 넘기고, 답변·생성 방식·출처를 돌려준다.

- 서버는 대화를 저장하지 않는다. 클라이언트가 매 요청에 대화 전체를 보낸다(R10).
- 생성기는 `mock`(기본)·`llm`·`rag`를 지원한다. Solar 서비스의 RAG 연결은 [연결 가이드](../../references/api-rag-integration.md)를 따른다. 표시용 임베딩 메타데이터는 선택 응답 필드이며 기존 요청·세 필드 응답은 유지한다.
- 포켓몬 지식(상성, 데이터 조회, 질문 분기)을 API에 구현하지 않는다. 답변 내용은 모두 생성기를 거친다(R9).
- 메시지 길이 한도, 출처 개수 한도는 두지 않는다(스펙 REQ-1·REQ-3).

## 2. 용어

| 코드 이름 | 뜻 |
| --- | --- |
| `Role` | `StrEnum`: `user`, `assistant` |
| `Message` | 대화 메시지 하나. `role`, `content`(앞뒤 공백 제거된 값) |
| `Conversation` | 한 요청의 대화. `messages`, `question`(마지막 user 메시지), `history`(그 앞 메시지) |
| `ConversationLimits` | 메시지 수 한도 값 객체 `max_messages` |
| `Answer` | 생성 결과. `text`, `mode`, `sources`, 선택 `embedding` |
| `EmbeddingInfo` | 실제 질의·인덱스 임베딩 모델 ID. 표시 전용이며 모델 선택 기능이 아님 |
| `AnswerMode` | `StrEnum`: `mock`, `llm`, `rag` |
| `Source` | 출처 하나. `ref`, `chunk_id`, `source_ref_id` (생성기 값 그대로) |
| `AnswerGenerator` | 답변 생성기 포트 |
| `AskService` | 유스케이스 서비스 |

## 3. 도메인

### 3.1 엔티티·값 객체

`api/chat/domain/conversation.py`:

| 타입 | 필드 | 규칙 (불변식) |
| --- | --- | --- |
| `ConversationLimits` (frozen) | `max_messages: int` | 1 이상 (container가 `Settings.max_messages`로 만든다) |
| `Message` (frozen) | `role: Role`, `content: str` | `content`는 앞뒤 공백 제거 후 비어 있지 않음 |
| `Conversation` (frozen) | `messages: tuple[Message, ...]` | `create(raw, limits)`만으로 만든다. 4.2 판정 순서 |

- `Conversation.create(raw: Sequence[tuple[str, str]], limits) -> Conversation`: `(role, content)` 원시 값을 받아 4.2 순서로 검사하고, `content`를 `strip()`한 값으로 `Message`를 만든다.
- `question` 프로퍼티: `messages[-1].content`. `history` 프로퍼티: `messages[:-1]`.

`api/chat/domain/answer.py`:

| 타입 | 필드 | 규칙 |
| --- | --- | --- |
| `Source` (frozen) | `ref: int`, `chunk_id: str`, `source_ref_id: str` | 검증·변환하지 않는다. 값은 생성기(RAG)가 정한 그대로(스펙 REQ-3) |
| `EmbeddingInfo` (frozen) | `query_model: str`, `document_model: str` | 각 값은 공백뿐이지 않은 1~200자 문자열. Unicode `C` 범주 문자는 거부. 잘못된 값은 `AnswerGenerationError` |
| `Answer` (frozen) | `text: str`, `mode: AnswerMode`, `sources: tuple[Source, ...] = ()`, `embedding: EmbeddingInfo \| None = None` | `__post_init__`: `text`가 앞뒤 공백 제거 후 비어 있거나 제공된 `embedding`이 `EmbeddingInfo`가 아니거나 `mode`가 `rag`가 아닌데 `embedding`을 제공하면 `AnswerGenerationError`. `sources` 개수 한도·순서 변경·번호 재부여 없음 |

### 3.2 규칙 위반과 예외

`api/chat/domain/exceptions.py`:

| 예외 | 기반 | 상태 | `error_code` | 발생 조건 |
| --- | --- | --- | --- | --- |
| `InvalidConversationError` | `InvalidInputError` | 400 | `VALIDATION_ERROR` | 메시지 0개, `max_messages` 초과, 첫·마지막이 user 아님, 교대 깨짐, 알 수 없는 role, 빈 content |
| `AnswerGenerationError` | `UpstreamError` | 502 | `ANSWER_GENERATION_FAILED` | 생성기가 답을 만들지 못함(네트워크, 모델, SDK 오류), 빈 답변 |

- `InvalidConversationError`는 `error_code`를 바꾸지 않는다. 400은 모두 `VALIDATION_ERROR`다(스펙 REQ-1·REQ-3). 구분은 `message`로 한다.
- "근거가 부족해 확인할 수 없다"는 정상 답변(200)이다. 생성기가 `text`에 담고 `sources`는 빈 목록이다.

## 4. 포트와 구현체

### 4.1 포트

```python
# api/chat/domain/generator.py — 계약 원본은 연결 가이드 2절
class AnswerGenerator(ABC):
    @abstractmethod
    async def generate(self, conversation: Conversation) -> Answer: ...
```

| 구현체 | 위치 | `mode` | 동작 | 예외 |
| --- | --- | --- | --- | --- |
| `MockAnswerGenerator` | `api/chat/infrastructure/mock_generator.py` | `mock` | 고정 문구 + 받은 질문 앞 100자. `sources=()`. 평가셋 정답을 넣지 않는다(R16) | 없음 |
| `LlmAnswerGenerator` | `api/chat/infrastructure/llm_generator.py` | `llm` | 생성자로 `BaseChatModel`을 받는다(R4). 임시 시스템 프롬프트 + `history`를 `HumanMessage`/`AIMessage`로 + `question`. 검색 없음, `sources=()` | SDK·네트워크 예외 → `AnswerGenerationError`(로그에는 예외 타입명만), 빈 응답 → `AnswerGenerationError` |
| `RagAnswerGenerator` | Solar 대화 어댑터 | `rag` | [연결 가이드](../../references/api-rag-integration.md) 4절 | — |

- `LlmAnswerGenerator`의 시스템 프롬프트: 영문 Red·Blue 151마리 기준, 다른 세대 값을 말하지 않음, 근거 문서가 없으므로 확실하지 않으면 확인할 수 없다고 답함, 사용자 언어로 답함. RAG 연결 전 임시용이다.
- `llm` 모드 답변에는 근거가 없어 `[n]`이 없다. `[n]`은 `rag` 모드에서 체인이 붙인다.

### 4.2 대화 검증 판정 순서 (에러 판정 순서)

요청 하나에 위반이 여러 개면 **먼저 걸린 하나**만 응답한다.

| 순서 | 판정 | 위치 | 예외 | 예시 `message` |
| --- | --- | --- | --- | --- |
| 1 | JSON 파싱, 스키마: 본문이 JSON 객체, `messages` 존재·배열, 각 항목 객체, `role`이 `user`·`assistant`, `content`가 문자열 | presentation (pydantic) | `RequestValidationError` | `body.messages.0.role: Input should be 'user' or 'assistant'` |
| 2 | 개수: 1개 이상 `max_messages`개 이하 | domain `Conversation.create` | `InvalidConversationError` | `메시지는 1개 이상 20개 이하여야 합니다.` |
| 3 | 첫 메시지와 마지막 메시지가 user, 중간은 user·assistant 교대 | domain | `InvalidConversationError` | `대화는 user로 시작하고 끝나야 하며 user와 assistant가 번갈아 와야 합니다.` |
| 4 | 각 `content`가 앞뒤 공백 제거 후 비어 있지 않음 | domain | `InvalidConversationError` | `메시지 내용이 비어 있습니다.` |

- 1에서 걸리면 2~4는 보지 않는다(FastAPI가 서비스 호출 전에 막는다). 2~4는 `Conversation.create` 안에서 이 순서로 검사한다.
- domain도 role 값을 `Role(...)`로 확인한다(스키마를 거치지 않은 호출 대비). 이 경우도 `InvalidConversationError`.
- 규칙 2·3이 동시에 성립하려면 메시지 수는 항상 홀수다. 별도 규칙으로 두지 않는다.
- `max_messages`는 `ConversationLimits`로 받는다. domain은 환경 변수를 읽지 않는다.
- 400 메시지에 요청 원문(`content`)을 넣지 않는다.

## 5. 유스케이스

`api/chat/application/service.py`:

```python
class AskService:
    def __init__(self, generator: AnswerGenerator, limits: ConversationLimits) -> None: ...

    async def ask(self, raw: Sequence[tuple[str, str]]) -> Answer:
        conversation = Conversation.create(raw, self.limits)   # 규칙은 도메인 (R3)
        return await self.generator.generate(conversation)
```

- 검증 실패 시 생성기를 부르지 않는다.
- 생성기가 `AnswerGenerationError`를 내면 그대로 올린다(→ 502). 그 밖의 예외는 500으로 떨어진다(어댑터가 SDK 예외를 바꿀 책임).
- 서비스·생성기는 앱당 하나, 상태 없음.

## 6. 엔드포인트 명세

### `POST /api/v1/chat`

요청 본문 (`ChatRequest`, `Content-Type: application/json`):

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `messages` | array | 예 | 대화 전체. 1개 이상 `API_MAX_MESSAGES`개 이하 (도메인 판정) |
| `messages[].role` | string (`user` \| `assistant`) | 예 | 화자 |
| `messages[].content` | string | 예 | 내용. 앞뒤 공백 제거 후 비어 있으면 안 된다. 길이 한도 없음 |

- 정의되지 않은 추가 필드는 무시한다(pydantic 기본).
- `ChatRequest.to_raw()`가 `[(m.role, m.content), ...]`를 만든다.

응답 `data` (`ChatData`, `SuccessResponse[ChatData]`):

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `answer` | string | 예 | 답변. 비어 있지 않음. `rag` 모드에서는 근거 문장 뒤에 `[n]` |
| `mode` | string (`mock` \| `llm` \| `rag`) | 예 | 생성 방식. `rag`가 아니면 근거 없는 답변 |
| `sources` | array | 예 | 출처. 개수 한도 없음. 생성기 순서·값 그대로. `mock`·`llm`은 `[]` |
| `sources[].ref` | integer | 예 | 출처 번호. `answer` 안 `[n]`의 `n`과 같은 값(체인이 정함) |
| `sources[].chunk_id` | string | 예 | 청크 ID (RAG 메타데이터 그대로) |
| `sources[].source_ref_id` | string | 예 | 도감번호 3자리(예: `001`). [documents](documents.md) 조회 키 |
| `embedding` | object | 아니오 | RAG가 실제 임베딩 정보를 제공한 경우에만 존재. 없으면 `null` 대신 필드 생략 |
| `embedding.query_model` | string | 객체 존재 시 예 | 이번 질의 임베딩에 실제 사용한 모델 ID, 1~200자·공백뿐인 값과 Unicode `C` 범주 문자 금지 |
| `embedding.document_model` | string | 객체 존재 시 예 | 현재 인덱스에 결합된 문서 임베딩 모델 ID, query와 같은 문자열 규칙 |

`ChatData.from_domain(answer)`가 `Answer` → 응답 스키마로 바꾼다. 값을 가공하지 않는다.

`embedding`은 GPT 답변 모델명이 아니다. RAG 서비스가 질의 임베딩 호출 뒤 확인한 query 모델과 인덱스에 결합된 document 모델만 전달한다. API는 환경 변수로 추정하지 않는다. 필드가 없으면 기존 RAG·mock·llm 응답은 `answer`, `mode`, `sources`만 유지한다. 제공된 `embedding`이 `null`·비객체·필수 값 누락·모델 ID 규칙 위반이면 어댑터가 전체 답변을 502 `ANSWER_GENERATION_FAILED`로 거부한다. 요청·저장소·모델 선택에는 변경이 없다.

상태 코드:

| HTTP | `error_code` | 조건 |
| --- | --- | --- |
| 200 | — | 답변 생성 (근거 부족으로 "확인할 수 없다"는 답 포함) |
| 400 | `VALIDATION_ERROR` | 4.2의 1~4 위반 |
| 405 | `METHOD_NOT_ALLOWED` | POST 외 메서드 |
| 502 | `ANSWER_GENERATION_FAILED` | 생성기 실패, 빈 답변, 제공된 임베딩 메타데이터 오류. `message`: `답변을 생성하지 못했습니다. 잠시 후 다시 시도하세요.` |
| 500 | `INTERNAL_ERROR` | 처리 못 한 예외. 원문 비노출 |

예시:

```http
POST /api/v1/chat
{"messages": [
  {"role": "user", "content": "꼬부기는 무슨 타입이야?"},
  {"role": "assistant", "content": "..."},
  {"role": "user", "content": "진화하면?"}
]}
```

```json
{"success": true, "data": {"answer": "[mock] 아직 RAG가 연결되지 않아 고정 응답을 돌려줍니다. 받은 질문: 진화하면?", "mode": "mock", "sources": []}}
```

`rag` 모드 응답 형태(값은 체인이 정한다):

```json
{"success": true, "data": {"answer": "<근거 문장> [1].", "mode": "rag",
  "sources": [{"ref": 1, "chunk_id": "<청크 ID>", "source_ref_id": "001"}]}}
```

실제 임베딩 정보를 제공하는 RAG에서는 같은 `data`에 `"embedding": {"query_model": "<실제 질의 임베딩 모델 ID>", "document_model": "<인덱스 문서 임베딩 모델 ID>"}`가 추가된다. 모델 ID는 생성·추정하지 않는다.

```json
{"success": false, "error_code": "VALIDATION_ERROR", "message": "대화는 user로 시작하고 끝나야 하며 user와 assistant가 번갈아 와야 합니다."}
```

파일 배치:

```text
api/chat/
  __init__.py
  domain/          conversation.py (Role, Message, ConversationLimits, Conversation), answer.py (AnswerMode, Source, EmbeddingInfo, Answer),
                   generator.py (AnswerGenerator), exceptions.py
  application/     service.py (AskService)
  infrastructure/  mock_generator.py, llm_generator.py, rag_generator.py
  presentation/    schemas.py (MessageIn, ChatRequest, SourceOut, EmbeddingOut, ChatData), dependencies.py (provide_ask_service), router.py
```

- router: `APIRouter(prefix="/api/v1", tags=["chat"])`, `POST /chat`, `response_model=SuccessResponse[ChatData]`, `response_model_exclude_none=True`. router에서 `try/except` 하지 않는다(R6).
- container: `create_answer_generator(settings)` — `mock` → `MockAnswerGenerator()`, `llm` → 분기 안에서 `langchain_openai.ChatOpenAI(model=os.environ["OPENAI_CHAT_MODEL"], temperature=0, reasoning_effort=os.environ.get("OPENAI_REASONING_EFFORT", "low"))`를 만들어 `LlmAnswerGenerator`에 넣는다. `rag` → 해당 분기에서만 Solar `create_service`를 import하고 `run_in_threadpool`과 함께 `RagAnswerGenerator`에 넣는다. 서비스·DB·공급자 구성은 실제 요청까지 지연한다. 알 수 없는 값은 시작 시 `RuntimeError`다. `AskService(generator, ConversationLimits(settings.max_messages))`를 `provide_ask_service`에 연결한다.

## 7. 설정

| 변수 | 기본값 | 쓰임 |
| --- | --- | --- |
| `ANSWER_BACKEND` | `mock` | 생성기 선택 `mock` \| `llm` \| `rag`. 알 수 없는 값이면 앱 시작 실패 |
| `API_MAX_MESSAGES` | `20` | 메시지 수 상한 (R11) |
| `OPENAI_CHAT_MODEL` | (`.env.example` 값) | `llm`의 ChatOpenAI와 `rag`의 Solar 공급자가 읽는 답변 모델명. 임베딩 모델 표시에는 사용하지 않는다 |
| `OPENAI_REASONING_EFFORT` | `low` | `llm` 모드 추론 강도. `gpt-6-luna`는 `low`로 쓴다(팀 결정). temperature 0은 유지. `llm` 분기에서만 읽는다 |
| `OPENAI_API_KEY` | (각자) | `llm`의 ChatOpenAI와 `rag`의 Solar 공급자가 서버 환경에서 읽는다. 로그·응답에 남기지 않는다 |

## 8. 테스트 시나리오 (`api/tests/chat/`)

| # | 종류 | 시나리오 | 기대 |
| --- | --- | --- | --- |
| T1 | 도메인 | user 1개, user/assistant/user 3개 | 성공, `question`·`history` 값, `content` strip 됨 |
| T2 | 도메인 | 0개, `max+1`개 | `InvalidConversationError` |
| T3 | 도메인 | assistant로 시작, assistant로 끝남, user/user 연속 | `InvalidConversationError` |
| T4 | 도메인 | content `"   "` | `InvalidConversationError` |
| T5 | 도메인 순서 | `max+1`개이면서 빈 content 포함 | 개수 메시지 (2가 4보다 먼저) |
| T6 | 도메인 순서 | assistant로 시작하면서 빈 content 포함 | 교대 메시지 (3이 4보다 먼저) |
| T7 | 도메인 | `Answer(text=" ", mode=MOCK)` | `AnswerGenerationError` |
| T8 | 도메인 | `Source(ref=3, ...)` 여러 개로 `Answer` | 순서·번호 그대로, 개수 제한 없음 |
| T9 | 서비스 | fake 생성기, 정상 대화 | 생성기가 검증된 `Conversation` 1회 받음 |
| T10 | 서비스 | 잘못된 대화 | `InvalidConversationError`, 생성기 호출 0회 |
| T11 | 어댑터 | `LlmAnswerGenerator(FakeListChatModel(["hello"]))` | `("hello", llm, ())` |
| T12 | 어댑터 | 모델이 `TimeoutError("network down sk-secret")` | `AnswerGenerationError`, `message`에 `sk-secret` 없음 |
| T13 | API 성공 | 기본 wiring(mock), user 1개 | 200, `data.answer` 문자열, `data.mode == "mock"`, `data.sources == []` |
| T14 | API 성공 | fake 생성기가 `sources` 2개(`ref` 1, 2) 반환 | 200, `sources` 값·순서 그대로 |
| T15 | API 400 | `{"messages": []}`, `{}`, JSON 아닌 본문, role `bot`, content 숫자, `max+1`개, 교대 깨짐, 빈 content | 모두 400 `VALIDATION_ERROR`, 공통 에러 형식 |
| T16 | API 502 | 생성기가 `AnswerGenerationError` | 502 `ANSWER_GENERATION_FAILED` |
| T17 | API 500 | 생성기가 `RuntimeError("raw-secret")` (`raise_app_exceptions=False`) | 500 `INTERNAL_ERROR`, 본문에 `raw-secret` 없음 |
| T18 | API | `GET /api/v1/chat` | 405 `METHOD_NOT_ALLOWED` |
| T19 | 도메인·어댑터·API | 실제 RAG embedding 제공 / 미제공, mock·llm | 제공 값 그대로 응답 / 미제공이면 키 자체 생략, 환경으로 보충하지 않음 |
| T20 | 도메인·어댑터·API | embedding null·비객체·누락·빈값·201자·제어문자 | 502 `ANSWER_GENERATION_FAILED`, 원문 값 비노출, 재호출·mock fallback 없음 |

실제 LLM·네트워크를 부르지 않는다. `OPENAI_API_KEY` 없이 통과해야 한다(R15).

## 9. 변경 제안 (설계안 밖 파일)

| 파일 | 제안 |
| --- | --- |
| `docs/references/api-rag-integration.md` §2 `Message` 행 | "앞뒤 공백 제거, 길이 한도 검증 완료" → "앞뒤 공백 제거, 빈 값·개수·순서 검증 완료". 스펙 REQ-3에서 메시지 길이 한도를 없앴는데 문구가 남아 있다 |

## 10. 질문

| 질문 | 임시 기본값 |
| --- | --- |
| 요청 본문의 정의되지 않은 필드(`messages[].name` 등) | 무시 (pydantic 기본). 400으로 막지 않음 |
| `rag` 모드에서 `source_ref_id`가 도감번호 3자리가 아니면 | RAG 어댑터가 기존 pokemon:N 또는 document_id를 세 자리로 변환한다. 지원하지 않는 식별자는502로 거부하고 domain·router는 값을 재가공하지 않는다 |
| `answer`의 `[n]`과 `sources[].ref` 불일치 | API는 검사하지 않는다(체인 책임, 연결 가이드 3절 3) |
| mock 응답에 질문을 몇 자까지 넣을지 | 앞 100자 |
