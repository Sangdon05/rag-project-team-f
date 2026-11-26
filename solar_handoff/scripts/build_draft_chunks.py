"""Build an offline, ineligible A-boundary draft; never embeds or indexes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONFIG = {'schema': 'draft-a-v1', 'boundary': 'exact-heading-A', 'version_group': 'red-blue',
          'games': ['red', 'blue'], 'parent_body': 'first-child', 'review_status': 'pending',
          'index_eligible': False, 'evidence_mapping': 'section-and-transitive-dependencies-not-row-pairs'}
SECTIONS = {'profile': ['profile_and_stats'], 'stats': ['profile_and_stats'],
            'evolution': ['evolution'], 'learnset_level': ['learnset'],
            'learnset_machine': ['learnset', 'machine'], 'machine_acquisition': ['machine_acquisition'],
            'stab': ['stab_example'], 'attack_matchup': ['attack'], 'defense_matchup': ['defense'],
            'encounter': ['encounter']}
# 002 is pinned legacy evidence with different labels and no dependency graph.
# The evolution record contains the full target pokemon record used by profile/stats.
LEGACY = {'profile': ['evolution', 'type_calculations'], 'stats': ['evolution'],
          'evolution': ['evolution'], 'learnset_level': ['evolution', 'learnset', 'learnset_and_stab', 'type_calculations'],
          'learnset_machine': ['evolution', 'learnset', 'learnset_and_stab', 'machine', 'type_calculations'],
          'machine_acquisition': ['evolution', 'learnset', 'learnset_and_stab', 'machine', 'machine_acquisition'],
          'stab': ['evolution', 'learnset', 'learnset_and_stab', 'calculation', 'type_calculations'],
          'attack_matchup': ['evolution', 'attack', 'type_calculations', 'calculation', 'learnset_and_stab'],
          'defense_matchup': ['evolution', 'defense', 'type_calculations', 'defense_probe'],
          'encounter': ['evolution', 'encounter']}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def safe(root, rel):
    if not isinstance(rel, str) or not rel or '\\' in rel or ':' in rel or '\0' in rel or any(x in ('', '.', '..') for x in rel.split('/')):
        raise ValueError('unsafe path')
    p = root
    for part in rel.split('/'):
        p = p / part
        info = p.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('linked path: ' + rel)
    if not p.resolve().is_relative_to(root.resolve()):
        raise ValueError('path escapes root')
    return p


def specs(name, machine):
    last = name.rstrip('♀♂')[-1]
    particle = '과' if 0xAC00 <= ord(last) <= 0xD7A3 and (ord(last)-0xAC00) % 28 else '와'
    return [('# '+name, 'profile'), ('## 어떤 포켓몬인가요?', None), ('## 종족치', 'stats'),
            ('## 진화', 'evolution'), ('## 기술', None), ('### 레벨업으로 배우는 기술', 'learnset_level'),
            ('### 기술머신·비전머신으로 배우는 기술', 'learnset_machine'),
            *([('### 머신은 어디서 얻나요?', 'machine_acquisition')] if machine else []),
            ('## 타입 · 상성', None), ('### 자속 보정 (같은 타입 기술 1.5배)', 'stab'),
            (f'### 공격 상성 ({name}{particle} 같은 타입 기술이 잘 통하는 타입)', 'attack_matchup'),
            ('### 방어 상성 (약점과 저항)', 'defense_matchup'), ('## 획득처', 'encounter')]


def parse_document(raw, pid, name, machine):
    lines = raw.decode('utf-8').splitlines()
    if not lines or lines[0].strip() != '# '+name or sum(x.strip() == f'- **도감번호:** {pid:03d}' for x in lines) != 1 or sum(x.strip() == '영문 Pokémon Red·Blue 기준' for x in lines) != 1:
        raise ValueError('invalid title, number or version')
    headings, fence = [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith('```'):
            fence = not fence
        elif not fence and line.strip().startswith('#'):
            headings.append((i, line.strip()))
    expected = specs(name, machine)
    if fence or [h for _, h in headings] != [h for h, _ in expected]:
        raise ValueError('unknown, missing, duplicate or reordered heading')
    result = [{'section': s, 'heading': '기본 정보' if s == 'profile' else h.lstrip('#').strip(),
               'body': [], 'heading_lines': []} for h, s in expected if s]
    by = {s['section']: s for s in result}
    for j, ((start, h), (_, section)) in enumerate(zip(headings, expected)):
        target = section or ('profile' if h == '## 어떤 포켓몬인가요?' else expected[j+1][1])
        end = headings[j+1][0] if j+1 < len(headings) else len(lines)
        by[target]['heading_lines'].append(start+1)
        by[target]['body'].extend((i+1, lines[i]) for i in range(start+1, end))
    covered = [n for s in result for n, _ in s['body']] + [n for s in result for n in s['heading_lines']]
    if sorted(covered) != list(range(1, len(lines)+1)):
        raise ValueError('line partition failure')
    return result


def content(name, heading, body):
    out = []
    for _, line in body:
        if not line.strip() and (not out or not out[-1].strip()):
            continue
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return f'{name} — {heading}\n\n' + '\n'.join(out)


def evidence_map(e, pid, section):
    if pid == 1:
        pilot = e['historical_pilot']['data']['chunks']
        section_to_index = {c['section']: i for i, c in enumerate(pilot)}
        deps = e['section_dependencies']
        tags = {section}; pending = [section]
        while pending:
            for dep in deps.get(pending.pop(), []):
                if dep not in tags:
                    tags.add(dep); pending.append(dep)
        indexes = sorted(section_to_index[t] for t in tags)
        if any(not pilot[i]['source_records'] for i in indexes):
            raise ValueError('empty historical evidence')
        return {'format': 'historical-pilot-001', 'sections': sorted(tags),
                'chunk_indexes': indexes, 'pointer_base': '/historical_pilot/data/chunks',
                'records_pointer_key': 'source_records'}
    if pid == 2:
        tags = set(LEGACY[section]); refs = e['references']
        if set(r['section'] for r in refs) != set().union(*(set(v) for v in LEGACY.values())):
            raise ValueError('unexpected legacy tags')
    else:
        tags = set(SECTIONS[section])
        # Existing references carry Korean type names under this tag. Add it as
        # a dependency, not a direct section, so missing direct evidence still fails.
        if section in ('profile', 'learnset_level', 'learnset_machine'):
            tags.add('type_calculations')
        pending = list(tags)
        while pending:
            for dep in e['section_dependencies'][pending.pop()]:
                if dep not in tags:
                    tags.add(dep); pending.append(dep)
        refs = e['references']
    indexes = [i for i, r in enumerate(refs) if r['section'] in tags]
    direct = any(refs[i]['section'] in (LEGACY[section] if pid == 2 else SECTIONS[section]) for i in indexes)
    # A dragon-only species can have no regular-damage probe at all. Its
    # canonical calculator metadata explicitly records this; dependencies still
    # cite the entity, learnset and chart rather than inventing a move record.
    no_probe = (pid >= 3 and section == 'stab' and e['calculator']['stab_examples']
                and all(x['kind'] == 'no_regular_damage_probe' and x['move_id'] is None
                        for x in e['calculator']['stab_examples']))
    if not indexes or (not direct and not no_probe):
        raise ValueError('missing section evidence')
    result = {'format': 'legacy-002-pinned' if pid == 2 else 'generated-full',
              'sections': sorted(tags), 'reference_indexes': indexes, 'pointer_base': '/references'}
    if no_probe:
        result['calculator_metadata_pointer'] = '/calculator/stab_examples'
        result['limitation'] = 'No regular-damage STAB probe; no move record fabricated.'
    return result


def build(root=ROOT):
    root = Path(root).resolve(strict=True)
    inputs = {}
    def read(rel):
        raw = safe(root, rel).read_bytes(); inputs[rel] = sha(raw); return raw
    register = json.loads(read('data/document_register.json'))
    mons = json.loads(read('data/processed/pokemon.json'))
    if len(mons) != 151 or sorted(x['id'] for x in mons) != list(range(1,152)):
        raise ValueError('invalid pokemon inventory')
    byid = {x['id']: x for x in mons}
    entries = register['documents']
    if register['schema_version'] != 1 or len(entries) != 151 or sorted(x['pokemon_id'] for x in entries) != list(range(1,152)):
        raise ValueError('invalid register')
    chunks, omissions = [], []
    config_hash = sha(encode(CONFIG))
    for entry in sorted(entries, key=lambda x: x['pokemon_id']):
        pid = entry['pokemon_id']; mon = byid[pid]; name = mon['name_ko']
        docpath = f'documents/{pid:03d}_{name}.md'; evpath = f'document_evidence/{pid:03d}.json'
        if entry['path'] != docpath or entry['evidence'] != evpath or entry['status'] != 'pending' or entry['index_eligible'] is not False:
            raise ValueError('register identity or status mismatch')
        raw = read(docpath); evraw = read(evpath); ev = json.loads(evraw)
        if sha(raw) != entry['sha256'] or (ev['pokemon_id'], ev['document_path'], ev['document_sha256']) != (pid, docpath, sha(raw)):
            raise ValueError('document or evidence identity mismatch')
        machine = any(x['version_group'] == 'red-blue' and x['method'] == 'machine' for x in mon['learnset'])
        if not machine: omissions.append(pid)
        sections = parse_document(raw, pid, name, machine)
        for sec in sections:
            section = sec['section']; text = content(name, sec['heading'], sec['body'])
            if pid == 1:
                historical = next(c for c in ev['historical_pilot']['data']['chunks'] if c['section'] == section)
                if historical['content'] != text:
                    raise ValueError('001 historical content mismatch')
            chunks.append({'schema_version': 1, 'draft': True, 'review_status': 'pending', 'index_eligible': False,
                           'chunk_id': f'pokemon:{pid}#{section}', 'document_id': f'pokemon:{pid}',
                           'pokemon_id': pid, 'name_ko': name, 'section': section, 'heading': sec['heading'],
                           'source_document': docpath, 'source_document_sha256': sha(raw),
                           'source_lines': [n for n, _ in sec['body']], 'source_heading_lines': sec['heading_lines'],
                           'evidence_path': evpath, 'evidence_sha256': sha(evraw),
                           'evidence': evidence_map(ev, pid, section), 'content': text,
                           'content_sha256': sha(text.encode('utf-8')), 'config_sha256': config_hash,
                           'games': ['red', 'blue'], 'version_group': 'red-blue',
                           'limitations': ['Historical encounter aggregation can imply unrecorded intermediate levels.'] if pid == 1 and section == 'encounter' else []})
    if omissions != [10,11,13,14,129,132] or len(chunks) != 1504 or len({c['chunk_id'] for c in chunks}) != len(chunks):
        raise ValueError('unexpected omissions or chunk inventory')
    return chunks, dict(sorted(inputs.items())), omissions


def main():
    parser = argparse.ArgumentParser(description='Offline A-boundary chunks; no embedding or indexing.')
    parser.add_argument('--root', type=Path, default=ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--output', type=Path, help='new JSONL file outside input root')
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if args.output:
        out = args.output.resolve()
        if out.is_relative_to(root) or root.is_relative_to(out) or out.exists() or out.is_symlink():
            raise ValueError('output must be a new file outside input root')
        if not out.parent.is_dir(): raise ValueError('output parent must exist')
    chunks, _, _ = build(root)
    data = b''.join(encode(c) for c in chunks)
    if args.check:
        if safe(root, 'chunks/draft-a-v1/chunks.jsonl').read_bytes() != data:
            raise ValueError('chunk output drift')
        print('PASS: 1504 chunks match byte-for-byte')
    else:
        with out.open('xb') as f: f.write(data)
        print('PASS: wrote 1504 chunks without overwrite')

if __name__ == '__main__':
    main()
