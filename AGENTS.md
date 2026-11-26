# AGENTS.md — 포켓몬 도감 RAG 오케스트레이터

영문 Red·Blue 플레이어를 대상으로 포켓몬 151마리 도감을 다루는 RAG 프로젝트다. 답변은 Red·Blue 기준으로 하며 다른 세대 값을 병기하지 않는다.
이 문서는 오케스트레이터의 역할, 개발 루프, 가드레일을 정의하고 세부 문서로 가는 링크를 모아 둔다.
세부 절차는 이 문서에 쓰지 않고 링크된 스킬·에이전트 문서에 둔다.

## 이정표

| 무엇을                                   | 어디서                                                                                                                  |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 에이전트 정의 (Claude Code 서브에이전트) | [.claude/agents/](.claude/agents/)                                                                                      |
| 스킬 정의 (Claude Code 스킬)             | [.claude/skills/](.claude/skills/)                                                                                      |
| 에이전트 개요, 에이전트 간 계약          | [docs/references/agents/README.md](docs/references/agents/README.md)                                                    |
| 스킬 개요, 설계 원칙, 데이터 현황        | [docs/references/skills/README.md](docs/references/skills/README.md)                                                    |
| 개발 환경 (Python, uv, .env, PostgreSQL) | [docs/references/environment.md](docs/references/environment.md)                                                        |
| 문서 동기화 규칙, 검사 스크립트          | [.claude/skills/doc-sync/SKILL.md](.claude/skills/doc-sync/SKILL.md)                                                    |
| PR 전 보안 점검 규칙, 검사 스크립트      | [.claude/skills/security-check/SKILL.md](.claude/skills/security-check/SKILL.md)                                        |
| 포켓몬 번호·이름·타입 참조표             | [docs/references/pokemon-gen1-reference.md](docs/references/pokemon-gen1-reference.md)                                  |
| 기준 데이터 (해시 고정)                  | [data/processed/](data/processed/), 검증 [scripts/gen1_battle/data_integrity.py](scripts/gen1_battle/data_integrity.py) |
| 상성 계산 (툴로 재사용)                  | [scripts/gen1_battle/gen1_battle_rules.py](scripts/gen1_battle/gen1_battle_rules.py)                                    |
| 정제 데이터와 출처 관리                  | [.claude/skills/data-normalize/SKILL.md](.claude/skills/data-normalize/SKILL.md), `data/source_manifest.json`            |
| 청크 메타데이터 계약                     | `contracts/chunk_schema.json` (예정, 초안은 chunking 스킬)                                                              |
| 버전·실행 기록                           | `runs/manifest.jsonl` (예정)                                                                                            |
| 평가셋·평가 결과·실패 분석               | `eval/` (예정, 2차 Eval 에이전트)                                                                                       |
| API 규칙·완료 게이트 (FastAPI `api/`)    | [.claude/skills/api-invariants/SKILL.md](.claude/skills/api-invariants/SKILL.md)                                        |
| API 설계안                               | [docs/design/api/README.md](docs/design/api/README.md)                                                                  |
| API–RAG 연결 계약·절차                   | [docs/references/api-rag-integration.md](docs/references/api-rag-integration.md)                                        |

## 에이전트

| 에이전트                                         | 맡기는 일                                                    | 스킬                               |
| ------------------------------------------------ | ------------------------------------------------------------ | ---------------------------------- |
| [data-engineer](.claude/agents/data-engineer.md) | 정규화·Markdown, 청킹, 임베딩, 인덱스 sync                   | data-normalize, chunking, vectordb |
| [rag-developer](.claude/agents/rag-developer.md) | 런타임 툴·체인, 검색 방식 설정, 프롬프트, 트레이스          | tool-calling, langchain-rag        |
| [security-reviewer](.claude/agents/security-reviewer.md) | PR 전 보안 점검 실행·분류 보고 (읽기 전용)          | security-check                     |
| [eval](.claude/agents/eval.md)                   | 평가 실행·기록·실패 분석·비교 보고서, 평가셋 의견서          | rag-eval                           |
| [question-designer](.claude/agents/question-designer.md) | 질문 전용 패킷으로 페르소나별 질문 후보·조건 확인사항 제안 | question-design |
| [api-architect](.claude/agents/api-architect.md) | FastAPI 슬라이스 설계안 작성 (`docs/design/api/`만 수정) | api-invariants, api-architecture |
| [api-implementer](.claude/agents/api-implementer.md) | 설계안대로 `api/` 슬라이스 4계층 구현, 완료 게이트 실행 | api-invariants, api-architecture, api-implementation, layer-check |
| [api-reviewer](.claude/agents/api-reviewer.md) | `api/` 변경 독립 리뷰·실행 검증 (읽기 전용) | api-invariants, api-architecture, api-implementation, layer-check, fastapi-run |

question-designer는 공식 평가셋 작성 전의 후보 제안 역할이다. v2 입력은 `problem.md`의 세 인물 발화 프로필을 포함하며, '쎄?' 같은 원표현과 기존 질문의 정보 요구를 함께 보존한다. 정답·허용 근거를 생성하거나 `eval/`을 읽고 수정하지 않는다. 후보 채택·정답 검수·평가셋 작성·잠금은 [평가셋 소유 규칙](eval/README.md)에 따라 팀원이 맡는다. 사용·검증·전달 절차는 [질문 설계 안내](docs/references/question-design.md)를 따른다.

API 에이전트 세 개는 저장소 루트 `api/` 패키지(루트 `pyproject.toml` 공유)만 다룬다. DB·로그인·서버 쪽 대화 저장 없이 RAG를 중개하며, RAG 완성 전에는 mock 또는 검색 없는 LLM으로 답한다. RAG 연결은 [연결 가이드](docs/references/api-rag-integration.md)를 따른다. 모노레포 전체 폴더 규칙은 다른 파트가 합쳐진 뒤 정한다.

2차 예정: eval, qa, reviewer(RAG 쪽). 정의되기 전까지 해당 역할은 오케스트레이터가 직접 수행하되, 수정한 에이전트에게 평가를 맡기지 않는다.

## 오케스트레이터의 역할

1. 요청을 작업 단위로 나누고 담당 에이전트에게 발주한다.
2. 하위 에이전트의 보고를 검토한다. 보고는 자기 주장이므로 산출물을 직접 확인한다.
3. 버전을 파일로 관리한다 (`runs/manifest.jsonl`). 대화나 메모리에 의존하지 않는다.
4. 실험 규칙을 정하고 채택·기각을 판정한다.
5. 가드레일 위반을 막는다.
6. 문서 동기화를 책임진다. 스킬 [doc-sync](.claude/skills/doc-sync/SKILL.md)를 따른다.
7. PR 전 보안 점검을 [security-reviewer](.claude/agents/security-reviewer.md)에게 발주하고, 보고를 보고 수정 발주와 PR 진행을 판정한다.

### 발주 양식

```
task: 한 문장 목표
agent: data-engineer | rag-developer | security-reviewer | eval | question-designer | api-architect | api-implementer | api-reviewer
inputs: 경로 + schema_version / index_version
outputs: 기대 산출물 경로
done_when: 확인 가능한 완료 조건
constraints: 이번 작업에서 바꾸면 안 되는 것
```

### 보고 검토 절차

1. 보고서의 `changed_files`를 `git diff --stat`과 대조한다.
2. `checks`의 evidence 명령을 직접 다시 실행한다 (예: `verify_bundle()`, 테스트, 청크 수).
3. manifest에 해당 run이 기록됐는지 확인한다.
4. `downstream_impact`에 따라 후속 작업을 발주한다.
5. doc-sync 검사를 실행해 관련 문서가 함께 갱신됐는지 확인한다.
6. 코드·설정·`.claude/`가 바뀌었으면 security-reviewer에게 점검을 발주한다.

하나라도 확인되지 않으면 완료로 처리하지 않는다.

## 개발 루프

```
발주 → 구현 → 자체 검증 → 평가 → 실패 분석 → 재현 → 수정 → 재평가 → 채택 판정 → 리뷰 → 문서 동기화 → 보안 점검 → PR
```

| 단계    | 담당           | 게이트                                                |
| ------- | -------------- | ----------------------------------------------------- |
| 데이터  | data-engineer  | `verify_bundle()` 통과, 대상 ID·출처 검증, 문서 검토 상태 확인 |
| 인덱스  | data-engineer  | 청크 누락 0, 이름 smoke test, sync 결과 manifest 기록 |
| 툴·체인 | rag-developer  | 툴 단위 테스트 통과, 출처 포함 답변, 트레이스 생성    |
| API     | api-implementer → api-reviewer | [api-invariants §7](.claude/skills/api-invariants/SKILL.md) 게이트 통과, smoke PASS, 리뷰 APPROVE |
| 평가    | eval (2차)     | 평가셋 전체 실행, run 결과 저장                       |
| 채택    | 오케스트레이터 | 아래 실험 규칙 충족                                   |
| 리뷰    | reviewer (2차) | 가드레일·계약 위반 없음                               |
| 문서    | 오케스트레이터 | doc-sync 검사 ERROR 0, WARN 처리                      |
| 보안    | security-reviewer | security-check 검사 ERROR 0, WARN 분류·처리        |

### 평가셋 (Eval 정의 전 기준)

- 유형: 단일 사실, 이름 해석(한글·별칭·오타), 수치·단위, 기술·습득, 상성, 비교, 집계·필터, 세대 구분, 서술형, 답할 수 없는 질문
- 사실형 정답은 `data/processed/`에서 자동 생성한다. 서술형은 사람이 검수한다.
- 문항마다 qid, 유형, 정답, 정답 출처 id를 기록한다. 검색 평가 대상은 허용 근거 청크 ID를 별도로 연결한다.

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
- 개발셋과 최종 평가셋은 분리한다. 3회 반복으로 불안정 실패를 구분하는 방식은 나중에 도입한다.

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
| 체인 진입점·반환 형식 변경         | 연결 가이드 갱신 → API 어댑터 수정 → API 게이트 |
| `api/` 코드                        | API 게이트 → api-reviewer (RAG 평가 재실행 불필요) |

## 가드레일

- `data/processed/`의 해시 고정 파일을 수정하지 않는다. 보강은 별도 파일로 한다.
- 입력은 저장소에 커밋된 파일과 PokeAPI만 쓴다. 팀원과 공유되지 않는 개인 로컬 파일에 의존하지 않는다.
- 평가셋 정답을 프롬프트, 코드, few-shot 예시에 넣지 않는다.
- API 키·`.env`·비밀을 커밋하지 않는다. 키는 환경 변수로만 읽는다.
- 대용량·생성물(`runs/`, DB 볼륨)을 커밋하지 않는다. 발제 제출용 실행·채점 기록(`results/`)은 커밋한다.
- 패키지는 `uv add` / `uv remove`로만 관리한다. 모델명·DB 접속 정보는 환경 변수로 읽고 하드코딩하지 않는다.
- 런타임 질문 라우터를 따로 만들지 않는다. 툴 선택은 툴 docstring과 시스템 프롬프트로 해결한다.
- 집계·정렬·top-N을 벡터 검색으로 풀지 않는다.
- PR 전에 doc-sync 검사(`--strict`)를 통과시킨다. WARN을 남기면 PR 본문에 사유를 쓴다.
- PR 전과 PR 브랜치 push 전에 security-check 검사를 통과시킨다. ERROR가 있으면 PR을 만들지 않는다. push된 키는 지우는 것으로 끝내지 않고 폐기한다.
- main에 직접 push하지 않는다. 브랜치 → PR → 리뷰 → 머지. 커밋 메시지는 `type: 요약` (feat, fix, docs, chore).
- 작업 시작 전 `git fetch`로 main 변경을 확인한다. 팀원이 머지한 데이터·코드를 먼저 반영한다.
- 문서 파일 이름을 `agents.md`로 짓지 않는다. 대소문자 구분이 없는 파일시스템에서 `AGENTS.md`로 인식된다.

## 미정 사항

| 항목                         | 기본값(제안)                 |
| ---------------------------- | ---------------------------- |
| `/pokemon-species` 수집 추가 | 추가                         |
| 메타데이터 관리              | 계약 파일                    |
