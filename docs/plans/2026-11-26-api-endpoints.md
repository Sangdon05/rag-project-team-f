---
type: plan
id: 2026-11-26-api-endpoints
title: API 엔드포인트 3종 구현 계획
status: in_progress
owner: orchestrator
spec: 2026-11-26-api-endpoints
created: 2026-11-26
updated: 2026-11-26
approved_by: 오케스트레이터
approved_at: 2026-11-26
completed_at:
archived_at:
base_commit: f758951
---

# API 엔드포인트 3종 구현 계획

## 1. 개요

- 스펙: [2026-11-26-api-endpoints](../specs/2026-11-26-api-endpoints.md)
- 목표: suggestion·chat·documents 엔드포인트를 mock·llm 모드로 동작시키고, 출처 `source_ref_id`(도감번호 3자리)로 Solar 원문까지 조회되게 한다.
- 기준 커밋: f758951 (작성 시점 main)
- 브랜치: `docs/api-ep-contracts` → `docs/api-design` → `feat/api-core` → `feat/api-chat` → `feat/api-documents` 순서로 쌓는다. 파일럿 메타데이터는 main 기준 `feat/source-ref-id`(워크트리 `../rag-project-team-f-source-ref`).

## 2. 작업 분해

| ID | 작업 | 담당 | 선행 | 산출물 | 완료 기준 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| T-1 | 계약 문서를 확정 EP 명세에 맞춘다 (응답 형식, `Source`, 문서 저장소 포트, R7·R11, smoke) | 오케스트레이터 | - | `docs/references/api-rag-integration.md`, `.claude/skills/api-invariants/`, `.claude/skills/api-implementation/`, `.claude/skills/api-architecture/` | 지원: doc-sync ERROR 0 | done |
| T-2 | health·suggestion·chat·documents 설계안 작성 | api-architect | T-1 | `docs/design/api/` | 지원: 설계안 4개 "검토 중", doc-sync ERROR 0 | done |
| T-3 | 공통(shared, error_handlers, container, main) + health + suggestion 구현 | api-implementer | T-2 | `api/shared/`, `api/health/`, `api/suggestion/`, `api/main.py`, `api/container.py`, `api/error_handlers.py`, `api/tests/` | AC-1 | done |
| T-4 | T-3 독립 리뷰·smoke | api-reviewer | T-3 | | AC-5 | done |
| T-5 | chat 슬라이스 구현 (mock·llm) | api-implementer | T-3 | `api/chat/`, `api/tests/chat/` | AC-1 | done |
| T-6 | T-5 독립 리뷰·smoke | api-reviewer | T-5 | | AC-5 | done |
| T-7 | documents 슬라이스, 500 CORS·dotenv 보완, role 검증 수정, `reasoning_effort` | api-implementer | T-5 | `api/documents/`, `api/tests/documents/` | AC-1, AC-3 | done |
| T-8 | T-7 독립 리뷰·smoke | api-reviewer | T-7 | | AC-5 | done |
| T-9 | `source_ref_id` 도감번호 3자리로 계약·설계안·smoke 갱신 | 오케스트레이터 | T-8 | `docs/design/api/documents.md`, `docs/references/api-rag-integration.md`, `.claude/skills/api-invariants/SKILL.md` | 지원: doc-sync ERROR 0 | done |
| T-10 | documents를 `<번호>_*.md` 조회로 바꾸고 기본 폴더를 `solar_handoff/documents`로 | api-implementer | T-9 | `api/documents/`, `api/tests/documents/`, `api/shared/settings.py`, `.env.example` | AC-1, AC-4 | todo |
| T-11 | 파일럿 청크 `source_ref_id`를 도감번호 3자리로 | data-engineer | - | `scripts/helper/pilot_vector_index.py`, `tests/test_pilot_vector_index.py`, `.claude/skills/chunking/SKILL.md` | AC-6 | done |
| T-12 | 최종 변경 독립 리뷰·smoke (`DOC_ID=001`) | api-reviewer | T-10 | | AC-2, AC-5 | todo |
| T-13 | PR 전 보안 점검 (두 브랜치) | security-reviewer | T-10, T-11 | | AC-8 | todo |
| T-14 | 문서 동기화 검사 | 오케스트레이터 | T-10, T-11 | | AC-7 | todo |

- 담당: `.claude/agents/`에 있는 에이전트 이름, 또는 `오케스트레이터`·`디렉터`·`팀원`·`사용자`.
- 선행: 먼저 끝나야 하는 작업 ID (쉼표 구분, 없으면 `-`).
- 산출물: 이 작업이 쓰는 파일·폴더 (백틱, 쉼표 구분). 같은 단계의 작업끼리 겹치면 안 된다.
- 완료 기준: 스펙의 AC ID. 스펙 AC에 직접 대응하지 않는 지원 작업은 `지원: <확인 조건>`으로 쓴다.
- 상태: `todo` | `doing` | `done` | `blocked` | `cancelled`.

## 3. 병렬 실행

`workdocs.py waves`가 계산한 단계를 붙인다. 같은 단계의 작업은 동시에 발주할 수 있다.

```
단계 1: T-1(오케스트레이터), T-11(data-engineer)
단계 2: T-2(api-architect)
단계 3: T-3(api-implementer)
단계 4: T-4(api-reviewer), T-5(api-implementer)
단계 5: T-6(api-reviewer), T-7(api-implementer)
단계 6: T-8(api-reviewer)
단계 7: T-9(오케스트레이터)
단계 8: T-10(api-implementer)
단계 9: T-12(api-reviewer), T-13(security-reviewer), T-14(오케스트레이터)
```

## 4. 발주서

T-1~T-8은 스펙 작성 전에 같은 내용으로 발주·완료했다(7절). 남은 작업:

```
task: documents를 도감번호 3자리 source_ref_id로 <API_DOCUMENTS_DIR>/<번호>_*.md를 찾게 바꾸고 기본 폴더를 solar_handoff/documents로 한다 (T-10)
agent: api-implementer
inputs: docs/design/api/documents.md (T-9 갱신본), solar_handoff/documents/ (main f758951)
outputs: api/documents/, api/tests/documents/, api/shared/settings.py, .env.example, docs/references/environment.md, README.md
done_when: AC-1 api-invariants §7 게이트 통과, AC-4 `uv run python -m unittest api.tests.documents.test_documents_api` OK이고 001 요청이 solar_handoff/documents/001_이상해씨.md 내용과 같음
constraints: solar_handoff/·data/·eval/·.claude/·설계안 수정 금지, 커밋 금지
```

```
task: 파일럿 청크 source_ref_id를 도감번호 3자리(pokemon_id zero-pad)로 바꾼다 (T-11)
agent: data-engineer
inputs: scripts/helper/pilot_vector_index.py, .claude/skills/chunking/SKILL.md, data/synthetic/pilot/ (schema_version 3)
outputs: 위 파일과 tests/test_pilot_vector_index.py
done_when: AC-6 `uv run python -m unittest tests.test_pilot_vector_index` OK, 10개 청크 모두 001
constraints: data/processed/·solar_handoff/·eval/ 수정 금지, chunk_id·document_id 규칙 유지
```

```
task: T-10 결과 독립 리뷰와 smoke (T-12)
agent: api-reviewer
inputs: feat/api-documents 최신 커밋, docs/design/api/documents.md
outputs: 리뷰 보고
done_when: AC-2 api-invariants §10 smoke(DOC_ID=001) 결과: 모두 PASS, AC-5 APPROVE
constraints: 읽기 전용
```

```
task: feat/api-documents, feat/source-ref-id PR 전 보안 점검 (T-13)
agent: security-reviewer
inputs: 두 브랜치, base origin/main
outputs: 분류 보고
done_when: AC-8 ERROR 0
constraints: 읽기 전용
```

## 5. 검증과 보고

- 하위 에이전트 보고: 각 에이전트 정의의 보고 형식 (`status`, `changed_files`, `checks`의 evidence, `refused`, `downstream_impact`).
- 오케스트레이터 검토: `AGENTS.md` 보고 검토 절차. evidence 명령을 직접 다시 실행하고 결과를 7절에 남긴다.
- 읽기 전용 에이전트(리뷰어 등)의 판정은 보고 원문 요약을 7절에 남기고, 그 AC의 확인 방법은 `보고: <에이전트>`로 쓴다.
- 사용자 보고: 작업이 끝나거나 막힐 때 아래 형식으로 보고한다. 보고는 알림이며 승인 요청이 아니다. 스펙 변경이 필요할 때만 `next`에 사용자 결정 요청을 쓴다.

```
plan: 2026-11-26-api-endpoints
done: [T-n, ...]
blocked: [T-n: 이유와 필요한 결정]
ac: [AC-n: pass | fail | not_run — 근거]
next: 디렉터가 정한 다음 단계 (스펙 변경이 필요할 때만 사용자 결정 요청)
```

## 6. 위험과 대응

| 위험 | 대응 |
| --- | --- |
| Solar 문서 폴더에 같은 번호 파일이 둘 이상 생김 | 저장소가 모호함으로 보고 502 `DOCUMENT_SOURCE_FAILED`. 파일명 규칙은 RAG 쪽 원본 |
| Solar CLI가 아직 `source_ref_id`를 내보내지 않아 rag 모드에서 출처 조회가 안 됨 | 범위 밖. 후속 목록 G7 옆에 rag-developer 항목으로 남긴다 |
| 쌓인 브랜치를 슬라이스별 PR로 나눌 때 중간 PR의 문서 검사 실패 | 각 커밋에서 패키지·환경 변수 문서를 같이 갱신했다. PR 전에 브랜치마다 doc-sync를 다시 돌린다 |

## 7. 진행 기록

| 날짜 | 작업 | 내용 | 근거 |
| --- | --- | --- | --- |
| 2026-11-26 | T-1 | 계약 문서 갱신, smoke 가짜 서버로 good 12 PASS / old 4 FAIL 확인 | `docs/api-ep-contracts` 739c6a1 |
| 2026-11-26 | T-2 | 설계안 4개 작성(api-architect), 오케스트레이터 커밋 | `docs/api-design` 9c8f8d8, 211f290 |
| 2026-11-26 | T-3 | 게이트 4개 통과(api 30, tests 101 OK) | `feat/api-core` 47f66e3 |
| 2026-11-26 | T-4 | api-reviewer APPROVE, 주의 3건(500 CORS, dotenv, `API_DOCUMENTS_DIR` 문서) → T-7로 반영 | 리뷰 보고 |
| 2026-11-26 | T-5 | 게이트 통과(api 62 OK) | `feat/api-chat` 84953be |
| 2026-11-26 | T-6 | api-reviewer APPROVE, 주의 1건(role 비문자열 TypeError) → T-7로 반영 | 리뷰 보고 |
| 2026-11-26 | T-7 | documents·보완 3건·role 수정·`reasoning_effort`, 게이트 통과(api 88 OK), security ERROR 0·WARN 0 | `feat/api-documents` a38df67, 500dd5a, 925d38d |
| 2026-11-26 | T-8 | api-reviewer APPROVE, smoke 14항목 PASS | 리뷰 보고 |
| 2026-11-26 | T-9 | documents·chat·health 설계안, 연결 가이드, api-invariants §10·smoke(`DOC_ID=001`, 없는 번호 999), 스킬 표를 도감번호 3자리로 갱신. 후속 G8 추가. doc-sync ERROR 0 | `feat/api-documents` |
| 2026-11-26 | T-11 | 파일럿 5판 10청크 `source_ref_id` 모두 `001`, `tests.test_pilot_vector_index` 14 OK, tests 127 OK(skipped=1), doc-sync ERROR 0, security ERROR 0. 이전 파일명 방식 커밋과 합쳐 한 커밋으로 정리 | `feat/source-ref-id` f479d1b |
| 2026-11-26 | - | origin/main(f758951) 기준 rebase(`--update-refs`), 충돌 README·environment.md 해결 | `git log origin/main..feat/api-documents` |

## 8. 결정 기록

디렉터의 판단: 계획 확정, 작업 추가·변경·취소, 막힌 작업 처리. 사용자 확인은 필요 없다(스펙 변경이 따르면 스펙 절차).

| 날짜 | 결정 | 결정자 | 근거 |
| --- | --- | --- | --- |
| 2026-11-26 | T-1~T-8은 spec-plan 스킬 머지 전에 수행한 작업이라 완료 상태로 기록한다 | 오케스트레이터 | main f758951에 spec-plan 머지 |
| 2026-11-26 | T-9의 `documents.md` 갱신은 결정 반영만이므로 api-architect 대신 오케스트레이터가 한다 | 오케스트레이터 | 사용자 결정(도감번호 3자리)의 기계적 반영 |

## 9. 완료 판정

| AC | 결과 | 근거 | 확인자 |
| --- | --- | --- | --- |
| AC-1 | | | |
| AC-2 | | | |
| AC-3 | | | |
| AC-4 | | | |
| AC-5 | | | |
| AC-6 | | | |
| AC-7 | | | |
| AC-8 | | | |

결과: `pass` | `fail` | `waived`. `waived`는 사용자 결정이 필요하며 근거 칸에 결정자·날짜를 적는다. 확인자는 그 AC를 맡은 담당이 아니어야 한다(예외: `명령:` AC는 오케스트레이터·디렉터가 다시 실행해 확인 가능). 취소한 작업의 AC도 판정한다.
