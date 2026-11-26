"""Read-only Solar corpus and deterministic BM25/RRF retrieval."""
import math
import re
import unicodedata
from collections import Counter

TOKEN = re.compile(r'[가-힣]+|[a-z0-9]+')
SQL_SEARCH = ('SELECT v.chunk_id, v.embedding OPERATOR(public.<=>) %s::public.vector AS distance '
              'FROM solar_handoff.vectors v JOIN solar_handoff.chunks c ON c.chunk_id = v.chunk_id '
              'ORDER BY distance, v.chunk_id LIMIT %s')


def valid_vector(v):
    if not isinstance(v, list) or len(v) != 1024 or any(type(x) not in (int, float) or not math.isfinite(x) for x in v) or not any(v):
        raise ValueError('invalid Solar vector')
    return v


class Database:
    def __init__(self, env):
        self.env = env
        self.conn = None

    def __enter__(self):
        import psycopg
        url = self.env.get('DATABASE_URL')
        if not url:
            raise ValueError('DATABASE_URL required')
        from .store import normalize_database_url
        url = normalize_database_url(url)
        self.conn = psycopg.connect(url, connect_timeout=10, options='-c search_path=pg_catalog')
        try:
            self.cur = self.conn.cursor()
            self.cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            self.cur.execute('SELECT chunk_id, document_id, content, metadata FROM solar_handoff.chunks ORDER BY chunk_id')
            self.records = []
            for cid, doc, text, metadata in self.cur.fetchall():
                if not isinstance(metadata, dict) or any(metadata.get(k) != v for k, v in [('chunk_id', cid), ('document_id', doc), ('content', text)]):
                    raise ValueError('chunk metadata mismatch')
                self.records.append(metadata)
            if len({x['chunk_id'] for x in self.records}) != len(self.records):
                raise ValueError('duplicate chunks')
            self.cur.execute('SELECT chunk_id FROM solar_handoff.vectors ORDER BY chunk_id')
            vector_ids = [r[0] for r in self.cur.fetchall()]
            if vector_ids != [r['chunk_id'] for r in self.records]:
                raise ValueError('vector and chunk coverage mismatch')
            self.cur.execute('SELECT id, config FROM solar_handoff.index_info ORDER BY id')
            self.index_info = [{'id': i, 'config': c} for i, c in self.cur.fetchall()]
            return self
        except BaseException:
            self.conn.close()
            raise

    def __exit__(self, *_):
        try:
            self.conn.rollback()
        finally:
            self.conn.close()

    def search(self, vector):
        valid_vector(vector)
        value = '[' + ','.join(repr(float(x)) for x in vector) + ']'
        self.cur.execute(SQL_SEARCH, (value, 20))
        rows = self.cur.fetchall()
        if len(rows) > 20 or len({x[0] for x in rows}) != len(rows) or any(type(d) not in (int, float) or not math.isfinite(d) for _, d in rows):
            raise ValueError('invalid vector results')
        return [{'chunk_id': cid, 'rank': n, 'distance': float(d)} for n, (cid, d) in enumerate(rows, 1)]


def tokens(text):
    out = []
    for word in TOKEN.findall(unicodedata.normalize('NFKC', text).casefold()):
        out.append(word)
        if len(word) > 1 and all('가' <= c <= '힣' for c in word):
            out.extend(word[i:i+2] for i in range(len(word)-1))
    return out


def bm25(corpus, query, limit=20):
    corpus = sorted(corpus, key=lambda c: c['chunk_id'])
    if not corpus:
        return []
    freqs = [Counter(tokens(c['content'])) for c in corpus]
    lengths = [sum(f.values()) for f in freqs]
    avg = sum(lengths) / len(lengths)
    if not avg:
        raise ValueError('empty corpus text')
    df = Counter(t for f in freqs for t in f)
    rows = []
    for c, f, length in zip(corpus, freqs, lengths):
        score = sum(math.log(1 + (len(corpus)-df[t]+.5)/(df[t]+.5))*f[t]*2.2/(f[t]+1.2*(.25+.75*length/avg)) for t in sorted(set(tokens(query))) if f[t])
        if score > 0:
            rows.append({'chunk_id': c['chunk_id'], 'score': score})
    rows.sort(key=lambda r: (-r['score'], r['chunk_id']))
    return [dict(row, rank=i) for i, row in enumerate(rows[:limit], 1)]


def fuse(*rankings):
    scores = {}
    for rows in rankings:
        seen = set()
        for rank, row in enumerate(rows, 1):
            cid = row['chunk_id']
            if cid in seen or row['rank'] != rank:
                raise ValueError('invalid rank')
            seen.add(cid)
            scores[cid] = scores.get(cid, 0) + 1/(60+rank)
    return [{'chunk_id': cid, 'rank': i, 'rrf_score': score} for i, (cid, score) in enumerate(sorted(scores.items(), key=lambda x: (-x[1], x[0])), 1)]
