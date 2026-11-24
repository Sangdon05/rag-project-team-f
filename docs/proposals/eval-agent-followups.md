# eval 에이전트 도입에 따른 후속 수정 요청

eval 에이전트·rag-eval 스킬을 추가하면서, 다른 에이전트·스킬·문서에도 수정이 필요한 곳이 생겼다.
이번 작업에서는 eval 관련 파일만 만들고 아래 항목은 **수정하지 않았다**. 각 담당자(또는 오케스트레이터)가 검토 후 반영한다.

이번에 반영된 것: `.claude/agents/eval.md`, `.claude/skills/rag-eval/`, `eval/README.md`, `scripts/eval/evalset_lock.py`, 그리고 doc-sync 검사를 통과시키기 위한 등록 행 3줄(AGENTS.md 에이전트 표, agents·skills README 표).

## 전제 결정 (사용자 확정)

| 항목 | 결정 |
| --- | --- |
| 평가 대상 | 고정 RAG 체인 (질문 → 리라이트 → 검색 → 결합 → 재정렬 → 근거 선택 → 답변·출처 또는 정보 부족). 런타임 툴은 부가 기능으로 분리 |
| 평가셋 | 사용자만 작성·수정. 에이전트는 의견서만. 해시 잠금으로 보호 |
| 채점 | 판단이 필요한 지표는 사람이 처음부터 채점 (LLM 판정 없음) |
| 최적화 | 쿼리 리라이트만 |

## 우선순위

- **차단**: 반영 전에는 eval 에이전트가 발제 기준 평가를 할 수 없거나 규칙이 충돌한다.
- **필요**: 평가 전까지 반영해야 한다.
- **정리**: 문서 일관성.

## 요청 목록

| # | 대상 | 우선 | 수정 내용 | 이유 |
| --- | --- | --- | --- | --- |
| 1 | `AGENTS.md` 평가셋 섹션 | 차단 | "사실형 정답은 `data/processed/`에서 자동 생성" 문구를 삭제하고 "평가셋은 사용자만 작성·수정, 해시 잠금, test는 최종 평가 때만, 판단 지표는 사람 채점"으로 교체. 상세는 [eval/README.md](../../eval/README.md)·rag-eval 스킬 링크 | 사용자 결정과 정면 충돌 |
| 2 | `langchain-rag` 스킬 | 차단 | 툴 선택 에이전트 체인 → 고정 RAG 체인으로 전환. A/B/C/C+RW를 config로 전환, 공통 조건(모델·프롬프트·출력 한도·컨텍스트 제한) 고정, 근거 부족 판정 기준은 dev로만, `no_evidence`와 `error/timeout` 구분, 인용 ⊆ 최종 검색 결과 검증 | 발제 STEP 4 (A/B/C 같은 흐름·같은 조건) |
| 3 | `langchain-rag` 스킬 트레이스 형식 | 차단 | 현재 트레이스(`tool_calls` 중심) → rag-eval [records 형식](../../.claude/skills/rag-eval/references/records.md) (단계별 후보·점수, 재정렬 전후 순위, 근거 `doc_id`·`source_loc`, status, 단계별 시간) | eval이 Hit@5·실패 분류를 계산할 원본 |
| 4 | `chunking` 스킬 메타데이터 | 차단 | `chunk_id`, `doc_id`, `source_loc` 추가 (`doc_id` 예 `pokemon:25`, `source_loc` 예 `data/processed/pokemon.json[id=25].stats_gen1`) | 발제 필수 (청크마다 문서 ID·원문 위치), 평가셋 `allowed_evidence`가 의존 |
| 5 | `chunking` 스킬 입력 | 필요 | `eval/`을 입력·색인 대상에서 제외한다고 명시 | 정답표가 색인에 섞이면 평가 무효 |
| 6 | `chunking` 스킬 learnset 청크 | 필요 | "기술 요약(기술머신은 개수만)" → 레벨업 기술과 습득 레벨 전체, 기술머신 목록. "습득 레벨은 툴이 담당" 문구 수정 | 평가 대상 체인은 툴 없이 검색만 쓰므로 청크에 사실이 있어야 답할 수 있음 |
| 7 | `chunking` 스킬 청크 ID 규칙 | 필요 | ID 규칙을 바꾸면 평가셋 근거 매핑이 낡으므로 오케스트레이터 보고 → 사용자 매핑 갱신·재잠금 | `evalset_lock.py verify --chunks`가 실패함 |
| 8 | `rag-developer` 에이전트 | 필요 | 담당: RAG 체인(A/B/C, 리라이트, 근거 선택), 툴은 부가 기능. 하지 않는 것: `eval/` 읽기, 정답을 리라이터 입력에 넣기, `results/` 수정. 완료 조건·보고 형식을 records 기준으로 | holdout 보호, 평가 대상 변경 |
| 9 | `tool-calling` 스킬 | 필요 | 범위 명시: 부가 기능, 평가 대상 체인·A/B/C에 연결하지 않음 | 결정 (평가 대상 분리) |
| 10 | `data-normalize` 스킬 | 필요 | 문서 목록 `docs/sources.md` 생성 (doc_id, 제목, 출처, 이용 조건, 버전·수집 시점, 원문 위치, 재수집 방법) | 발제 필수 산출물 |
| 11 | `AGENTS.md` 실패 분석 표 | 필요 | "툴 선택 실패", "정답 오류 → eval이 평가셋 수정" 삭제. rag-eval [failure-taxonomy](../../.claude/skills/rag-eval/references/failure-taxonomy.md)의 7개 유형 + "정답표 의심 → 사용자"로 교체 | 평가 대상 변경, 평가셋 소유 규칙 |
| 12 | `AGENTS.md` 재현·실험 규칙 | 필요 | 3회 반복은 dev에서만, 최종은 A/B/C 각 1회(60건) + C+RW 1회(20건), `retry`/`extra` 분리, 튜닝·채택은 dev로만, 최종 후 설정 변경 금지. "temperature 0" → 실제 호출로 확인한 생성 파라미터 고정 | 발제 STEP 6 |
| 13 | `AGENTS.md` 가드레일 | 필요 | 추가: 평가셋은 사용자만 수정 / rag-developer는 `eval/` 읽기 금지 / 정답을 리라이터 입력·색인에 넣지 않음 / 실패 run 삭제·선별 보고 금지. 수정: "툴 선택은 docstring으로" · "집계를 벡터 검색으로 풀지 않음" 문구를 평가 대상 분리 기준으로 | 결정 반영 |
| 14 | `AGENTS.md` 기타 | 정리 | 발주 양식 agent 목록에 `eval` 추가, 개발 루프 "평가" 행 담당 `eval (2차)` → `eval`, "2차 예정"에서 eval 제거, 이정표 "평가셋·평가 결과" 행을 `eval/README.md`·rag-eval·`results/`로, 변경 영향 표에 "청크 ID 규칙 변경 → 재잠금 요청", "툴 변경 → 평가 대상 아님", 결정 사항 표 추가 | 일관성 |
| 15 | `vectordb` 스킬 | 정리 | "정렬·집계는 툴의 몫" → 평가 대상 체인에서는 한계로 기록, 정확한 처리는 부가 툴 | 평가 대상 변경 |
| 16 | `docs/references/agents/README.md` | 정리 | 계약 다이어그램에 rag-developer → eval(records), 사용자 ↔ eval(평가셋·의견서·채점) 추가, "2차 예정"에서 Eval 제거 | 일관성 |
| 17 | `docs/references/skills/README.md` | 정리 | tool-calling·langchain-rag 요약 갱신, "2차 예정"에서 rag-eval 제거, hybrid-retrieval·reranking·query-rewrite 추가 | 일관성 |
| 18 | `doc-sync` 스킬 | 정리 | doc-map coupling 추가: `eval/README.md` → rag-eval / `records.md` ↔ langchain-rag / `evalset_lock.py` → eval README·rag-eval·eval 에이전트 / chunking 규칙에 `eval/README.md` 추가. SKILL.md 원본 문서 표에 "평가셋 스키마 → `eval/README.md`", "실행 기록 형식 → rag-eval records" 추가 | 새 의존 관계 등록 |

## 확인이 필요한 것

- `gpt-6-luna`가 temperature를 받는지 (추론 모델이면 reasoning effort 등으로 고정). `.env`에 키가 없어 확인하지 못했다.
- 평가 실행기·집계 스크립트(`scripts/eval/`)는 eval 담당으로 두었다. 체인 호출 인터페이스(입력: 질문·config, 출력: records 한 줄)는 rag-developer와 합의가 필요하다.
