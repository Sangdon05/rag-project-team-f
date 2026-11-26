"""Validate actual cited IDs; expose metadata locations as unverified."""
import re
from pathlib import PurePosixPath

BRACKETS = re.compile(r'(\[+)([^\[\]\r\n]*)(\]*)')
ID = re.compile(r'pokemon:[0-9]+#[A-Za-z0-9_-]+\Z')


def ranges(lines):
    if not isinstance(lines, list) or any(type(n) is not int or n < 1 for n in lines) or lines != sorted(set(lines)):
        raise ValueError('invalid source line metadata')
    out = []
    for n in lines:
        if out and n == out[-1][-1] + 1:
            out[-1].append(n)
        else:
            out.append([n])
    return ', '.join(str(x[0]) if len(x) == 1 else f'{x[0]}–{x[-1]}' for x in out)


def location(record):
    try:
        path, heading = record['source_document'], record['heading']
        if not isinstance(path, str) or not path or '\\' in path or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or ':' in path:
            raise ValueError('invalid path')
        if not isinstance(heading, str) or not heading.strip():
            raise ValueError('invalid heading')
        return {'status': 'metadata_only_unverified', 'path': path, 'heading': heading,
                'heading_lines': ranges(record['source_heading_lines']), 'body_lines': ranges(record['source_lines'])}
    except (KeyError, ValueError, TypeError):
        return {'status': 'location_unavailable', 'path': None, 'heading': None, 'heading_lines': None, 'body_lines': None}


def validate(answer, selected, refusal=False):
    mentions, malformed = [], []
    for m in BRACKETS.finditer(answer):
        opening, body, closing = m.groups()
        if not body.lstrip().startswith('pokemon:') and not (len(opening) >= 2 and len(closing) >= 2):
            continue
        if ((len(opening), len(closing)) in ((1, 1), (2, 2)) and ID.fullmatch(body)):
            mentions.append(body)
        else:
            malformed.append(m.group(0))
    allowed = {r['chunk_id']: r for r in selected}
    invalid = sorted(set(mentions) - allowed.keys())
    if invalid or malformed:
        status = 'invalid_citations'
    elif refusal:
        status = 'provider_refusal'
    elif not mentions:
        status = 'missing_citations_unreviewed'
    else:
        status = 'ids_valid_claim_support_unreviewed'
    return {'status': status, 'cited_ids': list(dict.fromkeys(mentions)), 'invalid_ids': invalid,
            'malformed': malformed, 'human_review_required': True,
            'explanation': '인용 ID만 확인했으며 주장의 근거 적합성과 문서 위치는 사람의 검토가 필요합니다. 줄 범위는 불연속 구간을 구분합니다.',
            'sources': [{'chunk_id': cid, **location(allowed[cid])} for cid in dict.fromkeys(mentions) if cid in allowed]}
