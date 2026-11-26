# suggestion 설계안

상태: 검토 중

입력 원본: [API 엔드포인트 스펙](../../archives/specs/2026-11-26-api-endpoints.md) 3절 요구사항, `GET /api/v1/suggestion`. 응답 형식·공통 에러·기반 예외·설정은 [health 설계안 0절(공통)](health.md#0-공통)을 따른다.

## 1. 목적과 범위

프론트 첫 화면에 보여 줄 추천 질문을 사용자 등급별로 돌려준다. 등급은 [problem.md §2](../../problem.md) 페르소나에 대응한다(`beginner`=P1, `novice`=P2, `expert`=P3).

- 후보는 **fake 데이터**다. 평가셋(`eval/`)과 무관하며 평가셋 질문·정답을 넣지 않는다(R16).
- 데이터는 domain 포트 `SuggestionProvider` 뒤 infrastructure 구현체에 둔다. 나중에 실제 제공자로 바꿔도 router·서비스는 그대로다.
- RAG·LLM을 부르지 않는다.

## 2. 용어

| 코드 이름 | 뜻 |
| --- | --- |
| `SuggestionLevel` | 등급. `StrEnum`: `beginner`, `novice`, `expert` |
| `Suggestion` | 추천 질문 하나. `id`, `text` |
| `SuggestionSet` | 응답 단위. 적용된 `level` + `suggestions` |
| `SuggestionProvider` | 등급별 추천 질문을 주는 포트 |
| `FakeSuggestionProvider` | 고정 데이터 구현체 |
| `SuggestionService` | 유스케이스 서비스 |

## 3. 도메인

`api/suggestion/domain/suggestion.py`:

| 타입 | 필드 | 규칙 (불변식) | 위반 시 |
| --- | --- | --- | --- |
| `SuggestionLevel(StrEnum)` | `BEGINNER="beginner"`, `NOVICE="novice"`, `EXPERT="expert"` | 값은 소문자 고정, 대소문자 구분 | — (형식 검증은 presentation의 query 타입이 한다. 6절) |
| `Suggestion` (frozen dataclass) | `id: str`, `text: str` | `__post_init__`: `id`, `text`가 앞뒤 공백 제거 후 비어 있지 않음 | `InvalidSuggestionError` |
| `SuggestionSet` (frozen dataclass) | `level: SuggestionLevel`, `suggestions: tuple[Suggestion, ...]` | 0개 허용. `create(level, items)`가 `id` 중복을 막는다 | `InvalidSuggestionError` |

`api/suggestion/domain/exceptions.py`:

| 예외 | 기반 | 상태 | `error_code` | 발생 |
| --- | --- | --- | --- | --- |
| `InvalidSuggestionError` | `ApiError` | 500 | `INTERNAL_ERROR` | 제공자 데이터가 불변식을 어김(빈 문장, id 중복). 사용자 입력 오류가 아니라 서버 데이터 오류이므로 500 |

사용자 입력 오류(허용값 밖 `level`)는 `RequestValidationError` → 400 `VALIDATION_ERROR`([health 공통 0.4](health.md#0-공통)).

## 4. 포트와 구현체

```python
# api/suggestion/domain/provider.py
class SuggestionProvider(ABC):
    @abstractmethod
    async def list_for(self, level: SuggestionLevel) -> tuple[Suggestion, ...]: ...
```

| 구현체 | 위치 | 동작 |
| --- | --- | --- |
| `FakeSuggestionProvider` | `api/suggestion/infrastructure/fake_provider.py` | 모듈 상수 `FAKE_SUGGESTIONS: dict[SuggestionLevel, tuple[Suggestion, ...]]`에서 반환. 생성자에 `data`를 선택 인자로 받아 테스트가 바꿔 넣을 수 있다 |

fake 데이터 (등급별 예시. 평가셋과 무관하게 새로 쓴 질문이며 [problem.md §2](../../problem.md)의 말투만 참고):

| level | `id` | `text` |
| --- | --- | --- |
| `beginner` (P1, 짧은 반말) | `beginner-01` | `파이리는 뭐한테 약해?` |
| | `beginner-02` | `피카츄는 진화하면 누구야?` |
| | `beginner-03` | `꼬부기는 무슨 기술 배워?` |
| `novice` (P2, 짧은 상황 질문) | `novice-01` | `이상해씨 골랐는데 뭐부터 보면 돼?` |
| | `novice-02` | `종족치가 뭐야?` |
| | `novice-03` | `타입 상성은 어떻게 읽어?` |
| `expert` (P3, 구어체·검색체) | `expert-01` | `리자몽 특수 종족치 몇임?` |
| | `expert-02` | `잠만보 레벨업 기술 뭐 있음?` |
| | `expert-03` | `스타미 스피드 종족치랑 타입 어떻게 됨?` |

- 구현자는 위 표를 그대로 쓰거나 같은 성격의 질문으로 바꿀 수 있다. `eval/`을 열어 참고하지 않는다.
- 답변 내용(정답)은 넣지 않는다. 질문 문장만 둔다.

## 5. 유스케이스

`api/suggestion/application/service.py`:

```python
class SuggestionService:
    def __init__(self, provider: SuggestionProvider) -> None: ...

    async def suggest(self, level: SuggestionLevel) -> SuggestionSet:
        items = await self.provider.list_for(level)
        return SuggestionSet.create(level, items)   # 불변식은 도메인에서 (R3)
```

## 6. 엔드포인트 명세

### `GET /api/v1/suggestion`

요청 query:

| 이름 | 타입 | 필수 | 기본값 | 설명 |
| --- | --- | --- | --- | --- |
| `level` | string (`beginner` \| `novice` \| `expert`) | 아니오 | `beginner` | 사용자 등급. 대소문자 구분 |

- presentation은 `level: SuggestionLevel = SuggestionLevel.BEGINNER`(또는 `Literal`)로 받는다. 허용값 밖(`bad`, `Beginner`)이나 빈 값(`?level=`)이면 FastAPI가 `RequestValidationError` → 400.
- `level`을 여러 번 주면(`?level=novice&level=expert`) FastAPI 기본 동작(단일 값 query는 마지막 값)을 따른다. 별도 처리하지 않으며 구현 시 동작을 테스트로 확인만 한다.

응답 `data` (`SuggestionData`):

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `level` | string | 예 | 적용된 등급 (기본값이 적용되면 `beginner`) |
| `suggestions` | array | 예 | 추천 질문. 0개일 수 있다 |
| `suggestions[].id` | string | 예 | 추천 질문 ID (등급 안에서 유일) |
| `suggestions[].text` | string | 예 | 질문 문장 |

상태 코드:

| HTTP | `error_code` | 조건 |
| --- | --- | --- |
| 200 | — | 성공 (0개 포함) |
| 400 | `VALIDATION_ERROR` | `level`이 허용값 밖이거나 빈 값 |
| 405 | `METHOD_NOT_ALLOWED` | GET 외 메서드 |
| 500 | `INTERNAL_ERROR` | 제공자 데이터 불변식 위반 등 처리 못 한 예외 |

예시:

```http
GET /api/v1/suggestion?level=novice
```

```json
{"success": true, "data": {"level": "novice", "suggestions": [
  {"id": "novice-01", "text": "이상해씨 골랐는데 뭐부터 보면 돼?"},
  {"id": "novice-02", "text": "종족치가 뭐야?"}
]}}
```

```json
{"success": false, "error_code": "VALIDATION_ERROR", "message": "query.level: Input should be 'beginner', 'novice' or 'expert'"}
```

파일 배치:

```text
api/suggestion/
  __init__.py
  domain/          suggestion.py (SuggestionLevel, Suggestion, SuggestionSet), provider.py (SuggestionProvider), exceptions.py
  application/     service.py (SuggestionService)
  infrastructure/  fake_provider.py (FakeSuggestionProvider, FAKE_SUGGESTIONS)
  presentation/    schemas.py (SuggestionItem, SuggestionData.from_domain), dependencies.py (provide_suggestion_service), router.py
```

- router: `APIRouter(prefix="/api/v1", tags=["suggestion"])`, `GET /suggestion`, `response_model=SuccessResponse[SuggestionData]`.
- container: `SuggestionService(FakeSuggestionProvider())`를 앱당 하나 만들어 `provide_suggestion_service`에 연결.

## 7. 설정

없음. 제공자 선택 환경 변수는 두지 않는다(구현체가 하나뿐).

## 8. 테스트 시나리오 (`api/tests/suggestion/`)

| # | 종류 | 시나리오 | 기대 |
| --- | --- | --- | --- |
| S1 | 도메인 | `Suggestion(id="a", text="  ")` | `InvalidSuggestionError` |
| S2 | 도메인 | `SuggestionSet.create(level, [같은 id 2개])` | `InvalidSuggestionError` |
| S3 | 서비스 | fake 제공자가 받은 `level` 기록, 0개 반환 | `SuggestionSet(level, ())`, 제공자가 그 `level`로 호출됨 |
| S4 | API 성공 | `GET /api/v1/suggestion` | 200, `data.level == "beginner"`, `suggestions` 2개 이상, 각 항목 `id`·`text` 문자열 |
| S5 | API 성공 | `?level=expert` | 200, `data.level == "expert"` |
| S6 | API 에러 | `?level=bad`, `?level=Beginner`, `?level=` | 각각 400 `VALIDATION_ERROR`, 공통 에러 형식 |
| S7 | API 0개 | 빈 데이터 제공자 주입 | 200, `suggestions == []` |
| S8 | API 500 | 제공자가 `RuntimeError("secret-detail")` (`raise_app_exceptions=False`) | 500 `INTERNAL_ERROR`, 본문에 `secret-detail` 없음 |

## 9. 변경 제안 (설계안 밖 파일)

없음. (`api-architecture` 폴더 트리 갱신은 [health 설계안 9절](health.md)에 묶었다.)

## 10. 질문

| 질문 | 임시 기본값 |
| --- | --- |
| 등급별 추천 질문 개수 | 3개 (0개도 200) |
| `level`을 여러 번 준 경우 | FastAPI 기본(마지막 값). 별도 400 처리 없음 |
| 추천 질문 순서 | 제공자가 준 순서 그대로 |
