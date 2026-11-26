---
type: spec
id: 2026-11-26-api-endpoints
title: API 엔드포인트 3종 (suggestion, chat, documents)
status: done
owner: orchestrator
created: 2026-11-26
updated: 2026-11-26
approved_by: 사용자
approved_at: 2026-11-26
completed_at: 2026-11-26
archived_at: 2026-11-26
related: []
---

# API 엔드포인트 3종 (suggestion, chat, documents)

## 1. 배경과 목적

프론트가 쓸 FastAPI 서비스(`api/`)에 팀이 확정한 엔드포인트 3개(추천 질문, 질문 답변, 출처 원문 조회)를 만든다. 답변 출처 `[n]`에서 원문 Markdown까지 이어지게 해, RAG 연결 전에도 mock·llm 모드로 프론트 연동을 시작할 수 있게 한다.
학습 프로젝트이므로 서비스용 제한(요청 크기, 타임아웃, 호출 횟수)은 두지 않고 동작 기준으로 판단한다.

## 2. 범위

포함:

- `GET /health`, `GET /api/v1/suggestion`, `POST /api/v1/chat`, `GET /api/v1/documents/{source_ref_id}`
- 공통 응답 형식과 에러 변환, mock·llm 답변 생성기
- 출처 문서 ID(`source_ref_id`) 형식 확정과 파일럿 청크 메타데이터 반영
- API–RAG 연결 계약 문서, api-invariants 규칙·smoke 갱신

제외:

- `rag` 답변 생성기 연결 ([연결 가이드](../../references/api-rag-integration.md) 4절, RAG 진입점 준비 후)
- Solar 질문 CLI가 `source_ref_id`를 내보내도록 바꾸는 일 (rag-developer 후속)
- 실제 OpenAI 키로 llm 모드 호출 확인

## 3. 요구사항

| ID | 요구사항 | 구분 |
| --- | --- | --- |
| REQ-1 | 모든 응답이 성공 `{"success": true, "data": {...}}`, 실패 `{"success": false, "error_code", "message"}` 형식이다. 요청 형식·값 오류는 400 `VALIDATION_ERROR`, 없는 경로 404 `NOT_FOUND`, 허용하지 않는 메서드 405 `METHOD_NOT_ALLOWED`, 처리 못 한 예외 500 `INTERNAL_ERROR`(CORS 헤더 유지, 원문 비노출)다 | 필수 |
| REQ-2 | `GET /api/v1/suggestion?level=`이 `beginner`(기본)·`novice`·`expert`별 추천 질문 `{level, suggestions[{id, text}]}`를 돌려준다. 허용값 밖이나 빈 값은 400 | 필수 |
| REQ-3 | `POST /api/v1/chat`이 `messages[{role, content}]`(1개 이상 `API_MAX_MESSAGES`개 이하, 첫·마지막 user, 교대, 빈 content 금지, 길이 한도 없음)를 받아 `{answer, mode, sources[{ref, chunk_id, source_ref_id}]}`를 돌려준다. 생성기 실패는 502 `ANSWER_GENERATION_FAILED` | 필수 |
| REQ-4 | llm 모드는 `OPENAI_CHAT_MODEL`을 temperature 0, `reasoning_effort`=`OPENAI_REASONING_EFFORT`(기본 `low`)로 호출한다 | 필수 |
| REQ-5 | `source_ref_id`는 도감번호 3자리(예: `001`)다. `GET /api/v1/documents/{source_ref_id}`가 `<API_DOCUMENTS_DIR>/<source_ref_id>_*.md` 원문을 `{source_ref_id, markdown}`으로 그대로 돌려준다(기본 폴더 `solar_handoff/documents`). 형식 위반 400, 파일 없음 404 `DOCUMENT_NOT_FOUND`, 저장소 읽기 실패 502 `DOCUMENT_SOURCE_FAILED` | 필수 |
| REQ-6 | 파일럿 청크 메타데이터의 `source_ref_id`가 REQ-5 형식이다 | 필수 |
| REQ-7 | 연결 계약 문서와 규칙 문서가 REQ-1~6과 일치한다 | 필수 |

구분: `필수` | `선택`. 필수 요구사항은 완료 기준이 하나 이상 있어야 한다.

## 4. 제약

- 바꾸면 안 되는 것: `data/processed/` 해시 고정 파일, `eval/`, `solar_handoff/` 내용(읽기만), 청크 `chunk_id`·`document_id` 규칙
- 따를 가드레일: `AGENTS.md` 가드레일 절, [api-invariants](../../../.claude/skills/api-invariants/SKILL.md) R1~R16, [chunking](../../../.claude/skills/chunking/SKILL.md)

## 5. 입력과 산출물

| 구분 | 경로 | 버전·기준 |
| --- | --- | --- |
| 입력 | 팀 EP 명세 (외부 문서, 사용자 제공) | 2026-11-26 확정본 |
| 입력 | `solar_handoff/documents/` | main f758951 |
| 입력 | `data/synthetic/pilot/` | schema_version 3 |
| 산출물 | `api/`, `api/tests/` | |
| 산출물 | `docs/design/api/` | 설계안 4개 |
| 산출물 | `docs/references/api-rag-integration.md`, `.claude/skills/api-invariants/` | |
| 산출물 | `scripts/helper/pilot_vector_index.py`, `.claude/skills/chunking/SKILL.md` | |

## 6. 완료 기준

| ID | 기준 | 확인 방법 | 기대 결과 | 요구사항 |
| --- | --- | --- | --- | --- |
| AC-1 | API 완료 게이트 통과 | 명령: api-invariants §7 게이트 | layer-check 위반 0, `import api.main` exit 0, `api/tests` 실패·skip 0, `tests` 실패 0 | REQ-1, REQ-2, REQ-3, REQ-4, REQ-5 |
| AC-2 | 서버 smoke 통과 | 명령: api-invariants §10 절차 (`DOC_ID=001`) | `결과: 모두 PASS` | REQ-1, REQ-2, REQ-3, REQ-5 |
| AC-3 | llm 모드 생성 파라미터 | 명령: `uv run python -m unittest api.tests.chat.test_chat_api` | OK, `reasoning_effort` 기본 `low`·temperature 0 단언 포함 | REQ-4 |
| AC-4 | 도감번호로 Solar 원문 조회 | 명령: `uv run python -m unittest api.tests.documents.test_documents_api` | OK, `001` 요청 결과가 `solar_handoff/documents/001_이상해씨.md` 내용과 같음 | REQ-5 |
| AC-5 | API 독립 리뷰 | 보고: api-reviewer | 최종 변경에 APPROVE | REQ-1, REQ-2, REQ-3, REQ-4, REQ-5 |
| AC-6 | 파일럿 청크 `source_ref_id` | 명령: `uv run python -m unittest tests.test_pilot_vector_index` | OK, 10개 청크 모두 `001` | REQ-6 |
| AC-7 | 문서 동기화 | 명령: `uv run python .claude/skills/doc-sync/scripts/check_docs.py --base origin/main` | ERROR 0 | REQ-7 |
| AC-8 | 보안 점검 | 보고: security-reviewer | ERROR 0 | REQ-1, REQ-2, REQ-3, REQ-4, REQ-5, REQ-6 |

작성 규칙은 spec-plan 스킬의 completion-criteria 참조 문서를 따른다.
