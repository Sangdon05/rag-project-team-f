# API 개발 환경 후속 확인 사항 (TODO)

PR #9(API 개발 환경 추가) 비판 리뷰에서 나온 지적이다. 다른 파트의 코드가 이 저장소에 합쳐진 뒤 함께 확인하고 정리한다.
항목마다 반영하면 상태를 `완료`로 바꾸고 커밋·PR 번호를 적는다.

## 결정

| 항목 | 결정 |
| --- | --- |
| 공개 API의 LLM 호출 횟수 제한(rate limit, 예산) | 테스트성 프로젝트라 두지 않는다. 규칙으로 추가하지 않는다 |
| 서비스 패키지 이름 `api` | 유지. 충돌하면 `layer-profile.json`의 `root`·`package`만 바꾼다 |

## 1. 스크립트

| # | 대상 | 상태 | 내용 |
| --- | --- | --- | --- |
| S1 | `fastapi-run/scripts/run_server.sh` | TODO | `stop`·`status`가 PID 파일의 프로세스가 실제 서버인지 확인하지 않는다. 재사용된 PID면 상관없는 프로세스를 끈다(재현 확인). `ps -o command=`로 uvicorn·`$APP` 여부를 확인하고 아니면 PID 파일만 지운다 |
| S2 | `run_server.sh`, `api-invariants/scripts/smoke.sh` | TODO | `curl`에 시간 제한이 없어 응답 없는 서버에서 끝나지 않는다. `--connect-timeout`·`--max-time` 추가, 포트 사용 확인은 `lsof`/`nc -z`로 |
| S3 | `run_server.sh` | TODO | macOS bash 3.2에서 `"포트 $PORT를"`이 `PORT\xeb: unbound variable`로 깨진다. `${PORT}`로 |
| S4 | `run_server.sh` | TODO | `APP=api:app`처럼 패키지 `__init__.py`에 앱이 있으면 미구현(3)으로 잘못 판단. `--factory` 등 uvicorn 옵션 전달 수단 없음. uvicorn이 바로 죽어도 "30초 안에 준비되지 않음"으로 표시 |
| S5 | `layer-check/scripts/check_layers.py` | TODO | 슬라이스 안 계층 밖 폴더(`chat/utils/`)를 검사하지 않는다(재현 확인). 슬라이스 루트 `.py`·중첩 슬라이스는 경고만 |
| S6 | `check_layers.py` | TODO | `[CORS]`가 리스트 안의 `"*"`만 잡는다. `allow_origins="*"`, `allow_origin_regex`, 변수 경유를 놓친다 |
| S7 | `check_layers.py` | TODO | `HTTPException`을 별칭으로 import하면 놓치고, `except HTTPException`(잡기만 함)은 잘못 잡는다 |
| S8 | `check_layers.py` | TODO | domain이 `container.py`·`main.py`·서비스 루트 모듈을 import해도 잡지 않는다. `importlib`·속성 접근 경유 import도 놓친다 |
| S9 | `check_layers.py` | TODO | 프로파일 값 형식 검증 없음. `fsd`가 문자열이면 예외로 종료 코드 1, 리스트 자리에 문자열이면 검사가 조용히 약해진다. `--root`가 있어도 `root` 키를 요구한다 |
| S10 | `layer-profile.json` | TODO | 접두어 일치가 `_`만 인정해 `psycopg2`를 놓친다. 목록에 추가하거나 일치 규칙을 문서화 |
| S11 | `smoke.sh` | 일부 완료 (docs/api-ep-contracts) | 교대 순서·`error_code` 확인은 반영. 남은 것: `openapi.json`이 JSON이 아닐 때 처리. 원문: 메시지 수 초과 검사: `MAX_MESSAGES`가 홀수면 user가 연속돼 순서 오류 400으로도 통과한다. 교대 순서로 만들고 `error_code`도 확인. `openapi.json`이 JSON이 아니면 FAIL이 아니라 "미구현"으로 넘어간다 |
| S13 | `doc-sync/scripts/check_docs.py` `check_deps_docs` | TODO | `dependencies\s*=\s*\[(.*?)\]`가 `psycopg[binary,pool]`의 `]`에서 끝나 뒤 패키지(`pydantic`, `python-dotenv`, `ragas`, `uvicorn`)를 검사하지 않는다. TOML 파서(`tomllib`)로 읽도록 고친다 |
| S12 | 검증 재현성 | TODO | PR 본문의 검증 결과(unittest 12개, smoke 9항목, 위반 검출)를 재현할 파일이 저장소에 없다. layer-check·smoke 자체 테스트 fixture를 커밋 |

## 2. 문서 정합성

| # | 대상 | 상태 | 내용 |
| --- | --- | --- | --- |
| D1 | 연결 가이드 ↔ `api-implementation`·`api-architecture` | TODO | 가이드의 `Conversation.history`·공백 제거가 예시 코드·용어표에 없다. 포트 시그니처가 세 곳에 반복된다. 가이드 하나만 원본으로 두고 나머지는 링크 |
| D2 | `Source` 계약 | 완료 (docs/api-ep-contracts) | `ref`, `chunk_id`, `source_ref_id`로 확정. `source_ref_id`는 원문 Markdown 파일명. 원문: `chunk_id`, `source_ref_id`만 있다. chunking 스킬의 필수 항목 `document_id`, `source_loc` 추가 여부를 RAG 담당과 결정 |
| D3 | `api-invariants` §7 게이트 4 | TODO | "skip 수는 base와 같음"을 에이전트가 측정할 수 없다(브랜치 변경 금지, 환경 의존 skip). 발주서가 기준 수를 주거나 "새 skip 데코레이터 없음"으로 바꾼다 |
| D4 | `api-reviewer.md` | TODO | 보고 형식이 `fastapi-run §4`를 가리키지만 보고 형식은 §5 |
| D5 | `error_handlers.py` 역할 | TODO | 문서(api-architecture, fsd-architecture)는 app(조립), 프로파일은 shared로 검사. 하나로 맞춘다 |
| D6 | `layer-profile.json` `rule_ids` | TODO | `구조`→R1, `슬라이스`→R5가 규칙 뜻과 다르다. 구조·슬라이스 규칙 ID를 새로 두거나 비운다 |
| D7 | 보고 어휘 | TODO | `not_run`(implementer) / `미구현`(reviewer) / 심각도 `미구현` 포함 여부가 문서마다 다르다. api-invariants에서 하나로 정한다 |
| D8 | 기본값 중복 | 일부 완료 (docs/api-ep-contracts) | 메시지 길이 한도(`2000`)는 삭제. `API_MAX_MESSAGES=20` 중복은 남음. 원문: `API_MAX_MESSAGES=20`·`2000`이 네 곳에 있다. §10이 smoke에 `MAX_MESSAGES`를 넘기지 않는다. 원본 한 곳과 doc-map coupling |
| D9 | `api-architect.md` | TODO | `uv run`(`.venv` 생성)을 쓰게 하면서 환경 변경·저장소 밖 파일 생성을 금지한다. api-invariants §7의 `.venv` 예외를 같이 적거나 `--no-sync` 사용 |
| D10 | 패키지 설명 | TODO | "pydantic-settings 미설치"는 사실과 다르다(`uv.lock`에 전이 의존). `httpx`도 전이 의존이므로 첫 구현에서 `uv add --dev httpx` |
| D11 | `layered-architecture` | TODO | 공통 스킬에 프로젝트 표현("답변 생성기 계약", "연결 가이드")과 FastAPI 전용 조립 규칙(§4.4)이 남아 있다. 중립 예시로 바꾸고 FastAPI 예시임을 표시 |
| D12 | eval 문서 잔여 문구 | TODO | `eval-agent-followups.md` #1의 "쓰기 승인이 나지 않았다" 문장, `eval/README.md`의 "(미반영)". eval/README는 팀원 확인 후 수정 |

## 3. 설계

| # | 대상 | 상태 | 내용 |
| --- | --- | --- | --- |
| G1 | `api-implementation` | TODO | 사실상 완성 코드라 URI·에러 코드·기본값을 미리 정해 설계안(R14)보다 앞선다. 스킬은 짧은 패턴만 남기고 구체 값은 `docs/design/api/chat.md` 초안으로 옮긴다 |
| G2 | llm 모드 근거 표시 | TODO | 출처 없는 답임을 표시하는 일이 프론트 재량이다. `mode != rag`이면 경고 표시를 HTTP 계약에 넣을지 프론트 담당과 결정 |
| G3 | 규모 | TODO | `api-architect` opus/high → sonnet/medium 검토. R1~R16이 여러 문서에 반복되므로 8개 안팎으로 통합 검토. 리뷰 에이전트가 읽는 스킬 수(7개) 축소 검토 |
| G4 | PR 범위 | TODO | eval 문서 최신화(c900f45)가 API PR에 섞여 있다. 다음부터 별도 PR로 낸다 |
| G5 | RAG 경계 목록 | TODO | 아직 없는 `pokedex`·`src/pokedex/`를 경계 규칙에 미리 넣었다. RAG 진입점이 정해지면 실제 이름으로 갱신 (연결 가이드 3절 [미정]) |
| G7 | RAG 체인 `reasoning_effort` | TODO | `gpt-6-luna`는 `reasoning_effort=low`로 쓴다(팀 결정, temperature 0 유지). API `llm` 모드는 `OPENAI_REASONING_EFFORT`(기본 `low`)로 반영함. RAG 체인(langchain-rag 스킬 45행, 체인 코드)은 rag-developer가 같은 변수로 반영. 실제 키로 temperature 0과 함께 받아지는지 1회 확인 필요 |
| G8 | Solar 질문 CLI 출처 | TODO | API는 `sources[].source_ref_id`를 도감번호 3자리(`001`)로 받아 `solar_handoff/documents/001_*.md`를 연다. Solar CLI 결과(`source_document`, `pokemon_id`)에서 이 값을 내보내도록 rag-developer가 반영 |
| G6 | FSD 강도 | TODO | `fsd.cross_slice: off`. 다른 파트 합류 후 `warn`/`error` 결정 |
