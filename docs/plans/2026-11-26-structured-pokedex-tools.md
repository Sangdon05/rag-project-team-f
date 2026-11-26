---
type: plan
id: 2026-11-26-structured-pokedex-tools
title: 도감 정형 조회와 상성 계산 구현 계획
status: in_progress
owner: orchestrator
spec: 2026-11-26-structured-pokedex-tools
created: 2026-11-26
updated: 2026-11-26
approved_by: 오케스트레이터
approved_at: 2026-11-26
completed_at:
archived_at:
base_commit: 3945d46
---

# 도감 정형 조회와 상성 계산 구현 계획

## 1. 개요

- 스펙: [도감 정형 조회와 상성 계산 도구](../specs/2026-11-26-structured-pokedex-tools.md)
- 목표: 검색 순위와 독립해 팀·기술 근거를 조회하고, 확인된 Red·Blue 상성을 대화에 연결한다.
- 기준 커밋: `3945d465c1f2f72345ad7e8a9f057b36b6139e57` (작성 시점 main)
- 브랜치: `feat/structured-pokedex-tools`

## 2. 작업 분해

| ID | 작업 | 담당 | 선행 | 산출물 | 완료 기준 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| T-1 | 정형 도구 및 대화 호출과 회귀 테스트 구현 | rag-developer | - | `src/pokedex/`, `solar_handoff/src/conversation.py`, `solar_handoff/src/providers.py`, `tests/test_pokedex_structured_tools.py`, `tests/test_solar_conversation.py`, `tests/test_solar_tool_provider.py` | AC-1, AC-2, AC-3, AC-4, AC-5 | done |
| T-2 | 구현·출처 표시·검증 범위 문서 동기화 | rag-developer | T-1 | `solar_handoff/README.md`, `.claude/agents/rag-developer.md`, `.claude/skills/tool-calling/SKILL.md`, `.claude/skills/langchain-rag/SKILL.md`, `docs/references/api-rag-integration.md`, `docs/references/agents/README.md`, `docs/references/skills/README.md`, `AGENTS.md`, `.claude/skills/rag-eval/references/records.md`, `.claude/skills/api-architecture/SKILL.md`, `.claude/skills/api-implementation/SKILL.md` | AC-6 | blocked |
| T-3 | 독립 보안 점검 | security-reviewer | T-1 | - | AC-7 | done |
| T-4 | 잠긴 평가 입력으로 RAG 평가 게이트 확인 | eval | T-2 | `results/` | AC-8 | blocked |

- 담당: `.claude/agents/`에 있는 에이전트 이름, 또는 `오케스트레이터`·`디렉터`·`팀원`·`사용자`.
- 선행: 먼저 끝나야 하는 작업 ID (쉼표 구분, 없으면 `-`).
- 산출물: 이 작업이 쓰는 파일·폴더 (백틱, 쉼표 구분). 같은 단계의 작업끼리 겹치면 안 된다.
- 완료 기준: 스펙의 AC ID. 스펙 AC에 직접 대응하지 않는 지원 작업은 `지원: <확인 조건>`으로 쓴다.
- 상태: `todo` | `doing` | `done` | `blocked` | `cancelled`.

## 3. 병렬 실행

`workdocs.py waves`가 계산한 단계를 붙인다. 같은 단계의 작업은 동시에 발주할 수 있다.

```
단계 1: T-1(rag-developer)
단계 2: T-2(rag-developer), T-3(security-reviewer)
단계 3: T-4(eval)
```

T-4는 팀 평가 입력 잠금과 별도 실행 승인이 있을 때만 발주한다.

## 4. 발주서

작업마다 `AGENTS.md` 발주 양식으로 쓴다. `done_when`에는 2절의 완료 기준을 옮긴다.

```
task: T-1 — 정형 도구 구현 및 Solar 대화 호출 연결.
agent: rag-developer
inputs: 스펙, 기준 3945d46, 해시 검증 Red·Blue 정제 데이터, 기존 청크 schema_version=1.
outputs: 2절 T-1 코드와 테스트.
done_when: 스펙 AC-1–AC-5 명령으로 재현 팀·기술 예외·출처·검색 경로·보호 파일 검증 통과.
constraints: 정형 데이터 단일 읽기 로더, 같은 GPT 도구 선택, 기존 CLI A/B/C 및 HTTP 계약 유지. DB 접속·유료 요청·평가셋 열람 금지.
```

```
task: T-2 — 대화의 실제 구현과 프로젝트 문서를 동기화.
agent: rag-developer
inputs: 스펙, T-1 검증 결과, doc-sync 커플링.
outputs: 2절 T-2 문서.
done_when: AC-6 명령 ERROR 0, WARN 0; 오프라인·실행 미검증 범위를 구분.
constraints: 문서만 수정. 기존 질문 CLI를 도구 기반이라고 표현하지 않는다.
```

```
task: T-3 — 보안 검사를 실행하고 결과를 분류.
agent: security-reviewer
inputs: 브랜치 변경분, 최신 origin/main, security-check.
outputs: 읽기 전용 분류 보고.
done_when: AC-7 명령 ERROR 0, WARN이 있다면 각각 처리 사유가 있음.
constraints: 파일 수정·커밋·push·DB·유료 호출 금지.
```

```
task: T-4 — 팀원이 잠근 평가 입력으로 RAG 평가.
agent: eval
inputs: 승인된 실제 실행과 잠금 통과 평가 입력, T-1·T-2 산출물.
outputs: results/{run_id}/ 평가 기록.
done_when: AC-8 및 AGENTS.md 평가 게이트 통과.
constraints: 입력 잠금·비용·DB 접근 승인 전 발주하지 않는다. 평가셋은 수정하지 않는다.
```

## 5. 검증과 보고

- 하위 에이전트 보고: 각 에이전트 정의의 보고 형식 (`status`, `changed_files`, `checks`의 evidence, `refused`, `downstream_impact`).
- 오케스트레이터 검토: `AGENTS.md` 보고 검토 절차. evidence 명령을 직접 다시 실행하고 결과를 7절에 남긴다.
- 읽기 전용 에이전트(리뷰어 등)의 판정은 보고 원문 요약을 7절에 남기고, 그 AC의 확인 방법은 `보고: <에이전트>`로 쓴다.
- 사용자 보고: 작업이 끝나거나 막힐 때 아래 형식으로 보고한다. 보고는 알림이며 승인 요청이 아니다. 스펙 변경이 필요할 때만 `next`에 사용자 결정 요청을 쓴다.

```
plan: 2026-11-26-structured-pokedex-tools
done: [T-n, ...]
blocked: [T-n: 이유와 필요한 결정]
ac: [AC-n: pass | fail | not_run — 근거]
next: 디렉터가 정한 다음 단계 (스펙 변경이 필요할 때만 사용자 결정 요청)
```

## 6. 위험과 대응

| 위험 | 대응 |
| --- | --- |
| 팀·상대·후보 이름 혼동 | 도구 설명에서 역할을 구분하고 명단이 불명확하면 확인을 요청한다. 서버는 허용된 인수·팀 ID를 검증한다. |
| 기술 효과에 습득표 인용 | 포켓몬 출처 번호는 기존 청크로 제한하고, 기술 분류는 확인된 레코드를 텍스트 근거로 표기한다. HTTP 형식은 바꾸지 않는다. |
| 검색 비교 실험에 도구 변경이 섞임 | 기존 CLI A/B/C와 컷오프를 바꾸지 않는다. 대화 도구의 오프라인 결과를 별도 기록한다. |
| 잠긴 평가 입력·유료 실행 승인 없음 | 오프라인 검증을 진행하되 AC-8은 미실행으로 남긴다. |

## 7. 진행 기록

| 날짜 | 작업 | 내용 | 근거 |
| --- | --- | --- | --- |
| 2026-11-26 | 착수 | 원격 main 확인 후 브랜치 생성. 입력 해시·기존 테스트 확인. | `git rev-list --left-right --count HEAD...origin/main` 결과 `0 0`, `verify_bundle()` 통과, 기존 `test_solar*.py` 35개 통과. |
| 2026-11-26 | T-1 1차 검토 | 정형·Solar·API 어댑터 오프라인 테스트는 통과. 한국어 이름 부분 일치가 다른 포켓몬·기술을 허용해 수정 발주. | 정형 8개·Solar 47개·어댑터 6개 통과. `_unmentioned_reference`에서 `피죤투`만 입력하고 `피죤` 선택, `몸통박치기`만 입력하고 `박치기` 선택을 각각 잘못 허용함. |
| 2026-11-26 | T-1 재검토 | 부분 일치 회귀 및 기존 계약을 다시 확인. 인메모리 HTTP에서 팀·불꽃펀치·망각술을 실행. | 정형 8개·Solar 50개·API 어댑터 6개·상성 10개 통과(상성의 선택 호환 1개 생략), HTTP 3건 200·정형 임베딩 필드 생략, 보호 경로 차이 없음. |
| 2026-11-26 | T-2 1차 검토 | 변경된 문서 7개와 연동 대상 4개를 검토. 남은 연동을 수정 발주. | `check_docs.py --strict` ERROR 0, WARN 4, 종료 1. 기존 보관 링크 예외 54건 유지. |
| 2026-11-26 | T-2 재검토 | 평가·API 연동 3건 반영. 보호된 `AGENTS.md`에는 쓰기가 허용되지 않아 중단하고 원본을 유지했다. | `git diff --exit-code HEAD -- AGENTS.md` 종료 0. `check_docs.py --strict` ERROR 0, WARN 1(담당표 연동), 종료 1. |
| 2026-11-26 | T-3 | 독립 `security-reviewer`가 읽기 전용으로 검사하고 오케스트레이터가 같은 명령을 재실행했다. | `check_security.py --base origin/main` 트리 758개·인덱스 749개·변경 22개, ERROR 0, WARN 0, 종료 0. |
| 2026-11-26 | T-4 | 실 모델 호출·DB 연결 및 공식 평가는 미실행. 개발·최종 평가 입력과 잠금 파일 부재를 파일 존재 여부로만 확인했다. | `eval/dev.json`, `eval/test.json`, `eval/LOCK.json` 없음. 평가셋 열람·변경 없음. |

## 8. 결정 기록

디렉터의 판단: 계획 확정, 작업 추가·변경·취소, 막힌 작업 처리. 사용자 확인은 필요 없다(스펙 변경이 따르면 스펙 절차).

| 날짜 | 결정 | 결정자 | 근거 |
| --- | --- | --- | --- |
| 2026-11-26 | 채팅에서 승인된 개선안을 스펙으로 반영한다. 라이브 DB와 외부 모델은 실행하지 않는다. | 오케스트레이터 | 사용자: “ㅇㅋ 그러면 브렌치 파고 구현진행해줘” |
| 2026-11-26 | 기존 검색과 정형 도구를 GPT의 도구 목록에 제공하고 별도 라우터는 만들지 않는다. | 오케스트레이터 | `AGENTS.md`, 스펙 REQ-4. |
| 2026-11-26 | 기술 분류 근거는 확인된 레코드를 표기한다. 번호 출처는 포켓몬 원문만 가리킨다. | 오케스트레이터 | 기존 `sources[].source_ref_id`의 도감번호 계약. |
| 2026-11-26 | T-2에 `rag-developer`의 실제 지원 범위 동기화를 포함한다. | 오케스트레이터 | 정형 로더·두 도구가 없다고 적힌 기존 설명의 정정. |
| 2026-11-26 | T-2에 도구 담당표·평가 기록의 경계·API 역할 문서 네 곳을 추가한다. | 오케스트레이터 | `doc-sync` 연동 경고 4건. 기존 평가 지표·API 계약·실행 게이트는 변경하지 않는다. |
| 2026-11-26 | 문서 게이트는 면제하지 않고, 반영된 작업 트리의 읽기 전용 보안 점검은 독립해 진행한다. | 오케스트레이터 | `AGENTS.md` 쓰기를 재시도하지 않는다. 경고 1건은 결함 없는 것으로 판정하지 않는다. |

## 9. 완료 판정

| AC | 결과 | 근거 | 확인자 |
| --- | --- | --- | --- |
| AC-1 | pass | `test_pokedex_structured_tools.py` 8개 통과: 팀원 네 마리, 근거 여덟 청크, 전기 방어 빈틈과 후보. | 오케스트레이터 |
| AC-2 | pass | 같은 테스트에서 불꽃펀치 4배 두 마리·2배 스물네 마리와 방어 근거를 대조함. | 오케스트레이터 |
| AC-3 | pass | 같은 테스트와 상성 계산 회귀에서 변화기·별도 피해·미확정과 일반 배율을 분리함. | 오케스트레이터 |
| AC-4 | pass | `test_solar*.py` 50개, 어댑터 6개 통과. 인메모리 HTTP 3건에서 응답 계약과 정형 임베딩 필드 생략을 확인함. | 오케스트레이터 |
| AC-5 | pass | 지정 보호 경로의 `git diff --exit-code HEAD` 종료 0, 추가 파일 0개. 오프라인 검증으로 DB 쓰기와 임베딩 실행 없음. | 오케스트레이터 |
| AC-6 | fail | `check_docs.py --strict` ERROR 0, WARN 1. 보호된 `AGENTS.md`를 변경하지 않아 담당표 연동 경고가 남음. | 오케스트레이터 |
| AC-7 | pass | `check_security.py --base origin/main`, 읽기 전용 에이전트 검사와 재실행 모두 ERROR 0, WARN 0. | 오케스트레이터 |
| AC-8 | | | |

결과: `pass` | `fail` | `waived`. `waived`는 사용자 결정이 필요하며 근거 칸에 결정자·날짜를 적는다. 확인자는 그 AC를 맡은 담당이 아니어야 한다(예외: `명령:` AC는 오케스트레이터·디렉터가 다시 실행해 확인 가능). 취소한 작업의 AC도 판정한다.
