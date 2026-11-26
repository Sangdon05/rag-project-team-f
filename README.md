# 포켓몬 도감 RAG

1세대(Red/Blue) 포켓몬 151마리 도감을 대상으로 하는 RAG 프로젝트.

## 개발 환경

| 항목 | 값 |
| --- | --- |
| Python | 3.13 (`.python-version`), [uv](https://docs.astral.sh/uv/)로 가상환경 `.venv/` 관리 |
| 패키지 | `pyproject.toml` + `uv.lock` |
| LLM | OpenAI `gpt-6-luna` |
| 임베딩 | OpenAI `text-embedding-3-small` |
| 벡터 DB | PostgreSQL 17 + pgvector (Docker, 포트 5432, 운영 환경과 동일) |
| 설정 | `.env` (템플릿 `.env.example`) |

### 사전 준비

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker (Docker Desktop 등)
- OpenAI API 키

### 설정

```bash
uv sync                  # .venv 생성 + 패키지 설치 (Python 3.13이 없으면 자동 설치)
cp .env.example .env     # .env에 OPENAI_API_KEY 입력
docker compose up -d     # PostgreSQL + pgvector 기동 (최초 기동 시 vector 확장 생성)
docker compose ps        # STATUS가 healthy인지 확인
```

로컬에서 다른 Postgres가 5432 포트를 쓰고 있으면 먼저 멈춘다. 포트는 바꾸지 않는다.

### 확인

```bash
uv run python -V                                       # Python 3.13.x
uv run python -c "import langchain_openai, langchain_postgres, ragas"
docker compose exec postgres psql -U pokedex -d pokedex \
  -c "select extversion from pg_extension where extname='vector';"
uv run python -m unittest discover -s tests            # 테스트
```

노트북은 커널로 `.venv/bin/python`을 선택한다.

### 환경 변수

| 변수 | 설명 |
| --- | --- |
| `OPENAI_API_KEY` | 각자 발급 |
| `OPENAI_CHAT_MODEL` / `OPENAI_EMBEDDING_MODEL` | 사용할 LLM / 임베딩 모델 |
| `OPENAI_REASONING_EFFORT` | API `llm` 모드 추론 강도 (기본 `low`) |
| `UPSTAGE_API_KEY` | Solar 임베딩 API 인증 키 |
| `UPSTAGE_EMBEDDING_MODEL` / `UPSTAGE_QUERY_MODEL` | Solar 문서 / 질문 임베딩 모델 ID |
| `POSTGRES_*`, `DATABASE_URL` | DB 접속 정보 (docker compose와 앱, Solar 전달본에서 사용). Solar 작업 전 실제 대상·권한 확인 |
| `PGVECTOR_COLLECTION` | 기존 방식에서 사용할 벡터 컬렉션(인덱스 버전). 필수 |
| `ANSWER_BACKEND` | API 답변 생성기 `mock`(기본) \| `llm` |
| `API_CORS_ORIGINS` | API가 허용할 프론트 origin, 쉼표 구분 (비우면 CORS 없음) |
| `API_MAX_MESSAGES` | API 요청당 메시지 수 상한 (기본 20) |
| `API_DOCUMENTS_DIR` | API 문서 조회가 읽는 원문 Markdown 폴더 (기본 `solar_handoff/documents`, 파일은 `<폴더>/<도감번호 3자리>_*.md`) |

### 규칙

- 패키지는 `uv add` / `uv remove`로만 관리한다 (`pip install` 금지).
- `.env`와 API 키는 커밋하지 않는다.
- 모델명과 DB 접속 정보는 코드에 하드코딩하지 않고 환경 변수로 읽는다.

자세한 내용: [docs/references/environment.md](docs/references/environment.md)

## 문서

- [Solar 데이터·검색 팀 전달본](solar_handoff/README.md) — 데이터, 복원·질문 실행, 검증 및 보안 경계
- [문제와 성공 기준](docs/problem.md) — 세 페르소나, 싱글 배틀 준비 여정, 질문 9개·답변·근거·검증 및 평가 운영 기준
- [페르소나별 질문 생성기 예시](docs/persona-question-generator.md) — 같은 정보 요구의 자연어 표현 변형 예시
- [질문 설계 에이전트 사용·공유 안내](docs/references/question-design.md) — 세 페르소나의 질문 후보 제안, 실행·검증과 팀원 전달 절차

- [AGENTS.md](AGENTS.md) — 개발 에이전트 오케스트레이션, 개발 루프, 가드레일
- [docs/references/](docs/references/) — 환경, 에이전트·스킬 개요, 포켓몬 참조표

## 영문 Red·Blue 진화·서식지·머신 데이터

| 구분 | 파일 |
|---|---|
| 진화 결과 | `data/processed/evolutions_red_blue.json` |
| 진화 아이템 이름 결과 | `data/processed/evolution_items_red_blue.json` |
| 서식환경·등장/획득 장소 결과 | `data/processed/encounters_red_blue.json` |
| 기술머신·비전머신 결과 | `data/processed/machines_red_blue.json` |
| 머신 획득 장소·방법 결과 | `data/processed/machine_acquisition_red_blue.json` |
| 장소 한국어명 대응표 (사용자 승인) | `data/processed/location_names_ko_red_blue.json` |
| 진화 추출 스크립트 | `pokeapi/tools/data_prep/extract_evolutions_red_blue.py` |
| 서식지 추출 스크립트 | `pokeapi/tools/data_prep/extract_encounters_red_blue.py` |
| 머신 추출 스크립트 | `pokeapi/tools/data_prep/extract_machines_red_blue.py` |
| 머신 획득 정보 추출 스크립트 | `pokeapi/tools/data_prep/extract_machine_acquisition_red_blue.py` |
| 진화 아이템 이름 추출 스크립트 | `scripts/helper/extract_evolution_items_red_blue.py` |
| 머신 획득 정보 설명 | `pokeapi/tools/data_prep/MACHINE_ACQUISITION_README.md` |
| 머신 상세 설명 | `pokeapi/tools/data_prep/MACHINES_README.md` |
| 상세 설명 | `pokeapi/tools/data_prep/EVOLUTION_README.md`, `pokeapi/tools/data_prep/ENCOUNTERS_README.md` |
| 수집 원본·매니페스트 | `pokeapi/sources/evolution_red_blue/`, `pokeapi/sources/encounters_red_blue/` |
| 데이터 검증 테스트 | `pokeapi/tests/test_evolutions_red_blue.py`, `pokeapi/tests/test_encounters_red_blue.py` |
| 진화 아이템 이름 검증 테스트 | `tests/test_evolution_items_red_blue.py` |
| 장소 한국어명 대응표 생성 스크립트·검증 테스트 | `scripts/helper/build_location_names_ko_red_blue.py`, `tests/test_location_names_ko_red_blue.py` |
| 파일럿 청크 생성 스크립트·검증 테스트 | `scripts/helper/build_pilot_chunks.py`, `tests/test_pilot_chunks.py`, `tests/test_pilot_chunks_v3.py` |
| 파일럿 테스트 컬렉션 sync·검색 스크립트·테스트 (사용법: vectordb 스킬) | `scripts/helper/pilot_vector_index.py`, `tests/test_pilot_vector_index.py` |

진화는 PokéAPI의 고정 정적 데이터와 영문 Red·Blue 게임의 커뮤니티 디스어셈블리 진화표를 비교한 결과입니다. 실제 게임 실행 검증은 하지 않았습니다. 서식환경은 종의 일반 분류이며, 게임 버전별 등장·획득 장소와 다릅니다. API 기록이 없는 포켓몬은 획득 불가가 아니라 **API에 기록이 없는 상태**로 표시합니다. API가 제공하지 않은 한국어 장소명은 `null`입니다. 머신 획득 장소는 55개 각각에 최소 한 경로를 기록했으나 모든 가능한 경로·접근 조건을 전부 검증한 것은 아닙니다. 데이터와 Pokémon 관련 권리의 이용·재배포 조건은 별도로 확인해야 합니다.

## 팀원이 실행할 수 있는 계산 테스트

`data/processed/`, `scripts/`, `tests/`가 있으면 로컬 `pokeapi/` 폴더 없이도 상성·자속 계산 테스트를 실행할 수 있습니다.

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
```

이 테스트는 배틀 계산을 검증하며 진화·서식지·머신 데이터의 원본 대조는 포함하지 않습니다. 선택적 `pokeapi/tools/compat`이 없으면 해당 호환 테스트는 건너뜁니다.

## 로컬 원본이 있을 때 데이터 검증

아래 명령은 `pokeapi/`의 추출 스크립트, 테스트와 수집 원본이 필요하며, 그 폴더를 공유하지 않은 팀원 환경에서는 실행되지 않습니다.

```sh
python -m unittest discover -s pokeapi/tests -p 'test_evolutions_red_blue.py' -v
python -m unittest discover -s pokeapi/tests -p 'test_encounters_red_blue.py' -v
python -m unittest discover -s pokeapi/tests -p 'test_machines_red_blue.py' -v
python -m unittest discover -s pokeapi/tests -p 'test_machine_acquisition_red_blue.py' -v
```

진화 스크립트는 기본적으로 보존된 스냅샷에서 결과를 재생성합니다. 서식지 스크립트는 네트워크로 새로 수집하며 기존 산출물을 덮어쓰지 않습니다. 실행 전 각 상세 설명의 경로와 재수집 조건을 확인하세요.
