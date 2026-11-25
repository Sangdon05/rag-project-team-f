#!/usr/bin/env python3
"""파일럿 청크 JSON → OpenAI 임베딩 → pgvector 테스트 컬렉션 증분 sync, 검색, SQL 검증 (vectordb 스킬).

테스트 전용이다. 정식 인덱스는 승인된 문서만 대상으로 하므로 이 스크립트는 `test-`로 시작하는 컬렉션에만 쓴다.
검색 결과는 원본 그대로 저장하고 채점(Hit@k·MRR·적중 여부)하지 않는다. 질의 파일의 기대 정답 필드는 읽지 않는다.

사용법 (저장소 루트에서):
    # (a) 증분 sync: 레코드 id `{collection}:{chunk_id}`, embedded / meta_only / deleted / unchanged 집계
    uv run python scripts/helper/pilot_vector_index.py --sync --chunks data/synthetic/pilot/v3a/bulbasaur_red_blue.json \
        --collection test-pilot-v3a-te3s-tpl3a [--out 로그.json]
    # (b) 단일 검색 (chunk_id, section, heading, distance)
    uv run python scripts/helper/pilot_vector_index.py --query "질문" -k 5 --collection test-pilot-v3a-te3s-tpl3a
    # (c) 질의 파일 전체 검색 → 원본 결과 JSON (qid, query, 순위별 결과, 질의별 소요 시간, 오류)
    uv run python scripts/helper/pilot_vector_index.py --queries eval/pilot_smoke_queries.json -k 5 \
        --collection test-pilot-v3a-te3s-tpl3a --chunks data/synthetic/pilot/v3a/bulbasaur_red_blue.json --out 결과.json
    # (d) SQL 검증 (API 호출 없음). --chunks를 주면 id·content_hash를 청크 파일과 대조한다
    uv run python scripts/helper/pilot_vector_index.py --verify --collection test-pilot-v3a-te3s-tpl3a [--chunks ...]
    # (e) 테스트 컬렉션 삭제
    uv run python scripts/helper/pilot_vector_index.py --drop --collection test-pilot-v3a-te3s-tpl3a --yes

- 모델명(OPENAI_EMBEDDING_MODEL)·DB 접속(DATABASE_URL)·키는 환경 변수로만 읽는다(.env는 load_dotenv). 값을 출력하지 않는다.
- 임베딩 본문은 청크 content 그대로다. 접두어를 붙이지 않는다.
- 쓰기(upsert·메타 UPDATE·delete)는 한 트랜잭션이며 대상 컬렉션 행만 건드린다. 다른 컬렉션에 같은 id가 있으면 멈춘다.
- 컬렉션 이름의 `-tplN`이 청크 파일 template_version과 다르거나, 기존 행의 schema·template 버전이 청크 파일과 다르면
  sync를 거부한다 (예: v1 기준선 컬렉션에 tpl2 청크를 덮어쓰는 실수 방지).
- 검색은 SQL(`embedding <=> 질의 벡터`, 코사인 거리, 필터 없음)로 한다. PGVector 객체는 생성 시 컬렉션을 만들기 때문에
  읽기 전용 작업에서 쓰지 않는다.
- OpenAI 클라이언트 자동 재시도는 끈다(max_retries=0). 실패한 질의는 오류로 기록하고 다시 보내지 않는다.
- API 오류는 예외 종류·HTTP 상태만 기록한다 (메시지에 키 조각이 섞일 수 있어 남기지 않는다).
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEST_PREFIX = "test-"
GAME_VERSION = "red-blue"
DEFAULT_COLLECTION = "langchain"  # collection_name을 안 주면 섞여 들어가는 기본 컬렉션 (vectordb 스킬)
MARKDOWN_SOURCE_PREFIX = "pilot_markdown:"
HEADING_SEPARATOR = " — "
RUN_NOTE = "테스트 전용 원본 검색 결과. 채점·비교 없음. 질의 파일의 기대 정답 필드는 읽지 않았다."

STATS = {"embed_requests": 0, "embed_texts": 0, "embed_tokens_estimate": 0}


class GuardError(ValueError):
    """쓰기 대상 컬렉션이 테스트 컬렉션이 아니다."""


# ------------------------------------------------------------------ 순수 함수 (네트워크 없음, 단위 테스트 대상)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_writable_collection(name, official=None):
    """쓰기 허용 여부. `test-`로 시작하고 정식 PGVECTOR_COLLECTION과 다른 이름만 허용한다."""
    if not isinstance(name, str) or not name.startswith(TEST_PREFIX) or len(name) <= len(TEST_PREFIX):
        raise GuardError(f"'{TEST_PREFIX}'로 시작하지 않는 컬렉션에는 쓰지 않는다: {name!r}")
    if official and name == official:
        raise GuardError(f"정식 PGVECTOR_COLLECTION과 같은 이름이다: {name!r}")
    return name


def check_sync_compatibility(collection, chunk_doc, stored_versions):
    """다른 템플릿·스키마 컬렉션을 덮어쓰지 않게 막는다 (템플릿 변경은 새 컬렉션, vectordb 스킬).

    - 컬렉션 이름이 `-tplN`으로 끝나면 청크 파일의 template_version(없으면 tpl1)과 같아야 한다.
    - 컬렉션에 이미 있는 행의 (schema_version, template_version)은 청크 파일과 같아야 한다.
    stored_versions = 기존 행의 {(schema_version, template_version 또는 None)} 집합.
    """
    template = chunk_doc.get("template_version", "tpl1")
    suffix = collection.rsplit("-", 1)[-1]
    if suffix.startswith("tpl") and suffix != template:
        raise GuardError(f"컬렉션 템플릿({suffix})과 청크 파일 템플릿({template})이 다르다: {collection}")
    expected = (chunk_doc["schema_version"], template)
    others = {(schema, tpl or "tpl1") for schema, tpl in stored_versions} - {expected}
    if others:
        raise GuardError(f"컬렉션의 기존 행 버전 {sorted(others, key=str)}이 청크 파일 {expected}과 다르다 — 새 컬렉션을 쓴다")
    return expected


def record_id(collection, chunk_id):
    """레코드 id = `{collection}:{chunk_id}` (id는 컬렉션과 무관한 전역 PK라 접두어로 구분한다)."""
    if not collection or not chunk_id:
        raise ValueError("collection과 chunk_id가 필요하다")
    return f"{collection}:{chunk_id}"


def content_hash(model, text):
    return sha256_text(model + "|" + text)


def meta_hash(meta):
    body = {k: v for k, v in meta.items() if k not in ("content_hash", "meta_hash")}
    return sha256_text(json.dumps(body, sort_keys=True, ensure_ascii=False))


def heading_of(chunk):
    """표시용 한글 제목: 청크 머리말 `{포켓몬명} — {주제}`의 주제. 머리말 형식이 아니면 section."""
    first = chunk["content"].split("\n", 1)[0]
    return first.split(HEADING_SEPARATOR, 1)[1] if HEADING_SEPARATOR in first else chunk["section"]


def markdown_record(chunk):
    found = [r for r in chunk.get("source_records", []) if r.get("source_id", "").startswith(MARKDOWN_SOURCE_PREFIX)]
    return found[0] if len(found) == 1 else {}


def build_rows(chunk_doc, chunk_path, collection, model, pokemon_rows, type_names):
    """청크 문서 → 적재 행 [{id, text, meta}]. 본문은 content 그대로 (접두어 없음)."""
    record = next(p for p in pokemon_rows if p["id"] == chunk_doc["pokemon_id"])
    markdown_path = next((f["path"] for f in chunk_doc.get("source_files", [])
                          if f.get("source_id", "").startswith(MARKDOWN_SOURCE_PREFIX)), None)
    rows = []
    for chunk in chunk_doc["chunks"]:
        md = markdown_record(chunk)
        meta = {
            "chunk_id": chunk["chunk_id"],
            "document_id": chunk["doc_id"],
            "entity": "pokemon",
            "pokemon_id": record["id"],
            "name_ko": record["name_ko"],
            "name_en": record["name"],
            "section": chunk["section"],
            "heading": heading_of(chunk),
            "game_version": GAME_VERSION,
            "review_status": chunk["review_status"],
            "source_path": markdown_path,
            "line_start": md.get("line_start"),
            "line_end": md.get("line_end"),
            "source_ref_id": f"{chunk_path}#{chunk['chunk_id']}",
            "schema_version": chunk_doc["schema_version"],
            "template_version": chunk_doc.get("template_version", "tpl1"),
            "embed_model": model,
            "index_version": collection,
            "test_only": True,
        }
        for name in type_names:
            meta[f"type_{name}"] = name in record["types_gen1"]
        text = chunk["content"]
        meta["content_hash"] = content_hash(model, text)
        meta["meta_hash"] = meta_hash(meta)
        rows.append({"id": record_id(collection, chunk["chunk_id"]), "text": text, "meta": meta})
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("중복 레코드 id")
    return rows


def classify(rows, stored):
    """stored = {id: (content_hash, meta_hash)} → 증분 sync 분류."""
    new_ids = {r["id"] for r in rows}
    to_embed = [r for r in rows if r["id"] not in stored or stored[r["id"]][0] != r["meta"]["content_hash"]]
    meta_only = [r for r in rows if r["id"] in stored and stored[r["id"]][0] == r["meta"]["content_hash"]
                 and stored[r["id"]][1] != r["meta"]["meta_hash"]]
    unchanged = [r for r in rows if r["id"] in stored
                 and stored[r["id"]] == (r["meta"]["content_hash"], r["meta"]["meta_hash"])]
    deleted = sorted(set(stored) - new_ids)
    return {"embed": to_embed, "meta_only": meta_only, "unchanged": unchanged, "delete": deleted}


def load_queries(path):
    """질의 파일에서 qid·query만 꺼낸다. 다른 필드(기대 정답 등)는 돌려주지 않는다."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    items = doc["queries"] if isinstance(doc, dict) else doc
    queries = [{"qid": item["qid"], "query": item["query"]} for item in items]
    qids = [q["qid"] for q in queries]
    if len(qids) != len(set(qids)):
        raise ValueError("중복 qid")
    return queries


def hit_record(rank, meta, distance):
    return {"rank": rank, "chunk_id": meta.get("chunk_id"), "section": meta.get("section"),
            "heading": meta.get("heading"), "distance": round(float(distance), 6)}


def api_error(exc):
    """키·메시지를 노출하지 않고 오류 종류만."""
    return {"type": type(exc).__name__, "status_code": getattr(exc, "status_code", None)}


def run_queries(queries, search_fn, k):
    """질의마다 search_fn(query, k) → [(meta, distance)]. 재시도·선별 없이 오류는 오류로 기록한다."""
    results = []
    for item in queries:
        t0 = time.perf_counter()
        try:
            hits = search_fn(item["query"], k)
            error = None
        except Exception as exc:  # noqa: BLE001
            hits, error = [], api_error(exc)
        seconds = round(time.perf_counter() - t0, 3)
        results.append({"qid": item["qid"], "query": item["query"], "seconds": seconds, "error": error,
                        "n_results": len(hits),
                        "results": [hit_record(i + 1, meta, dist) for i, (meta, dist) in enumerate(hits)]})
    return results


def run_document(*, collection, model, k, query_file, chunk_file, started_at, results, api, collection_rows):
    """질의 파일 실행 결과 문서 (원본 결과만)."""
    return {
        "kind": "pilot_vector_search_raw",
        "collection": collection,
        "embed_model": model,
        "k": k,
        "filter": None,
        "distance": "cosine (pgvector <=>)",
        "query_file": {"path": query_file["path"], "sha256": query_file["sha256"]},
        "chunk_file": {"path": chunk_file["path"], "sha256": chunk_file["sha256"]},
        "collection_rows": collection_rows,
        "started_at_utc": started_at,
        "manifest_run_id": "none",
        "scoring": None,
        "note": RUN_NOTE,
        "n_queries": len(results),
        "n_errors": sum(1 for r in results if r["error"]),
        "api": api,
        "results": results,
    }


def rel(path):
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# ------------------------------------------------------------------ 환경·DB·API


def env(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"환경 변수 {name} 없음")
    return value


def psycopg_url():
    """SQLAlchemy 형식(`<scheme>+psycopg://`)의 드라이버 표기를 빼 psycopg가 읽는 형식으로 바꾼다."""
    scheme, sep, rest = env("DATABASE_URL").partition("://")
    return scheme.split("+", 1)[0] + sep + rest


def connect():
    import psycopg
    return psycopg.connect(psycopg_url())


def make_embeddings(model):
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model=model, max_retries=0)


def count_api(model, texts, chunk_size):
    import tiktoken
    enc = tiktoken.encoding_for_model(model)
    STATS["embed_requests"] += math.ceil(len(texts) / (chunk_size or 1000))
    STATS["embed_texts"] += len(texts)
    STATS["embed_tokens_estimate"] += sum(len(enc.encode(t)) for t in texts)


def embed_texts(embeddings, texts):
    count_api(embeddings.model, texts, embeddings.chunk_size)
    return embeddings.embed_documents(texts)


def api_stats():
    return dict(STATS, token_count_method="tiktoken encoding_for_model 추정")


def vector_literal(vec):
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def collection_counts(conn):
    if not conn.execute("select to_regclass('public.langchain_pg_embedding')").fetchone()[0]:
        return {"__tables_exist__": False, "__total__": 0}
    rows = conn.execute(
        "select c.name, count(e.id) from langchain_pg_collection c left join langchain_pg_embedding e"
        " on e.collection_id = c.uuid group by c.name order by c.name").fetchall()
    out = {name: n for name, n in rows}
    out["__total__"] = conn.execute("select count(*) from langchain_pg_embedding").fetchone()[0]
    return out


def collection_uuid(conn, collection):
    row = conn.execute("select uuid from langchain_pg_collection where name = %s", (collection,)).fetchone()
    return row[0] if row else None


def stored_hashes(conn, collection):
    return {i: (m.get("content_hash"), m.get("meta_hash")) for i, m in conn.execute(
        "select e.id, e.cmetadata from langchain_pg_embedding e join langchain_pg_collection c"
        " on e.collection_id = c.uuid where c.name = %s", (collection,)).fetchall()}


def load_rows(chunk_path, collection, model):
    chunk_doc = json.loads(Path(chunk_path).read_text(encoding="utf-8"))
    pokemon = json.loads((ROOT / "data/processed/pokemon.json").read_text(encoding="utf-8"))
    types = [t["name"] for t in json.loads((ROOT / "data/processed/types.json").read_text(encoding="utf-8"))]
    return build_rows(chunk_doc, rel(chunk_path), collection, model, pokemon, types)


def sync(chunk_path, collection, model):
    from langchain_postgres import PGVector
    from langchain_postgres.vectorstores import DistanceStrategy

    chunk_doc = json.loads(Path(chunk_path).read_text(encoding="utf-8"))
    with connect() as conn:
        stored_versions = {(m.get("schema_version"), m.get("template_version")) for (m,) in conn.execute(
            "select e.cmetadata from langchain_pg_embedding e join langchain_pg_collection c"
            " on e.collection_id = c.uuid where c.name = %s", (collection,)).fetchall()}
    check_sync_compatibility(collection, chunk_doc, stored_versions)  # API·쓰기 전에 멈춘다
    rows = load_rows(chunk_path, collection, model)
    log = {"collection": collection, "embed_model": model, "chunk_file": {"path": rel(chunk_path),
           "sha256": sha256_file(chunk_path)}, "n_chunks": len(rows), "timing_s": {}}
    embeddings = make_embeddings(model)
    with connect() as conn:
        log["counts_before"] = collection_counts(conn)
    # 테이블·컬렉션 행 생성 (없을 때만). test- 컬렉션에만 도달한다.
    PGVector(embeddings=embeddings, collection_name=collection, connection=env("DATABASE_URL"), use_jsonb=True,
             distance_strategy=DistanceStrategy.COSINE)
    with connect() as conn:
        uuid = collection_uuid(conn, collection)
        clash = conn.execute("select id from langchain_pg_embedding where id = any(%s) and collection_id <> %s",
                             ([r["id"] for r in rows], uuid)).fetchall()
        if clash:
            raise SystemExit(f"다른 컬렉션에 같은 id가 있다 — 중단: {[c[0] for c in clash]}")
        plan = classify(rows, stored_hashes(conn, collection))
        vectors = []
        if plan["embed"]:
            t0 = time.perf_counter()
            vectors = embed_texts(embeddings, [r["text"] for r in plan["embed"]])
            log["timing_s"]["embed_documents"] = round(time.perf_counter() - t0, 3)
            log["embedding_dim"] = len(vectors[0])
        with conn.transaction():
            for r, vec in zip(plan["embed"], vectors):
                cur = conn.execute(
                    "insert into langchain_pg_embedding (id, collection_id, embedding, document, cmetadata)"
                    " values (%s, %s, %s::vector, %s, %s::jsonb)"
                    " on conflict (id) do update set embedding = excluded.embedding, document = excluded.document,"
                    " cmetadata = excluded.cmetadata where langchain_pg_embedding.collection_id = excluded.collection_id",
                    (r["id"], uuid, vector_literal(vec), r["text"], json.dumps(r["meta"], ensure_ascii=False)))
                if cur.rowcount != 1:
                    raise RuntimeError(f"upsert 실패(다른 컬렉션 id?): {r['id']}")
            for r in plan["meta_only"]:
                conn.execute("update langchain_pg_embedding set cmetadata = %s::jsonb where id = %s and collection_id = %s",
                             (json.dumps(r["meta"], ensure_ascii=False), r["id"], uuid))
            if plan["delete"]:
                conn.execute("delete from langchain_pg_embedding where id = any(%s) and collection_id = %s",
                             (plan["delete"], uuid))
        log["sync"] = {"embedded": len(plan["embed"]), "meta_only": len(plan["meta_only"]),
                       "deleted": len(plan["delete"]), "unchanged": len(plan["unchanged"])}
        log["counts_after"] = collection_counts(conn)
    log["api"] = api_stats()
    return log


def sql_search(conn, collection, vector, k):
    rows = conn.execute(
        "select e.cmetadata, e.embedding <=> %s::vector as distance from langchain_pg_embedding e"
        " join langchain_pg_collection c on e.collection_id = c.uuid where c.name = %s"
        " order by distance, e.id limit %s", (vector_literal(vector), collection, k)).fetchall()
    return [(meta, dist) for meta, dist in rows]


def make_search_fn(conn, collection, embeddings):
    def search(query, k):
        vector = embed_texts(embeddings, [query])[0]  # 질의 본문 그대로 (접두어 없음)
        return sql_search(conn, collection, vector, k)
    return search


def require_collection(conn, collection):
    if collection_uuid(conn, collection) is None:
        raise SystemExit(f"컬렉션 없음: {collection}")


def verify(collection, chunk_path=None, model=None):
    with connect() as conn:
        rows = conn.execute(
            "select e.id, vector_dims(e.embedding), e.cmetadata, e.document from langchain_pg_embedding e"
            " join langchain_pg_collection c on e.collection_id = c.uuid where c.name = %s order by e.id",
            (collection,)).fetchall()
        counts = collection_counts(conn)
    report = {"collection": collection, "count": len(rows), "vector_dims": sorted({d for _, d, _, _ in rows}),
              "default_collection_rows": counts.get(DEFAULT_COLLECTION, 0), "counts_all": counts,
              "records": [{"id": i, "chunk_id": m.get("chunk_id"), "section": m.get("section"),
                           "heading": m.get("heading"), "content_hash": m.get("content_hash"),
                           "content_hash_recomputed_ok": m.get("content_hash") == content_hash(m.get("embed_model", ""), doc)}
                          for i, _, m, doc in rows]}
    checks = {"content_hash_matches_document": all(r["content_hash_recomputed_ok"] for r in report["records"]),
              "default_collection_empty": report["default_collection_rows"] == 0}
    if chunk_path:
        expected = load_rows(chunk_path, collection, model)
        got = {r["id"]: r["content_hash"] for r in report["records"]}
        want = {r["id"]: r["meta"]["content_hash"] for r in expected}
        checks.update({"count_equals_chunks": len(rows) == len(expected), "missing_ids": sorted(set(want) - set(got)),
                       "extra_ids": sorted(set(got) - set(want)),
                       "content_hash_equals_chunk_file": all(got.get(i) == h for i, h in want.items())})
        checks["ok"] = (checks["count_equals_chunks"] and not checks["missing_ids"] and not checks["extra_ids"]
                        and checks["content_hash_equals_chunk_file"] and checks["content_hash_matches_document"]
                        and checks["default_collection_empty"])
    report["checks"] = checks
    return report


def drop(collection):
    with connect() as conn:
        before = collection_counts(conn)
        with conn.transaction():
            n = conn.execute("delete from langchain_pg_embedding where collection_id in (select uuid from"
                             " langchain_pg_collection where name = %s)", (collection,)).rowcount
            conn.execute("delete from langchain_pg_collection where name = %s", (collection,))
        return {"dropped": collection, "rows_deleted": n, "before": before, "after": collection_counts(conn)}


def write_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="파일럿 청크 테스트 컬렉션 sync·검색·검증 (vectordb 스킬)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sync", action="store_true", help="--chunks를 --collection에 증분 sync")
    mode.add_argument("--query", help="질의 하나를 검색한다")
    mode.add_argument("--queries", type=Path, help="질의 파일의 모든 질의를 검색해 원본 결과를 --out에 저장한다")
    mode.add_argument("--verify", action="store_true", help="SQL 검증 (API 호출 없음)")
    mode.add_argument("--drop", action="store_true", help="테스트 컬렉션 삭제 (--yes 필요)")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--chunks", type=Path, help="청크 JSON (sync 필수, queries 필수: 출처 기록용)")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--out", type=Path, help="결과·로그 JSON 경로")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.sync or args.drop:
            check_writable_collection(args.collection)
    except GuardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.drop and not args.yes:
        print("error: --drop은 --yes와 함께 실행한다", file=sys.stderr)
        return 2
    if (args.sync or args.queries) and not args.chunks:
        print("error: --chunks가 필요하다", file=sys.stderr)
        return 2
    if args.queries and not args.out:
        print("error: --queries는 --out이 필요하다", file=sys.stderr)
        return 2

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if args.sync or args.drop:
        try:
            check_writable_collection(args.collection, os.environ.get("PGVECTOR_COLLECTION"))
        except GuardError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if args.drop:
        print(json.dumps(drop(args.collection), ensure_ascii=False, indent=1))
        return 0
    model = env("OPENAI_EMBEDDING_MODEL")
    if args.verify:
        report = verify(args.collection, args.chunks, model)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["checks"].get("ok", True) else 1
    if args.sync:
        started = datetime.now(timezone.utc).isoformat()
        try:
            log = sync(args.chunks, args.collection, model)
            status = "done"
        except GuardError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:  # noqa: BLE001
            log, status = {"collection": args.collection, "error": api_error(exc), "api": api_stats()}, "blocked"
        log.update({"started_at_utc": started, "status": status, "manifest_run_id": "none"})
        if args.out:
            write_json(args.out, log)
        print(json.dumps({k: log.get(k) for k in ("status", "collection", "sync", "api", "error", "counts_before",
                                                     "counts_after")}, ensure_ascii=False, indent=1))
        return 0 if status == "done" else 3

    embeddings = make_embeddings(model)
    with connect() as conn:
        require_collection(conn, args.collection)
        search = make_search_fn(conn, args.collection, embeddings)
        if args.query:
            [result] = run_queries([{"qid": None, "query": args.query}], search, args.k)
            output = {"collection": args.collection, "embed_model": model, "k": args.k, **result}
            print(json.dumps(output, ensure_ascii=False, indent=1))
            return 0 if result["error"] is None else 3
        started = datetime.now(timezone.utc).isoformat()
        rows = collection_counts(conn).get(args.collection, 0)
        results = run_queries(load_queries(args.queries), search, args.k)
    document = run_document(collection=args.collection, model=model, k=args.k,
                            query_file={"path": rel(args.queries), "sha256": sha256_file(args.queries)},
                            chunk_file={"path": rel(args.chunks), "sha256": sha256_file(args.chunks)},
                            started_at=started, results=results, api=api_stats(), collection_rows=rows)
    write_json(args.out, document)
    print(json.dumps({"out": str(args.out), "n_queries": document["n_queries"], "n_errors": document["n_errors"],
                      "api": document["api"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
