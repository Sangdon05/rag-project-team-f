# 에이전트 개요

에이전트 원본은 `.claude/agents/<name>.md`(Claude Code 규칙)에 있다. 이 문서는 사람이 읽는 개요다.
오케스트레이터의 역할과 개발 루프는 루트 [AGENTS.md](../../../AGENTS.md)를 본다.

## 1차 에이전트

| 에이전트 | 스킬 | 산출물 |
| --- | --- | --- |
| [data-engineer](../../../.claude/agents/data-engineer.md) | data-normalize, chunking, vectordb | `pokedex_extra.json`, `chunks.jsonl`, pgvector 컬렉션, manifest |
| [rag-developer](../../../.claude/agents/rag-developer.md) | tool-calling, langchain-rag | `src/pokedex/` 툴·체인·프롬프트, 트레이스 로그 |
| [security-reviewer](../../../.claude/agents/security-reviewer.md) | security-check | 보안 점검 보고 (파일 수정 없음) |

벡터 DB는 data-engineer가 맡는다. 청킹이 바뀌면 재인덱싱이 반드시 따라오므로 한 에이전트가 끝까지 맡는 편이 버전 관리가 단순하다. retriever 설정(k, 필터)은 rag-developer가 맡는다.

security-reviewer는 읽기 전용이다. 검출은 스크립트가 결정적으로 하고 모델은 WARN 분류만 하므로 haiku + low effort로 둔다. 수정은 오케스트레이터가 담당 에이전트에게 발주한다.

2차 예정: Eval(rag-eval), QA(testing), Reviewer(계약 점검), Backend(api-server, 필요 시).

## 두 에이전트 사이의 계약

```
data-engineer                                rag-developer
  data/processed/*.json         ─────────▶   resolve / get / learnset / filter / compare 툴
  data/processed/pokedex_extra.json
  scripts/gen1_battle/          ─────────▶   type_effectiveness 툴 (재사용)
  data/chunks/chunks.jsonl
  pgvector 컬렉션 {index_version} ──────▶   search_pokedex 툴
  runs/manifest.jsonl           ─────────▶   사용 버전 확인
```

- rag-developer는 데이터를 `src/pokedex/store.py` 하나로만 읽는다.
- 정규화·청크 스키마가 바뀌면 `schema_version`을 올리고, rag-developer는 툴 테스트를 다시 돌린다.
- 청크 템플릿이나 임베딩 모델이 바뀌면 새 `index_version`으로 전체 빌드한다. 데이터만 바뀌면 증분 sync한다.

## manifest 레코드 예시

```json
{"run_id": "2026-11-24T10-00_sync", "stage": "index",
 "schema_version": "1", "index_version": "v1-te3s-tpl1",
 "embed_model": "text-embedding-3-small",
 "embedded": 1, "meta_only": 0, "deleted": 0, "unchanged": 919}
```
