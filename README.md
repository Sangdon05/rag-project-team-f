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
| `POSTGRES_*`, `DATABASE_URL` | DB 접속 정보 (docker compose와 앱이 함께 사용) |
| `PGVECTOR_COLLECTION` | 사용할 벡터 컬렉션(인덱스 버전). 필수 |

### 규칙

- 패키지는 `uv add` / `uv remove`로만 관리한다 (`pip install` 금지).
- `.env`와 API 키는 커밋하지 않는다.
- 모델명과 DB 접속 정보는 코드에 하드코딩하지 않고 환경 변수로 읽는다.

자세한 내용: [docs/references/environment.md](docs/references/environment.md)

## 문서

- [AGENTS.md](AGENTS.md) — 개발 에이전트 오케스트레이션, 개발 루프, 가드레일
- [docs/references/](docs/references/) — 환경, 에이전트·스킬 개요, 포켓몬 참조표
