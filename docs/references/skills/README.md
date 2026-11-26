# 스킬 개요

스킬 원본은 `.claude/skills/<name>/SKILL.md`(Claude Code 규칙)에 있다. 이 문서는 사람이 읽는 개요다.

## 설계 원칙

1. 스킬은 개발 절차(입력, 출력, 절차, 규칙, 검증)를 담는다. 서비스 런타임 동작(질문 이해, 툴 선택)은 스킬이 아니라 툴 docstring과 시스템 프롬프트로 구현한다.
2. 메타데이터 스키마는 스킬이 아니라 계약 파일(`contracts/chunk_schema.json`, 예정)로 관리한다.
3. 변경 없는 데이터는 다시 임베딩하지 않는다.
4. 집계·정렬은 벡터 DB가 아니라 정규화 데이터로 푼다.

## 스킬 목록

| 스킬 | 사용 에이전트 | 요약 |
| --- | --- | --- |
| [data-normalize](../../../.claude/skills/data-normalize/SKILL.md) | data-engineer | 해시 고정 데이터 보호, Red·Blue 정제 데이터·출처 검증, Solar 문서 생성 범위 |
| [chunking](../../../.claude/skills/chunking/SKILL.md) | data-engineer | 포켓몬별 Markdown 청킹·근거 연결 및 Solar 제목 기반 청크 |
| [vectordb](../../../.claude/skills/vectordb/SKILL.md) | data-engineer | 기존 pgvector 컬렉션 sync, 빈 볼륨 최초 Solar 스키마 초기화와 별도 벡터 복원·증분 적재 |
| [tool-calling](../../../.claude/skills/tool-calling/SKILL.md) | rag-developer | 향후 정형 조회·상성·검색 툴 계약과 Solar CLI의 경계 |
| [langchain-rag](../../../.claude/skills/langchain-rag/SKILL.md) | rag-developer | Solar 질문 CLI·검색·트레이스와 향후 에이전트 체인 |
| [doc-sync](../../../.claude/skills/doc-sync/SKILL.md) | 오케스트레이터 | 문서 의존 지도와 동기화 검사, Docker 초기화·Solar 스키마 관련 문서 연결 점검 |
| [spec-plan](../../../.claude/skills/spec-plan/SKILL.md) | 오케스트레이터 | 업무 스펙(HITL 승인)·작업 계획 형식과 frontmatter, 완료 기준 규칙, 활성·보관 문서 관리 스크립트 |
| [security-check](../../../.claude/skills/security-check/SKILL.md) | security-reviewer | PR 전 비밀·금지 파일·위험 코드 점검 (트리 + 브랜치 기록) |
| [rag-eval](../../../.claude/skills/rag-eval/SKILL.md) | eval | 사용자 평가셋 검증·의견서, 실행 기록, 발제 지표, 사람 채점 집계, 실패 분석, 비교 보고서 |
| [layered-architecture](../../../.claude/skills/layered-architecture/SKILL.md) | api-architect, api-implementer, api-reviewer | (공통) 4계층 책임·의존 방향·포트·DI 조립, 서비스가 주입할 항목 |
| [fsd-architecture](../../../.claude/skills/fsd-architecture/SKILL.md) | api-architect, api-reviewer | (공통) FSD 슬라이스 구성·공개 API·슬라이스 간 규칙과 강도 설정 |
| [api-invariants](../../../.claude/skills/api-invariants/SKILL.md) | api-architect, api-implementer, api-reviewer | `api/` 규칙 R1~R16과 완료 게이트 원본, 공통 스킬에 주입하는 프로파일·smoke·실행 정보 |
| [api-architecture](../../../.claude/skills/api-architecture/SKILL.md) | api-architect, api-implementer, api-reviewer | `api/`가 공통 스킬을 적용하는 방식: 폴더, 슬라이스, `AnswerGenerator` 포트, 조립 |
| [api-implementation](../../../.claude/skills/api-implementation/SKILL.md) | api-implementer, api-reviewer | 계층별 코드 패턴, 공통 에러 형식, mock·llm 생성기, unittest 작성법 |
| [layer-check](../../../.claude/skills/layer-check/SKILL.md) | api-implementer, api-reviewer | (공통) 프로파일 기반 계층 import 방향·경계 자동 검사 스크립트 |
| [fastapi-run](../../../.claude/skills/fastapi-run/SKILL.md) | api-reviewer | (공통) PID 파일 방식 FastAPI 서버 기동·종료. 앱 경로·설정·smoke는 서비스가 주입 |
| [question-design](../../../.claude/skills/question-design/SKILL.md) | question-designer | '쎄?' 등 원표현과 세 인물의 v2 발화 프로필·질문 의도를 보존한 후보 제안, 답변 없는 입력 추출·출력 구조 검사, 사람 채택으로 전달 |

2차 예정: testing(QA).

## 데이터 현황 (설계 근거)

- PokeAPI `/pokemon` 응답은 대부분 moves·sprites이고 핵심 필드는 약 0.4%다. 필요한 필드만 뽑아 쓴다.
- 정규화: `data/processed/`의 해시 고정 파일과 별도 진화·진화 아이템 이름·획득처·머신 데이터. 파일별 범위와 검증은 [data-normalize 스킬](../../../.claude/skills/data-normalize/SKILL.md)을 따른다.
- 상성 계산: `scripts/gen1_battle/gen1_battle_rules.py` — 툴로 재사용.
- 추가 데이터가 필요하면 현재 문서·질문 범위와 출처를 먼저 확인한다. 포켓몬별 Markdown과 청크는 [chunking 스킬](../../../.claude/skills/chunking/SKILL.md)을 따른다.
