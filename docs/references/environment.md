# 개발 환경

## 구성

| 항목 | 값 |
| --- | --- |
| Python | 3.13 (`.python-version`), uv 관리 가상환경 `.venv/` |
| 패키지 | `pyproject.toml` + `uv.lock` (커밋 대상) |
| LLM | OpenAI `gpt-6-luna` |
| 임베딩 | OpenAI `text-embedding-3-small` (1536차원) |
| 벡터 DB | PostgreSQL 17 + pgvector 0.8 (`docker-compose.yml`, 이미지 `pgvector/pgvector:pg17`, 호스트 포트 5432) |
| 설정 | `.env` (커밋 금지), 템플릿 `.env.example` |

## 최초 설정

```bash
uv sync                      # .venv 생성 + uv.lock 기준 설치 (Python 3.13 자동 설치)
cp .env.example .env         # OPENAI_API_KEY 입력
docker compose up -d         # PostgreSQL + pgvector, 최초 기동 시 vector 확장 생성
docker compose ps            # STATUS가 healthy인지 확인
```

노트북: VS Code / Jupyter에서 커널로 `.venv/bin/python`을 선택한다 (ipykernel 포함).

## 패키지

| 패키지 | 용도 |
| --- | --- |
| langchain, langchain-core, langchain-classic | 에이전트 체인, 툴, 프롬프트 |
| langchain-openai | `ChatOpenAI`, `OpenAIEmbeddings` |
| langchain-postgres | `PGVector` 벡터 스토어 |
| psycopg[binary,pool] | PostgreSQL 드라이버 (psycopg 3), 증분 sync용 직접 SQL |
| langchain-community | 기타 통합 (sunset 예정 경고 있음, 새 코드에서는 가급적 쓰지 않는다) |
| ragas, datasets | 평가 |
| pydantic | 툴 인자 스키마 |
| python-dotenv | `.env` 로딩 |
| ipykernel | 노트북 커널 |
| fastapi, uvicorn | API 서비스(`api/`)와 실행 서버 |
| httpx (dev) | API 테스트 클라이언트 |

추가·삭제는 `uv add` / `uv remove`로만 한다. `pip install`을 쓰지 않는다 (`uv.lock`과 어긋난다).

## 환경 변수 (`.env.example`)

| 변수 | 설명 |
| --- | --- |
| `OPENAI_API_KEY` | 각자 발급. 커밋·공유 금지 |
| `OPENAI_CHAT_MODEL` | `gpt-6-luna` |
| `OPENAI_REASONING_EFFORT` | API `llm` 모드 추론 강도. 기본 `low`(팀 결정), temperature 0은 유지. `ANSWER_BACKEND=llm`일 때만 읽는다 |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `UPSTAGE_API_KEY` | Solar 임베딩 API 인증. 커밋·공유 금지 |
| `UPSTAGE_EMBEDDING_MODEL` | Solar 문서 임베딩 모델 ID |
| `UPSTAGE_QUERY_MODEL` | Solar 질문 임베딩 모델 ID. 문서 모델 ID와 다르고 인덱스 설정과 일치해야 한다 |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST` / `POSTGRES_PORT` | docker compose와 앱이 함께 사용 |
| `DATABASE_URL` | 기존 SQLAlchemy와 Solar 전달본의 PostgreSQL 접속. Solar 작업 전 실제 대상과 권한을 확인 |
| `PGVECTOR_COLLECTION` | 기존 컬렉션 방식에서 필수. 사용할 컬렉션 = index_version. 미지정 시 기본 컬렉션 `langchain`에 섞인다 |
| `ANSWER_BACKEND` | API(`api/`) 답변 생성기. `mock`(기본, LLM 호출 없음) \| `llm`(검색 없이 LLM). 그 밖의 값이면 앱 시작 실패 |
| `API_CORS_ORIGINS` | API가 허용할 프론트 origin, 쉼표 구분. 비우면 CORS 미들웨어를 붙이지 않는다. `*` 금지 |
| `API_MAX_MESSAGES` | API 요청당 메시지 수 상한. 기본 `20`, 1 이상 정수가 아니면 앱 시작 실패 |
| `API_DOCUMENTS_DIR` | API documents 슬라이스가 읽는 원문 Markdown 폴더. 기본 `data/synthetic/pilot`, 파일은 `<폴더>/<source_ref_id>.md`, 상대 경로는 서버 작업 디렉터리 기준. 시작 시 검사하지 않고 폴더가 없으면 요청 시 502 `DOCUMENT_SOURCE_FAILED` |

코드는 모델명과 접속 정보를 하드코딩하지 않고 환경 변수로 읽는다. 기존 진입점의 `load_dotenv()`와 달리 Solar 코드는 `.env`를 자동으로 읽지 않는다. Solar 환경 전달과 DB·비용 승인 경계는 [Solar 전달본](../../solar_handoff/README.md#환경과-안전-경계)을 따른다.

## 확인 명령

```bash
uv run python -V                                  # 3.13.x
uv run python -c "import langchain_openai, ragas" # import 확인
docker compose exec postgres psql -U pokedex -d pokedex -c "select extversion from pg_extension where extname='vector';"
```

## 포트

호스트 포트는 운영 환경과 같은 5432로 고정한다. 다른 로컬 Postgres가 5432를 쓰고 있으면 그쪽을 멈추고 띄운다 (`docker ps`로 확인). 포트를 바꾸지 않는다.

## PGVector 컬렉션

- 컬렉션은 테이블이 아니라 `langchain_pg_collection`의 한 행이다. 모든 벡터는 `langchain_pg_embedding` 한 테이블에 있다.
- 레코드 id는 컬렉션과 무관한 전역 PK다. 여러 index_version을 같은 DB에 둘 때 id에 index_version을 붙인다 (vectordb 스킬).
