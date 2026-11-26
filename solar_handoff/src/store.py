"""Portable bundle validation and transactional team PostgreSQL storage."""
import base64
import hashlib
import json
import math
import os
import struct
from pathlib import Path

DIM = 1024


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate JSON key')
        out[key] = value
    return out


def loads(data):
    return json.loads(data, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def binary_to_values(encoded):
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) != 4100 or raw[:4] != struct.pack('!HH', DIM, 0):
        raise ValueError('invalid vector wire format')
    values = struct.unpack('!1024f', raw[4:])
    if not all(math.isfinite(x) for x in values) or not any(values):
        raise ValueError('invalid vector values')
    return values


def vector_text(encoded):
    return '[' + ','.join(repr(x) for x in binary_to_values(encoded)) + ']'


def encoded_vector(values):
    if len(values) != DIM or any(type(x) not in (int, float) for x in values):
        raise ValueError('invalid vector')
    raw = struct.pack('!HH1024f', DIM, 0, *values)
    encoded = base64.b64encode(raw).decode('ascii')
    binary_to_values(encoded)
    return encoded


def validate_record(row):
    if not isinstance(row, dict):
        raise ValueError('invalid chunk')
    for field in ('chunk_id', 'document_id', 'content'):
        if not isinstance(row.get(field), str) or not row[field] or '\x00' in row[field]:
            raise ValueError('invalid chunk field')
    if 'content_sha256' in row and row['content_sha256'] != hashlib.sha256(row['content'].encode('utf-8')).hexdigest():
        raise ValueError('content hash mismatch')
    canonical(row)


def bundle(config, records):
    payload = {'format': 'solar-handoff-v1', 'config': config, 'records': records}
    validate_payload(payload)
    return dict(payload, sha256=hashlib.sha256(canonical(payload)).hexdigest())


def validate_payload(payload):
    if set(payload) != {'format', 'config', 'records'} or payload['format'] != 'solar-handoff-v1':
        raise ValueError('invalid bundle format')
    config = payload['config']
    if not isinstance(config, dict) or config.get('dimension') != DIM or any(not isinstance(config.get(k), str) or not config[k] for k in ('document_model', 'query_model')):
        raise ValueError('invalid model configuration')
    if not isinstance(payload['records'], list) or not payload['records']:
        raise ValueError('empty bundle')
    seen = set()
    for item in payload['records']:
        if not isinstance(item, dict) or set(item) != {'metadata', 'vector'}:
            raise ValueError('invalid bundle row')
        row = item['metadata']
        validate_record(row)
        if row['chunk_id'] in seen:
            raise ValueError('duplicate chunk id')
        seen.add(row['chunk_id'])
        binary_to_values(item['vector'])


def read_bundle(path):
    obj = loads(Path(path).read_bytes())
    if not isinstance(obj, dict) or set(obj) != {'format', 'config', 'records', 'sha256'}:
        raise ValueError('invalid bundle')
    payload = {k: obj[k] for k in ('format', 'config', 'records')}
    validate_payload(payload)
    if hashlib.sha256(canonical(payload)).hexdigest() != obj['sha256']:
        raise ValueError('bundle digest mismatch')
    return obj


def normalize_database_url(value):
    """Convert only SQLAlchemy's psycopg URL prefix, without parsing its contents."""
    if not isinstance(value, str):
        raise ValueError('unsupported DATABASE_URL scheme')
    prefix = 'postgresql+psycopg://'
    if value.startswith(prefix):
        return 'postgresql://' + value[len(prefix):]
    if value.startswith(('postgresql://', 'postgres://')):
        return value
    raise ValueError('unsupported DATABASE_URL scheme')


def connect():
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise ValueError('DATABASE_URL required')
    url = normalize_database_url(url)
    import psycopg
    return psycopg.connect(url)


def check_target(conn, confirmed_name, allow_remote=False):
    """Require an explicitly named, non-source database before any write."""
    import ipaddress
    # Use the actual connected address, not URI host text which hostaddr or
    # libpq environment variables can override.
    try:
        local = ipaddress.ip_address(conn.info.hostaddr).is_loopback
    except (TypeError, ValueError):
        local = False
    if not local and not allow_remote:
        raise ValueError('non-loopback target requires explicit remote confirmation')
    actual, source_full, source_solar = conn.execute(
        'SELECT current_database(), to_regnamespace(%s), to_regnamespace(%s)',
        ('pokedex_v3a_full_v1', 'pokedex_v3a_solar_v1'),
    ).fetchone()
    if not confirmed_name or confirmed_name != actual or source_full is not None or source_solar is not None:
        raise ValueError('target confirmation failed or source schemas present')
    return actual, conn.info.hostaddr, str(conn.info.port) if conn.info.port is not None else ''


class CommitOutcomeUnknown(RuntimeError):
    """Transaction commit raised; the database outcome must be inspected."""


def init(conn, confirmed_name, allow_remote=False):
    sql = (Path(__file__).resolve().parent.parent / 'db' / 'schema.sql').read_text(encoding='utf-8')
    if conn.info.transaction_status != 0:  # libpq PQTRANS_IDLE
        raise ValueError('init requires an idle connection')
    ready_to_commit = False
    try:
        with conn.transaction():
            identity = check_target(conn, confirmed_name, allow_remote)
            if not identity[1] or not identity[2]:
                raise ValueError('init requires a verifiable TCP target address')
            conn.execute(sql)
            ready_to_commit = True
    except Exception as exc:
        if ready_to_commit:
            raise CommitOutcomeUnknown('commit outcome unknown') from exc
        raise
    return identity


def verify_init(conn):
    objects = conn.execute(
        'SELECT to_regnamespace(%s), to_regclass(%s), to_regclass(%s), to_regclass(%s)',
        ('solar_handoff', 'solar_handoff.chunks', 'solar_handoff.vectors', 'solar_handoff.index_info'),
    ).fetchone()
    if objects is None or len(objects) != 4 or any(obj is None for obj in objects):
        raise ValueError('schema readback missing expected objects')


def verify(cur, obj):
    config_rows = cur.execute('SELECT id, config FROM solar_handoff.index_info').fetchall()
    if config_rows != [('solar', obj['config'])]:
        raise ValueError('readback config mismatch')
    rows = cur.execute('SELECT c.chunk_id,c.document_id,c.content,c.metadata,public.vector_send(v.embedding) FROM solar_handoff.chunks c JOIN solar_handoff.vectors v USING (chunk_id)').fetchall()
    counts = cur.execute('SELECT (SELECT count(*) FROM solar_handoff.chunks), (SELECT count(*) FROM solar_handoff.vectors)').fetchone()
    if counts != (len(obj['records']), len(obj['records'])) or len(rows) != len(obj['records']):
        raise ValueError('readback row count mismatch')
    actual = {r[0]: (r[1], r[2], r[3], bytes(r[4])) for r in rows}
    for item in obj['records']:
        r = item['metadata']
        if actual.get(r['chunk_id']) != (r['document_id'], r['content'], r, base64.b64decode(item['vector'], validate=True)):
            raise ValueError('readback mismatch')


def restore(conn, obj, confirmed_name, allow_remote=False):
    validate_payload({k: obj[k] for k in ('format', 'config', 'records')})
    # A nested transaction could release a savepoint without committing.
    if conn.info.transaction_status != 0:  # libpq PQTRANS_IDLE
        raise ValueError('restore requires an idle connection')
    ready_to_commit = False
    try:
        with conn.transaction():
            identity = check_target(conn, confirmed_name, allow_remote)
            if not identity[1] or not identity[2]:
                raise ValueError('restore requires a verifiable TCP target address')
            with conn.cursor() as cur:
                cur.execute('LOCK TABLE solar_handoff.chunks, solar_handoff.vectors, solar_handoff.index_info IN ACCESS EXCLUSIVE MODE')
                if cur.execute('SELECT EXISTS(SELECT 1 FROM solar_handoff.chunks) OR EXISTS(SELECT 1 FROM solar_handoff.vectors) OR EXISTS(SELECT 1 FROM solar_handoff.index_info)').fetchone()[0]:
                    raise ValueError('restore requires empty target tables')
                cur.execute('INSERT INTO solar_handoff.index_info(id,config) VALUES (%s,%s::jsonb)', ('solar', canonical(obj['config']).decode()))
                for item in obj['records']:
                    r = item['metadata']
                    cur.execute('INSERT INTO solar_handoff.chunks(chunk_id,document_id,content,metadata) VALUES (%s,%s,%s,%s::jsonb)', (r['chunk_id'], r['document_id'], r['content'], canonical(r).decode()))
                    cur.execute('INSERT INTO solar_handoff.vectors(chunk_id,embedding) VALUES (%s,%s::public.vector)', (r['chunk_id'], vector_text(item['vector'])))
                verify(cur, obj)
            ready_to_commit = True
    except Exception as exc:
        if ready_to_commit:
            raise CommitOutcomeUnknown('commit outcome unknown') from exc
        raise
    return identity
