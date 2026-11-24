# AGENTS.md — 포켓몬 도감 RAG 오케스트레이터

1세대(Red/Blue) 포켓몬 151마리 도감을 대상으로 하는 RAG 프로젝트다.
이 문서는 오케스트레이터의 역할, 개발 루프, 가드레일을 정의하고 세부 문서로 가는 링크를 모아 둔다.
세부 절차는 이 문서에 쓰지 않고 링크된 스킬·에이전트 문서에 둔다.

## 이정표

| 무엇을                                   | 어디서                                                                                                                  |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 에이전트 정의 (Claude Code 서브에이전트) | [.claude/agents/](.claude/agents/)                                                                                      |
| 스킬 정의 (Claude Code 스킬)             | [.claude/skills/](.claude/skills/)                                                                                      |
| 에이전트 개요, 에이전트 간 계약          | [docs/references/agents/README.md](docs/references/agents/README.md)                                                    |
| 스킬 개요, 설계 원칙, 데이터 현황        | [docs/references/skills/README.md](docs/references/skills/README.md)                                                    |
| 포켓몬 번호·이름·타입 참조표             | [docs/references/pokemon-gen1-reference.md](docs/references/pokemon-gen1-reference.md)                                  |
| 기준 데이터 (해시 고정)                  | [data/processed/](data/processed/), 검증 [scripts/gen1_battle/data_integrity.py](scripts/gen1_battle/data_integrity.py) |
| 상성 계산 (툴로 재사용)                  | [scripts/gen1_battle/gen1_battle_rules.py](scripts/gen1_battle/gen1_battle_rules.py)                                    |
| 보강 데이터 생성 (PokeAPI)               | `scripts/helper/build_pokedex_extra.py` (예정)                                                                          |
| 청크 메타데이터 계약                     | `contracts/chunk_schema.json` (예정, 초안은 chunking 스킬)                                                              |
| 버전·실행 기록                           | `runs/manifest.jsonl` (예정)                                                                                            |
| 평가셋·평가 결과·실패 분석               | `eval/` (예정, 2차 Eval 에이전트)                                                                                       |

## 에이전트

| 에이전트                                         | 맡기는 일                                                    | 스킬                               |
| ------------------------------------------------ | ------------------------------------------------------------ | ---------------------------------- |
| [data-engineer](.claude/agents/data-engineer.md) | 정규화 보강, 청킹, 임베딩, 인덱스 sync                       | data-normalize, chunking, vectordb |
| [rag-developer](.claude/agents/rag-developer.md) | 런타임 툴, 에이전트 체인, 프롬프트, retriever 설정, 트레이스 | tool-calling, langchain-rag        |

2차 예정: eval, qa, reviewer, backend(필요 시). 정의되기 전까지 해당 역할은 오케스트레이터가 직접 수행하되, 수정한 에이전트에게 평가를 맡기지 않는다.

## 오케스트레이터의 역할

1. 요청을 작업 단위로 나누고 담당 에이전트에게 발주한다.
2. 하위 에이전트의 보고를 검토한다. 보고는 자기 주장이므로 산출물을 직접 확인한다.
3. 버전을 파일로 관리한다 (`runs/manifest.jsonl`). 대화나 메모리에 의존하지 않는다.
4. 실험 규칙을 정하고 채택·기각을 판정한다.
5. 가드레일 위반을 막는다.

### 발주 양식

```
task: 한 문장 목표
agent: data-engineer | rag-developer
inputs: 경로 + schema_version / index_version
outputs: 기대 산출물 경로
done_when: 확인 가능한 완료 조건
constraints: 이번 작업에서 바꾸면 안 되는 것
```

### 보고 검토 절차

1. 보고서의 `changed_files`를 `git diff --stat`과 대조한다.
2. `checks`의 evidence 명령을 직접 다시 실행한다 (예: `verify_bundle()`, 테스트, 청크 수).
3. manifest에 해당 run이 기록됐는지 확인한다.
4. `downstream_impact`에 따라 후속 작업을 발주한다. 하나라도 확인되지 않으면 완료로 처리하지 않는다.

## 개발 루프

```
발주 → 구현 → 자체 검증 → 평가 → 실패 분석 → 재현 → 수정 → 재평가 → 채택 판정 → 리뷰 → PR
```

| 단계    | 담당           | 게이트                                                |
| ------- | -------------- | ----------------------------------------------------- |
| 데이터  | data-engineer  | `verify_bundle()` 통과, extra 151/151, 스키마 검증    |
| 인덱스  | data-engineer  | 청크 누락 0, 이름 smoke test, sync 결과 manifest 기록 |
| 툴·체인 | rag-developer  | 툴 단위 테스트 통과, 출처 포함 답변, 트레이스 생성    |
| 평가    | eval (2차)     | 평가셋 전체 실행, run 결과 저장                       |
| 채택    | 오케스트레이터 | 아래 실험 규칙 충족                                   |
| 리뷰    | reviewer (2차) | 가드레일·계약 위반 없음                               |

### 평가셋 (Eval 정의 전 기준)

- 유형: 단일 사실, 이름 해석(한글·별칭·오타), 수치·단위, 기술·습득, 상성, 비교, 집계·필터, 세대 구분, 서술형, 답할 수 없는 질문
- 사실형 정답은 `data/processed/`에서 자동 생성한다. 서술형은 사람이 검수한다.
- 문항마다 qid, 유형, 정답, 정답 출처 id를 기록한다.

### 실패 분석

트레이스로 단계별 산출물을 보고, 처음 실패한 단계를 원인으로 정한다.

| 실패 유형    | 수정 담당                                               |
| ------------ | ------------------------------------------------------- |
| 데이터 누락  | data-engineer                                           |
| 검색 실패    | data-engineer (청킹·임베딩) 또는 rag-developer (k·필터) |
| 툴 선택 실패 | rag-developer (툴 docstring)                            |
| 생성 실패    | rag-developer (프롬프트)                                |
| 정답 오류    | eval (평가셋 수정)                                      |

### 재현

- temperature 0, 모델·임베딩 버전, index_version, config 해시를 고정한다.
- 실패 qid 목록으로 해당 문항만 다시 돌릴 수 있게 한다.
- 나중에 도입: dev/holdout 분리, 3회 반복으로 불안정 실패 구분.

### 실험 규칙 (채택 판정)

- 한 번에 변수 하나만 바꾼다.
- 채택: 목표 실패가 줄고, 기존에 맞던 문항이 회귀하지 않는다 (run 간 문항 단위 비교).
- 채택 여부는 오케스트레이터가 판정한다. 수정한 에이전트는 자기 결과를 평가하지 않는다.

### 변경 영향

| 변경                               | 후속 작업                                       |
| ---------------------------------- | ----------------------------------------------- |
| PokeAPI 보강 데이터 재생성         | 증분 sync → 평가                                |
| 해시 고정 파일 값 변경             | 파일 + `HASHES` 갱신 별도 PR → 증분 sync → 평가 |
| 정규화 필드 추가/변경              | schema_version 상향 → 툴 테스트 → 평가          |
| 청크 템플릿·섹션, 임베딩 모델 변경 | 새 index_version 전체 빌드 → 평가               |
| k·필터·프롬프트                    | 체인 테스트 → 평가                              |
| 툴 추가·시그니처 변경              | 툴 테스트 → 평가                                |

## 가드레일

- `data/processed/`의 해시 고정 파일을 수정하지 않는다. 보강은 별도 파일로 한다.
- 입력은 저장소에 커밋된 파일과 PokeAPI만 쓴다. 팀원과 공유되지 않는 개인 로컬 파일에 의존하지 않는다.
- 평가셋 정답을 프롬프트, 코드, few-shot 예시에 넣지 않는다.
- API 키·`.env`·비밀을 커밋하지 않는다. 키는 환경 변수로만 읽는다.
- `vectorstore/` 같은 대용량·생성물을 커밋하지 않는다.
- 런타임 질문 라우터를 따로 만들지 않는다. 툴 선택은 툴 docstring과 시스템 프롬프트로 해결한다.
- 집계·정렬·top-N을 벡터 검색으로 풀지 않는다.
- main에 직접 push하지 않는다. 브랜치 → PR → 리뷰 → 머지. 커밋 메시지는 `type: 요약` (feat, fix, docs, chore).
- 작업 시작 전 `git fetch`로 main 변경을 확인한다. 팀원이 머지한 데이터·코드를 먼저 반영한다.
- 문서 파일 이름을 `agents.md`로 짓지 않는다. 대소문자 구분이 없는 파일시스템에서 `AGENTS.md`로 인식된다.

## 미정 사항

| 항목                         | 기본값(제안)                 |
| ---------------------------- | ---------------------------- |
| `/pokemon-species` 수집 추가 | 추가                         |
| LLM·임베딩 제공자            | 팀 결정                      |
| 답변 기준 세대               | 1세대 Red/Blue, 현재 값 병기 |
| 메타데이터 관리              | 계약 파일                    |
