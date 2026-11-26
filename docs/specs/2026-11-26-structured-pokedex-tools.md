---
type: spec
id: 2026-11-26-structured-pokedex-tools
title: 도감 정형 조회와 상성 계산 도구
status: approved
owner: orchestrator
created: 2026-11-26
updated: 2026-11-26
approved_by: 사용자
approved_at: 2026-11-26
completed_at:
archived_at:
related: []
---

# 도감 정형 조회와 상성 계산 도구

## 1. 배경과 목적

대화 검색의 공통 상위 청크에 팀원의 근거가 빠지거나, 기술 습득표만 검색되어 상대의 방어 상성 질문에 답하지 못했다. 기존 검색을 유지하면서 명시된 대상을 직접 조회하고 Red·Blue 정제 데이터로 계산한 결과를 답변에 사용할 수 있게 한다.

## 2. 범위

포함:

- Solar 대화 경로의 팀 약점·추가/교체 후보 조회와 특정 기술에 약한 포켓몬 조회.
- GPT 도구 선택, 정제 데이터 읽기 전용 조회·계산, 기존 도감 청크·기술 분류 근거 연결, 오프라인 회귀 검증.

제외:

- 재임베딩, 인덱스·원문·정제 데이터 갱신, 별도 질문 라우터, API/프론트 요청·응답 계약 변경.
- 실제 HP 피해량·배틀 승률·기술 습득 여부를 상성 배율로 추정하는 기능, 새 외부 서비스·모델·평가셋 변경.
- DB 접근과 유료 외부 실행은 구현 승인과 분리한다. 공식 평가 게이트를 면제하지 않는다.

## 3. 요구사항

| ID | 요구사항 | 구분 |
| --- | --- | --- |
| REQ-1 | 팀 명단의 모든 포켓몬을 도감 ID로 확인하고 각 타입·방어 근거를 확보한다. 팀이 버티지 못하는 약점을 확인해 보완 후보와 해당 후보의 근거를 제공한다. | 필수 |
| REQ-2 | 일반 공격기는 기술 ID의 Red·Blue 타입과 151마리 방어 상성을 대조해 배율이 1보다 큰 대상을 근거와 함께 찾는다. | 필수 |
| REQ-3 | 직접 피해 없는 기술은 피해 배율을 제공하지 않고 확인된 효과를 안내한다. 고정·조건부 피해 및 미확정 분류를 일반 배율로 계산하거나 추측하지 않는다. | 필수 |
| REQ-4 | 같은 GPT가 도구 설명과 대화 의도로 필요한 도구를 선택한다. 서버가 이름·입력을 검증하고, 명단 불명확 시 확인을 요청한다. 일반 질문의 기존 A/B/C 검색 정책과 대화/API 계약을 유지한다. | 필수 |
| REQ-5 | 원문·정제 데이터·임베딩·인덱스 및 공식 평가셋을 변경하지 않는다. 근거와 검증 범위를 문서에 기록하고 저장소 완료 게이트를 적용한다. | 필수 |

구분: `필수` | `선택`. 필수 요구사항은 완료 기준이 하나 이상 있어야 한다.

## 4. 제약

- `data/processed/`, `solar_handoff/data/`, `solar_handoff/documents/`, `solar_handoff/chunks/`, `solar_handoff/db/`, 공식 평가셋과 CLI A/B/C 실험 경로를 변경하지 않는다. API와 프론트 응답 계약을 유지한다.
- [AGENTS.md](../../AGENTS.md), [tool-calling](../../.claude/skills/tool-calling/SKILL.md), [langchain-rag](../../.claude/skills/langchain-rag/SKILL.md)의 읽기 전용 도구·검증·평가 가드레일을 따른다. 모델명·키·접속 정보를 추가로 하드코딩하지 않는다.
- 챗봇은 제공된 자료로만 답한다. 습득표를 기술 효과의 근거로 바꾸어 쓰지 않으며, 호출하지 않은 임베딩 모델 정보를 표시하지 않는다.

## 5. 입력과 산출물

| 구분 | 경로 | 버전·기준 |
| --- | --- | --- |
| 입력 | `data/processed/`, `scripts/gen1_battle/` | 해시 검증된 English Red·Blue 데이터, 기준 `3945d46` |
| 입력 | `solar_handoff/chunks/draft-a-v1/chunks.jsonl`, 기존 `solar_handoff` 인덱스 | 청크 `schema_version=1`; 인덱스와 모델 결합 변경 없음 |
| 입력 | `solar_handoff/src/conversation.py`, `solar_handoff/src/providers.py` | 기준 `3945d46`; 기존 API 사용 방식 유지 |
| 산출물 | `src/pokedex/`, `solar_handoff/src/`, `tests/test_pokedex_structured_tools.py`, `tests/test_solar_conversation.py` | 정형 조회·계산, 대화에서의 도구 호출, 오프라인 검증 |

## 6. 완료 기준

| ID | 기준 | 확인 방법 | 기대 결과 | 요구사항 |
| --- | --- | --- | --- | --- |
| AC-1 | 팀원·후보 근거를 검색 순위와 독립해 검증 | 명령: `uv run --offline --no-sync --no-env-file python -B -m unittest discover -s tests -p test_pokedex_structured_tools.py` | 재현 팀의 팀원 네 마리와 타입·방어 근거 여덟 개, 전기 방어 빈틈, 그 빈틈을 보완하는 후보와 방어 근거, 유효하지 않은 팀 처리 확인 | REQ-1 |
| AC-2 | 직접 피해를 주는 기술의 대상 필터 검증 | 명령: `uv run --offline --no-sync --no-env-file python -B -m unittest discover -s tests -p test_pokedex_structured_tools.py` | 불꽃펀치의 방어 상성 4배 두 마리·2배 스물네 마리와 직접 근거 확인 | REQ-2 |
| AC-3 | 변화기와 특수·미확정 기술 분리 검증 | 명령: `uv run --offline --no-sync --no-env-file python -B -m unittest discover -s tests -p test_pokedex_structured_tools.py` | 망각술의 특수 상승에 피해 배율을 넣지 않고, 별도 규칙 기술과 미확정 조건도 일반 피해로 처리하지 않음 | REQ-3 |
| AC-4 | 도구 선택·출처·기존 대화 검색의 오프라인 회귀 검증 | 명령: `uv run --offline --no-sync --no-env-file python -B -m unittest discover -s tests -p test_solar_conversation.py` | 가짜 공급자·저장소에서 올바른 도구 실행, 명단 확인과 잘못된 입력 거부, 실제 사용 모델만 표시, A/B/C 기존 후보·인용 규칙 통과 | REQ-4 |
| AC-5 | 보호된 파일과 기존 검색·API 계약 유지 | 명령: `git diff --exit-code HEAD -- data/processed solar_handoff/data solar_handoff/documents solar_handoff/chunks solar_handoff/db solar_handoff/config solar_handoff/src/cli.py solar_handoff/src/retrieval.py api frontend eval` | 종료 코드 0, 보호 경로의 추가 파일 없음, DB 쓰기·임베딩 배치 실행 없음 | REQ-4, REQ-5 |
| AC-6 | 문서 동기화 게이트 | 명령: `uv run --offline --no-sync --no-env-file python -B .claude/skills/doc-sync/scripts/check_docs.py --strict` | ERROR 0, WARN 0 | REQ-5 |
| AC-7 | 보안 게이트 | 명령: `uv run --offline --no-sync --no-env-file python -B .claude/skills/security-check/scripts/check_security.py --base origin/main` | ERROR 0, WARN이 있으면 분류·기록 | REQ-5 |
| AC-8 | RAG 평가 게이트 | 명령: `AGENTS.md` 개발 루프 평가 게이트 | 팀원이 잠근 평가 입력이 verify를 통과하고 승인된 전체 실행의 결과가 기록됨 | REQ-5 |

작성 규칙은 spec-plan 스킬의 completion-criteria 참조 문서를 따른다.
