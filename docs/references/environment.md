# 개발 환경

## 구성

| 항목 | 값 |
| --- | --- |
| Python | 3.13 (`.python-version`), uv 관리 가상환경 `.venv/` |
| 패키지 | `pyproject.toml` + `uv.lock` (커밋 대상) |
| LLM | OpenAI `gpt-6-luna` |
| 임베딩 | OpenAI `text-embedding-3-small` (1536차원) |
| 벡터 DB | PostgreSQL 17 + pgvector 0.8 (`docker-compose.yml`, 이미지 `pgvector/pgvector:pg17`, 호스트 포트 5434) |
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
| langchain-community | 기타 통합 (sunset 예정 경고 있음, 새 코드에서는 가급적 쓰지 않는다) |
| ragas, datasets | 평가 |
| pydantic | 툴 인자 스키마 |
| python-dotenv | `.env` 로딩 |
| ipykernel | 노트북 커널 |

추가·삭제는 `uv add` / `uv remove`로만 한다. `pip install`을 쓰지 않는다 (`uv.lock`과 어긋난다).

## 환경 변수 (`.env.example`)

| 변수 | 설명 |
| --- | --- |
| `OPENAI_API_KEY` | 각자 발급. 커밋·공유 금지 |
| `OPENAI_CHAT_MODEL` | `gpt-6-luna` |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST` / `POSTGRES_PORT` | docker compose와 앱이 함께 사용 |
| `DATABASE_URL` | `postgresql+psycopg://…` (psycopg 3 드라이버) |
| `PGVECTOR_COLLECTION` | 필수. 사용할 컬렉션 = index_version. 미지정 시 기본 컬렉션 `langchain`에 섞인다 |

코드는 모델명과 접속 정보를 하드코딩하지 않고 환경 변수로 읽는다. 진입점에서 `load_dotenv()`를 한 번 호출한다.

## 확인 명령

```bash
uv run python -V                                  # 3.13.x
uv run python -c "import langchain_openai, ragas" # import 확인
docker compose exec postgres psql -U pokedex -d pokedex -c "select extversion from pg_extension where extname='vector';"
```

## 포트

호스트 포트 기본값은 5434다. 5432/5433은 다른 로컬 Postgres 컨테이너가 쓰는 경우가 있다. 바꾸려면 `.env`의 `POSTGRES_PORT`와 `DATABASE_URL`을 함께 바꾼다.

## PGVector 컬렉션

- 컬렉션은 테이블이 아니라 `langchain_pg_collection`의 한 행이다. 모든 벡터는 `langchain_pg_embedding` 한 테이블에 있다.
- 레코드 id는 컬렉션과 무관한 전역 PK다. 여러 index_version을 같은 DB에 둘 때 id에 index_version을 붙인다 (vectordb 스킬).
