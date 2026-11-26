# 에이전트 개요

에이전트 원본은 `.claude/agents/<name>.md`(Claude Code 규칙)에 있다. 이 문서는 사람이 읽는 개요다.
오케스트레이터의 역할과 개발 루프는 루트 [AGENTS.md](../../../AGENTS.md)를 본다.

## 1차 에이전트

아래 산출물은 담당 범위와 예정된 결과를 나타내며, 실제 구현·생성 여부는 파일과 실행 기록으로 확인한다.

| 에이전트 | 스킬 | 산출물 |
| --- | --- | --- |
| [data-engineer](../../../.claude/agents/data-engineer.md) | data-normalize, chunking, vectordb | 정제 데이터·문서·청크·인덱스; Solar 전달 및 기존 pgvector 컬렉션 |
| [rag-developer](../../../.claude/agents/rag-developer.md) | tool-calling, langchain-rag | Solar 질문 CLI·대화·검색·기록, `src/pokedex/` 정형 로더·팀/기술 도구, 향후 LangChain 범용 도구·체인 |
| [security-reviewer](../../../.claude/agents/security-reviewer.md) | security-check | 보안 점검 보고 (파일 수정 없음) |
| [eval](../../../.claude/agents/eval.md) | rag-eval | `results/` 실행 기록·채점표·비교 보고서, `eval/feedback/` 의견서 |
| [question-designer](../../../.claude/agents/question-designer.md) | question-design | 질문 전용 패킷을 바탕으로 한 `draft` 질문 후보 JSON (응답으로 반환) |
| [api-architect](../../../.claude/agents/api-architect.md) | layered-architecture, fsd-architecture, api-invariants, api-architecture | `docs/design/api/<slice>.md` 설계안 (코드 수정 없음) |
| [api-implementer](../../../.claude/agents/api-implementer.md) | layered-architecture, api-invariants, api-architecture, api-implementation, layer-check | `api/` 슬라이스 코드와 `api/tests/` 테스트 |
| [api-reviewer](../../../.claude/agents/api-reviewer.md) | layered-architecture, fsd-architecture, api-invariants, api-architecture, api-implementation, layer-check, fastapi-run | 게이트·smoke 결과와 APPROVE/REQUEST_CHANGES 판정 (파일 수정 없음) |

벡터 DB는 data-engineer가 맡는다. 청킹이 바뀌면 재인덱싱이 반드시 따라오므로 한 에이전트가 끝까지 맡는 편이 버전 관리가 단순하다. retriever 설정(k, 필터)은 rag-developer가 맡는다.
청크는 승인된 포켓몬별 Markdown을 주제별로 나누고 원본 근거를 연결한다. 구체적인 섹션과 계약은 [chunking 스킬](../../../.claude/skills/chunking/SKILL.md)을 따른다.
검색 방식별 비교 설정·기록은 [langchain-rag 스킬](../../../.claude/skills/langchain-rag/SKILL.md)을 따르며, 결과의 품질·채택은 구현자가 아닌 독립 평가와 오케스트레이터가 판정한다.
BM25 인덱스의 생성·동기화 담당과 출력 계약은 구현 착수 전 발주에서 명확히 정한다.

[Solar 전달본](../../../solar_handoff/README.md)에서 data-engineer는 문서·청크와 Solar 벡터 전달·적재를, rag-developer는 질문 CLI·대화·검색·모델 호출·출처를 담당한다. 현재 대화는 팀·기술 정형 조회와 일반 검색·확인을 GPT 도구로 선택한다. 단일 질문 CLI에는 도구 선택을 붙이지 않는다. 평가·채택은 구현과 독립적으로 수행한다.

security-reviewer는 읽기 전용이다. 검출은 스크립트가 결정적으로 하고 모델은 WARN 분류만 하므로 haiku + low effort로 둔다. 수정은 오케스트레이터가 담당 에이전트에게 발주한다.

API 에이전트는 설계(api-architect, opus/high) → 구현(api-implementer, sonnet/medium) → 리뷰·실행 검증(api-reviewer, sonnet/high)으로 나눈다. DB가 없어 실행 검증이 다른 작업과 섞이지 않으므로 리뷰와 실행 검증을 한 에이전트가 맡는다. 구현한 에이전트는 자기 결과를 판정하지 않는다.
RAG와의 경계는 [API–RAG 연결 가이드](../api-rag-integration.md)가 원본이다. RAG 에이전트·스킬은 API를 알지 않는다. 체인 진입점·반환 형식이 바뀌면 오케스트레이터가 가이드를 고치고 api-implementer에게 어댑터 수정을 발주한다.

2차 예정: QA(testing), Reviewer(RAG 쪽 계약 점검).

## 두 에이전트 사이의 계약

현재 Solar 대화에서 rag-developer는 루트의 해시 고정 자료를 `src/pokedex/store.py` 한 곳에서 읽어 팀·기술을 계산하고, 필요한 포켓몬 근거는 기존 청크의 정확한 ID로 찾는다. 일반 질문의 기존 후보 생성 규칙과 임베딩·인덱스는 유지한다. [langchain-rag 스킬](../../../.claude/skills/langchain-rag/SKILL.md)은 현재 CLI 트레이스와 대화 감사 기록을 구분한다. 아래 데이터·툴 흐름과 평가 JSONL은 별도의 향후 LangChain 설계다.

질문 설계는 별도 준비 경로다: `오케스트레이터의 허용 필드 추출 → question-designer 후보 제안 → 독립 검토·팀원 채택 → 팀원의 평가셋 작성·잠금 → Eval 실행`. v2 패킷은 세 인물의 연령·성별과 검색 입력 방식을 포함하며, '쎄?' 같은 구어체를 사용해도 원질문의 정보 요구를 보존한다. 생성 담당은 정답·근거·평가 파일을 읽거나 쓰지 않으며 런타임 질문을 바꾸지 않는다. [실행·공유 안내](../question-design.md)에서 도구 명령과 사람 검토 경계를 확인한다.

```
data-engineer                                rag-developer
  data/processed/*.json         ─────────▶   resolve / get / learnset / filter / compare 툴
  포켓몬별 Markdown + 출처 연결  ─────────▶   승인 후 주제별 청킹
  scripts/gen1_battle/          ─────────▶   type_effectiveness 툴 (재사용)
  data/chunks/chunks.jsonl
  pgvector 컬렉션 {index_version} ──────▶   search_pokedex 툴
  runs/manifest.jsonl           ─────────▶   사용 버전 확인
```

```
팀원                                         eval
  eval/dev.json, test.json, LOCK.json ───▶   잠금 verify → 평가 실행 (평가셋 수정 없음)
  채점표의 사람 채점 칸            ◀──────▶   채점표 준비 / 채운 결과 집계
  평가셋 수정·재잠금               ◀──────   eval/feedback/ 의견서 (정답표 의심 등)

rag-developer                                eval
  체인 트레이스 (langchain-rag 형식) ─────▶  results/{run_id}/ 원본 기록, 지표, 실패 분석
  수정 발주 (오케스트레이터 경유)  ◀──────   실패 유형별 보고, 비교 보고서
```

- 트레이스 형식의 원본은 langchain-rag 스킬이고, eval은 [records.md](../../../.claude/skills/rag-eval/references/records.md)에서 그 형식을 읽는다.
- 채택 판정은 eval이 아니라 오케스트레이터가 한다.

- 향후 정형 툴도 이미 구현된 단일 로더를 확장해 사용한다. Solar CLI의 기존 DB 읽기 경로는 별개다.
- 정규화·청크 스키마가 바뀌면 `schema_version`을 올리고, rag-developer는 툴 테스트를 다시 돌린다.
- 청크 템플릿이나 임베딩 모델이 바뀌면 새 `index_version`으로 전체 빌드한다. 데이터만 바뀌면 증분 sync한다.

## manifest 레코드 예시

```json
{"run_id": "2026-11-24T10-00_sync", "stage": "index",
 "schema_version": "1", "index_version": "v1-te3s-tpl1",
 "embed_model": "text-embedding-3-small",
 "embedded": 1, "meta_only": 0, "deleted": 0, "unchanged": 919}
```
