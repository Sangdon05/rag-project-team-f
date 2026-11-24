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
| [data-normalize](../../../.claude/skills/data-normalize/SKILL.md) | data-engineer | 해시 고정 데이터는 그대로 두고 `pokedex_extra.json`으로 보강 |
| [chunking](../../../.claude/skills/chunking/SKILL.md) | data-engineer | 포켓몬 × 5섹션 + 기술 165개, 청크 ID·메타데이터 규칙 |
| [vectordb](../../../.claude/skills/vectordb/SKILL.md) | data-engineer | PostgreSQL + pgvector, index_version, 해시 2개 기반 증분 sync |
| [tool-calling](../../../.claude/skills/tool-calling/SKILL.md) | rag-developer | 런타임 툴 8개, 작성 규칙, 결정적 테스트 |
| [langchain-rag](../../../.claude/skills/langchain-rag/SKILL.md) | rag-developer | 에이전트 체인, 프롬프트 규칙, 트레이스 로깅 |

2차 예정: rag-eval(Eval), testing(QA), api-server(Backend, 필요 시).

## 데이터 현황 (설계 근거)

- PokeAPI `/pokemon` 응답은 대부분 moves·sprites이고 핵심 필드는 약 0.4%다. 필요한 필드만 뽑아 쓴다.
- 정규화(PR #3): `data/processed/` — pokemon(151), moves(165), types(15), type_chart, 기술 분류. 1세대 Red/Blue 기준, SHA-256 고정.
- 상성 계산: `scripts/gen1_battle/gen1_battle_rules.py` — 툴로 재사용.
- 부족한 것: 키/몸무게(`/pokemon`), 분류·도감 설명·진화(`/pokemon-species`), 별칭. `pokedex_extra.json`으로 보강한다.
