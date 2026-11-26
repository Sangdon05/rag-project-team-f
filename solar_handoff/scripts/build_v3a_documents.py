"""Generate pending Red/Blue documents offline into a new separate bundle."""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.audit_bulk_inputs import audit
from scripts.v3a_document_evidence import build_evidence, validate_evidence
from scripts.v3a_sections_core import render_core
from scripts.v3a_sections_moves import render_moves
from scripts.v3a_sections_battle import render_battle
from scripts.v3a_sections_encounter import render_encounter


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def headings(text, mon):
    stem = mon['name_ko'].rstrip('♀♂')
    suffix = '과' if (ord(stem[-1]) - 0xac00) % 28 else '와'
    expected = ['# ' + mon['name_ko'], '## 어떤 포켓몬인가요?', '## 종족치', '## 진화',
                '## 기술', '### 레벨업으로 배우는 기술', '### 기술머신·비전머신으로 배우는 기술']
    if any(r['version_group'] == 'red-blue' and r['method'] == 'machine' for r in mon['learnset']):
        expected.append('### 머신은 어디서 얻나요?')
    expected += ['## 타입 · 상성', '### 자속 보정 (같은 타입 기술 1.5배)',
                 f"### 공격 상성 ({mon['name_ko']}{suffix} 같은 타입 기술이 잘 통하는 타입)",
                 '### 방어 상성 (약점과 저항)', '## 획득처']
    actual, fenced = [], False
    for line in text.splitlines():
        if line.strip().startswith('```'):
            fenced = not fenced
        elif not fenced and re.match(r'^\s*#{1,}', line):
            actual.append(line.strip())
    if fenced or actual != expected or f'- **도감번호:** {mon["id"]:03d}\n' not in text:
        raise ValueError('invalid document headings or identity: ' + str(mon['id']))


def planned(root):
    audit(root)
    mons = json.loads((root / 'data/processed/pokemon.json').read_bytes())
    if sorted(p['id'] for p in mons) != list(range(1, 152)):
        raise ValueError('expected all 151 IDs')
    mons = {p['id']: p for p in mons}
    result = []
    for i in range(3, 152):
        mon = mons[i]
        path = f'documents/{i:03d}_{mon["name_ko"]}.md'
        text = ''.join(f(root, i) for f in (render_core, render_moves, render_battle, render_encounter))
        headings(text, mon)
        data = text.encode('utf-8')
        evidence = build_evidence(root, i, path, digest(data))
        validate_evidence(root, evidence, expected_pokemon_id=i,
                          expected_document_path=path, expected_document_sha256=digest(data))
        entry = {'path': path, 'pokemon_id': i, 'status': 'pending', 'index_eligible': False,
                 'sha256': digest(data), 'evidence': f'document_evidence/{i:03d}.json'}
        result.append((entry, data, evidence))
    return result


def main():
    parser = argparse.ArgumentParser(description="Regenerate 003–151; preserve 001 and 002. Never overwrite inputs.")
    parser.add_argument('--root', type=Path, default=ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--output', type=Path, help='new directory outside input root')
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    register = json.loads((root / 'data/document_register.json').read_bytes())
    entries = register['documents']
    if len(entries) != 151 or [e['pokemon_id'] for e in entries] != list(range(1, 152)):
        raise ValueError('invalid register inventory')
    mons = json.loads((root / 'data/processed/pokemon.json').read_bytes())
    for i in (1, 2):
        entry = entries[i-1]
        if entry['path'] != f'documents/{i:03d}_{mons[i-1]["name_ko"]}.md' or entry['evidence'] != f'document_evidence/{i:03d}.json':
            raise ValueError('invalid special document path')
        raw = (root / entry['path']).read_bytes()
        ev = json.loads((root / entry['evidence']).read_bytes())
        if digest(raw) != entry['sha256'] or ev['document_sha256'] != digest(raw) or ev['pokemon_id'] != i:
            raise ValueError('special document identity mismatch')
    if args.output:
        out = args.output.resolve()
        if out == root or out.is_relative_to(root) or root.is_relative_to(out):
            raise ValueError('output must be separate from input root')
        if out.exists() or out.is_symlink():
            raise FileExistsError('output already exists')
        if not out.parent.is_dir():
            raise ValueError('output parent must exist')
    items = planned(root)
    if args.check:
        for entry, data, evidence in items:
            current = entries[entry['pokemon_id']-1]
            if current != entry or (root / entry['path']).read_bytes() != data:
                raise ValueError('document mismatch: ' + entry['path'])
            old = json.loads((root / entry['evidence']).read_bytes())
            # Historical provenance and code fingerprints remain preserved in the
            # original evidence; compare the new record links and computations.
            for field in ('pokemon_id','document_path','document_sha256','sources','references','section_dependencies'):
                if old[field] != evidence[field]:
                    raise ValueError('evidence mismatch: ' + entry['evidence'] + ' ' + field)
            old_calc, new_calc = dict(old['calculator']), dict(evidence['calculator'])
            for calc in (old_calc, new_calc):
                calc.pop('sha256', None)
                calc['helper'] = {k: v for k, v in calc['helper'].items() if k != 'sha256'}
            if old_calc != new_calc:
                raise ValueError('calculation evidence mismatch: ' + entry['evidence'])
        print('PASS: 001–002 preserved; 149 generated documents and evidence links match')
        return
    assert args.output is not None
    out = args.output.resolve()
    out.mkdir()
    (out / 'documents').mkdir(); (out / 'document_evidence').mkdir(); (out / 'data').mkdir()
    # The new bundle has its own inputs and generator, never links to the old one.
    shutil.copytree(root / 'data/processed', out / 'data/processed')
    shutil.copy2(root / 'data/source_manifest.json', out / 'data/source_manifest.json')
    scripts_out = out / 'scripts'
    scripts_out.mkdir()
    for script in ROOT.joinpath('scripts').glob('*.py'):
        shutil.copy2(script, scripts_out / script.name)
    (scripts_out / 'gen1_battle').mkdir()
    for script in ROOT.joinpath('scripts/gen1_battle').glob('*.py'):
        shutil.copy2(script, scripts_out / 'gen1_battle' / script.name)
    for entry in entries[:2]:
        for rel in (entry['path'], entry['evidence']):
            with (out / rel).open('xb') as f: f.write((root / rel).read_bytes())
    for entry, data, evidence in items:
        for rel, raw in ((entry['path'], data), (entry['evidence'], json_bytes(evidence))):
            with (out / rel).open('xb') as f: f.write(raw)
    with (out / 'data/document_register.json').open('xb') as f:
        f.write(json_bytes(dict(register, documents=entries[:2] + [e for e, _, _ in items])))
    print('PASS: wrote 151 documents and evidence to new directory; 001–002 copied unchanged')

if __name__ == '__main__':
    main()
