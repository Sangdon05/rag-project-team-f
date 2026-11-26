---
title: API 엔드포인트 3종 구현 계획
status: 구현 완료 (PR 대기)
created: 2026-11-26
owner: 오케스트레이터
---

# API 엔드포인트 3종 구현 계획

팀 명세(외부 문서)로 확정한 엔드포인트 3개를 `api/`에 구현하는 계획이다. 이 문서의 "확정 규격"은 설계안 작성(api-architect)의 입력이다.
학습 프로젝트이므로 서비스용 제한(요청 크기, 타임아웃, 호출 횟수)은 두지 않고 동작 기준으로 판단한다.

## 1. 범위

- `GET /api/v1/suggestion`, `POST /api/v1/chat`, `GET /api/v1/documents/{source_ref_id}`, `GET /health`
- 답변 생성은 `mock`·`llm`까지. `rag` 연결은 범위 밖이며 [연결 가이드](../references/api-rag-integration.md) 4절을 따른다.

## 2. 결정

| 항목 | 결정 |
| --- | --- |
| 응답 형식 | 성공 `{"success": true, "data": {...}}`, 실패 `{"success": false, "error_code", "message"}` (모든 엔드포인트, `/health` 포함) |
| 문서 ID 필드 | `source_ref_id`로 통일 (chat `sources[]`, documents 경로·응답) |
| `source_ref_id` 값 | 원문 Markdown 파일명(확장자 제외). 허용 문자 `[A-Za-z0-9_-]`. 예: `bulbasaur_red_blue` |
| 예시 ID | RAG가 주는 값을 그대로 쓴다. API는 형식을 바꾸지 않는다 |
| 메시지 길이 | 한도 없음. 앞뒤 공백 제거 후 비어 있지만 않으면 된다 |
| 메시지 수 | `API_MAX_MESSAGES` (기본 20) 유지 |
| 출처 수 | 한도 없음. `API_MAX_SOURCES`를 두지 않는다 |
| `ref` 번호 | 체인이 정한 값을 그대로 쓴다. answer의 `[n]`과 같은 값 |
| 400 `error_code` | 스키마 위반과 대화 규칙 위반 모두 `VALIDATION_ERROR` (슬라이스 전용 400 코드를 두지 않는다) |
| PR 나누기 | 계약 문서 → RAG 메타데이터 → 공통+health+suggestion → chat → documents |

## 3. 확정 규격

### 공통

| HTTP | error_code | 조건 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | 요청 형식·값 오류 (FastAPI 기본 422를 400으로 바꾼다) |
| 404 | `NOT_FOUND` | 없는 경로 (Starlette 기본 `{"detail"}`을 공통 형식으로 바꾼다) |
| 405 | `METHOD_NOT_ALLOWED` | 허용하지 않는 메서드 |
| 500 | `INTERNAL_ERROR` | 처리하지 못한 예외. 스택·원문 오류를 응답에 넣지 않는다 |

### `GET /health`

- 응답 `{"success": true, "data": {"status": "ok"}}`. 외부 호출 없음.

### `GET /api/v1/suggestion`

- query `level`: `beginner`(P1, 기본값) / `novice`(P2) / `expert`(P3). 대소문자 구분. 허용값 밖이거나 빈 값이면 400.
- 응답 `data`: `level`(적용된 등급), `suggestions[]`(`id`, `text`). 0개일 수 있다.
- 후보는 fake 데이터(포켓몬 질문)이며 제공자 포트 뒤에 둔다. 평가셋과 무관하다.

### `POST /api/v1/chat`

- 요청 `messages[]`(`role`: `user` | `assistant`, `content`). 1개 이상 `API_MAX_MESSAGES`개 이하. 첫·마지막은 user, 중간은 교대. content는 앞뒤 공백 제거 후 비어 있으면 안 된다.
- 서버는 대화를 저장하지 않는다. 클라이언트가 매 요청에 대화 전체를 보낸다.
- 응답 `data`: `answer`(비어 있지 않음, 근거 문장 뒤 `[n]`), `mode`(`mock` | `llm` | `rag`), `sources[]`(`ref`, `chunk_id`, `source_ref_id`).
- "근거가 부족해 확인할 수 없다"는 200. 생성기 실패는 502 `ANSWER_GENERATION_FAILED`.

### `GET /api/v1/documents/{source_ref_id}`

- chat `sources[].source_ref_id`로 호출한다. 문서 원본은 RAG 데이터이며 API는 그대로 전달한다.
- 응답 `data`: `source_ref_id`, `markdown`(원문 그대로, HTML 변환 없음).
- 400 `VALIDATION_ERROR`: `[A-Za-z0-9_-]` 밖의 문자 포함. 404 `DOCUMENT_NOT_FOUND`: 형식은 맞지만 파일 없음. 502 `DOCUMENT_SOURCE_FAILED`: 저장소 읽기 실패.
- 문서 위치는 환경 변수 `API_DOCUMENTS_DIR`. 파일은 `<API_DOCUMENTS_DIR>/<source_ref_id>.md`.

## 4. 기존 문서와 충돌 (1단계에서 처리)

| 파일 | 내용 | 처리 |
| --- | --- | --- |
| `docs/references/api-rag-integration.md` §2 | `Source`에 `ref` 없음, HTTP 계약이 공통 형식 아님, 문서 저장소 포트 없음 | 갱신 |
| `.claude/skills/api-invariants/SKILL.md` R7, R11, §10 | 502가 답변 생성기만, 길이 한도 규칙, smoke 표가 최상위 `answer` | 갱신 |
| `.claude/skills/api-invariants/scripts/smoke.sh` | 최상위 `answer`·`sources`·`mode` 검사, documents 검사 없음 | `data.*` 검사, documents 항목 추가 |
| `.claude/skills/api-implementation/SKILL.md`, `references/testing.md` | `API_MAX_MESSAGE_CHARS`, 슬라이스 전용 400 코드, 공통 형식 없는 응답 | 갱신 |
| `.claude/skills/api-architecture/SKILL.md` §4 | `Source`에 `ref` 없음, 길이 한도 | 갱신 |
| `.claude/skills/chunking/SKILL.md:120`, `scripts/helper/pilot_vector_index.py:144` | `source_ref_id` = `{청크 JSON 경로}#{chunk_id}` | 2단계(data-engineer) |

## 5. 단계

### 1단계 — 오케스트레이터: 계약 문서 (PR ①)

4절 표의 문서 행을 고친다. 코드 없음. 게이트: `check_docs.py --base HEAD` ERROR 0, security-check 통과.

### 2단계 — data-engineer: `source_ref_id` 값 형식 (PR ②, 1단계와 병렬)

```
task: 청크 메타데이터 source_ref_id를 원문 Markdown 파일명(확장자 제외)으로 바꾼다
agent: data-engineer
inputs: .claude/skills/chunking/SKILL.md (메타데이터 표), scripts/helper/pilot_vector_index.py, data/synthetic/pilot/ (schema_version 3)
outputs: 위 두 파일, 관련 테스트
done_when: 파일럿 청크 10개의 source_ref_id가 모두 bulbasaur_red_blue, uv run python -m unittest discover -s tests 통과
constraints: data/processed/ 수정 금지, chunk_id 규칙 유지, eval/ 열람 금지
```

151마리 Markdown 파일명 규칙도 이 단계에서 정한다(권장 `{영문명}_red_blue`, 허용 문자 `[A-Za-z0-9_-]`).

### 3단계 — api-architect: 설계안 (1단계 머지 후)

```
task: health, suggestion, chat, documents 설계안을 이 계획의 확정 규격대로 작성한다
agent: api-architect
inputs: docs/plans/2026-11-26-api-endpoints.md 3절, docs/references/api-rag-integration.md, .claude/skills/api-invariants/SKILL.md
outputs: docs/design/api/{health,suggestion,chat,documents}.md, docs/design/api/README.md 표
done_when: 네 설계안 상태 "검토 중", doc-sync ERROR 0
constraints: docs/design/api/만 수정
```

설계안의 "확정"은 팀원이 정한다.

### 4단계 — api-implementer → api-reviewer: 슬라이스별 구현 (PR ③ ④ ⑤)

| PR | 범위 |
| --- | --- |
| ③ | `api/shared/`(응답 형식, 예외, 설정), `error_handlers.py`, `container.py`, `main.py`, health, suggestion |
| ④ | chat: `Conversation` 검증(개수, role, 교대, 빈 값), mock·llm 생성기, 502 |
| ⑤ | documents: `DocumentStore` 포트, 파일 구현체, `API_DOCUMENTS_DIR`(`.env.example`, environment.md, README 함께) |

```
task: <슬라이스> 설계안대로 구현한다
agent: api-implementer
inputs: docs/design/api/<slice>.md
outputs: api/<slice>/, api/tests/
done_when: api-invariants §7 게이트 통과, §10 smoke(mock) PASS
constraints: data/, scripts/, eval/ 수정 금지, 실제 LLM 호출 금지
```

구현 뒤 api-reviewer에게 같은 슬라이스의 독립 리뷰를 발주한다(APPROVE 전 머지 금지).

### 5단계 — 오케스트레이터: 마무리

- PR마다 doc-sync `--strict`, security-reviewer 점검.
- [연결 가이드](../references/api-rag-integration.md) 6절 체크리스트 갱신. `rag` 행은 예정 유지.
- 확인: `GET /api/v1/documents/bulbasaur_red_blue` → 200 (`API_DOCUMENTS_DIR=data/synthetic/pilot`).

## 6. 완료 조건

- 엔드포인트 4개가 3절 규격대로 응답한다(smoke와 curl로 상태 코드·`error_code` 확인).
- PR ①~⑤가 게이트 통과와 리뷰 APPROVE 뒤 머지된다.
- 파일럿 청크의 `source_ref_id`로 documents 조회가 성공한다.

## 7. 진행 기록

| 단계 | 브랜치 | 커밋 | 결과 |
| --- | --- | --- | --- |
| 1 계약 문서 | `docs/api-ep-contracts` | b096b09 | doc-sync ERROR 0, security ERROR 0 |
| 2 `source_ref_id` | `feat/source-ref-id` (main 기준, 별도) | dff952e | 파일럿 10청크 `bulbasaur_red_blue`, tests 103 OK |
| 3 설계안 | `docs/api-design` | 81a6581, cc17162 | 네 설계안 "검토 중" |
| 4-③ 공통·health·suggestion | `feat/api-core` | 16d1ac7 | api-reviewer APPROVE |
| 4-④ chat | `feat/api-chat` | 95938ae | api-reviewer APPROVE |
| 4-⑤ documents + 공통 보완 + role 수정 + `reasoning_effort` | `feat/api-documents` | 698f707, 9e697a9, 21fd77f | api-reviewer APPROVE, smoke 14항목 PASS |

브랜치는 1 → 3 → ③ → ④ → ⑤ 순서로 쌓여 있다. ③의 `environment.md` 패키지 행(fastapi·uvicorn·httpx)은 ⑤ 커밋에 들어가 있어 ③만 따로 PR하면 doc-sync ERROR가 난다.

추가 결정: llm 모드 `OPENAI_REASONING_EFFORT`(기본 `low`), temperature 0 유지. RAG 체인 반영과 실제 키 확인은 [후속 목록](../proposals/api-dev-env-followups.md) G7.

## 8. 위험

- 2단계가 늦어지면 ⑤는 파일명을 직접 넣는 테스트로 완료하고, chat → documents 연결 확인은 `rag` 연결 때로 미룬다(mock·llm은 `sources`가 비어 있다).
- api-implementation 스킬의 예시 코드는 1단계에서 문서만 고친다. 실제 동작 확인은 ③ ④ 구현의 게이트에서 한다.
