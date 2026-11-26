"""Build portable, per-document source evidence; this module never writes files.

Evidence is not document validation, human review, or permission to index. The
caller supplies the hash of the bytes it will write; no document is opened.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import inspect
import json
from math import prod
from pathlib import Path, PurePosixPath
import re

try:
    from .gen1_battle.gen1_battle_rules import BattleRules, COMMIT
    from .v3a_sections_core import _graph, _component
except ImportError:
    from gen1_battle.gen1_battle_rules import BattleRules, COMMIT
    from v3a_sections_core import _graph, _component

NAMES = ('pokemon', 'moves', 'types', 'type_chart', 'red_blue_move_damage_classification',
         'machines_red_blue', 'machine_acquisition_red_blue', 'location_names_ko_red_blue',
         'evolutions_red_blue', 'evolution_items_red_blue', 'encounters_red_blue')

# References tagged with a section are direct inputs; entries here name additional
# reference sections that must be included when attributing that section.
SECTION_DEPENDENCIES = {
    'profile_and_stats': [],
    'learnset': ['profile_and_stats'],
    'machine': ['profile_and_stats', 'learnset'],
    'machine_acquisition': ['profile_and_stats', 'learnset', 'machine'],
    'evolution': [],
    'encounter_trade': [],
    'encounter': ['profile_and_stats', 'encounter_trade'],
    'type_calculations': ['profile_and_stats'],
    'attack_probe': [],
    'defense_probe': [],
    'attack': ['profile_and_stats', 'type_calculations', 'attack_probe'],
    'defense': ['profile_and_stats', 'type_calculations', 'defense_probe'],
    'stab_example': ['profile_and_stats', 'learnset', 'type_calculations', 'attack_probe'],
}


@lru_cache(maxsize=32)
def _parse(raw):
    return json.loads(raw)


def _load(root):
    upstream_raw = (root / 'data/source_manifest.json').read_bytes()
    upstream = json.loads(upstream_raw)
    declared = {r['source_id']: r for r in upstream['processed_files']}
    data, sources = {}, {}
    for name in NAMES:
        sid = 'processed:' + name
        path = 'data/processed/' + name + '.json'
        raw = (root / path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if declared[sid]['path'] != path:
            raise ValueError('source path mismatch: ' + sid)
        data[name] = _parse(raw)
        sources[sid] = {'path': path, 'sha256': digest}
    return upstream, data, sources


def _index(rows, key):
    out = {}
    for i, row in enumerate(rows):
        k = row[key]
        if k in out:
            raise ValueError(f'duplicate {key}: {k!r}')
        out[k] = (i, row)
    return out


def _resolve(data, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
        raise ValueError('invalid JSON pointer')
    value = data
    for token in pointer.split('/')[1:]:
        if re.search(r'~(?![01])', token):
            raise ValueError('invalid JSON pointer escape')
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token):
                raise ValueError('invalid array index')
            value = value[int(token)]
        else:
            value = value[token]
    return value


def validate_evidence(root: Path, evidence: dict, *, expected_pokemon_id=None,
                      expected_document_path=None, expected_document_sha256=None) -> None:
    """Check the complete canonical evidence and all record identities.

    Expected values are optional trusted caller context. For a written document,
    the caller must hash its actual bytes and pass the digest (or compare it
    separately); this function does not open the document. This is not semantic
    document or review validation.
    """
    root = Path(root)
    try:
        pokemon_id = evidence['pokemon_id']
        document_path = evidence['document_path']
        document_sha256 = evidence['document_sha256']
        for actual, expected in ((pokemon_id, expected_pokemon_id),
                                 (document_path, expected_document_path),
                                 (document_sha256, expected_document_sha256)):
            if expected is not None and (type(actual) is not type(expected) or actual != expected):
                raise ValueError('evidence differs from expected document identity or digest')
        canonical = build_evidence(root, pokemon_id, document_path, document_sha256)
        # JSON comparison also distinguishes bool from int and rejects additions,
        # omissions, reordered arrays and changes anywhere in the payload.
        actual_json = json.dumps(evidence, sort_keys=True, ensure_ascii=False, allow_nan=False)
        canonical_json = json.dumps(canonical, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if actual_json != canonical_json:
            raise ValueError('evidence differs from canonical payload')
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError('invalid evidence') from exc
    manifest, data, sources = _load(root)
    if evidence['sources'] != sources:
        raise ValueError('source fingerprints differ')
    manifests = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                 for name in ('data/source_manifest.json',)}
    if evidence['provenance_manifests'] != manifests or evidence['source_revision'] is not None:
        raise ValueError('manifest fingerprint or revision differs')
    for entry in (evidence['calculator'], evidence['calculator']['helper']):
        if entry['path'] not in ('scripts/gen1_battle/gen1_battle_rules.py', 'scripts/gen1_battle/data_integrity.py'):
            raise ValueError('unexpected calculator path')
        if hashlib.sha256((root / entry['path']).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('calculator fingerprint differs')
    try:
        for ref in evidence['references']:
            sid = ref['source_id']
            source = data[sid.removeprefix('processed:')]
            pointer = ref['pointer']
            value = _resolve(source, pointer)
            parent_pointer = ref.get('record_pointer', pointer)
            if parent_pointer != pointer and not pointer.startswith(parent_pointer + '/'):
                raise ValueError('subrecord outside record')
            parent = _resolve(source, parent_pointer)
            field = ref['identity_field']
            actual = parent if field is None else parent[field]
            if actual != ref['identity_value']:
                raise ValueError('record identity mismatch')
            if 'expected_subrecord' in ref:
                expected = ref['expected_subrecord']
                if not isinstance(value, dict) or any(value.get(k) != v for k, v in expected.items()):
                    raise ValueError('subrecord identity mismatch')
            if not ref['record_id'] or not ref['section']:
                raise ValueError('missing record identity or section')
            if sid == 'processed:type_chart':
                parts = pointer.split('/')
                if len(parts) != 3 or ref['record_id'] != f'type_matchup:{parts[1]}:{parts[2]}':
                    raise ValueError('chart identity mismatch')
            else:
                prefix = {'processed:pokemon': 'pokemon', 'processed:encounters_red_blue': 'pokemon',
                          'processed:evolutions_red_blue': 'pokemon', 'processed:moves': 'move',
                          'processed:red_blue_move_damage_classification': 'move', 'processed:types': 'type',
                          'processed:machines_red_blue': 'machine', 'processed:machine_acquisition_red_blue': 'machine',
                          'processed:location_names_ko_red_blue': 'location_name',
                          'processed:evolution_items_red_blue': 'item'}[sid]
                if ref['record_id'] != f'{prefix}:{actual}':
                    raise ValueError('record ID mismatch')
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError('invalid reference') from exc


def build_evidence(root: Path, pokemon_id: int, document_path: str, document_sha256: str) -> dict:
    """Return deterministic evidence for one planned document, without writing it."""
    if type(pokemon_id) is not int or not 1 <= pokemon_id <= 151:
        raise ValueError('pokemon_id must be an integer from 1 to 151')
    if not isinstance(document_path, str) or '\\' in document_path or '\x00' in document_path:
        raise ValueError('invalid document path')
    path = PurePosixPath(document_path)
    if (path.is_absolute() or len(path.parts) != 2 or path.parts[0] != 'documents'
            or any(p in ('.', '..') for p in document_path.split('/')) or str(path) != document_path):
        raise ValueError('document path must be a direct relative documents path')
    if not isinstance(document_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', document_sha256):
        raise ValueError('document_sha256 must be lowercase SHA-256')
    root = Path(root)
    manifest, d, sources = _load(root)
    mons = _index(d['pokemon'], 'id')
    if set(mons) != set(range(1, 152)):
        raise ValueError('expected exactly 151 pokemon IDs')
    pi, mon = mons[pokemon_id]
    if path.name != f"{pokemon_id:03d}_{mon['name_ko']}.md":
        raise ValueError('document filename must match pokemon ID and Korean name')
    documents = (root / 'documents').resolve()
    if not documents.is_relative_to(root.resolve()) or not (documents / path.name).resolve().is_relative_to(documents):
        raise ValueError('document path escapes documents directory')
    moves = _index(d['moves'], 'name')
    move_ids = _index(d['moves'], 'id')
    classes = _index(d['red_blue_move_damage_classification']['moves'], 'id')
    types = _index(d['types'], 'name')
    evo = _index(d['evolutions_red_blue']['records'], 'id')
    items = _index(d['evolution_items_red_blue']['items'], 'name')
    locs = _index(d['location_names_ko_red_blue']['entries'], 'id')
    machine = _index(d['machines_red_blue']['machines'], 'move')
    acq = _index(d['machine_acquisition_red_blue']['machines'], 'code')
    encounters = _index(d['encounters_red_blue']['pokemon'], 'id')
    refs = []
    seen = set()
    def add(source, pointer, record_id, field, value, section, parent=None, expected=None):
        key = (source, pointer, section)
        if key in seen:
            return
        seen.add(key)
        r = {'source_id': 'processed:' + source, 'pointer': pointer, 'record_id': record_id,
             'identity_field': field, 'identity_value': value, 'section': section}
        if parent is not None:
            r['record_pointer'] = parent
            r['expected_subrecord'] = deepcopy(expected)
        refs.append(r)
    def addmon(i, section):
        ix, _ = mons[i]
        add('pokemon', f'/{ix}', f'pokemon:{i}', 'id', i, section)
    def addmove(move, section):
        ix, row = move_ids[move]
        ci, c = classes[move]
        if c['name'] != row['name'] or c['source_move']['type'].lower().removesuffix('_type') != row['values_by_version_group']['red-blue']['type']:
            raise ValueError('move classification mismatch')
        add('moves', f'/{ix}', f'move:{move}', 'id', move, section)
        add('red_blue_move_damage_classification', f'/moves/{ci}', f'move:{move}', 'id', move, section)
    def addloc(key, section):
        i, _ = locs[key]
        add('location_names_ko_red_blue', f'/entries/{i}', f'location_name:{key}', 'id', key, section)
    addmon(pokemon_id, 'profile_and_stats')
    for i, t in enumerate(d['types']):
        add('types', f'/{i}', f"type:{t['id']}", 'id', t['id'], 'type_calculations')
    learned = {}
    for i, row in enumerate(mon['learnset']):
        if row['version_group'] != 'red-blue':
            continue
        add('pokemon', f'/{pi}/learnset/{i}', f'pokemon:{pokemon_id}', 'id', pokemon_id, 'learnset',
            f'/{pi}', {k: row[k] for k in ('move', 'method', 'level', 'version_group', 'order')})
        _, m = moves[row['move']]
        addmove(m['id'], 'learnset')
        if row['method'] in ('level-up', 'machine') and classes[m['id']][1]['classification'] == 'regular_damage':
            typ = m['values_by_version_group']['red-blue']['type']
            rank = (row['method'] != 'level-up', row['level'] if row['method'] == 'level-up' else 0, m['id'])
            if typ not in learned or rank < learned[typ][0]:
                learned[typ] = (rank, m['id'])
        if row['method'] == 'machine':
            mi, machine_row = machine[row['move']]
            code = machine_row['code']
            ai, acquisition = acq[code]
            if acquisition['move'] != row['move'] or machine_row['move_id'] != m['id'] or machine_row['version_group'] != 'red-blue':
                raise ValueError('machine join mismatch')
            add('machines_red_blue', f'/machines/{mi}', f'machine:{code}', 'code', code, 'machine')
            add('machine_acquisition_red_blue', f'/machines/{ai}', f'machine:{code}', 'code', code, 'machine_acquisition')
            for li, place in enumerate(acquisition['locations']):
                versions = place['versions']
                if not versions or len(versions) != len(set(versions)) or not set(versions) <= {'red', 'blue'}:
                    raise ValueError('invalid machine versions')
                add('machine_acquisition_red_blue', f'/machines/{ai}/locations/{li}', f'machine:{code}', 'code', code,
                    'machine_acquisition', f'/machines/{ai}', {k: place[k] for k in ('map_id_raw', 'method', 'versions')})
                addloc('pokered_map:' + place['map_id_raw'], 'machine_acquisition')
    outgoing, incoming = _graph({k: v[1] for k, v in mons.items()}, {k: v[1] for k, v in evo.items()})
    roots = _component(pokemon_id, outgoing, incoming)
    todo, component = list(roots), set()
    while todo:
        node = todo.pop()
        if node in component:
            continue
        component.add(node)
        todo.extend(edge['to_id'] for edge in outgoing[node])
    for node in sorted(component):
        addmon(node, 'evolution')
        ei, record = evo[node]
        add('evolutions_red_blue', f'/records/{ei}', f'pokemon:{node}', 'id', node, 'evolution')
        for side in ('evolves_from', 'evolves_to'):
            for j, edge in enumerate(record[side]):
                add('evolutions_red_blue', f'/records/{ei}/{side}/{j}', f'pokemon:{node}', 'id', node,
                    'evolution', f'/records/{ei}', {k: edge[k] for k in ('from_id', 'to_id', 'trigger', 'min_level', 'item')})
                if edge['item'] is not None:
                    ii, _ = items[edge['item']]
                    add('evolution_items_red_blue', f'/items/{ii}', f"item:{edge['item']}", 'name', edge['item'], 'evolution')
    en_i, en = encounters[pokemon_id]
    if (en['name'], en['name_ko']) != (mon['name'], mon['name_ko']):
        raise ValueError('encounter identity mismatch')
    add('encounters_red_blue', f'/pokemon/{en_i}', f'pokemon:{pokemon_id}', 'id', pokemon_id, 'encounter')
    mon_names = _index(d['pokemon'], 'name')
    for version in ('red', 'blue'):
        ver = en['versions'][version]
        if ver['status'] not in ('recorded_in_api', 'no_record_in_api') or bool(ver['encounters']) != (ver['status'] == 'recorded_in_api'):
            raise ValueError('invalid encounter status')
        for j, entry in enumerate(ver['encounters']):
            if entry['version_detail']['version']['name'] != version:
                raise ValueError('encounter version mismatch')
            area = entry['location_area']['name']
            addloc('pokeapi_location_area:' + area, 'encounter')
            p = f'/pokemon/{en_i}/versions/{version}/encounters/{j}'
            add('encounters_red_blue', p, f'pokemon:{pokemon_id}', 'id', pokemon_id, 'encounter',
                f'/pokemon/{en_i}', {'location_area': entry['location_area'], 'version_detail': entry['version_detail']})
            for detail in entry['version_detail']['encounter_details']:
                for condition in detail['condition_values']:
                    name = condition['name']
                    if name.startswith('trade-') and name[6:] in mon_names:
                        addmon(mon_names[name[6:]][1]['id'], 'encounter_trade')
    chart = d['type_chart']
    own = mon['types_gen1']
    if not 1 <= len(own) <= 2 or len(set(own)) != len(own) or set(chart) != set(types):
        raise ValueError('invalid types')
    probes = {}
    for _, m in sorted(move_ids.values(), key=lambda x: x[1]['id']):
        if classes[m['id']][1]['classification'] == 'regular_damage':
            probes.setdefault(m['values_by_version_group']['red-blue']['type'], m['id'])
    if len(types) != 15 or any(set(row) != set(types) for row in chart.values()):
        raise ValueError('invalid chart')
    for attack in own:
        for defense in sorted(types):
            add('type_chart', f'/{attack}/{defense}', f'type_matchup:{attack}:{defense}', None, chart[attack][defense], 'attack')
    for attack in sorted(types):
        for defense in own:
            add('type_chart', f'/{attack}/{defense}', f'type_matchup:{attack}:{defense}', None, chart[attack][defense], 'defense')
    # Build the actual calculator against the already-parsed pinned data.
    rules = BattleRules.__new__(BattleRules)
    rules.pokemon = BattleRules._index(d['pokemon'], 'pokemon')
    rules.moves = BattleRules._index(d['moves'], 'move')
    rules.types = BattleRules._index(d['types'], 'type')
    rules.chart = chart
    rules.classifications = {k: v[1] for k, v in classes.items()}
    if d['red_blue_move_damage_classification']['source_commit'] != COMMIT:
        raise ValueError('classification commit mismatch')
    examples = []
    for typ in own:
        probe = probes.get(typ)
        if probe is not None:
            addmove(probe, 'attack_probe')
            for defense in types:
                result = rules.calculate(version='red-blue', user=pokemon_id, target=pokemon_id, move=probe, target_types=[defense])
                if result['calculation'] != 'basic_type_and_stab' or result['type_effectiveness'] != chart[typ][defense]:
                    raise ValueError('attack calculator mismatch')
        example = learned[typ][1] if typ in learned else probe
        kind = 'learnable' if typ in learned else ('hypothetical' if probe is not None else 'no_regular_damage_probe')
        if example is not None:
            addmove(example, 'stab_example')
            if rules.calculate(version='red-blue', user=pokemon_id, target=pokemon_id, move=example)['stab'] != 1.5:
                raise ValueError('STAB calculator mismatch')
        examples.append({'type': typ, 'move_id': example, 'kind': kind})
    for typ in sorted(types):
        probe = probes.get(typ)
        if probe is not None:
            addmove(probe, 'defense_probe')
            result = rules.calculate(version='red-blue', user=pokemon_id, target=pokemon_id, move=probe)
            if result['calculation'] != 'basic_type_and_stab' or result['type_effectiveness'] != prod(chart[typ][x] for x in own):
                raise ValueError('defense calculator mismatch')
    calcpath = 'scripts/gen1_battle/gen1_battle_rules.py'
    digest = hashlib.sha256((root / calcpath).read_bytes()).hexdigest()

    if hashlib.sha256(Path(inspect.getfile(BattleRules)).read_bytes()).hexdigest() != digest:
        raise ValueError('loaded calculator differs from snapshot calculator')
    helperpath = 'scripts/gen1_battle/data_integrity.py'
    helper_digest = hashlib.sha256((root / helperpath).read_bytes()).hexdigest()

    calculator = {'path': calcpath, 'sha256': digest, 'helper': {'path': helperpath, 'sha256': helper_digest},
                  'version': 'red-blue', 'user_id': pokemon_id,
                  'target_id': pokemon_id, 'classification_source_commit': COMMIT,
                  'attack_and_stab_probes': {t: probes.get(t) for t in own},
                  'defense_probes': {t: probes.get(t) for t in sorted(types)},
                  'calculator_unchecked_attack_types': [t for t in own if t not in probes],
                  'calculator_unchecked_defense_types': [t for t in sorted(types) if t not in probes],
                  'stab_examples': examples,
                  'method': 'BattleRules.calculate type_effectiveness; single-type target override for attack; actual target for defense; STAB separately; missing regular-damage probes chart-only'}
    result = {'schema_version': 1, 'document_path': document_path, 'pokemon_id': pokemon_id,
              'document_sha256': document_sha256, 'source_revision': None,
              'provenance_manifests': {
                  name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                  for name in ('data/source_manifest.json',)},
              'sources': sources, 'calculator': calculator, 'references': refs,
              'section_dependencies': deepcopy(SECTION_DEPENDENCIES),
              'limitations': ['Evidence links inputs and calculations, not document truth or review approval.',
                              'Encounter and machine acquisition records may be incomplete; absence is not impossibility.',
                              'Historical move and stat values may include present-value fallbacks; see source manifest.',
                              'The classification source records a historical moves input hash different from this snapshot.',
                              'Chart-only types without a regular-damage probe are not calculator-verified.']}
    return result
