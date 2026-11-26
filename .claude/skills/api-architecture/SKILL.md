---
name: api-architecture
description: Use when designing api/ slices or wiring DI. Folder layout, 4-layer roles, ports, container.py assembly, RAG seam.
---

# api-architecture

FastAPI 서비스(`api/`)에서 **무엇을 어디에 두고 왜 그렇게 하는가**를 정한다.
규칙 문장의 원본은 [api-invariants](../api-invariants/SKILL.md)(R번호)이고, 계층별 코드는 [api-implementation](../api-implementation/SKILL.md), 자동 검사는 [layer-check](../layer-check/SKILL.md)가 맡는다.

## 1. 저장소 안의 위치

- 서비스는 저장소 루트의 `api/` 패키지 하나다. 별도 `uv init`·`pyproject.toml`을 만들지 않고 루트 `pyproject.toml`(Python 3.13)과 `.venv`를 함께 쓴다.
- import는 `api.` 접두어를 붙인 절대 경로로 쓴다: `from api.chat.domain.conversation import Conversation`. 다른 서비스가 합쳐져도 `shared`, `main` 같은 이름이 서로 겹치지 않는다.
- 실행: `uv run uvicorn api.main:app --port 8000` (저장소 루트에서)
- 테스트는 서비스 안 `api/tests/`에 두고 저장소 관례인 `unittest`로 돌린다. 루트 `tests/` 아래에 `api/` 폴더를 만들면 discover가 `tests/`를 import 기준으로 잡아 `api` 패키지와 이름이 겹친다.
- 모노레포 전체 폴더 규칙(FSD 등)은 **아직 정하지 않았다.** 다른 파트가 합쳐진 뒤 정리할 때 고정한다. 그 전까지 이 스킬은 `api/` 안만 다룬다. 아래 슬라이스 구조는 FSD의 slice/segment와 대응하지만 강제 규칙이 아니라 현재 서비스의 구조다.

## 2. 폴더 구조

```text
api/
  __init__.py
  main.py              앱 생성, load_dotenv, CORS, 예외 핸들러·의존성 연결, 라우터 등록 (조립 지점)
  container.py         추상 ↔ 구현체 연결, ANSWER_BACKEND에 따른 생성기 선택 (조립 지점)
  error_handlers.py    shared 예외 → 공통 에러 응답 변환
  shared/
    __init__.py
    exceptions.py      기반 예외 (순수 파이썬, domain도 import 가능)
    settings.py        환경 변수 읽기 (domain은 import 금지)
  health/
    __init__.py
    presentation/      router.py — 규칙이 없으므로 presentation만 둔다
  chat/
    __init__.py
    domain/            conversation.py, answer.py, generator.py(AnswerGenerator ABC), exceptions.py
    application/       service.py (AskService)
    infrastructure/    mock_generator.py, llm_generator.py (나중에 rag_generator.py)
    presentation/      schemas.py, dependencies.py(provide_*), router.py
  tests/
    __init__.py
    chat/ ...
```

- 슬라이스(health, chat)는 기능 단위 묶음이다. 필요한 계층 폴더만 만든다. 만든 폴더에는 `__init__.py`를 둔다.
- 여러 슬라이스가 쓰는 코드는 `shared/`에 둔다. 슬라이스 안에 다른 슬라이스용 공용 코드를 두지 않는다.
- 새 슬라이스는 설계안(`docs/design/api/<slice>.md`)부터 만든다. 목록은 [설계안 목록](../../../docs/design/api/README.md)에 링크한다.

## 3. 계층 책임

| 계층 | 책임 | 파일 |
| --- | --- | --- |
| presentation | 요청·응답 스키마(Pydantic), 라우터, 주입 지점(`provide_*`). 스키마 ↔ 도메인 객체 변환 | `schemas.py`, `router.py`, `dependencies.py` |
| application | 유스케이스 흐름. 도메인 객체를 만들고 추상 생성기를 호출해 결과를 돌려준다 | `service.py` |
| domain | 엔티티·값 객체, 규칙 메서드, 슬라이스 예외, **추상 인터페이스(포트)** | `<엔티티>.py`, `generator.py`, `exceptions.py` |
| infrastructure | 포트 구현체. LLM·RAG 체인·외부 API 호출과 그 SDK 예외를 도메인 예외로 바꾸는 일 | `*_generator.py` |
| 조립 | 구현체 선택과 연결 | `api/container.py`, `api/main.py` |

```text
presentation ──▶ application ──▶ domain ◀── infrastructure
      ▲                                          ▲
      └──────────── api/container.py ────────────┘  (조립 지점만 양쪽을 안다)
```

- DB가 없으므로 레포지토리·ORM 모델·트랜잭션 계층이 없다(R10). 외부 의존은 답변 생성기 하나다.
- 상태 저장이 필요해지면(대화 기록 등) 이 스킬과 R10을 먼저 바꾸고 설계안을 새로 쓴다.

## 4. 도메인 설계 원칙

- 용어는 코드·설계안·API 필드에서 같게 쓴다: `Conversation`(한 요청의 대화), `Message`(role, content), `Answer`(text, sources, mode), `Source`(chunk_id, source_ref_id).
- 규칙은 엔티티의 생성 팩토리에 둔다. 예: `Conversation.create(messages, limits)`가 빈 대화, 마지막 메시지가 user가 아님, 메시지 수·길이 초과, 알 수 없는 role을 검사하고 슬라이스 예외를 낸다(R3, R11).
- 한도 값은 domain이 환경 변수를 읽지 않고 `ConversationLimits` 값 객체로 받는다. 읽는 일은 `shared/settings.py`, 넘기는 일은 container가 한다.
- 답변의 출처 형식은 RAG 청크 메타데이터 이름(`chunk_id`, `source_ref_id`)을 따른다. mock·llm 모드에서는 `sources`가 빈 목록이다.

## 5. 포트: AnswerGenerator

```python
# api/chat/domain/generator.py
from abc import ABC, abstractmethod

from api.chat.domain.answer import Answer
from api.chat.domain.conversation import Conversation


class AnswerGenerator(ABC):
    @abstractmethod
    async def generate(self, conversation: Conversation) -> Answer: ...
```

- 계약의 원본과 RAG 연결 절차는 [API–RAG 연결 가이드](../../../docs/references/api-rag-integration.md)다(R9).
- 구현체 이름은 `<방식>AnswerGenerator`다: `MockAnswerGenerator`, `LlmAnswerGenerator`, 나중에 `RagAnswerGenerator`.
- 구현체는 SDK 예외를 그대로 올리지 않고 `AnswerGenerationError`(502)로 바꾼다. 원문 오류는 로그에만 남기고 응답에 넣지 않는다(R7).
- `Answer.mode`는 구현체가 정한다(`mock` | `llm` | `rag`). 프론트와 평가가 근거 있는 답인지 구분하는 값이다.

## 6. 조립

### 6.1 플레이스홀더 — `presentation/dependencies.py`

```python
from api.chat.application.service import AskService


def provide_ask_service() -> AskService:
    """FastAPI Depends 플레이스홀더 (api/container.py에서 연결)"""
    raise NotImplementedError("AskService 의존성이 연결되지 않았습니다.")
```

### 6.2 컨테이너 — `api/container.py`

- `ANSWER_BACKEND`(`mock` | `llm`, 나중에 `rag`) 값으로 생성기를 하나 고른다. 알 수 없는 값이면 앱 시작 시점에 실패시킨다(요청 때 500이 나는 것보다 낫다).
- 생성기와 서비스는 상태가 없으므로 앱당 하나를 만들어 재사용한다(R10).
- `wire_dependencies(app)`가 `app.dependency_overrides`에 `provide_*` → 팩토리를 모두 연결한다(R5).
- 테스트는 같은 `dependency_overrides`로 fake 생성기를 넣는다.

### 6.3 등록 — `api/main.py`

`load_dotenv()` → `FastAPI()` → CORS(환경 변수 목록, R13) → `register_exception_handlers(app)` → `wire_dependencies(app)` → `include_router(...)` 순서다. 앱 객체는 `create_app()` 함수로 만들어 테스트가 설정을 바꿔 다시 만들 수 있게 한다.

## 7. 새 슬라이스 체크리스트

1. 설계안 `docs/design/api/<slice>.md` 작성, 목록 README에 링크 (api-architect)
2. `domain/`: 엔티티(규칙 메서드), `exceptions.py`, 필요하면 포트(ABC)
3. `infrastructure/`: 포트 구현체
4. `application/service.py`: 추상만 받는 생성자
5. `presentation/`: `schemas.py`, `dependencies.py`, `router.py`
6. `api/container.py` 팩토리와 매핑, `api/main.py` 라우터 등록
7. `api/tests/<slice>/` 테스트
8. [api-invariants §7](../api-invariants/SKILL.md) 완료 게이트
