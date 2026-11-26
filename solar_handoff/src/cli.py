"""One-question Solar retrieval CLI; JSON output is a trace, not an evaluation."""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from . import citations, providers, retrieval

CONFIG = Path(__file__).resolve().parents[1] / 'config' / 'retrieval.json'
EXPECTED_CONFIG = {'candidate_limit':20, 'final_limit':5, 'rrf_k':60, 'bm25_k1':1.2, 'bm25_b':0.75,
                   'tokenization':'NFKC-casefold Korean words and bigrams; ASCII alphanumeric words',
                   'reasoning_effort':'low', 'rewrite_prompt_version':'1', 'rerank_prompt_version':'1', 'answer_prompt_version':'2'}


def secrets(env):
    values = [v for k,v in env.items() if isinstance(v,str) and v and re.search(r'(?:^|_)(?:API_KEY|PASSWORD|PASSWD|SECRET|TOKEN|DATABASE_URL|DB_URL)$', k, re.I)]
    url = env.get('DATABASE_URL')
    if isinstance(url, str):
        try:
            password = urllib.parse.urlsplit(url).password
        except ValueError:
            password = None
        if password:
            # Decode common percent-encoding layers without exposing the URL in errors.
            for _ in range(3):
                values.append(password)
                password = urllib.parse.unquote(password)
            values.append(password)
    # Best effort only: direct and common Base64 forms are not comprehensive
    # declassification or general question/source sensitive-data detection.
    # Splits, alternate encodings and arbitrary transformations can still leak.
    for value in list(values):
        try:
            raw = value.encode('utf8', 'strict')
        except UnicodeError:
            continue
        for encoded in (base64.b64encode(raw), base64.urlsafe_b64encode(raw)):
            text = encoded.decode('ascii')
            if text:
                values.extend((text, text.rstrip('=')))
    return list(dict.fromkeys(v for v in values if v))


def unsafe(value, values):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False)
    variants = {raw}
    for _ in range(3):
        variants |= {urllib.parse.unquote(x) for x in list(variants)}
        variants |= {urllib.parse.unquote_plus(x) for x in list(variants)}
        variants |= {re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1),16)), x.replace('\\/', '/')) for x in list(variants)}
    return any(secret in text or json.dumps(secret,ensure_ascii=True)[1:-1] in text for secret in values for text in variants)


def config():
    obj = providers.json_unique(CONFIG.read_text(encoding='utf8'))
    if obj != EXPECTED_CONFIG:
        raise ValueError('unexpected retrieval config')
    return obj


def execute(question, method, answer_provider, rewrite, env, *, database_factory=retrieval.Database, provider_factory=providers.Providers, qid=None):
    cfg = config()
    trace = {'status':'started', 'qid':qid, 'question':question, 'search_query':None, 'rewrite_status':'off',
             'rewrite_response_status':None, 'rewrite_failure_type':None,
             'config_sha256':hashlib.sha256(json.dumps(cfg,sort_keys=True,separators=(',', ':')).encode()).hexdigest(),
             'config':cfg, 'retrieval':{'method':method,'called':False,'vector':None,'bm25':None,'union':None,'pre_rerank':None,'final':None},
             'embedding':None, 'answer_provider':answer_provider, 'answer':None, 'citations':None,
             'error':None, 'cost':'unknown', 'timings_ms':{}}
    start = time.monotonic()
    stage = 'input'
    try:
        providers.valid_text(question)
        if qid is not None:
            providers.valid_text(qid)
        if method not in ('A','B','C') or answer_provider != 'gpt' or type(rewrite) is not bool or unsafe((question,qid,cfg), secrets(env)):
            raise ValueError('invalid or sensitive input')
        stage = 'database'
        with database_factory(env) as db:
            corpus = db.records
            byid = {r['chunk_id']:r for r in corpus}
            if len(byid) != len(corpus):
                raise ValueError('duplicate corpus')
            p = provider_factory(env)
            for name in ('UPSTAGE_EMBEDDING_MODEL','UPSTAGE_QUERY_MODEL','OPENAI_CHAT_MODEL'):
                value = env.get(name)
                if value and unsafe(value, secrets(env)):
                    raise ValueError('sensitive provider configuration')
            stage = 'provider_preflight'
            p.preflight(method, answer_provider, rewrite)
            stage = 'database'
            infos = db.index_info
            if not isinstance(infos,list) or len(infos) != 1 or infos[0].get('id') != 'solar' or not isinstance(infos[0].get('config'),dict):
                raise ValueError('missing index model binding')
            info = infos[0]['config']
            if info.get('dimension') != 1024 or info.get('document_model') != p.document_model or info.get('query_model') != p.query_model:
                raise ValueError('index model binding mismatch')
            trace['index_info'] = infos
            if unsafe((corpus,infos), secrets(env)):
                raise ValueError('sensitive corpus or config')
            if not corpus:
                trace['status'] = 'no_evidence'
                return trace
            query = question
            if rewrite:
                stage = 'rewrite'
                t = time.monotonic()
                try:
                    query, trace['rewrite_model'] = p.rewrite(question)
                except providers.ProviderResponseError as exc:
                    trace['rewrite_response_status'] = exc.response_status
                    trace['rewrite_failure_type'] = exc.failure_type
                    if exc.meta is not None:
                        trace['rewrite_model'] = exc.meta
                    if exc.response_status != 'completed' or exc.failure_type not in ('refusal', 'invalid_structure'):
                        trace['rewrite_status'] = 'failed'
                        raise
                    query = question
                    trace['rewrite_status'] = 'fallback_original'
                except Exception:
                    trace['rewrite_response_status'] = 'unknown'
                    trace['rewrite_failure_type'] = 'outcome_unknown'
                    trace['rewrite_status'] = 'failed'
                    raise
                finally:
                    trace['timings_ms']['rewrite'] = (time.monotonic()-t)*1000
                if trace['rewrite_status'] != 'fallback_original':
                    trace['rewrite_response_status'] = 'completed'
                    trace['rewrite_status'] = 'rewritten_unreviewed'
                try:
                    providers.valid_text(query)
                    if unsafe(query, secrets(env)):
                        raise ValueError('sensitive rewrite')
                except (ValueError, TypeError, UnicodeError):
                    trace['rewrite_status'] = 'failed'
                    trace['rewrite_failure_type'] = 'invalid_or_sensitive_query'
                    raise
            trace['search_query'] = query
            stage = 'embedding'
            t = time.monotonic()
            vector, trace['embedding'] = p.embed(query)
            retrieval.valid_vector(vector)
            trace['timings_ms']['embedding'] = (time.monotonic()-t)*1000
            stage = 'retrieval'
            t = time.monotonic()
            trace['retrieval']['called'] = True
            vs = db.search(vector)
            if len(vs)>20 or len({r['chunk_id'] for r in vs})!=len(vs) or any(r['rank']!=i or r['chunk_id'] not in byid for i,r in enumerate(vs,1)):
                raise ValueError('invalid vector results')
            bm = retrieval.bm25(corpus, query) if method in ('B','C') else None
            union = retrieval.fuse(bm, vs) if bm is not None else None
            def attach(rows):
                return [dict(byid[r['chunk_id']], **r) for r in rows]
            trace['retrieval'].update(vector=attach(vs), bm25=attach(bm) if bm is not None else None, union=attach(union) if union is not None else None)
            pre = attach((vs if method == 'A' else union)[:5])
            trace['retrieval']['pre_rerank'] = None if method == 'A' else pre
            trace['timings_ms']['retrieval'] = (time.monotonic()-t)*1000
            if method == 'C' and len(pre) != 5:
                raise ValueError('C requires five B candidates')
            if not pre:
                trace['retrieval']['final'] = []
                trace['status'] = 'no_evidence'
                return trace
            final = pre
            if method == 'C':
                stage = 'rerank'
                t = time.monotonic()
                order, trace['rerank_model'] = p.rerank(question, pre)
                if not isinstance(order, list) or len(order)!=5 or any(type(x) is not int for x in order) or set(order)!=set(range(1,6)):
                    raise ValueError('invalid rerank permutation')
                final = [dict(pre[n-1], rerank_rank=i) for i,n in enumerate(order,1)]
                trace['rerank_permutation'] = order
                trace['timings_ms']['rerank'] = (time.monotonic()-t)*1000
            trace['retrieval']['final'] = final
            stage = 'answer'
            t = time.monotonic()
            contexts = [{k:r.get(k) for k in ('chunk_id','content','document_id','source_document','heading','source_lines','source_heading_lines','evidence_path')} for r in final]
            result, trace['answer_model'] = p.answer(answer_provider, question, contexts)
            if not isinstance(result,dict) or set(result) != {'status','answer'} or result['status'] not in ('answer','insufficient_evidence') or not isinstance(result['answer'],str) or not result['answer'].strip():
                raise ValueError('invalid answer result')
            trace['timings_ms']['answer'] = (time.monotonic()-t)*1000
            stage = 'citation_validation'
            check = citations.validate(result['answer'],final)
            trace['citations'] = check
            if check['status'] == 'invalid_citations' or (result['status']=='answer' and check['status']!='ids_valid_claim_support_unreviewed'):
                trace['rejected_answer'] = result['answer']
                raise ValueError('answer citation validation failed')
            trace['answer'] = result['answer']
            trace['status'] = 'no_evidence' if result['status']=='insufficient_evidence' else 'completed'
            stage = 'output_validation'
            if unsafe(trace, secrets(env)):
                raise ValueError('sensitive output')
    except Exception:
        trace['status'] = 'failed'
        trace['error'] = stage
        trace['answer'] = None
    finally:
        trace['timings_ms']['total'] = (time.monotonic()-start)*1000
    # Never emit potentially secret-bearing provider/DB content, even on failure.
    if unsafe(trace, secrets(env)):
        return {'status':'failed','error':'sensitive_output','answer':None}
    return trace


def main(argv=None, *, database_factory=retrieval.Database, provider_factory=providers.Providers, env=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--question', help='question, or read from stdin')
    parser.add_argument('--qid')
    parser.add_argument('--method', choices=('A','B','C'), default='C')
    parser.add_argument('--answer', choices=('gpt',), default='gpt')
    parser.add_argument('--rewrite', action='store_true')
    parser.add_argument('--allow-cost', action='store_true', help='confirm separately approved provider cost and DB access')
    args = parser.parse_args(argv)
    if not args.allow_cost:
        print(json.dumps({'status':'failed','error':'approval_required'}))
        return 2
    question = args.question if args.question is not None else sys.stdin.read(3801)
    try:
        result = execute(question,args.method,args.answer,args.rewrite,dict(os.environ if env is None else env),database_factory=database_factory,provider_factory=provider_factory,qid=args.qid)
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
        return 1 if result['status'] == 'failed' else 0
    except Exception:
        print(json.dumps({'status':'failed','error':'configuration'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
