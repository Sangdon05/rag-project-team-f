---
type: spec
id: 2026-11-26-rag-citation-reliability
title: RAG 대화의 출처 인용 오류 개선
status: approved
owner: orchestrator
created: 2026-11-26
updated: 2026-11-26
approved_by: 사용자
approved_at: 2026-11-26
completed_at:
archived_at:
related: [2026-11-26-structured-pokedex-tools]
---

# RAG 대화의 출처 인용 오류 개선

## 1. 배경과 목적

로컬 대화 API에서 GPT 응답을 받은 뒤 인용 검사 단계의 `validation_error`가 502로 관측됐다. 인용 규칙 위반을 외부 호출 장애와 구분하고, 답변 본문에 모델이 인용 표기를 직접 넣는 의존성을 없앤다.

## 2. 범위

포함:

- 인용 검사 거부의 세부 사유를 안전한 코드로 구분하고, 확인된 답변을 만들 수 없으면 기존 정상 응답 형식으로 근거 확인 불가를 안내한다.
- 일반 검색은 모델의 주장과 근거 ID를 별개 필드로 받고, 서버가 이번 요청의 근거만 검증해 표시용 번호를 붙인다.
- 팀·기술 정형 도구는 계산 결과와 검증된 근거를 서버가 직접 연결해 답변을 표시한다. GPT의 도구 선택은 유지한다.

제외:

- 재임베딩, DB·인덱스·정제 데이터 변경, 검색 정책 변경, 별도 질문 라우터, 프론트·HTTP 필드 변경, 자동 모델 재시도.
- 공식 평가셋 수정, 유료 호출·실제 DB 접속 허용. 공식 평가 게이트를 면제하지 않는다.

## 3. 요구사항

| ID | 요구사항 | 구분 |
| --- | --- | --- |
| REQ-1 | 인용만 거부되면 검증되지 않은 본문이나 출처를 노출하지 않고 한국어 안내를 반환한다. 로그는 인용 누락·형식 위반·허용되지 않은 ID를 구분하며, 외부 호출·DB 실패는 기존 502를 유지한다. | 필수 |
| REQ-2 | 일반 검색의 각 사실 문장은 이번 호출의 선택 근거 ID를 별개로 참조한다. 서버가 참조를 검증하고 본문 `[n]`과 `sources`의 번호·순서를 일치시킨다. | 필수 |
| REQ-3 | 정형 팀·기술 답변은 검증된 Red·Blue 계산 결과와 일치하고, 서버가 해당 결과의 근거만 표시한다. 도구 선택 이후 GPT가 결과나 전체 인용을 다시 작성하지 않는다. | 필수 |
| REQ-4 | 기존 HTTP 필드, 데이터, CLI 및 A/B/C 정책을 유지하고 테스트·문서·보안·평가 게이트를 적용한다. | 필수 |

구분: `필수` | `선택`. 필수 요구사항은 완료 기준이 하나 이상 있어야 한다.

## 4. 제약

- `api/`, `frontend/`, 정형 도구의 계산·입력 계약, 해시 고정 파일, 청크, DB 및 CLI 답변 형식을 바꾸지 않는다. 질의 임베딩을 실제 호출한 경우에만 해당 메타데이터를 표시한다.
- 인용 형식을 추정해 고치거나 선택하지 않은 근거를 붙이지 않는다. ID 검증이 주장과 근거의 의미상 일치를 증명한다고 간주하지 않는다.
- 실패 로그에 질문·출처 원문·모델 본문·임의 ID·비밀·예외 내용을 넣지 않는다. 기존 미커밋 실패 단계 로깅과 사용자 변경을 보존한다.
- [AGENTS.md](../../AGENTS.md), [langchain-rag](../../.claude/skills/langchain-rag/SKILL.md), [tool-calling](../../.claude/skills/tool-calling/SKILL.md)의 호출 및 근거 검증 규칙을 따른다.

## 5. 입력과 산출물

| 구분 | 경로 | 버전·기준 |
| --- | --- | --- |
| 입력 | `solar_handoff/src/`, `src/pokedex/tools/` | 작업 기준 `0bab5fc` 및 기존 실패 로깅 작업 트리 |
| 입력 | `solar_handoff/chunks/draft-a-v1/chunks.jsonl` | 청크 `schema_version=1`; 인덱스·모델 설정 불변 |
| 산출물 | `solar_handoff/src/`, `tests/`, 관련 운영·연동 문서 | 대화 인용 형식, 검증 거부 처리, 정형 답변 렌더링, 오프라인 회귀 |

## 6. 완료 기준

| ID | 기준 | 확인 방법 | 기대 결과 | 요구사항 |
| --- | --- | --- | --- | --- |
| AC-1 | 인용 실패가 보호된 안내로 완료됨 | 명령: `uv run --offline --no-sync --no-env-file python -B -m unittest discover -s tests -p 'test_solar*.py'` | 모의 후속 요청에서 사유별 경고 1건과 빈 출처를 포함한 200 반환, 검증되지 않은 문장과 주입 표식 비노출. 같은 테스트에서 공급자·DB 실패는 재시도 없는 502 | REQ-1 |
| AC-2 | 일반 검색의 주장과 근거가 연결됨 | 명령: `uv run --offline --no-sync --no-env-file python -B -m unittest discover -s tests -p 'test_solar*.py'` | 요청별 근거 허용 목록, 주장별 인용, 일관된 중복 제거·번호, 기존 A/B/C·임베딩 메타데이터·단일 질문 CLI의 답변 스키마 유지 | REQ-2, REQ-4 |
| AC-3 | 서버가 정형 계산 결과를 근거와 함께 답변함 | 명령: `uv run --offline --no-sync --no-env-file python -B -m unittest discover -s tests -p 'test_solar*.py'` | 팀 약점·후보와 기술의 일반 피해·변화기·별도 피해·미확정 결과를 계산값으로 표시. 필수 근거 검증과 선택 호출 1회, 후속 GPT·임베딩 0회 | REQ-3 |
| AC-4 | 보호 경로 및 HTTP 연동 유지 | 명령: `git diff --exit-code 0bab5fc -- AGENTS.md api frontend data/processed solar_handoff/data solar_handoff/documents solar_handoff/chunks solar_handoff/db solar_handoff/config solar_handoff/src/cli.py solar_handoff/src/retrieval.py src/pokedex eval` | 종료 코드 0, 보호 경로에 새 파일 없음 | REQ-4 |
| AC-5 | 문서 동기화 게이트 | 명령: `uv run --offline --no-sync --no-env-file python -B .claude/skills/doc-sync/scripts/check_docs.py --strict` | ERROR 0 및 WARN 0 | REQ-4 |
| AC-6 | 보안 게이트 | 명령: `uv run --offline --no-sync --no-env-file python -B .claude/skills/security-check/scripts/check_security.py --base origin/main` | ERROR 0, WARN이 있으면 분류·기록 | REQ-4 |
| AC-7 | RAG 평가 게이트 | 명령: `AGENTS.md` 개발 루프 평가 게이트 | 팀원 잠금 검증을 통과한 승인된 전체 실행 결과가 기록됨 | REQ-4 |

작성 규칙은 spec-plan 스킬의 completion-criteria 참조 문서를 따른다.
