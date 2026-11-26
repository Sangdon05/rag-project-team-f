---
name: api-architecture
description: Use when designing api/ slices or wiring its DI. How api/ applies the generic layered and FSD skills: layout, slices, ports.
---

# api-architecture

`api/` 서비스가 공통 스킬 [layered-architecture](../layered-architecture/SKILL.md)와 [fsd-architecture](../fsd-architecture/SKILL.md)를 **어떻게 적용하는지**만 적는다.
계층 책임·의존 방향·포트·조립 원칙은 공통 스킬이 원본이며 여기서 다시 쓰지 않는다. 규칙 문장(R번호)은 [api-invariants](../api-invariants/SKILL.md)가 원본이다.

## 1. 서비스 위치

- 저장소 루트의 `api/` 패키지 하나다. 별도 `uv init`·`pyproject.toml` 없이 루트 `pyproject.toml`(Python 3.13)과 `.venv`를 쓴다.
- import는 `api.`로 시작하는 절대 경로다: `from api.chat.domain.conversation import Conversation`.
- 테스트는 `api/tests/`에 두고 저장소 관례인 `unittest`로 돌린다. 루트 `tests/api/`에 두면 discover가 `tests/`를 import 기준으로 잡아 `api` 이름이 겹친다.
- 공통 스킬에 주입하는 값: layer-check 프로파일 [layer-profile.json](../api-invariants/layer-profile.json), 실행 정보는 api-invariants "실행 확인" 절.
- FSD 슬라이스 간 규칙은 프로파일에서 `off`다. 모노레포 구조를 정리할 때 `warn`·`error`로 올릴지 정한다.

## 2. 서비스 전제

- DB가 없다. 데이터와 벡터 DB는 RAG 쪽이 관리하고 API는 중개만 한다. 그래서 레포지토리·ORM·트랜잭션 계층이 없다(R10).
- 로그인·계정이 없다. 대화 맥락은 프론트가 매 요청 `messages[]`로 보낸다.
- 외부 의존은 포트 세 개다: 답변 생성기(chat), 문서 저장소(documents), 추천 질문 제공자(suggestion, 지금은 fake 데이터).

## 3. 폴더

```text
api/
  __init__.py
  main.py              create_app: load_dotenv, CORS, 예외 핸들러, 의존성 연결, 라우터 등록 (app)
  container.py         ANSWER_BACKEND에 따른 생성기 선택, 슬라이스별 구현체 연결 (app)
  error_handlers.py    shared 예외 → 공통 에러 응답 (app)
  shared/
    exceptions.py      기반 예외 (순수 파이썬, domain도 import 가능)
    settings.py        환경 변수 읽기 (domain은 import 금지)
    responses.py       SuccessResponse[T], ErrorResponse (presentation·error_handlers만)
  health/
    presentation/      schemas.py, router.py — presentation만
  suggestion/          domain(SuggestionProvider 포트) / application / infrastructure(fake 제공자) / presentation
  documents/           domain(SourceRefId, DocumentStore 포트) / application / infrastructure(file_store.py) / presentation
  chat/
    domain/            conversation.py, answer.py, generator.py(포트), exceptions.py
    application/       service.py (AskService)
    infrastructure/    mock_generator.py, llm_generator.py (나중에 rag_generator.py)
    presentation/      schemas.py, dependencies.py(provide_*), router.py
  tests/
    health/ suggestion/ chat/ documents/ ...
```

폴더마다 `__init__.py`를 둔다. 새 슬라이스는 설계안 `docs/design/api/<slice>.md`부터 만들고 [설계안 목록](../../../docs/design/api/README.md)에 링크한다.

## 4. 도메인 용어

| 이름 | 뜻 |
| --- | --- |
| `Conversation` | 한 요청의 대화. `create(raw, limits)`가 빈 대화·빈 메시지·순서·role·수를 검증 (R3, R11) |
| `Message` | `role`(user \| assistant), `content` |
| `ConversationLimits` | 메시지 수 한도 값 객체 (환경 변수 값은 container가 넘김) |
| `Answer` | `text`, `mode`(mock \| llm \| rag), `sources` |
| `Source` | `ref`, `chunk_id`, `source_ref_id` (RAG 값 그대로. `source_ref_id`는 도감번호 3자리) |
| `DocumentStore` | documents 슬라이스 포트. `get(source_ref_id) -> str` ([연결 가이드](../../../docs/references/api-rag-integration.md)) |

## 5. 포트: AnswerGenerator

```python
class AnswerGenerator(ABC):
    @abstractmethod
    async def generate(self, conversation: Conversation) -> Answer: ...
```

- 계약 원본과 RAG 연결 절차: [API–RAG 연결 가이드](../../../docs/references/api-rag-integration.md) (R9).
- 구현체: `MockAnswerGenerator`, `LlmAnswerGenerator`, 나중에 `RagAnswerGenerator`. SDK 예외는 `AnswerGenerationError`(502)로 바꾼다 (R7).
- `Answer.mode`는 구현체가 정한다. 프론트가 근거 있는 답인지 구분하는 값이다.

## 6. 조립

- `container.py`: `ANSWER_BACKEND`(`mock` | `llm`, 나중에 `rag`)로 생성기를 하나 고른다. 알 수 없는 값이면 시작 시점에 실패. `llm`일 때만 `langchain_openai`를 import한다. 서비스·생성기는 앱당 하나.
- 주입 지점: `provide_ask_service` → `wire_dependencies(app, settings)`가 연결.
- `main.py`: `create_app(settings=None)`. 테스트는 설정을 직접 넘긴다.

## 7. 새 슬라이스 체크리스트

1. 설계안 작성·목록 링크 (api-architect)
2. [layered-architecture §6](../layered-architecture/SKILL.md) 순서로 구현 (api-implementer)
3. `container.py` 연결, `main.py` 라우터 등록, `api/tests/<slice>/`
4. [api-invariants §7](../api-invariants/SKILL.md) 완료 게이트
