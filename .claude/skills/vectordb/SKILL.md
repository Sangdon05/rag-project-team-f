---
name: vectordb
description: Use when building, syncing, or checking the vector index (OpenAI embedding, PostgreSQL pgvector collections, incremental re-embedding, index_version).
---

# vectordb

청크를 임베딩해 PostgreSQL(pgvector)에 저장하고, 데이터가 바뀌면 바뀐 청크만 다시 임베딩한다.
환경 설정은 `docs/references/environment.md`를 따른다.
입력은 `chunking` 스킬에 따라 승인된 Markdown에서 생성한 청크다. 문서 변경 시 청크 본문과 근거 연결을 먼저 갱신·검증한다.

## Solar 단일 임베딩 전달본

- [`solar_handoff/`](../../../solar_handoff/README.md)의 `db/schema.sql`은 별도 `solar_handoff` 스키마의 `chunks`, `vectors`, `index_info`를 정의한다. Upstage Solar 문서 모델과 질문 모델은 별도 ID이고 저장된 설정과 맞아야 하며 벡터 차원은 1024다. 접속은 기존 `DATABASE_URL`을 사용하며, 실행 전 실제 대상과 권한을 확인한다. 아래 기존 PGVector 컬렉션의 테이블·해시·삭제 규칙과 혼동하지 않는다.
- Compose는 빈 PGDATA의 최초 기동에서만 기본 DB에 `init.sql`로 `public.vector`를 먼저 준비하고 실제 `solar_handoff/db/schema.sql`을 단일 트랜잭션으로 포함한다. 스키마 생성 중 SQL 오류 시 해당 트랜잭션은 롤백되지만 초기화된 PGDATA에서 재시작은 자동 재시도하지 않으며 `pg_isready`의 `healthy`는 스키마 준비를 증명하지 않는다. 스키마·세 테이블의 존재를 확인하고 기존 DB·볼륨을 삭제하지 않는다. 기존 볼륨에는 자동 반영되지 않으며 빈 테이블만 만들고 번들·벡터를 적재하지 않는다. 기존 포트·대상 DB·스키마와 권한을 확인한다. 스키마가 이미 있으면 `init`을 다시 실행하지 않고, 없을 때만 승인 후 `public.vector` 준비와 수동 `init`을 수행한다. 스키마가 부분 생성되었거나 상태가 불명확하면 중단하고 조사한다.
- `legacy-export`는 CLI와 직접 함수 호출 모두 보안상 비활성화되어 원본을 조회하지 않는다. 기존에 검증된 Solar 벡터 1,504개 번들은 비공개 보관 중이며 사용자가 비공개 공유를 선택했지만 아직 전달되지 않았다. 번들 전달은 별도로 수행하며 본문·메타데이터·벡터가 포함되므로 ACL·출처·재배포 권리와 수신 대상을 확인한다. 승인된 세 테이블이 모두 빈 대상에만 재임베딩 없이 `restore`·`verify`를 수행한다. 자세한 분기와 실패 처리는 [Solar 안내](../../../solar_handoff/README.md#기존-solar-벡터를-팀-db로-전달)를 따른다. 임시 PostgreSQL 복원에서 1,504개 전체 메타데이터와 벡터 wire bytes를 독립 새 연결로 확인한 범위만 검증됐다.
- `src/ingest.py`는 제공된 청크에서 본문이 새롭거나 바뀐 항목만 임베딩하고 입력에서 빠진 항목은 삭제하지 않는다. 기존 설정이 다르면 별도 인덱스가 필요하다. dry-run도 DB에 연결한다. 새 입력 승인, DB 대상·권한과 백업, 매 실행의 유료 API 비용 및 보안 조건을 사전에 확인한다. 실행 플래그는 사용자 승인을 대신하지 않는다.
- 사용자 151문서 승인 의사와 원본 청크의 pending 상태는 별개다. 과거 승인 스냅샷 검증 시스템을 재도입하지 않는다. 검증은 위 복원과 승인된 질문 1건의 Solar C 검색·rewrite·GPT 답변에 한정되며 모든 모델·검색 조합이나 인용의 의미 정확성은 보장하지 않는다. 실패나 readback 결과 불명 시 자동 재시도하지 않고 대상을 확인한다.

## 기존 PGVector 컬렉션 방식

`DATABASE_URL`은 Solar 전달본과 공통으로 사용한다. 이하의 OpenAI 임베딩, 컬렉션 및 전체 목록에 없는 항목 삭제 절차는 기존 방식이며 Solar 전달본의 증분 적재에 적용하지 않는다.

## 구성

- 저장소: PostgreSQL 17 + pgvector (`docker compose up -d`), 접속은 `DATABASE_URL`
- 임베딩: `OPENAI_EMBEDDING_MODEL` (= `text-embedding-3-small`, 1536차원)
- 라이브러리: `langchain_postgres.PGVector(collection_name=..., connection=DATABASE_URL, use_jsonb=True, distance_strategy=COSINE)`
- 컬렉션 이름 = `index_version` = `v{n}-{임베딩 약칭}-{템플릿 버전}` (예: `v1-te3s-tpl1`), `PGVECTOR_COLLECTION`으로 지정
- 모델명, 접속 정보, 컬렉션 이름은 환경 변수로만 읽는다.

## 저장 구조 (pgvector 0.8, langchain-postgres 0.0.19에서 확인)

- 테이블은 2개뿐이다: `langchain_pg_collection`(name, uuid), `langchain_pg_embedding`(id, collection_id, embedding, document, cmetadata jsonb).
- 컬렉션은 별도 테이블이 아니라 `collection_id`로 나눈 논리 구분이다. `collection_name`을 안 주면 `"langchain"` 컬렉션에 섞여 들어간다. 그래서 `PGVECTOR_COLLECTION`을 반드시 지정한다.
- `langchain_pg_embedding.id`는 컬렉션과 무관한 전역 PRIMARY KEY이고, `add_documents(ids=...)`는 id 충돌 시 기존 행을 덮어쓴다. 다른 컬렉션에 같은 id를 넣으면 이전 컬렉션의 행이 조용히 덮어써지고 새 컬렉션은 0건이 된다 (실측).
- 따라서 레코드 id = `{index_version}:{chunk_id}` (예: `v1-te3s-tpl1:pokemon:25#stats`). 순수 `chunk_id`는 `cmetadata.chunk_id`에 둔다.

## 전체 빌드 vs 증분 sync

| 상황 | 방식 |
| --- | --- |
| 최초 빌드, 임베딩 모델 변경, 청크 템플릿 변경 | 새 컬렉션에 전체 빌드 |
| 데이터 일부 변경/추가/삭제 | 같은 컬렉션에 증분 sync |

이전 컬렉션은 새 컬렉션의 평가가 채택될 때까지 지우지 않는다 (비교와 롤백용).

## 증분 sync 절차

청크마다 메타데이터에 해시 2개를 저장한다.

- `content_hash = sha256(embed_model + "|" + text)` → 바뀌면 재임베딩
- `meta_hash = sha256(정렬된 메타데이터)` → 텍스트가 같고 이것만 바뀌면 메타데이터만 갱신

1. 해당 컬렉션의 저장된 id와 해시를 SQL로 한 번에 읽는다: `langchain_pg_embedding e JOIN langchain_pg_collection c ON e.collection_id = c.uuid WHERE c.name = %s`.
2. 새 chunks.jsonl과 비교해 분류한다.

   | 조건 | 처리 | 임베딩 |
   | --- | --- | --- |
   | 신규 또는 content_hash 다름 | 같은 id로 upsert | O |
   | content_hash 같음, meta_hash 다름 | `cmetadata`만 SQL UPDATE (PGVector에 메타데이터 단독 갱신 API 없음) | X |
   | 새 목록에 없음 | delete | X |
   | 둘 다 같음 | 건너뜀 | X |

3. embedded / meta_only / deleted / unchanged 건수를 `runs/manifest.jsonl`에 기록한다. 변경 없는 데이터를 임베딩하지 않았다는 증거다.
4. 한 sync는 한 트랜잭션으로 처리한다. 중간 실패 시 컬렉션이 반쯤 바뀐 상태로 남지 않게 한다.

참고 시뮬레이션(151마리 × 3섹션, 가짜 임베딩): 한 마리의 스탯만 변경 → 임베딩 1건, 유지 452건. 변경 없이 재실행 → 임베딩 0건. 메타데이터만 변경 → 임베딩 0건.

## 주의

- 청크 텍스트가 비결정적이면(시각, 순서, 숫자 포맷) 데이터가 그대로여도 전체가 재임베딩된다.
- 임베딩 모델명이 content_hash에 들어 있으므로 모델 변경은 증분 sync가 아니라 새 컬렉션으로 처리한다.
- 메타데이터 필터는 JSONB 조건이다. 키 이름과 값 표기(소문자 영문 enum)가 계약과 다르면 조용히 0건이 된다.
- 조건이 좁은 필터는 결과가 k보다 적을 수 있다. 검색 툴은 결과 개수를 함께 반환한다.
- 정렬·top-N·집계는 벡터 검색으로 풀지 않는다. 정규화 데이터를 직접 조회하는 툴의 몫이다.
- 테이블 스키마를 손으로 바꾸지 않는다. 바꿔야 하면 오케스트레이터에 보고한다.

## 검증

- 컬렉션 레코드 수 = chunks.jsonl 청크 수, 누락 id 0, `"langchain"` 기본 컬렉션 0건
- smoke test: 인덱싱된 포켓몬 이름으로 검색 시 해당 id가 top-1. 별도 기술 청크를 인덱싱한 경우 기술 이름도 검증한다.
- 변경 없이 sync 재실행 시 embedded = 0

## 파일럿 테스트 컬렉션 스크립트

`scripts/helper/pilot_vector_index.py` (테스트 `tests/test_pilot_vector_index.py`). `test-`로 시작하는 컬렉션에만 쓰고, 컬렉션 이름의 `-tplN`·기존 행의 schema·template 버전이 청크 파일과 다르면 sync를 거부한다. 임베딩 본문은 청크 `content` 그대로이며 `cmetadata.heading`(한글 제목, 표시용)을 더한다. 검색은 필터 없이 SQL 코사인 거리로 하고 채점하지 않는다. 테스트 컬렉션은 템플릿마다 하나다: `test-pilot-v1-te3s-tpl1`(v1/), `test-pilot-v2-te3s-tpl2`(v2/), `test-pilot-v3a-te3s-tpl3a`(v3a/, 채택 템플릿 tpl3a), `test-pilot-v3b-te3s-tpl3b`(v3b/, 기각된 실험 tpl3b의 비교 기록). 청크 파일은 버전 폴더의 JSON을 쓴다 (최신본 `data/synthetic/pilot/bulbasaur_red_blue.json`은 v3a 사본). 기존 컬렉션에 새 템플릿을 쓰지 않는지는 `--sync` 대신 `check_sync_compatibility` 단위 테스트로 확인한다.

```bash
S=scripts/helper/pilot_vector_index.py; C=test-pilot-v3a-te3s-tpl3a; J=data/synthetic/pilot/v3a/bulbasaur_red_blue.json
uv run python $S --sync --chunks $J --collection $C            # 증분 sync (embedded/meta_only/deleted/unchanged)
uv run python $S --query "질문" -k 5 --collection $C           # chunk_id·section·heading·distance
uv run python $S --queries eval/pilot_smoke_queries.json -k 5 --collection $C --chunks $J --out <결과.json>  # 원본 결과만
uv run python $S --verify --collection $C --chunks $J          # SQL 검증 (API 호출 없음)
uv run python $S --drop --collection $C --yes                  # test- 컬렉션만
```
