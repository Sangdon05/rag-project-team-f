---
name: layer-check
description: Use after writing api/ code or before a PR. Runs the 4-layer import-direction and boundary check on the api/ service.
---

# layer-check

`api/` 서비스의 폴더 구조와 계층 간 import 방향을 자동으로 검사한다. 규칙 원본은 [api-invariants](../api-invariants/SKILL.md)이고 이 스크립트는 그중 자동으로 판정할 수 있는 부분만 본다.

## 실행

저장소 루트에서 실행한다. 표준 라이브러리(`ast`)만 쓴다.

```bash
uv run python .claude/skills/layer-check/scripts/check_layers.py          # 기본: ./api
uv run python .claude/skills/layer-check/scripts/check_layers.py <경로>/api  # 복사한 트리 등
```

종료 코드: `0` 위반 없음, `1` 위반 있음, `2` 서비스 폴더 없음. 경고는 종료 코드에 영향을 주지 않는다.

- 폴더 이름이 import 이름이다. 다른 위치에서 검사할 때도 폴더 이름을 `api`로 둔다. 이름이 다르면 `api.` 절대 import를 외부 패키지로 보고 계층 위반을 놓친다.
- 슬라이스가 없으면 "검사한 슬라이스: (없음)"과 함께 0으로 끝난다. 통과가 아니라 **미구현**으로 보고한다.

## 검사 대상

| 대상 | 판단 기준 | 검사 |
| --- | --- | --- |
| 슬라이스 | `api/` 바로 아래에서 계층 폴더(domain, infrastructure, application, presentation)가 하나라도 있는 폴더 | 있는 계층 폴더의 `__init__.py`, import 방향, 금지 패키지. 4계층을 모두 요구하지는 않는다 |
| 공용 | `api/shared/` | `__init__.py`, import 방향, RAG 경계 패키지 |
| 서비스 루트 파일 | `error_handlers.py` 등 | shared와 같은 규칙 |
| 조립 지점 | `main.py`, `container.py` | import 제한 없음. CORS 검사만 |
| 제외 | `api/tests/`, `__pycache__/`, 숨김 폴더 | 검사하지 않음 |

## 위반 (종료 코드 1)

| 계층 | 참조 금지 계층 | import 금지 패키지 |
| --- | --- | --- |
| domain | infrastructure, application, presentation, `shared.exceptions` 밖의 shared | fastapi, starlette, pydantic, uvicorn, httpx, dotenv + RAG 경계 |
| application | infrastructure, presentation | fastapi, starlette, uvicorn + RAG 경계 |
| infrastructure | application, presentation | fastapi, starlette |
| presentation | infrastructure | RAG 경계 |
| shared, 서비스 루트 파일 | 슬라이스의 infrastructure, application, presentation | RAG 경계 |

- RAG 경계 패키지(R8): `langchain`·`langchain_*`, `langgraph`, `openai`, `tiktoken`, `ragas`, `psycopg`, `sqlalchemy`, RAG 패키지 `pokedex`, 저장소 `scripts`. 접두어가 같은 패키지(`langchain_core` 등)도 잡는다.
- 다른 슬라이스의 같은 계층이나 허용된 계층을 참조하는 것은 괜찮다(예: `chat.application` → `health.domain`). 슬라이스 간 규칙은 아직 강제하지 않는다([api-architecture §1](../api-architecture/SKILL.md)).
- `[HTTP예외]`: domain·application·presentation에서 `HTTPException` 이름을 쓰면 위반이다(R6).
- `[CORS]`: `allow_origins`에 `"*"`가 들어간 리스트를 쓰면 위반이다(R13).
- 상대 import(`from ..infrastructure import x`)도 절대 경로로 풀어 검사한다.

## 경고

- `[넓은예외]`: 전역 핸들러가 내장 `ValueError`·`LookupError`·`PermissionError`·`KeyError`를 잡는다. 처리 못 한 예외용 `Exception` 핸들러(500)는 경고하지 않는다.
- `[구조]`: 슬라이스 루트에 계층 밖 `.py` 파일이 있음, 또는 계층 폴더가 없는 하위 패키지가 있음.

## 검사의 한계

정독 규칙(R3 빈 엔티티, R4 추상만 받기, R5 container 매핑, R7 에러 형식, R10 상태 없음 등)은 보지 않는다. api-reviewer가 코드를 읽어 판정하고, 실제 응답은 [fastapi-run](../fastapi-run/SKILL.md) smoke로 확인한다.

## 스크립트를 고칠 때

규칙을 바꾸면 위반을 일부러 넣은 복사본으로 잡히는지 확인한다. 복사본 폴더 이름은 `api`로 둔다.

```bash
mkdir -p "$TMPDIR/lc" && cp -R api "$TMPDIR/lc/api"
# $TMPDIR/lc/api 안에 금지 import·HTTPException·allow_origins=["*"]를 넣는다
uv run python .claude/skills/layer-check/scripts/check_layers.py "$TMPDIR/lc/api"   # 위반으로 잡혀야 한다
rm -rf "$TMPDIR/lc"
```
