---
type: plan
id: 2026-11-26-rag-citation-reliability
title: RAG 출처 인용 오류 개선 계획
status: in_progress
owner: orchestrator
spec: 2026-11-26-rag-citation-reliability
created: 2026-11-26
updated: 2026-11-26
approved_by: 오케스트레이터
approved_at: 2026-11-26
completed_at:
archived_at:
base_commit: 3945d46
---

# RAG 출처 인용 오류 개선 계획

## 1. 개요

- 스펙: [2026-11-26-rag-citation-reliability](../specs/2026-11-26-rag-citation-reliability.md)
- 목표: 인용만 잘못된 경우 안전하게 안내하고, 일반·정형 답변에서 서버가 검증된 출처 번호를 붙인다.
- 작업 기준: `feat/structured-pokedex-tools`의 `0bab5fc` 및 현재 실패 로깅 변경. 기존 작업은 보존하고 새 변경은 커밋하지 않는다.
- 기준 커밋: 3945d46 (작성 시점 main)

## 2. 작업 분해

| ID | 작업 | 담당 | 선행 | 산출물 | 완료 기준 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| T-1 | 인용 거부 처리, 일반 주장·근거 응답, 정형 렌더링과 회귀 테스트·계약 문서 반영 | rag-developer | - | `solar_handoff/src/`, `tests/`, `solar_handoff/README.md`, `.claude/skills/langchain-rag/SKILL.md`, `.claude/skills/rag-eval/references/records.md`, `docs/references/api-rag-integration.md`, `docs/references/skills/README.md` | AC-1, AC-2, AC-3, AC-4 | done |
| T-2 | 비노출 및 저장소 검사 독립 확인 | security-reviewer | T-1 | - | AC-6 | done |
| T-3 | 문서 검사와 로컬 API 오프라인·기동 검증 | 오케스트레이터 | T-1 | - | AC-5 | blocked |
| T-4 | 잠긴 입력으로 공식 RAG 평가 | eval | T-2, T-3 | `results/` | AC-7 | blocked |

- 담당: `.claude/agents/`에 있는 에이전트 이름, 또는 `오케스트레이터`·`디렉터`·`팀원`·`사용자`.
- 선행: 먼저 끝나야 하는 작업 ID (쉼표 구분, 없으면 `-`).
- 산출물: 이 작업이 쓰는 파일·폴더 (백틱, 쉼표 구분). 같은 단계의 작업끼리 겹치면 안 된다.
- 완료 기준: 스펙의 AC ID. 스펙 AC에 직접 대응하지 않는 지원 작업은 `지원: <확인 조건>`으로 쓴다.
- 상태: `todo` | `doing` | `done` | `blocked` | `cancelled`.

## 3. 병렬 실행

`workdocs.py waves`가 계산한 단계를 붙인다. 같은 단계의 작업은 동시에 발주할 수 있다.

```
단계 1: T-1(rag-developer)
단계 2: T-2(security-reviewer), T-3(오케스트레이터)
단계 3: T-4(eval)
```

## 4. 발주서

작업마다 `AGENTS.md` 발주 양식으로 쓴다. `done_when`에는 2절의 완료 기준을 옮긴다.

```
task: T-1 — 인용 실패의 안내·진단부터 일반 검색 출력과 정형 렌더링까지 개선한다.
agent: rag-developer
inputs: 스펙, 0bab5fc와 작업 트리의 실패 로그, 기존 청크 schema_version=1, 기존 모의 HTTP 테스트.
outputs: 2절 T-1 범위의 코드·테스트·계약 문서.
done_when: AC-1–AC-4의 모의 차단/정상 응답·청크 허용 목록·정형 렌더링·보호 경로 검증이 통과한다.
constraints: 인용 가드를 완화하거나 임의 근거를 붙이지 않는다. 범위 밖 경로와 기존 로그를 보존하고 DB·실 API·공식 평가·커밋을 실행하지 않는다.
```

```
task: T-2 — 인용 거부 로그와 실패 안내의 비노출을 독립 검토한다.
agent: security-reviewer
inputs: 최신 origin/main 대비 T-1 변경분과 보안 검사 스킬.
outputs: 읽기 전용 보안 점검 보고.
done_when: AC-6의 검사 결과와 비노출 확인 근거가 보고됐다.
constraints: 파일 수정·보호 파일 열람·서비스 호출 금지.
```

```
task: T-3 — 문서 검사와 오프라인 HTTP 재현을 재실행하고 기존 로컬 API에 반영한다.
agent: 오케스트레이터
inputs: T-1 산출물, 모의 공급자와 로컬 API의 기동 계약.
outputs: 검증 근거와 로컬 API 상태 확인.
done_when: AC-5 결과 기록. 실패·정상 응답을 모의 HTTP로 검증하고 기존 API의 재기동 뒤 /health 200을 확인한다.
constraints: 새 유료 호출은 하지 않는다. 출처·상성·데이터·클라이언트 계약을 유지한다.
```

```
task: T-4 — 승인된 전체 RAG 평가를 수행한다.
agent: eval
inputs: 팀원이 잠근 평가 입력, 평가 승인, 검증된 T-1 결과.
outputs: results/{run_id}/ 실행 기록.
done_when: AC-7 및 AGENTS.md 평가 게이트 통과.
constraints: 팀 잠금 검증, 실제 DB·비용 승인 전에는 발주하지 않는다.
```

## 5. 검증과 보고

- 하위 에이전트 보고: 각 에이전트 정의의 보고 형식 (`status`, `changed_files`, `checks`의 evidence, `refused`, `downstream_impact`).
- 오케스트레이터 검토: `AGENTS.md` 보고 검토 절차. evidence 명령을 직접 다시 실행하고 결과를 7절에 남긴다.
- 읽기 전용 에이전트(리뷰어 등)의 판정은 보고 원문 요약을 7절에 남기고, 그 AC의 확인 방법은 `보고: <에이전트>`로 쓴다.
- 사용자 보고: 작업이 끝나거나 막힐 때 아래 형식으로 보고한다. 보고는 알림이며 승인 요청이 아니다. 스펙 변경이 필요할 때만 `next`에 사용자 결정 요청을 쓴다.

```
plan: 2026-11-26-rag-citation-reliability
done: [T-n, ...]
blocked: [T-n: 이유와 필요한 결정]
ac: [AC-n: pass | fail | not_run — 근거]
next: 디렉터가 정한 다음 단계 (스펙 변경이 필요할 때만 사용자 결정 요청)
```

## 6. 위험과 대응

| 위험 | 대응 |
| --- | --- |
| 인용 실패를 감추며 검증되지 않은 주장이 나감 | 로그는 고정 사유, 답변은 고정 안내 또는 검증된 도구 결과만 사용한다. |
| 일반 대화 내부 스키마 변경이 단일 질문 CLI에 전파됨 | 대화 경로의 형식만 바꾸고 CLI 스키마와 테스트를 보존한다. |
| 이전 브랜치 문서 경고 및 잠금 입력 부재 | 작업 단위·브랜치 문서 검사를 따로 남기고 기존 게이트를 면제하지 않는다. |

## 7. 진행 기록

| 날짜 | 작업 | 내용 | 근거 |
| --- | --- | --- | --- |
| 2026-11-26 | T-1 | 변경 기준 및 실제 실패 구간 확인 | 기존 로컬 커밋 `0bab5fc`, 콘솔 `citation_validation / validation_error`, 기존 로깅 변경 보존 |
| 2026-11-26 | T-4 | 평가 선행 입력 부재 | `eval/dev.json`, `eval/test.json`, `eval/LOCK.json`의 존재 여부만 확인 |
| 2026-11-26 | T-1 | 구현 및 후속 수정 독립 재검증 | Solar 61개, 정형 도구 8개, API chat 48개 통과. 루프백 Uvicorn 모의 정상·인용 거부·정형 요청 200, 인용 거부 경고 1건. 테스트용 DSN의 인증 필드를 제거한 뒤 전체 security-check ERROR 0, WARN 0 |
| 2026-11-26 | T-3 | 로컬 RAG API에 반영 및 기동 확인, 브랜치 문서 게이트 미통과 | 기존 Uvicorn만 재시작(검증 PID 48236). `/health`, 문서 `039`, 기존 프론트, CORS 사전 요청 200. 유료 호출 미실행. doc-sync `--strict`는 보호된 기존 연동 WARN 1건 |
| 2026-11-26 | T-2 | 독립 보안 검토 완료 | `security-reviewer`: 수정 필요 발견 없음, 집중 mock 테스트 25개 통과. 오케스트레이터 전체 security-check `--base origin/main`: ERROR 0, WARN 0 |

## 8. 결정 기록

디렉터의 판단: 계획 확정, 작업 추가·변경·취소, 막힌 작업 처리. 사용자 확인은 필요 없다(스펙 변경이 따르면 스펙 절차).

| 날짜 | 결정 | 결정자 | 근거 |
| --- | --- | --- | --- |
| 2026-11-26 | 인용 출력과 실패 처리만 조정하고 DB·검색·외부 계약은 유지 | 오케스트레이터 | 사용자가 안내, 일반 검색 근거 분리, 정형 출처 렌더링 세 개선을 승인 |
| 2026-11-26 | 내부 인용 처리에 관한 문서만 맞춤; API 계층별 스킬은 변경하지 않음 | 오케스트레이터 | 작업 단위 연동 경고 2건은 API 프론트 계약·어댑터에 영향 없음. 브랜치 strict 경고 1건은 기존 보호된 `AGENTS.md`이며 면제하지 않음 |

## 9. 완료 판정

| AC | 결과 | 근거 | 확인자 |
| --- | --- | --- | --- |
| AC-1 | pass | Solar 테스트 61개 및 루프백 200 안전 안내·고정 사유 로그 확인, 공급자·DB 502 유지 | 오케스트레이터 |
| AC-2 | pass | 같은 테스트의 선택 청크 enum, 번호·중복, 임베딩 메타데이터, A/B/C 및 단일 질문 CLI 회귀 통과 | 오케스트레이터 |
| AC-3 | pass | 정형 도구 테스트 8개와 HTTP 모의 팀·기술 출력, 선택 1회·답변과 임베딩 호출 0회 검증 | 오케스트레이터 |
| AC-4 | pass | 보호 경로 tracked diff 0, 새 파일 0, API chat 테스트 48개 통과 | 오케스트레이터 |
| AC-5 | fail | doc-sync `--strict` 종료 1: ERROR 0, 보호된 `AGENTS.md` 기존 연동 WARN 1 | 오케스트레이터 |
| AC-6 | pass | 전체 security-check 종료 0, ERROR 0, WARN 0. 독립 검토에서 인용 허용 목록·로그 비노출·200/502 분리 확인 | 오케스트레이터 |
| AC-7 | | | |

결과: `pass` | `fail` | `waived`. `waived`는 사용자 결정이 필요하며 근거 칸에 결정자·날짜를 적는다. 확인자는 그 AC를 맡은 담당이 아니어야 한다(예외: `명령:` AC는 오케스트레이터·디렉터가 다시 실행해 확인 가능). 취소한 작업의 AC도 판정한다.
