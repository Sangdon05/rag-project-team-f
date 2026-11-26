# API–RAG 연결 가이드

FastAPI 서비스(`api/`)와 RAG 체인을 잇는 계약과 절차다. Solar 대화 서비스가 준비된 환경에서는 RAG 생성기로 연결한다. mock은 외부 호출 없이 프론트를 검사하며 llm은 검색 없는 임시 답변이다.
어댑터는 생성기 포트를 구현한다. 선택 응답 필드를 추가할 때는 이 계약과 설계안을 먼저 갱신하고 기존 필드와 요청 형식은 유지한다.

- 이 문서는 답변 생성기 계약의 원본이다([api-invariants](../../.claude/skills/api-invariants/SKILL.md) R9). 계약을 바꾸려면 이 문서를 먼저 고친다.
- API 구조: [api-architecture](../../.claude/skills/api-architecture/SKILL.md) / 체인: [langchain-rag](../../.claude/skills/langchain-rag/SKILL.md)

## 1. 현재 상태

| `ANSWER_BACKEND` | 구현체 | 답변 | `sources` | 용도 |
| --- | --- | --- | --- | --- |
| `mock` (기본) | `MockAnswerGenerator` | 고정 문구 + 받은 질문 | 빈 목록 | 프론트 연동, 테스트, smoke |
| `llm` | `LlmAnswerGenerator` | 검색 없이 LLM이 답함 (Red·Blue 기준 시스템 프롬프트) | 빈 목록 | 임시 데모. 근거가 없으므로 평가에 쓰지 않는다 |
| `rag` | `RagAnswerGenerator` | Solar 대화의 일반 검색, 팀·기술 정형 조회 또는 확인 질문 | 인용한 포켓몬 청크. 포켓몬 인용이 없으면 빈 목록 | 경로에 따라 GPT, DB 및 Solar 설정을 사용 |

응답의 `mode`는 답변 생성기를 구분한다. `rag`가 검색이나 임베딩 호출을 뜻하지는 않는다. Solar 대화는 GPT에 단일 도구를 선택하도록 요청한다. 일반 검색만 A/B/C 정책을 쓰며, 정형 경로는 필요한 청크를 ID로 읽어 계산 결과를 서버가 표시한다(후속 GPT 호출 없음). 확인 질문에는 DB를 쓰지 않는다. 내부 동작은 [langchain-rag 스킬](../../.claude/skills/langchain-rag/SKILL.md)을 따른다.

## 2. 계약

API 쪽 포트(`api/chat/domain/generator.py`):

```python
class AnswerGenerator(ABC):
    async def generate(self, conversation: Conversation) -> Answer: ...
```

| 타입 | 필드 | 뜻 |
| --- | --- | --- |
| `Conversation` | `messages: tuple[Message, ...]` | 프론트가 보낸 대화 전체. 마지막은 항상 user 질문 (API가 검증해서 넘김) |
| | `question` | 마지막 user 메시지 |
| | `history` | 질문 앞의 대화 (user/assistant 교대) |
| `Message` | `role: "user" \| "assistant"`, `content: str` | 앞뒤 공백 제거, 빈 값·개수·순서 검증 완료 (길이 한도 없음) |
| `Answer` | `text: str` | 비어 있으면 안 됨 |
| | `mode: "mock" \| "llm" \| "rag"` | 생성 방식 |
| | `sources: tuple[Source, ...]` | 근거. 근거가 없으면 빈 목록 |
| | `embedding: EmbeddingInfo \| None = None` | 표시용 임베딩 모델 정보. `mode=rag`에서 서비스가 실제 사용 정보를 제공한 경우에만 허용하며 없으면 HTTP 응답에서 필드 자체를 생략한다. mock·llm에서 제공하면 `AnswerGenerationError` |
| `EmbeddingInfo` | `query_model: str`, `document_model: str` | 이번 질의 임베딩에 실제 사용한 모델과 현재 인덱스에 결합된 문서 임베딩 모델. 각 값은 공백만으로 이루어지지 않은 1~200자 문자열이며 Unicode 제어·형식·서로게이트 등 `C` 범주 문자를 허용하지 않는다. 답변 생성 GPT 모델이 아니다 |
| `Source` | `ref: int` | 출처 번호. Solar 대화 서비스가 검증된 근거의 본문 첫 등장 순서로 청크당 한 번호를 붙인다. `text` 안의 `[n]`과 같으며, API는 번호를 바꾸거나 목록을 자르지 않는다 |
| | `chunk_id`, `source_ref_id` | [chunking 스킬](../../.claude/skills/chunking/SKILL.md)의 청크 메타데이터 값 그대로. `source_ref_id`는 도감번호 3자리(예: `001`)이며 문서 조회 키로 쓴다. 체인이 `source_ref_id`를 주지 않으면 `rag` 어댑터가 `document_id`(`pokemon:{id}`)에서 `f"{id:03d}"`로 만든다(저장된 메타데이터·임베딩은 바꾸지 않는다) |

실패 규약:

- 네트워크, DB, 모델 응답 봉투·JSON·일반 답변 유효성 오류는 어댑터가 `AnswerGenerationError`로 바꿔 올린다 → 502 `ANSWER_GENERATION_FAILED`. 원문 오류나 모델 원문을 응답에 노출하지 않는다.
- 확인 질문 또는 "근거가 부족해 확인할 수 없다"는 안내는 정상 `rag` 답변이다. 인용한 포켓몬 청크가 없으면 `sources`는 빈 목록이다.
- 일반 검색의 완성된 답변이 인용만 누락하거나 잘못 참조하면, 답변 전체를 버리고 고정된 한국어 안내와 빈 `sources`를 HTTP 200 `mode=rag`로 반환한다. 실제 사용이 확인된 `embedding`만 유지하며 재호출하지 않는다. 이 경우 502 실패 이벤트 대신 별도 인용 거부 이벤트를 남긴다.
- 체인 안에서 대화 기록을 저장하지 않는다. 대화 맥락은 매 요청의 `messages`로만 받는다.
- RAG 반환값의 선택 `embedding`은 `{"query_model": str, "document_model": str}`이다. 질의 임베딩 호출 뒤 확인한 실제 query 모델과 인덱스에 결합된 document 모델만 사용한다. 정형 조회·확인 질문 등 질의 임베딩을 호출하지 않은 응답은 필드를 생략한다. API는 환경 변수나 답변 모델명으로 추정·보충하지 않는다. 필드가 제공됐지만 `null`·비객체·필수 값 누락·잘못된 모델 ID인 경우에는 전체 답변을 502 `ANSWER_GENERATION_FAILED`로 거부한다. mock·llm 및 이 필드를 제공하지 않는 기존 RAG는 기존 세 필드 응답을 유지한다.

### Solar 어댑터의 문서 ID 변환

일반 검색과 정형 조회 모두, Solar 대화 서비스는 인용한 포켓몬 청크에 `source_ref_id="pokemon:7"` 같은 값을 반환한다. 어댑터는 검증한 `pokemon:1`–`pokemon:151`을 `001`–`151`로 바꾸고 이미 세 자리인 ID는 유지한다. `source_ref_id`가 없으면 `document_id`를 같은 규칙으로 사용한다. 답변·`ref`·`chunk_id`·출처 순서는 바꾸지 않고 잘못된 ID나 non-rag 결과는 502로 처리한다. DB·임베딩 메타데이터는 변경하지 않는다.

기술 분류의 근거는 번호가 아니라 답변 본문에 표시한다. 예: `move:133` · `data/processed/red_blue_move_damage_classification.json#/moves/132` · `status` (`SPECIAL_UP2_EFFECT`). 기술 레코드는 포켓몬 문서가 아니므로 `sources`나 문서 조회 키에 넣지 않는다. 포켓몬 근거가 필요 없는 변화기 등의 답변은 `sources: []`여도 기술 레코드 근거를 본문에 포함할 수 있다. HTTP 요청·응답 스키마는 바꾸지 않는다.

### 문서 저장소 포트

출처 원문을 돌려주는 두 번째 경계다. API 쪽 포트(`api/documents/domain/store.py`):

```python
class DocumentStore(ABC):
    async def get(self, source_ref_id: str) -> str: ...   # 원문 Markdown
```

- 구현체는 `<API_DOCUMENTS_DIR>/<source_ref_id>_*.md`(예: `solar_handoff/documents/001_이상해씨.md`)를 읽는다. 같은 번호 파일이 둘 이상이면 502다. API는 파일을 읽기만 하고 고치지 않는다.
- 파일이 없으면 `DocumentNotFoundError` → 404 `DOCUMENT_NOT_FOUND`. 읽기 실패는 `DocumentSourceError` → 502 `DOCUMENT_SOURCE_FAILED`.
- 문서 파일 위치·이름 규칙은 RAG 쪽(chunking 스킬)이 원본이다. 바뀌면 `API_DOCUMENTS_DIR`만 바꾼다.

### HTTP 계약

프론트와의 계약이다. 모든 응답은 공통 형식 `{"success": true, "data": {...}}` / `{"success": false, "error_code", "message"}`이다.

| 엔드포인트 | `data` |
| --- | --- |
| `POST /api/v1/chat` (요청 `{"messages": [{"role", "content"}]}`) | `{"answer", "mode", "sources": [{"ref", "chunk_id", "source_ref_id"}]}`. 실제 RAG 임베딩 정보가 제공된 경우에만 `"embedding": {"query_model", "document_model"}` 추가 |
| `GET /api/v1/documents/{source_ref_id}` | `{"source_ref_id", "markdown"}` |
| `GET /api/v1/suggestion?level=` | `{"level", "suggestions": [{"id", "text"}]}` (RAG와 무관) |

세부 명세는 설계안([목록](../design/api/README.md))이 원본이다. 요구사항 원본은 [API 엔드포인트 스펙](../archives/specs/2026-11-26-api-endpoints.md) 3절이다(완료·보관).

## 3. 연결 전에 RAG 쪽이 준비할 것

API 쪽에서 요구하는 연결 전제 조건이다. RAG 에이전트·스킬에 API 작업을 넣지 않는다. 오케스트레이터가 RAG 산출물로 충족 여부를 확인하고, 갖춰지기 전에는 API에서 연결 작업을 시작하지 않는다.

1. **import 가능한 진입점.** API 어댑터가 부를 함수 또는 객체 하나. 예: `answer(question: str, history: list[dict]) -> {"answer": str, "sources": [...]}` (비동기면 더 좋다).
   - `solar_handoff.src.conversation.create_service().answer(messages)`가 동기 진입점이다. 어댑터는 전체 대화를 role/content 목록으로 넘기고 조립부가 주입한 스레드 실행기로 호출한다. 서비스는 질문 UTF-8 3,800바이트·총 대화128,000바이트 제한을 별도로 검증하며 위반은400으로 변환한다.
2. **설정은 환경 변수로.** GPT와 Solar 모델명, 필요한 경우 `DATABASE_URL` 등은 Solar 서비스가 읽는다. API는 DB에 직접 접속하지 않는다.
3. **출처 형식.** 대화 서비스의 `ref`, `chunk_id`, `source_ref_id`를 사용한다. 본문 `[n]`은 `ref`와 맞아야 하며 HTTP의 `source_ref_id`는 2절의 변환을 거친 도감번호다. 단일 질문 CLI 트레이스는 이 어댑터의 입력이 아니다.
4. **동작 확인 기록.** 툴·체인 테스트 결과와 실 인덱스를 쓴 경우의 `index_version`을 기록한다. [Solar 전달본](../../solar_handoff/README.md)의 새 대화 검증은 가짜 Responses와 인메모리 청크를 연결한 오프라인 검증이며 실 인덱스나 실제 모델의 품질을 확인한 것은 아니다.

## 4. 연결 절차

| 단계 | 담당 | 내용 |
| --- | --- | --- |
| 1 | 오케스트레이터 | 3절 준비 상태 확인, api-architect에게 설계안 갱신 발주 (`rag` 백엔드, 에러, 타임아웃) |
| 2 | api-implementer | `api/chat/infrastructure/rag_generator.py`에 `RagAnswerGenerator` 작성. 체인 진입점을 생성자로 받고, 결과를 `Answer(mode=rag)`와 `Source`로 바꾸고(`source_ref_id`가 없으면 `document_id` `pokemon:{id}` → `{id:03d}`, 형식이 다르면 `AnswerGenerationError`), 예외를 `AnswerGenerationError`로 바꾼다 |
| 3 | api-implementer | `api/container.py`에 `ANSWER_BACKEND=rag` 분기 추가. 체인 import는 이 분기 안에서만 한다(mock 모드는 체인·DB 없이 떠야 한다) |
| 4 | api-implementer | 테스트: fake 체인으로 변환·예외 처리 확인. 실제 체인·DB를 부르지 않는다 |
| 5 | api-reviewer | 완료 게이트, smoke(mock), 발주서에 명시되면 `rag` 모드 실제 호출 1~2회 |
| 6 | 오케스트레이터 | `.env.example`의 `ANSWER_BACKEND` 설명 갱신, 기본값 변경 여부 판정 |

연결 뒤에도 RAG 품질 평가는 API를 거치지 않고 Eval이 체인을 직접 실행한다. API는 중개만 하므로 API 변경은 평가 재실행 대상이 아니다. 체인의 입출력이 바뀌면 이 문서의 계약과 어댑터만 고친다.

## 5. 담당 경계

| 바꾸는 것 | 담당 | API 쪽 후속 |
| --- | --- | --- |
| 프롬프트, 검색 설정, 툴, 체인 내부 | rag-developer | 없음 |
| 체인 진입점 시그니처, 반환 형식, 출처 필드 | rag-developer | 오케스트레이터가 이 문서 갱신 → api-implementer에게 어댑터 수정 발주 |
| 청크 메타데이터 이름 | data-engineer | `Source` 필드 확인 |
| `api/` 코드 | api-implementer | — |
| `LlmAnswerGenerator`의 임시 시스템 프롬프트 | api-implementer | RAG 연결 후 `llm` 모드를 남길지 오케스트레이터가 판정 |

## 6. 전환 체크리스트

- [ ] 3절 준비 항목 4개 충족
- [ ] 설계안에 `rag` 백엔드와 에러·타임아웃 명세 반영
- [x] `RagAnswerGenerator` + 테스트 (fake 체인)
- [x] `ANSWER_BACKEND=mock`으로 서버가 체인·DB 없이 기동 (API 엔드포인트 계획 smoke로 확인)
- [x] api-invariants 완료 게이트, smoke 통과 (2026-11-26 main 3945d46: 게이트 4개 통과, mock smoke 모두 PASS, `rag` 실제 호출 2회 200)
- [x] `.env.example`, environment.md, README 환경 변수 설명 갱신
- [x] 이 문서 1절 표의 `rag` 행을 실제 구현으로 갱신
