---
name: vectordb
description: Use when building, syncing, or checking the vector index (OpenAI embedding, PostgreSQL pgvector collections, incremental re-embedding, index_version).
---

# vectordb

청크를 임베딩해 PostgreSQL(pgvector)에 저장하고, 데이터가 바뀌면 바뀐 청크만 다시 임베딩한다.
환경 설정은 `docs/references/environment.md`를 따른다.

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
- smoke test: 151마리, 165개 기술 이름으로 검색 시 해당 id가 top-1
- 변경 없이 sync 재실행 시 embedded = 0
