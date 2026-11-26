# api/ 테스트 작성법

저장소 관례대로 표준 라이브러리 `unittest`를 쓴다(pytest는 설치돼 있지 않다). 비동기 테스트는 `unittest.IsolatedAsyncioTestCase`로 쓴다.

## 위치와 실행

- 테스트는 `api/tests/<slice>/test_*.py`에 둔다. `api/tests/`와 그 아래 폴더마다 `__init__.py`를 둔다(없으면 discover가 들어가지 않는다).
- 루트 `tests/api/`에 두지 않는다. `discover -s tests`가 `tests/`를 import 기준으로 잡아 `tests/api`가 `api` 패키지 이름을 가로챈다.
- 실행(저장소 루트에서):

  ```bash
  uv run python -m unittest discover -s api/tests -t . -v
  ```

  `-t .`이 있어야 테스트가 `api.tests...`로 import되고 `from api.chat...`이 동작한다.
- 테스트는 실제 LLM·네트워크를 부르지 않는다. `OPENAI_API_KEY`가 비어 있어도 통과해야 한다(R15). skip으로 통과시키지 않는다.

## 테스트 종류

| 종류 | 무엇을 | 방법 |
| --- | --- | --- |
| 도메인 단위 | `Conversation.create` 규칙, 예외 클래스, `question` | 동기 `unittest.TestCase` |
| 서비스 | 생성기에 넘어가는 대화, 잘못된 입력이면 생성기를 부르지 않음 | `IsolatedAsyncioTestCase` + fake `AnswerGenerator` |
| 생성기 어댑터 | 응답 변환, `mode`, SDK 예외 → `AnswerGenerationError`, 예외 메시지에 원문 없음 | `FakeListChatModel`(langchain_core) 주입 |
| API | 상태 코드, 응답 본문, 공통 에러 형식, 기본 wiring(mock) | `httpx.AsyncClient` + `ASGITransport`, `dependency_overrides` |

슬라이스 예외는 전용 클래스로 확인한다(`assertRaises(InvalidConversationError)`). `ValueError`로 확인하면 엉뚱한 버그도 통과한다.

## fake 생성기

```python
class FakeGenerator(AnswerGenerator):
    def __init__(self):
        self.calls = []

    async def generate(self, conversation):
        self.calls.append(conversation)
        return Answer(text="fake", mode=AnswerMode.MOCK)
```

## LLM 어댑터

```python
from langchain_core.language_models.fake_chat_models import FakeListChatModel


class BrokenModel(FakeListChatModel):
    async def ainvoke(self, *args, **kwargs):
        raise TimeoutError("network down sk-secret")


class LlmGeneratorTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_llm_mode_without_sources(self):
        answer = await LlmAnswerGenerator(FakeListChatModel(responses=["hello"])).generate(CONV)
        self.assertEqual((answer.text, answer.mode, answer.sources), ("hello", AnswerMode.LLM, ()))

    async def test_sdk_error_becomes_domain_error_without_detail(self):
        with self.assertRaises(AnswerGenerationError) as ctx:
            await LlmAnswerGenerator(BrokenModel(responses=["x"])).generate(CONV)
        self.assertNotIn("sk-secret", ctx.exception.message)
```

## API

```python
SETTINGS = Settings(answer_backend="mock", cors_origins=["http://localhost:5173"], max_messages=20, documents_dir="solar_handoff/documents")


class ChatApiTest(unittest.IsolatedAsyncioTestCase):
    def client(self, generator=None):
        app = create_app(SETTINGS)                       # 환경 변수 대신 설정을 직접 넘긴다
        if generator is not None:
            svc = AskService(generator, ConversationLimits(20))
            app.dependency_overrides[provide_ask_service] = lambda: svc
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def test_error_shapes(self):
        cases = [
            ({"messages": []}, 400, "VALIDATION_ERROR"),
            ({"messages": [{"role": "bot", "content": "q"}]}, 400, "VALIDATION_ERROR"),
            ({}, 400, "VALIDATION_ERROR"),
        ]
        async with self.client() as c:
            for body, status, code in cases:
                r = await c.post("/api/v1/chat", json=body)
                self.assertEqual((r.status_code, r.json()["success"], r.json()["error_code"]), (status, False, code), body)
```

엔드포인트마다 성공 1건, 대표 에러(400, 502) 1건씩, 처리 못 한 예외의 500 응답에 원문이 없는지 1건을 둔다.

## 함정

- 500 테스트: `ASGITransport`는 기본으로 앱 예외를 다시 던진다. `httpx.ASGITransport(app=app, raise_app_exceptions=False)`로 만들어야 응답 본문을 볼 수 있다.
- `create_app()`은 `load_dotenv()`를 부른다. 개인 `.env`에 `ANSWER_BACKEND=llm`이 있어도 테스트가 LLM을 부르지 않도록 테스트에서는 항상 `create_app(SETTINGS)`로 설정을 직접 넘긴다. 모듈 수준 `app`을 테스트에서 쓰지 않는다.
- `logger.exception`이 테스트 출력에 traceback을 찍는 것은 정상이다. 실패 여부는 마지막 `OK` / `FAILED` 줄로 판단한다.
