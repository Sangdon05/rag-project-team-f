# API–RAG 연결 가이드

FastAPI 서비스(`api/`)와 RAG 체인을 잇는 계약과 절차다. 지금은 체인이 완성되지 않아 API가 mock 또는 검색 없는 LLM으로 답한다.
RAG가 완성되면 이 문서대로 생성기 하나를 추가해 연결한다. API의 router·서비스·응답 스키마는 바꾸지 않는다.

- 이 문서는 답변 생성기 계약의 원본이다([api-invariants](../../.claude/skills/api-invariants/SKILL.md) R9). 계약을 바꾸려면 이 문서를 먼저 고친다.
- API 구조: [api-architecture](../../.claude/skills/api-architecture/SKILL.md) / 체인: [langchain-rag](../../.claude/skills/langchain-rag/SKILL.md)

## 1. 현재 상태

| `ANSWER_BACKEND` | 구현체 | 답변 | `sources` | 용도 |
| --- | --- | --- | --- | --- |
| `mock` (기본) | `MockAnswerGenerator` | 고정 문구 + 받은 질문 | 빈 목록 | 프론트 연동, 테스트, smoke |
| `llm` | `LlmAnswerGenerator` | 검색 없이 LLM이 답함 (Red·Blue 기준 시스템 프롬프트) | 빈 목록 | 임시 데모. 근거가 없으므로 평가에 쓰지 않는다 |
| `rag` (예정) | `RagAnswerGenerator` | RAG 체인 답변 | 근거 청크 | 연결 후 기본값 후보 |

응답의 `mode`로 어떤 방식으로 답했는지 구분한다. 프론트는 `mode`가 `rag`가 아니면 "근거 없는 답변"임을 표시할 수 있다.

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
| `Message` | `role: "user" \| "assistant"`, `content: str` | 앞뒤 공백 제거, 길이 한도 검증 완료 |
| `Answer` | `text: str` | 비어 있으면 안 됨 |
| | `mode: "mock" \| "llm" \| "rag"` | 생성 방식 |
| | `sources: tuple[Source, ...]` | 근거. 근거가 없으면 빈 목록 |
| `Source` | `chunk_id`, `source_ref_id` | [chunking 스킬](../../.claude/skills/chunking/SKILL.md)의 청크 메타데이터 이름 그대로 |

실패 규약:

- 체인이 답을 만들지 못하면(네트워크, 모델, DB 오류) 어댑터가 `AnswerGenerationError`로 바꿔 올린다 → 502 `ANSWER_GENERATION_FAILED`. 원문 오류는 로그에만 남긴다.
- "근거가 부족해 확인할 수 없다"는 실패가 아니라 정상 답변이다. 체인이 그런 답을 내면 `text`에 담고 `sources`는 빈 목록으로 돌려준다.
- 체인 안에서 대화 기록을 저장하지 않는다. 대화 맥락은 매 요청의 `messages`로만 받는다.

HTTP 쪽 계약(프론트와의 계약)은 `POST /api/v1/chat` 요청 `{"messages": [{"role", "content"}]}`, 응답 `{"answer", "sources": [{"chunk_id", "source_ref_id"}], "mode"}`이다. 세부 명세는 설계안([목록](../design/api/README.md))이 원본이다.

## 3. 연결 전에 RAG 쪽이 준비할 것

rag-developer 담당이다. 아래가 갖춰지기 전에는 API에서 연결 작업을 시작하지 않는다.

1. **import 가능한 진입점.** API 어댑터가 부를 함수 또는 객체 하나. 예: `answer(question: str, history: list[dict]) -> {"answer": str, "sources": [...]}` (비동기면 더 좋다).
   - 지금 체인 코드는 패키지가 아니다. 진입점의 위치(예: `src/pokedex/`)와 import 방법(루트 `pyproject.toml`의 패키지 설정 등)은 [미정]이다. 정해지면 이 절에 적는다.
2. **설정은 환경 변수로.** 모델명, `DATABASE_URL`, `PGVECTOR_COLLECTION` 등을 체인이 직접 읽는다. API는 DB 접속 정보를 알지 않는다.
3. **출처 형식.** 답변 근거를 `chunk_id`, `source_ref_id`로 돌려준다.
4. **동작 확인 기록.** 툴·체인 테스트 통과, 사용한 `index_version` 기록(langchain-rag 스킬의 완료 조건).

## 4. 연결 절차

| 단계 | 담당 | 내용 |
| --- | --- | --- |
| 1 | 오케스트레이터 | 3절 준비 상태 확인, api-architect에게 설계안 갱신 발주 (`rag` 백엔드, 에러, 타임아웃) |
| 2 | api-implementer | `api/chat/infrastructure/rag_generator.py`에 `RagAnswerGenerator` 작성. 체인 진입점을 생성자로 받고, 결과를 `Answer(mode=rag)`와 `Source`로 바꾸고, 예외를 `AnswerGenerationError`로 바꾼다 |
| 3 | api-implementer | `api/container.py`에 `ANSWER_BACKEND=rag` 분기 추가. 체인 import는 이 분기 안에서만 한다(mock 모드는 체인·DB 없이 떠야 한다) |
| 4 | api-implementer | 테스트: fake 체인으로 변환·예외 처리 확인. 실제 체인·DB를 부르지 않는다 |
| 5 | api-reviewer | 완료 게이트, smoke(mock), 발주서에 명시되면 `rag` 모드 실제 호출 1~2회 |
| 6 | 오케스트레이터 | `.env.example`의 `ANSWER_BACKEND` 설명 갱신, 기본값 변경 여부 판정 |

연결 뒤에도 RAG 품질 평가는 API를 거치지 않고 Eval이 체인을 직접 실행한다. API는 중개만 하므로 API 변경은 평가 재실행 대상이 아니다. 체인의 입출력이 바뀌면 이 문서의 계약과 어댑터만 고친다.

## 5. 담당 경계

| 바꾸는 것 | 담당 | API 쪽 후속 |
| --- | --- | --- |
| 프롬프트, 검색 설정, 툴, 체인 내부 | rag-developer | 없음 |
| 체인 진입점 시그니처, 반환 형식, 출처 필드 | rag-developer | 이 문서 갱신 → api-implementer에게 어댑터 수정 발주 |
| 청크 메타데이터 이름 | data-engineer | `Source` 필드 확인 |
| `api/` 코드 | api-implementer | — |
| `LlmAnswerGenerator`의 임시 시스템 프롬프트 | api-implementer | RAG 연결 후 `llm` 모드를 남길지 오케스트레이터가 판정 |

## 6. 전환 체크리스트

- [ ] 3절 준비 항목 4개 충족
- [ ] 설계안에 `rag` 백엔드와 에러·타임아웃 명세 반영
- [ ] `RagAnswerGenerator` + 테스트 (fake 체인)
- [ ] `ANSWER_BACKEND=mock`으로 서버가 체인·DB 없이 기동
- [ ] api-invariants 완료 게이트, smoke 통과
- [ ] `.env.example`, environment.md, README 환경 변수 설명 갱신
- [ ] 이 문서 1절 표의 `rag` 행을 "예정"에서 실제 상태로 갱신
