"""Incrementally insert/update Solar chunks without deleting absent chunks.

Only --approve-cost permits paid Upstage calls. Costs depend on provider pricing
and token usage and are unknown here; check pricing and approve each run first.
No auto-retry: a failed request may still be billed; reconcile before retrying.
The 3800-byte limit is conservative, not proof against tokenizer truncation.
"""
import argparse
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path
if __package__:
    from . import store
else:
    import store

ENDPOINT = 'https://api.upstage.ai/v1/embeddings'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirect refused')


def model_settings(env):
    doc, query = env.get('UPSTAGE_EMBEDDING_MODEL', ''), env.get('UPSTAGE_QUERY_MODEL', '')
    if not doc or not query or doc == query or any(x != x.strip() or any(ord(c) < 32 or ord(c) == 127 for c in x) for x in (doc, query)):
        raise ValueError('document and query models required and must differ')
    return doc, query


def records_from(path):
    records = [store.loads(line) for line in Path(path).read_bytes().splitlines() if line.strip()]
    ids = set()
    for row in records:
        store.validate_record(row)
        if row['chunk_id'] in ids:
            raise ValueError('duplicate input id')
        ids.add(row['chunk_id'])
    if not records:
        raise ValueError('no records')
    return records


def snapshot(cur):
    config = cur.execute('SELECT id,config FROM solar_handoff.index_info').fetchall()
    rows = cur.execute('SELECT c.chunk_id,c.metadata,public.vector_send(v.embedding),c.document_id,c.content FROM solar_handoff.chunks c LEFT JOIN solar_handoff.vectors v USING(chunk_id)').fetchall()
    counts = cur.execute('SELECT (SELECT count(*) FROM solar_handoff.chunks),(SELECT count(*) FROM solar_handoff.vectors)').fetchone()
    if (len(config) > 1 or (config and config[0][0] != 'solar') or counts != (len(rows), len(rows))
            or any(row[2] is None or not isinstance(row[1], dict)
                   or row[1].get('chunk_id') != row[0] or row[1].get('document_id') != row[3]
                   or row[1].get('content') != row[4] for row in rows)):
        raise ValueError('inconsistent target')
    return (config[0][1] if config else None), {row[0]: (row[1], bytes(row[2])) for row in rows}


def plan(records, current):
    return [r for r in records if r['chunk_id'] not in current or current[r['chunk_id']][0].get('content') != r['content']]


def truncated(value):
    if isinstance(value, dict):
        return any((str(k).lower() in ('truncated', 'truncation') and v is not False and v is not None) or
                   (str(k).lower() == 'finish_reason' and v == 'length') or truncated(v) for k, v in value.items())
    return isinstance(value, list) and any(truncated(v) for v in value)


def embed(model, key, rows):
    texts = [r['content'] for r in rows]
    if not 1 <= len(rows) <= 4 or any(len(t.encode('utf-8')) > 3800 for t in texts):
        raise ValueError('conservative byte or batch limit exceeded')
    body = store.canonical({'model': model, 'input': texts})
    request = urllib.request.Request(ENDPOINT, data=body, method='POST', headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=120) as response:
        raw = response.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError('response too large')
    result = store.loads(raw)
    if not isinstance(result, dict) or result.get('model') != model or truncated(result):
        raise ValueError('invalid response')
    data = result.get('data')
    if not isinstance(data, list) or len(data) != len(rows):
        raise ValueError('invalid response count')
    vectors = [None] * len(rows)
    for item in data:
        if not isinstance(item, dict):
            raise ValueError('invalid response item')
        index = item.get('index')
        if type(index) is not int or not 0 <= index < len(rows) or vectors[index] is not None:
            raise ValueError('invalid response index')
        vectors[index] = store.encoded_vector(item.get('embedding', []))
    return vectors


def ingest(conn, records, doc, query, key, approved=False, embedder=embed,
           confirmed_name=None, allow_remote=False):
    identity = None
    if approved:
        if conn.info.transaction_status != 0:  # libpq PQTRANS_IDLE
            raise ValueError('ingest requires an idle connection')
        identity = store.check_target(conn, confirmed_name, allow_remote)
        if not identity[1] or not identity[2]:
            raise ValueError('ingest requires a verifiable TCP target address')
    with conn.cursor() as cur:
        config, current = snapshot(cur)
    conn.rollback()
    if config is not None and (config.get('document_model') != doc or config.get('query_model') != query or config.get('dimension') != 1024):
        raise ValueError('model mismatch: build a separate index')
    if config is None and current:
        raise ValueError('missing index metadata')
    needed = plan(records, current)
    if not approved:
        return {'inputs': len(records), 'api_inputs': len(needed), 'api_calls': (len(needed) + 3) // 4}
    if identity is None:
        raise ValueError('target identity unavailable')
    if needed and not key:
        raise ValueError('UPSTAGE_API_KEY required')
    if key and (key in doc or key in query or any(key in store.canonical(r).decode('utf-8') for r in records)):
        raise ValueError('credential appears in inputs')
    vectors = {}
    for i in range(0, len(needed), 4):
        batch = needed[i:i+4]
        result = embedder(doc, key, batch)
        if len(result) != len(batch):
            raise ValueError('invalid embedding count')
        for row, vector in zip(batch, result):
            store.binary_to_values(vector)
            vectors[row['chunk_id']] = vector
    new_config = config or {'provider': 'upstage', 'dimension': 1024, 'document_model': doc, 'query_model': query,
                            'settings': {'input': 'raw', 'tokenizer_parity': 'unverified', 'source_truncation': 'unproven'}}
    expected = {r['chunk_id']: (r, base64.b64decode(vectors[r['chunk_id']]) if r['chunk_id'] in vectors else current[r['chunk_id']][1]) for r in records}
    # A savepoint is not a commit: require an outermost transaction.
    if conn.info.transaction_status != 0:  # libpq PQTRANS_IDLE
        raise ValueError('ingest requires an idle connection')
    ready_to_commit = False
    try:
        with conn.transaction():
            if store.check_target(conn, confirmed_name, allow_remote) != identity:
                raise ValueError('target changed before write')
            with conn.cursor() as cur:
                cur.execute('LOCK TABLE solar_handoff.chunks, solar_handoff.vectors, solar_handoff.index_info IN ACCESS EXCLUSIVE MODE')
                now_config, now_current = snapshot(cur)
                if now_config != config or now_current != current:
                    raise ValueError('target changed during embedding; no rows written')
                if config is None:
                    cur.execute('INSERT INTO solar_handoff.index_info(id,config) VALUES (%s,%s::jsonb)', ('solar', store.canonical(new_config).decode()))
                for row in records:
                    cur.execute('INSERT INTO solar_handoff.chunks(chunk_id,document_id,content,metadata) VALUES (%s,%s,%s,%s::jsonb) ON CONFLICT (chunk_id) DO UPDATE SET document_id=EXCLUDED.document_id,content=EXCLUDED.content,metadata=EXCLUDED.metadata', (row['chunk_id'], row['document_id'], row['content'], store.canonical(row).decode()))
                    if row['chunk_id'] in vectors:
                        cur.execute('INSERT INTO solar_handoff.vectors(chunk_id,embedding) VALUES (%s,%s::public.vector) ON CONFLICT (chunk_id) DO UPDATE SET embedding=EXCLUDED.embedding', (row['chunk_id'], store.vector_text(vectors[row['chunk_id']])))
                verify_ingest(cur, records, expected, doc, query)
                verified_config, verified_rows = snapshot(cur)
                all_expected = dict(current)
                all_expected.update(expected)
                if verified_config != new_config or verified_rows != all_expected:
                    raise ValueError('transaction readback mismatch')
            ready_to_commit = True
    except Exception as exc:
        if ready_to_commit:
            raise store.CommitOutcomeUnknown('commit outcome unknown') from exc
        raise
    return {'inputs': len(records), 'embedded': len(needed), 'metadata_or_unchanged': len(records) - len(needed)}, expected, identity


def verify_ingest(cur, records, expected, doc, query):
    config, actual = snapshot(cur)
    if config is None or config.get('document_model') != doc or config.get('query_model') != query or config.get('dimension') != 1024:
        raise ValueError('readback model mismatch')
    for record in records:
        if actual.get(record['chunk_id']) != expected[record['chunk_id']]:
            raise ValueError('readback row mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chunks', required=True, help='JSONL complete chunk records')
    parser.add_argument('--approve-cost', action='store_true', help='authorize paid API calls for this run; otherwise dry-run')
    parser.add_argument('--confirm-input-approved', action='store_true', help='confirm that this exact input is approved for indexing')
    parser.add_argument('--confirm-target', help='exact target database name, required for writes')
    parser.add_argument('--allow-remote-target', action='store_true')
    args = parser.parse_args()
    if args.approve_cost and (not args.confirm_input_approved or not args.confirm_target):
        parser.error('writes require --confirm-input-approved and --confirm-target')
    committed = False
    commit_unknown = False
    try:
        doc, query = model_settings(os.environ)
        rows = records_from(args.chunks)
        with store.connect() as conn:
            try:
                outcome = ingest(conn, rows, doc, query, os.environ.get('UPSTAGE_API_KEY', ''), args.approve_cost,
                                 confirmed_name=args.confirm_target, allow_remote=args.allow_remote_target)
            except store.CommitOutcomeUnknown:
                commit_unknown = True
                raise
            committed = args.approve_cost
        if args.approve_cost:
            report, expected, identity = outcome
            with store.connect() as conn:
                if store.check_target(conn, args.confirm_target, args.allow_remote_target) != identity:
                    raise ValueError('readback target differs from ingest target')
                with conn.cursor() as cur:
                    verify_ingest(cur, rows, expected, doc, query)
        else:
            report = outcome
        print(json.dumps(report))
        return 0
    except Exception:
        if committed:
            print('committed_readback_unknown: do not retry automatically; inspect the target', file=sys.stderr)
        elif commit_unknown:
            print('commit_unknown: do not retry automatically; inspect the target database state; any sent request may have been billed', file=sys.stderr)
        else:
            print('operation failed before commit; do not retry automatically; any sent request may have been billed; investigate before retry; details suppressed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
