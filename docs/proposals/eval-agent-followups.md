# eval 에이전트 도입에 따른 후속 수정 요청

eval 에이전트·rag-eval 스킬을 추가하면서 다른 에이전트·스킬·문서에 필요한 수정을 정리한다.
eval 작업에서는 아래 항목을 직접 고치지 않는다(예외: #4, 사용자 지시로 반영). 담당자(또는 오케스트레이터)가 검토해 반영한다.
상태는 main(PR #5 반영)과 이 브랜치를 대조한 결과다.

## 사용자 결정

| 항목 | 결정 |
| --- | --- |
| 평가셋 | **사용자만 작성·수정.** 에이전트는 의견서만. 해시 잠금으로 보호 |
| 채점 | 판단이 필요한 지표는 사람이 처음부터 채점 (LLM 판정 없음) |
| 최적화 | 쿼리 리라이트만 |
| 평가 대상 | 고정 RAG 체인, 런타임 툴은 부가 기능으로 분리 (#2: 현재 langchain-rag와 차이 있음, 확인 필요) |

## 상태

| # | 대상 | 상태 | 내용 |
| --- | --- | --- | --- |
| 1 | `AGENTS.md` 평가셋 섹션 | **미반영 (승인 대기)** | "사실형 정답은 `data/processed/`에서 자동 생성" 문구가 "평가셋은 사용자만 작성" 결정과 충돌. 아래 교체안 참고. 이 브랜치에서 수정을 시도했으나 AGENTS.md 쓰기 승인이 나지 않았다 |
| 2 | `langchain-rag` 체인 구조 | 팀원 갱신으로 부분 해소 | A/B/C 검색 설정, 같은 조건 고정, dev로 설정 확정, 정답을 문서·프롬프트에 넣지 않음이 반영됨. 단 툴 선택 에이전트 구조는 유지 → "평가 대상 = 고정 RAG 체인" 결정과 다름. 아래 "확인 필요" 참고 |
| 3 | `langchain-rag` 트레이스 형식 | 팀원 갱신으로 대부분 해소, 필드 3개 요청 | rag-eval은 팀원이 정한 트레이스를 원본으로 쓰도록 맞췄다 ([records.md](../../.claude/skills/rag-eval/references/records.md)). 추가 요청: 상태(`ok`/`no_evidence`/`error`/`timeout`)와 오류 내용 / 리라이트 원문·결과·fallback·시간 / `final` 항목의 `document_id`·`source_loc` |
| 4 | `chunking` 메타데이터 | **반영 (이 브랜치)** | 팀원 갱신으로 `chunk_id`, `document_id`, `source_ref_id`가 이미 있음. 원문 위치를 바로 확인할 `source_loc`(Markdown 경로 + 절)을 추가하고 세 필드(`chunk_id`, `document_id`, `source_loc`)를 모든 청크의 필수로 명시 |
| 5 | `chunking` 입력에서 `eval/` 제외 | 해소 | 팀원 갱신: "평가셋과 정답은 검색 문서에 넣지 않는다" |
| 6 | `chunking` learnset 청크 | 해소 | 팀원 갱신: `learnset_level`(습득 레벨), `learnset_machine` |
| 7 | 청크 ID 변경 시 근거 매핑 | 해소 | 팀원 갱신: "분할 경계·의미가 바뀌면 평가셋 근거 ID 재검증". 재검증 후 사용자가 다시 잠근다 |
| 8 | `rag-developer` 에이전트 | 일부 해소, 1건 요청 | 팀원 갱신: 채택 판정 금지, 독립 평가 전달. 추가 요청: `eval/` 읽기 금지(holdout 보호), 리라이터 입력에 정답 금지 |
| 9 | `tool-calling` 범위 | #2 결정에 따름 | 현재 `search_pokedex`가 A/B/C 검색 설정을 따름 |
| 10 | 문서 목록 | 일부 해소 | 팀원 갱신: `data/source_manifest.json`. 발제 항목(문서 ID, 제목, 출처, 이용 조건, 버전·수집 시점, 원문 위치)이 모두 있는지 확인 필요 |
| 11 | `AGENTS.md` 실패 분석 표 | 미반영 | "툴 선택 실패", "정답 오류 → eval이 평가셋 수정" 삭제. rag-eval [failure-taxonomy](../../.claude/skills/rag-eval/references/failure-taxonomy.md)의 8개 유형 + "정답표 의심 → 사용자"로 교체 |
| 12 | `AGENTS.md` 재현·실험 규칙 | 미반영 | 3회 반복은 dev에서만, 최종은 A/B/C 각 1회(60건) + C+RW 1회(20건), `retry`/`extra` 분리, 최종 후 설정 변경 금지 |
| 13 | `AGENTS.md` 가드레일 | 미반영 | 평가셋은 사용자만 수정 / rag-developer `eval/` 읽기 금지 / 정답을 리라이터 입력·색인에 넣지 않음 / 실패 run 삭제·선별 보고 금지 |
| 14 | `AGENTS.md` 기타 | 미반영 | 발주 양식 agent 목록에 `eval`, 개발 루프 "평가" 담당 `eval (2차)` → `eval`, "2차 예정"에서 eval 제거, 이정표 평가 행을 `eval/README.md`·rag-eval·`results/`로 |
| 15 | `vectordb` | 해당 없음 | 팀원 갱신 내용과 충돌 없음 |
| 16 | agents README | 미반영 | 계약 다이어그램에 rag-developer → eval(트레이스), 사용자 ↔ eval(평가셋·의견서·채점), "2차 예정"에서 Eval 제거 |
| 17 | skills README | 미반영 | "2차 예정"에서 rag-eval 제거, query-rewrite 추가 |
| 18 | `doc-sync` 지도 | 미반영 | coupling 추가: `eval/README.md` → rag-eval / rag-eval `records.md` ↔ langchain-rag / `evalset_lock.py` → eval README·rag-eval·eval 에이전트 / chunking 규칙에 `eval/README.md` |

## #1 교체안 (AGENTS.md "평가셋" 섹션)

```markdown
### 평가셋

- **평가셋은 사용자만 작성·수정한다.** 에이전트는 평가셋을 만들거나 고치지 않고, 의견서(`eval/feedback/`)만 낸다.
- 구성: 개발용 `eval/dev.json` 10문항, 최종 평가용 `eval/test.json` 20문항. 스키마와 소유 규칙: `eval/README.md` (반영 시 링크로)
- 문항마다 qid, 유형, 질문, 핵심 사실, 허용 근거(청크 ID·문서 ID·원문 위치)를 사용자가 기록한다.
- 평가셋은 해시로 잠근다 (`scripts/eval/evalset_lock.py`). `lock`은 사용자만 실행하고, 평가 전 `verify`가 실패하면 실행하지 않는다.
```

## 확인 필요: 평가 대상과 툴 (#2)

현재 langchain-rag는 툴 선택 에이전트를 유지하고 A/B/C를 `search_pokedex`의 검색 설정으로 둔다. 이 구조에서 툴만으로 답한 문항은 검색을 호출하지 않으므로 발제 정의상 Hit@5 = 0이다. rag-eval은 두 구조 모두에서 동작하도록 트레이스의 `retrieval.called`로 채점하고, 검색 미호출 건수를 따로 보고한다.

- 기존 결정 유지: 평가 run에서는 툴을 끄고 검색 경로만 쓴다 (langchain-rag 수정 필요)
- 현 구조 유지: 툴 경로 문항의 Hit@5 = 0을 감수하고 보고서에서 검색 미호출로 분리 설명

## 그 밖에 확인할 것

- `gpt-6-luna`가 temperature를 받는지 (추론 모델이면 reasoning effort 등으로 고정). `.env`에 키가 없어 확인하지 못했다.
- 평가 실행기·집계 스크립트(`scripts/eval/`)는 eval 담당. 체인 호출 인터페이스(입력: 질문·config, 출력: 트레이스 한 줄)는 rag-developer와 합의가 필요하다.
