---
name: layer-check
description: Use after writing code in a 4-layer service or before a PR. Profile-driven check of layer import direction and injected boundaries.
---

# layer-check

4계층 서비스의 폴더 구조와 import 방향을 자동으로 검사하는 **공통 스크립트**다. 원칙은 [layered-architecture](../layered-architecture/SKILL.md), 슬라이스 규칙은 [fsd-architecture](../fsd-architecture/SKILL.md)를 따른다.
서비스별 규칙(위치, 금지 패키지, 에러·CORS 규칙, 규칙 ID)은 스크립트에 두지 않고 서비스가 **프로파일(JSON)** 로 주입한다.

## 실행

저장소 루트에서 실행한다. 표준 라이브러리만 쓴다.

```bash
uv run python .claude/skills/layer-check/scripts/check_layers.py --profile <프로파일.json>
uv run python .claude/skills/layer-check/scripts/check_layers.py --profile <프로파일.json> --root <복사본>/<패키지명>
```

종료 코드: `0` 위반 없음, `1` 위반 있음, `2` 프로파일 또는 서비스 폴더 없음. 경고는 종료 코드에 영향을 주지 않는다.

- 서비스 폴더가 없으면(2) 또는 슬라이스가 없으면("검사한 슬라이스: (없음)", 0) 통과가 아니라 **미구현**으로 보고한다.
- 프로파일 위치와 게이트 명령은 각 서비스 규칙 스킬이 정한다. 이 스킬은 어떤 서비스가 자기를 쓰는지 알지 않는다.

## 고정 규칙 (프로파일로 바꾸지 않음)

4계층의 정의 자체다.

| 태그 | 내용 |
| --- | --- |
| `[구조]` | 서비스 패키지, 슬라이스, 있는 계층 폴더, shared 폴더에 `__init__.py`가 없으면 위반. 4계층을 모두 요구하지는 않는다 |
| `[의존방향]` | domain → 다른 계층, application → infrastructure·presentation, infrastructure → application·presentation, presentation → infrastructure, shared·서비스 루트 파일 → 슬라이스의 infrastructure·application·presentation |

슬라이스 = 서비스 바로 아래에서 계층 폴더가 하나라도 있는 폴더. 조립 파일(`assembly_files`)은 import 제한이 없다. 상대 import도 절대 경로로 풀어 검사한다.

## 프로파일

```json
{
  "root": "<저장소 루트 기준 서비스 폴더>",
  "package": "<import 패키지명, 기본: root 폴더 이름>",
  "shared_dirs": ["shared"],
  "skip_dirs": ["tests"],
  "assembly_files": ["main.py", "container.py"],
  "forbidden_packages": {"domain": [], "application": [], "infrastructure": [], "presentation": [], "shared": []},
  "domain_shared_allowed": null,
  "http_exception_forbidden": [],
  "cors_wildcard_forbidden": false,
  "broad_exception_warn": [],
  "fsd": {"cross_slice": "off"},
  "rule_ids": {}
}
```

| 키 | 켜지는 검사 | 태그 |
| --- | --- | --- |
| `forbidden_packages` | 계층별 금지 패키지. 접두어 일치(`sdk` → `sdk_core`) | `[외부의존]` |
| `domain_shared_allowed` | domain이 import할 수 있는 shared 모듈 목록. `null`이면 제한 없음 | `[공용]` |
| `http_exception_forbidden` | 해당 계층에서 `HTTPException` 이름 사용 금지 | `[HTTP예외]` |
| `cors_wildcard_forbidden` | `allow_origins`에 `"*"` 금지 | `[CORS]` |
| `broad_exception_warn` | 전역 핸들러가 잡으면 경고할 내장 예외 | `[넓은예외]` (경고) |
| `fsd.cross_slice` | `off` / `warn` / `error`. 다른 슬라이스 내부 import, shared → 슬라이스 import | `[슬라이스]` |
| `rule_ids` | 태그 옆에 서비스 규칙 ID를 붙여 출력 (예: `{"HTTP예외": "R6"}` → `[HTTP예외 R6]`) | — |

`_`로 시작하는 키(`_doc` 등)는 설명용이라 무시한다.

## 경고 (종료 코드에 영향 없음)

- `[구조]`: 슬라이스 루트에 계층 밖 `.py` 파일, 계층 폴더가 없는 하위 패키지, 폴더 이름과 `package`가 다름(이 경우 `package.`로 시작하는 import만 내부로 판정한다).
- `[넓은예외]`, `fsd.cross_slice: warn`인 `[슬라이스]`.

## 검사의 한계

정독 규칙(빈 엔티티, 서비스의 비즈니스 if-else, 구현체 직접 생성, 주입 연결 누락, 에러 응답 형식)은 보지 않는다. 서비스의 리뷰어가 코드를 읽어 판정한다.

## 스크립트를 고칠 때

이 스크립트는 여러 서비스가 함께 쓴다. 특정 서비스 규칙을 스크립트에 넣지 말고 프로파일 키로 만든다.
고친 뒤에는 위반을 일부러 넣은 복사본으로 잡히는지 확인한다. 복사본 폴더 이름은 `package`와 같게 둔다.

```bash
mkdir -p "$TMPDIR/lc" && cp -R <서비스 폴더> "$TMPDIR/lc/<패키지명>"
# 복사본에 금지 import·HTTPException·allow_origins=["*"]·다른 슬라이스 내부 import를 넣는다
uv run python .claude/skills/layer-check/scripts/check_layers.py --profile <프로파일.json> --root "$TMPDIR/lc/<패키지명>"
rm -rf "$TMPDIR/lc"
```
