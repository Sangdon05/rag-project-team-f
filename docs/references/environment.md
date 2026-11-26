# 개발 환경

## 구성

| 항목 | 값 |
| --- | --- |
| Python | 3.13 (`.python-version`), uv 관리 가상환경 `.venv/` |
| 패키지 | `pyproject.toml` + `uv.lock` (커밋 대상) |
| LLM | OpenAI `gpt-6-luna` |
| 임베딩 | OpenAI `text-embedding-3-small` (1536차원) |
| 벡터 DB | PostgreSQL 17 + pgvector 0.8 (`docker-compose.yml`, 이미지 `pgvector/pgvector:pg17`, 호스트 포트 기본값 5432) |
| 설정 | `.env` (커밋 금지), 템플릿 `.env.example` |

## 최초 설정

기동 전 기존 포트·서비스·DB·볼륨을 확인하고 충돌 시 임의로 중지하거나 삭제하지 않는다.

```bash
uv sync                      # .venv 생성 + uv.lock 기준 설치 (Python 3.13 자동 설치)
[ -e .env ] || cp .env.example .env  # 각자 API 키를 안전하게 설정하고 값을 출력하지 않는다
docker compose up -d         # 빈 볼륨 최초 기동 시 vector 확장과 빈 Solar 스키마 생성
docker compose ps            # STATUS가 healthy인지 확인
```

노트북: VS Code / Jupyter에서 커널로 `.venv/bin/python`을 선택한다 (ipykernel 포함).

Compose는 빈 PGDATA의 최초 기동에만 기본 DB(`POSTGRES_DB`, 기본값 `pokedex`)에서 `init.sql`로 `public.vector`를 만든 다음 기존 `solar_handoff/db/schema.sql`을 단일 트랜잭션으로 포함해 빈 테이블을 만든다. 스키마 생성 중 SQL 오류가 나면 그 트랜잭션은 롤백되지만 PGDATA는 이미 초기화되어 재시작해도 자동 재시도되지 않는다. `pg_isready`의 `healthy`는 스키마 준비를 증명하지 않는다. 스키마·세 테이블을 확인하고 기존 DB와 볼륨은 삭제하지 않으며, 승인된 대상에서만 필요한 수동 초기화를 한다. 기존 볼륨에는 자동 반영되지 않고 데이터·벡터도 자동 적재하지 않는다. 구체적인 확인·복원은 [Solar 전달본](../../solar_handoff/README.md#기존-solar-벡터를-팀-db로-전달)을 따른다.

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

추가·삭제는 `uv add` / `uv remove`로만 한다. `pip install`을 쓰지 않는다 (`uv.lock`과 어긋난다).

## 환경 변수 (`.env.example`)

| 변수 | 설명 |
| --- | --- |
| `OPENAI_API_KEY` | 각자 발급. 커밋·공유 금지 |
| `OPENAI_CHAT_MODEL` | `gpt-6-luna` |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` |
| `UPSTAGE_API_KEY` | Solar 임베딩 API 인증. 커밋·공유 금지 |
| `UPSTAGE_EMBEDDING_MODEL` | Solar 문서 임베딩 모델 ID |
| `UPSTAGE_QUERY_MODEL` | Solar 질문 임베딩 모델 ID. 문서 모델 ID와 다르고 인덱스 설정과 일치해야 한다 |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST` / `POSTGRES_PORT` | docker compose와 앱이 함께 사용 |
| `DATABASE_URL` | 기존 SQLAlchemy와 Solar 전달본의 PostgreSQL 접속. Solar 작업 전 실제 대상과 권한을 확인 |
| `PGVECTOR_COLLECTION` | 기존 컬렉션 방식에서 필수. 사용할 컬렉션 = index_version. 미지정 시 기본 컬렉션 `langchain`에 섞인다 |

코드는 모델명과 접속 정보를 하드코딩하지 않고 환경 변수로 읽는다. 기존 진입점의 `load_dotenv()`와 달리 Solar 코드는 `.env`를 자동으로 읽지 않는다. Solar 환경 전달과 DB·비용 승인 경계는 [Solar 전달본](../../solar_handoff/README.md#환경과-안전-경계)을 따른다.

## 확인 명령

```bash
uv run python -V                                  # 3.13.x
uv run python -c "import langchain_openai, ragas" # import 확인
docker compose exec postgres psql -U pokedex -d pokedex -c "select extversion from pg_extension where extname='vector';"
```

## 포트

호스트 포트 기본값은 5432다. 기동 전 기존 서비스·포트·DB·볼륨을 확인한다. 충돌 시 기존 서비스를 임의로 멈추거나 DB·볼륨을 삭제하지 말고 팀과 별도 대상 및 접근 방법을 합의한다.

## PGVector 컬렉션

- 컬렉션은 테이블이 아니라 `langchain_pg_collection`의 한 행이다. 모든 벡터는 `langchain_pg_embedding` 한 테이블에 있다.
- 레코드 id는 컬렉션과 무관한 전역 PK다. 여러 index_version을 같은 DB에 둘 때 id에 index_version을 붙인다 (vectordb 스킬).
