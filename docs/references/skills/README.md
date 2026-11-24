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
| [data-normalize](../../../.claude/skills/data-normalize/SKILL.md) | data-engineer | 해시 고정 데이터 보호, Red·Blue 정제 데이터와 출처 검증 |
| [chunking](../../../.claude/skills/chunking/SKILL.md) | data-engineer | 포켓몬별 Markdown을 주제별로 청킹하고 청크 ID·근거·메타데이터 연결 |
| [vectordb](../../../.claude/skills/vectordb/SKILL.md) | data-engineer | PostgreSQL + pgvector, index_version, 해시 2개 기반 증분 sync |
| [tool-calling](../../../.claude/skills/tool-calling/SKILL.md) | rag-developer | 정제 데이터 조회·상성 결과 계약·검색 출처와 테스트 |
| [langchain-rag](../../../.claude/skills/langchain-rag/SKILL.md) | rag-developer | 에이전트 체인, A/B/C 검색 비교 설정과 트레이스 로깅 |
| [doc-sync](../../../.claude/skills/doc-sync/SKILL.md) | 오케스트레이터 | 문서 의존 지도, 원본 문서 규칙, 동기화 검사 스크립트 |
| [security-check](../../../.claude/skills/security-check/SKILL.md) | security-reviewer | PR 전 비밀·금지 파일·위험 코드 점검 (트리 + 브랜치 기록) |

2차 예정: rag-eval(Eval), testing(QA), api-server(Backend, 필요 시).

## 데이터 현황 (설계 근거)

- PokeAPI `/pokemon` 응답은 대부분 moves·sprites이고 핵심 필드는 약 0.4%다. 필요한 필드만 뽑아 쓴다.
- 정규화: `data/processed/`의 해시 고정 파일과 별도 진화·획득처·머신 데이터. 파일별 범위와 검증은 [data-normalize 스킬](../../../.claude/skills/data-normalize/SKILL.md)을 따른다.
- 상성 계산: `scripts/gen1_battle/gen1_battle_rules.py` — 툴로 재사용.
- 추가 데이터가 필요하면 현재 문서·질문 범위와 출처를 먼저 확인한다. 포켓몬별 Markdown과 청크는 [chunking 스킬](../../../.claude/skills/chunking/SKILL.md)을 따른다.
