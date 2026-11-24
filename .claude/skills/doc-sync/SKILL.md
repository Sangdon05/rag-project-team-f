---
name: doc-sync
description: Use before reporting a task done or opening a PR, and whenever skills, agents, env/config, or shared data change. Keeps linked docs in sync.
---

# doc-sync

오케스트레이터용 스킬. 스킬·에이전트·설정·데이터가 바뀔 때 관련 문서가 함께 바뀌었는지 확인한다.
한 곳만 고치고 폴더 안쪽 문서(README, 참조 문서, 다른 스킬)가 예전 내용으로 남는 것을 막는다.

구성:

- `doc-map.json` — 문서 의존 관계 정의 (무엇이 바뀌면 무엇을 확인하는가)
- `scripts/check_docs.py` — 검사 스크립트 (stdlib만 사용)

## 원칙

1. **사실마다 원본 문서는 하나다.** 다른 문서는 값을 복사하지 않고 링크한다. 복사가 필요한 값(모델명, 포트, Python 버전 등)은 `doc-map.json`의 `mirrors`에 등록해 검사로 묶는다.
2. **모든 문서는 허브에서 도달할 수 있어야 한다.** `AGENTS.md` 또는 `README.md`에서 파일 링크를 따라가 닿지 않는 문서는 아무도 갱신하지 않는다. 새 문서를 만들면 허브나 상위 README에 링크한다.
3. **새 의존 관계는 지도에 먼저 등록한다.** 문서 A가 B의 내용을 설명하게 되면 `doc-map.json`의 `coupling`에 규칙을 추가한다.
4. **검사가 통과해야 완료다.** 하위 에이전트의 보고, PR 생성 모두 이 검사를 거친다.

## 원본 문서 (Single Source of Truth)

| 사실 | 원본 | 설명·복사하는 곳 |
| --- | --- | --- |
| 환경 변수, 모델명, DB 접속 | `.env.example` | README, environment.md, langchain-rag·vectordb 스킬 |
| Python 버전 | `.python-version` | pyproject, README, environment.md |
| 패키지 | `pyproject.toml` | environment.md 패키지 표 |
| DB 포트·이미지 | `docker-compose.yml` | README, environment.md |
| 스킬 정의 | `.claude/skills/*/SKILL.md` | skills README 표 |
| 에이전트 정의·사용 스킬 | `.claude/agents/*.md` frontmatter | agents README 표, AGENTS.md 에이전트 표, skills README '사용 에이전트' |
| 청크 ID·섹션·메타데이터 | chunking 스킬 (→ `contracts/chunk_schema.json` 예정) | vectordb, tool-calling, langchain-rag 스킬, agents README |
| 툴 목록 | tool-calling 스킬 | langchain-rag 스킬, skills README |
| 기준 데이터 | `data/processed/`, `data_integrity.py` | data-normalize 스킬, skills README |
| 개발 루프·가드레일 | `AGENTS.md` | 에이전트 파일은 링크만 |

## 언제 실행하는가

- 하위 에이전트 보고를 검토할 때 (보고 검토 절차의 마지막 단계)
- 스킬·에이전트·설정·`data/processed/`를 바꾼 직후
- PR을 만들기 직전 (필수)

## 절차

1. 검사를 실행한다.

   ```bash
   # 작업 단위 (커밋 전): 이번 작업에서 바꾼 파일만 기준으로 연동 확인
   uv run python .claude/skills/doc-sync/scripts/check_docs.py --base HEAD
   # PR 직전: 브랜치 전체 기준, WARN도 실패
   uv run python .claude/skills/doc-sync/scripts/check_docs.py --strict
   ```

   브랜치가 길면 `origin/main` 기준으로는 대부분의 문서가 이미 "변경됨"이라 WARN이 잘 안 뜬다. 연동 누락은 작업 단위(`--base HEAD`)에서 잡는다.

2. **ERROR**는 모두 고친다. 구조가 깨진 상태다.

   | 종류 | 뜻 | 처리 |
   | --- | --- | --- |
   | link | 상대 링크 대상이 없음 | 경로 수정, 이름 바꾼 파일 추적 |
   | orphan | 허브에서 도달 불가 | 상위 README나 AGENTS.md 이정표에 링크 |
   | frontmatter | name이 경로와 다름, description 없음 | frontmatter 수정 |
   | registry | 스킬·에이전트 표 누락, 사용 스킬 불일치 | 표를 frontmatter에 맞춘다 (frontmatter가 원본) |
   | mirror | 복사된 값이 원본과 다름 | 원본 값으로 갱신 |
   | env / deps | 환경 변수·패키지 설명 누락 또는 삭제된 항목이 남음 | environment.md, README 갱신 |
   | forbidden | 금지어 (예: 개인 작업 폴더 경로) | 문장 제거 |

3. **WARN**(coupling)은 하나씩 판단한다. 함께 바뀌어야 할 수 있는 문서가 이번 변경에 없다는 뜻이다.
   - 내용을 읽고 영향이 있으면 갱신한다.
   - 영향이 없으면 PR 본문 "문서 영향" 섹션에 `파일 — 영향 없음: 이유`를 남긴다.
4. PR 본문에 검사 결과(`ERROR 0, WARN n`)와 WARN 처리 내역을 적는다.

## 지도 갱신 규칙

- 새 스킬·에이전트: frontmatter 작성 → skills/agents README 표, AGENTS.md 표에 추가 (검사가 강제)
- 새 참조 문서: `docs/references/` 아래 작성 → 허브 링크 → 다른 문서가 의존하면 `coupling` 추가
- 새 환경 변수: `.env.example` → environment.md, README 표 (검사가 강제)
- 문서끼리 같은 값을 쓰게 되면: `mirrors`에 등록
- 규칙을 추가·삭제하면 이 SKILL.md의 원본 문서 표도 갱신한다

## 검사의 한계

- WARN은 "같이 바뀌지 않았다"만 알려준다. 내용이 맞는지는 사람(오케스트레이터)이 읽고 판단한다. 예: 청크 ID 형식 변경은 WARN만 뜨고, vectordb·langchain-rag 스킬의 예시 ID는 직접 고쳐야 한다.
- mirror 검사는 새 값이 문서에 있는지만 본다. 예전 값이 함께 남아 있으면 잡지 못하므로 값을 바꿀 때 예전 값을 `grep`으로 찾아 지운다.
- 디렉터리 링크(`.claude/skills/`)는 도달성 계산에 넣지 않는다. 파일마다 링크가 있어야 한다.

## 하지 않는 것

- 검사를 통과시키려고 원본(frontmatter, `.env.example`, `pyproject.toml`)을 문서에 맞춰 바꾸지 않는다. 문서를 원본에 맞춘다.
- WARN을 근거 없이 무시하지 않는다.
- 사람이 읽는 개요(README)에 세부 절차를 복사하지 않는다. 스킬로 링크한다.
