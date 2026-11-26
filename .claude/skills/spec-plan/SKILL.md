---
name: spec-plan
description: Use when ordering work that needs a spec and plan, resolving spec ambiguities with the user, tracking plan progress, or completing and archiving spec/plan docs.
---

# spec-plan

오케스트레이터(디렉터)가 업무를 발주하기 전에 스펙을 쓰고, 사용자와 모호한 점을 해결해 승인받고, 계획을 세워 발주·검증한 뒤, 완료 기준을 충족하면 문서를 보관하는 절차다.

**사람의 판단(HITL)이 필요한 것은 스펙뿐이다.** 스펙의 미결 사항 해결·승인·변경·취소, 완료 기준 면제(`waived`)는 사용자가 정한다. 계획 작성·승인·변경, 발주, 막힌 작업 처리, 계획 취소, 완료 판정과 보관은 오케스트레이터(디렉터)가 스펙 범위 안에서 판단해 진행하고 결과를 보고한다.
문서 상태의 원본은 각 문서의 frontmatter다. 목록 README는 스크립트가 frontmatter로 만든다.

구성:

- [templates/spec.md](templates/spec.md), [templates/plan.md](templates/plan.md) — 문서 형식 (`new` 명령이 복사)
- [references/completion-criteria.md](references/completion-criteria.md) — 완료 기준 작성·판정 규칙
- `scripts/workdocs.py` — 생성, 검사, 병렬 단계 계산, 승인, 보관, 목록 갱신 (stdlib만 사용)

## 언제 쓰는가

- 작업이 에이전트 둘 이상, 또는 PR 하나 이상에 걸칠 때
- 요청에 범위·완료 조건이 모호한 부분이 있을 때
- 한 에이전트에 한 번 발주로 끝나는 작은 작업(오타, 표 한 줄)은 `AGENTS.md` 발주 양식만 쓰고 이 스킬을 쓰지 않는다

## 저장 위치와 이름

| 문서 | 활성 | 보관 | 목록 |
| --- | --- | --- | --- |
| 스펙 | `docs/specs/` | `docs/archives/specs/` | [docs/specs/README.md](../../../docs/specs/README.md) |
| 계획 | `docs/plans/` | `docs/archives/plans/` | [docs/plans/README.md](../../../docs/plans/README.md) |
| 보관 | | | [docs/archives/README.md](../../../docs/archives/README.md) |

- 파일 이름: `YYYY-MM-DD-{기능명 또는 작업명}.md`. 날짜는 작성일(`created`), 이름은 영문 소문자·숫자 kebab-case다 (예: `2026-11-26-chunk-schema-contract.md`).
- 스펙과 그 계획은 같은 이름을 써도 된다. 날짜는 각자의 작성일이다.
- 활성 폴더에는 진행 중인 문서만, 보관 폴더에는 `done`·`cancelled` 문서만 둔다. 검사가 강제한다.
- 보관 문서는 고치지 않는다. 오타도 그대로 둔다(`archived_hash` 검사). 다시 할 일이 생기면 새 스펙을 쓰고 `related`에 옛 id를 적는다.

## frontmatter

공통 필드 (값이 없으면 키만 두고 비운다):

| 필드 | 값 | 설명 |
| --- | --- | --- |
| `type` | `spec` \| `plan` | 문서 종류. 폴더와 맞아야 한다 |
| `id` | 파일 이름에서 `.md`를 뺀 값 | 문서끼리는 경로가 아니라 id로 가리킨다 (보관해도 안 바뀜). 종류 안에서 유일하다 |
| `title` | 한 줄 제목 | |
| `status` | 아래 상태 표 | |
| `owner` | `orchestrator` | 작성·관리 책임자 |
| `created`, `updated` | `YYYY-MM-DD` | 내용을 고칠 때마다 `updated`를 바꾼다 |
| `approved_by`, `approved_at` | 승인자, 날짜 | 스펙은 사용자, 계획은 오케스트레이터(디렉터). `approve` 명령이 채운다 |
| `approved_hash` | 해시 | `approve`가 승인 대상(스펙: 요구사항·완료 기준 표, 계획: 작업 표의 상태 외 열)을 고정한다. 손으로 고치지 않는다 |
| `completed_at`, `archived_at` | 날짜 | `archive`·`cancel` 명령이 채운다 |
| `archived_hash` | 해시 | 보관할 때 문서 전체를 고정한다. 보관 후 수정을 검사가 잡는다 |
| `cancel_reason` | 한 줄 | `cancel` 명령이 추가한다 |

스펙 전용: `related` (관련 문서 id 목록). 계획 전용: `spec` (스펙 id, 필수), `base_commit` (작성 시점 main 커밋).
스펙 하나에 계획이 여럿일 수 있다. 연결은 계획의 `spec` 필드 한 곳에만 쓴다.

### 상태

| 문서 | 상태 흐름 | 뜻 |
| --- | --- | --- |
| 스펙 | `draft` → `clarifying` → `approved` → `done` | 작성 중 → 사용자와 미결 사항 해결 중 → 사용자 승인 → 완료 기준 충족 |
| 계획 | `draft` → `approved` → `in_progress` → `done` | 작성 중 → 디렉터 확정 → 발주 시작(`start`) → 모든 작업·완료 기준 충족 |
| 공통 | 어느 단계에서든 → `cancelled` | 스펙은 사용자, 계획은 디렉터가 중단을 결정. 사유를 남기고 보관 |

승인(`approved` 이후)된 스펙의 요구사항·완료 기준을 바꾸려면 상태를 `clarifying`으로 되돌리고, 9절 변경 이력에 남기고, 다시 승인받는다. 승인 후 계획의 작업을 추가·변경·취소하면 디렉터가 계획 결정 기록에 이유를 남기고 `approve plan`을 다시 실행한다(상태는 유지, 사용자 확인 불필요). 단, 그 변경이 스펙의 범위·요구사항·완료 기준을 바꾸면 스펙 변경 절차(HITL)를 먼저 밟는다. 되돌리지 않고 고치면 `approved_hash`가 맞지 않아 검사가 실패한다.

## 문서 형식

스펙 ([templates/spec.md](templates/spec.md)):

| 절 | 내용 |
| --- | --- |
| 1. 배경과 목적 | 왜 하는가 |
| 2. 범위 | 포함·제외 |
| 3. 요구사항 | `REQ-n`, 결과로 쓴다. 구분 `필수`·`선택` |
| 4. 제약 | 바꾸면 안 되는 것, 따를 가드레일·스킬 규칙 (링크) |
| 5. 입력과 산출물 | 경로 + 버전(schema_version, index_version, 커밋) |
| 6. 완료 기준 | `AC-n`, 확인 방법·기대 결과·대응 REQ |
| 7. 미결 사항 | `Q-n`, 선택지·기본값·결정·상태(`open`/`resolved`) |
| 8. 결정 기록 | 날짜·결정·결정자·근거 |
| 9. 변경 이력 | 승인 후 변경과 재승인 |

계획 ([templates/plan.md](templates/plan.md)):

| 절 | 내용 |
| --- | --- |
| 1. 개요 | 스펙 링크, 목표, 기준 커밋 |
| 2. 작업 분해 | `T-n` 표: 작업, 담당, 선행, 산출물, 완료 기준(AC-n), 상태 |
| 3. 병렬 실행 | `waves` 명령 출력. 같은 단계 작업은 동시 발주 가능 |
| 4. 발주서 | 작업마다 `AGENTS.md` 발주 양식 |
| 5. 검증과 보고 | 에이전트 보고 형식, 오케스트레이터 검토 절차, 사용자 보고 형식 |
| 6. 위험과 대응 | |
| 7. 진행 기록 | 날짜·작업·내용·근거(명령, 경로, 커밋) |
| 8. 결정 기록 | 디렉터의 판단: 계획 확정, 작업 추가·변경·취소, 막힌 작업 처리 |
| 9. 완료 판정 | AC마다 결과(`pass`/`fail`/`waived`)·근거·확인자 |

표의 머리글(`| ID | 요구사항`, `| ID | 기준`, `| ID | 질문`, `| ID | 작업`, `| AC | 결과`, `| 날짜 | 결정`)은 스크립트가 표를 찾는 열쇠다. 열 이름과 순서를 바꾸지 않는다.

## 절차

명령은 저장소 루트에서 `uv run python .claude/skills/spec-plan/scripts/workdocs.py <명령>`으로 실행한다. 아래에서는 `workdocs.py`로 줄인다.

### 1. 스펙 작성 (오케스트레이터)

1. `git fetch` 후 관련 파일·스킬·기존 스펙을 읽는다. 보관 목록에서 같은 주제의 옛 스펙을 찾아 `related`에 적는다.
2. `workdocs.py new spec <name> --title "..."`로 만들고 1~6절을 채운다. 완료 기준은 [completion-criteria](references/completion-criteria.md)를 따른다.
3. 저장소로 확정할 수 없는 것은 추측하지 않고 7절 `Q-n`에 올린다. 각 질문에 선택지와 추천 기본값을 쓴다.

### 2. 미결 사항 해결 (HITL)

1. `status: clarifying`으로 바꾸고, `open`인 `Q-n`을 사용자에게 한 번에 묻는다. 서로 의존하는 질문은 따로 묻는다.
2. 답을 받으면 `결정` 칸을 채우고 `resolved`로 바꾸고, 8절에 결정자(사용자)와 날짜를 적는다. 답이 요구사항·완료 기준을 바꾸면 3·6절에 반영한다.
3. 답에서 새 모호함이 생기면 `Q-n`을 추가하고 반복한다.
4. 사용자가 스펙 전체를 확인하면 8절에 `| 날짜 | 스펙 승인 | <사용자> | 확인 방법 |` 행을 쓰고 `workdocs.py approve spec <spec-id> --by <사용자>`로 승인한다. 승인 행이 없거나, `open` 질문, 빈 확인 방법, 완료 기준 없는 필수 요구사항, 남은 `{{...}}`가 있으면 명령이 거부하고 파일을 되돌린다. `--by`에 에이전트나 오케스트레이터는 쓸 수 없다.

사용자의 명시적 확인 없이 승인하지 않는다. 기본값으로 진행해도 된다고 사용자가 말한 질문만 기본값으로 `resolved` 처리하고 그 사실을 결정 기록에 쓴다.

### 3. 계획 작성 (디렉터 판단, 사용자 확인 없음)

1. `workdocs.py new plan <name> --spec <spec-id> --title "..."`. 스펙이 `approved`가 아니면 만들지 않는다.
2. 2절 작업 분해: 작업 하나 = 담당 하나 = 발주 하나. 읽기 전용 에이전트(frontmatter `tools`에 Write·Edit 없음)는 산출물 칸을 비워도 된다. 담당은 `.claude/agents/`의 에이전트 또는 `오케스트레이터`·`디렉터`·`팀원`·`사용자`다. 평가셋 작성·잠금처럼 사람만 하는 일은 `팀원`에게 둔다 (`AGENTS.md` 가드레일).
3. 스펙의 모든 AC를 맡는 작업이 있어야 한다. 수정한 에이전트와 그 결과를 판정하는 담당을 같은 작업에 두지 않는다 (예: 구현 T-2 → 리뷰 T-3 api-reviewer).
4. `workdocs.py waves <plan-id>`로 단계를 계산해 3절에 붙인다. 같은 단계 작업의 산출물 경로가 겹치면 ERROR다 — 선행 관계를 넣어 순서를 정한다.
5. 4절 발주서와 5절 보고 형식을 쓴다. `done_when`은 해당 AC의 확인 방법·기대 결과를 그대로 옮긴다.
6. 디렉터가 검사(`workdocs.py check`)를 통과시킨 뒤 `workdocs.py approve plan <plan-id>`로 확정한다(`--by` 기본값 `오케스트레이터`, 하위 에이전트 이름은 거부). 사용자에게는 계획 요약을 보고만 한다.

### 4. 실행과 기록

1. 발주를 시작하면 `workdocs.py start <plan-id>`로 계획을 `in_progress`로 바꾼다. 단계 순서대로 발주하고, 같은 단계 작업은 동시에 발주한다.
2. 보고를 받으면 `AGENTS.md` 보고 검토 절차대로 evidence를 직접 다시 실행하고, 작업 상태와 7절 진행 기록을 갱신한다. 보고 내용만으로 `done`을 적지 않는다.
3. 막히면 작업을 `blocked`로 두고 디렉터가 처리를 정한다(재발주, 작업 분할·추가, 담당 변경, 계획 취소 후 새 계획). 판단은 8절 결정 기록에 남긴다. 스펙의 범위·요구사항·완료 기준을 바꿔야 할 때만 스펙을 `clarifying`으로 되돌리고 사용자에게 묻는다 (2절 절차).
4. 커밋 전마다 `workdocs.py check`를 실행한다.

### 5. 완료 판정과 보관

1. 9절 완료 판정 표를 채운다. 스펙의 모든 AC를 판정한다(취소한 작업의 AC 포함). 확인자 규칙은 [completion-criteria](references/completion-criteria.md) 6번이다.
2. `workdocs.py archive <spec-id> --dry-run`으로 조건을 확인한다. 조건은 [completion-criteria 판정 규칙](references/completion-criteria.md#판정-규칙)이다.
3. 통과하면 `workdocs.py archive <spec-id>`. 스펙과 연결된 활성 계획을 함께 `done`으로 바꾸고(`completed_at`, `archived_at`, `updated`, `archived_hash`), 보관 폴더로 옮기고(추적 중인 파일은 `git mv`, 아직 추적되지 않은 파일은 이동), 저장소 Markdown의 상대 링크와 목록 README를 갱신한다.
4. 5절 사용자 보고 형식으로 완료를 보고한다.

중단: `workdocs.py cancel spec|plan <id> --reason "..."`.
- 스펙 취소는 사용자 결정이다. 스펙 8절에 사람의 `취소` 결정 행이 있어야 명령이 동작하며, 연결된 활성 계획도 함께 취소·보관한다.
- 계획 취소는 디렉터가 판단한다. 스펙은 남고 새 계획을 쓴다.

## 검사

```bash
uv run python .claude/skills/spec-plan/scripts/workdocs.py check            # 커밋 전
uv run python .claude/skills/spec-plan/scripts/workdocs.py check --strict   # PR 전 (WARN도 실패)
```

| 종류 | 뜻 |
| --- | --- |
| name, location | 파일 이름 형식, 폴더와 type·status 불일치 |
| frontmatter, approval, template | 필드 누락·형식, 승인 정보 없음, 승인 후 내용 변경(`approved_hash`), 승인 후 자리표시 남음 |
| archive | 보관 후 내용 변경(`archived_hash`) |
| spec, ac | 미결 사항 남음, REQ↔AC 연결 누락, 확인 방법 형식, 모호한 표현(WARN) |
| plan | 없는 스펙·담당·선행·AC, 순환, 같은 단계 산출물 충돌, AC 누락 |
| done | 완료 처리 조건 미충족 |

보관 문서에는 WARN을 내지 않는다(고칠 수 없으므로). 출력 끝의 `루트`가 저장소 경로인지 확인한다(`WORKDOCS_ROOT`는 테스트용).
| index | 목록 README가 frontmatter와 다름 → `workdocs.py index` |

문서 링크·허브 도달성은 [doc-sync](../doc-sync/SKILL.md)가 따로 검사한다. 목록 README가 활성·보관 문서를 모두 링크하므로 `index`를 최신으로 두면 고아 문서가 생기지 않는다.

## 하지 않는 것

- 사용자 확인 없이 스펙을 승인·변경·취소하거나 `Q-n`을 임의로 `resolved` 처리하지 않는다.
- 반대로 계획·발주·작업 처리를 사용자 확인 대기로 멈추지 않는다. 디렉터가 정하고 보고한다.
- 완료 기준을 통과시키려고 승인 후 AC를 몰래 바꾸거나 지우지 않는다. 바꾸면 재승인을 받는다.
- 평가셋 정답이나 `eval/` 내용을 스펙·계획에 옮겨 적지 않는다 (`AGENTS.md` 가드레일).
- 보관 문서를 고치지 않는다. 목록 README를 손으로 고치지 않는다 (`index`가 덮어쓴다).
- 세부 절차를 스펙·계획에 복사하지 않는다. 해당 스킬·`AGENTS.md`로 링크한다.
