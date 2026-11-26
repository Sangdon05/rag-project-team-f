"""Offline preflight for bulk Red/Blue document generation; does not generate documents."""
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'processed'


def load(name):
    return json.loads((DATA / (name + '.json')).read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(root=ROOT):
    root = Path(root)
    data = root / 'data' / 'processed'
    def read(name):
        return json.loads((data / (name + '.json')).read_text(encoding='utf-8'))
    manifest = json.loads((root / 'data/source_manifest.json').read_text(encoding='utf-8'))
    require(len(manifest['processed_files']) == 11, 'expected 11 source records')
    pokemon, moves, types, chart = (read(n) for n in ('pokemon', 'moves', 'types', 'type_chart'))
    evo = read('evolutions_red_blue')['records']
    items = read('evolution_items_red_blue')['items']
    machines = read('machines_red_blue')['machines']
    acquisitions = read('machine_acquisition_red_blue')['machines']
    encounters = read('encounters_red_blue')['pokemon']
    locations = read('location_names_ko_red_blue')['entries']
    classes = read('red_blue_move_damage_classification')['moves']
    require(sorted(p['id'] for p in pokemon) == list(range(1, 152)), 'pokemon IDs are not exactly 1..151')
    by_id = {p['id']: p for p in pokemon}
    by_move = {m['name']: m for m in moves}
    require(len(by_move) == len(moves), 'duplicate move name')
    type_names = {t['name']: t for t in types}
    require(len(type_names) == 15 and set(chart) == set(type_names), 'type inventory mismatch')
    require(all(set(row) == set(type_names) for row in chart.values()), 'chart columns mismatch')
    require(all(t.get('name_ko') for t in types), 'missing Korean type name')
    code_by_move = {}
    for m in machines:
        code_by_move.setdefault(m['move'], []).append(m['code'])
    require(len({m['code'] for m in machines}) == len(machines), 'duplicate machine code')
    acq = {a['code']: a for a in acquisitions}
    require(len(acq) == len(acquisitions), 'duplicate acquisition code')
    locations_by_id = {x['id']: x for x in locations}
    require(len(locations_by_id) == len(locations), 'duplicate location ID')
    missing_localized = set()
    for machine in machines:
        a = acq.get(machine['code'])
        if a is None or a['move'] != machine['move']:
            raise ValueError('machine acquisition join mismatch: ' + machine['code'])
        for loc in a['locations']:
            require(set(loc['versions']) <= {'red', 'blue'}, 'unexpected acquisition version')
            key = 'pokered_map:' + loc['map_id_raw']
            require(key in locations_by_id, 'unknown machine location: ' + key)
            if locations_by_id[key]['name_ko'] is None:
                missing_localized.add(key)
    evo_by_id = {r['id']: r for r in evo}
    encounter_by_id = {r['id']: r for r in encounters}
    require(set(evo_by_id) == set(by_id) and len(evo_by_id) == len(evo), 'evolution IDs mismatch')
    require(set(encounter_by_id) == set(by_id) and len(encounter_by_id) == len(encounters), 'encounter IDs mismatch')
    item_by_name = {i['name']: i for i in items}
    require(len(item_by_name) == len(items), 'duplicate item name')
    edges = set()
    for p in pokemon:
        record = evo_by_id[p['id']]
        for edge in record['evolves_to']:
            a, b = edge['from_id'], edge['to_id']
            require(a == p['id'] and b in by_id, 'invalid evolution endpoint')
            require(any(e == edge for e in evo_by_id[b]['evolves_from']), 'evolution reverse edge mismatch')
            if edge['trigger'] == 'level-up':
                require(isinstance(edge['min_level'], int), 'missing evolution level')
            elif edge['trigger'] == 'use-item':
                require(edge['item'] in item_by_name and item_by_name[edge['item']]['name_ko'], 'missing evolution item')
            else:
                require(edge['trigger'] == 'trade', 'unknown evolution trigger')
            require((a, b) not in edges, 'duplicate evolution edge')
            edges.add((a, b))
    counts = Counter()
    no_machines = []
    file_names = []
    collision_keys = set()
    for p in pokemon:
        name = p['name_ko']
        require(bool(name) and not re.search(r'[<>:"/\\|?*\x00-\x1f]', name) and not name.endswith(('.', ' ')), 'unsafe file name')
        filename = f"{p['id']:03d}_{name}.md"
        key = unicodedata.normalize('NFC', filename).casefold()
        require(key not in collision_keys, 'file name collision')
        collision_keys.add(key)
        file_names.append(filename)
        require(all(t in type_names for t in p['types_gen1']), 'unknown pokemon type')
        learns = [r for r in p['learnset'] if r['version_group'] == 'red-blue' and r['method'] in ('level-up', 'machine')]
        if not any(r['method'] == 'machine' for r in learns):
            no_machines.append(p['id'])
        for r in learns:
            counts[r['method']] += 1
            require(r['move'] in by_move, 'unknown learnset move')
            move = by_move[r['move']]
            require(bool(move['name_ko']) and move['values_by_version_group']['red-blue']['type'] in type_names, 'move localization or versioned type missing')
            if r['method'] == 'machine':
                require(len(code_by_move.get(r['move'], [])) == 1, 'machine mapping is not unique')
        for version in ('red', 'blue'):
            for encounter in encounter_by_id[p['id']]['versions'][version]['encounters']:
                key = 'pokeapi_location_area:' + encounter['location_area']['name']
                require(key in locations_by_id, 'unknown encounter location: ' + key)
                if locations_by_id[key]['name_ko'] is None:
                    missing_localized.add(key)
    class_by_id = {c['id']: c['classification'] for c in classes}
    require(len(class_by_id) == len(classes), 'duplicate classification ID')
    require(all(m['id'] in class_by_id for m in moves), 'missing move classification')
    unchecked_types = [t for t in type_names if not any(m['values_by_version_group']['red-blue']['type'] == t and class_by_id[m['id']] == 'regular_damage' for m in moves)]
    return {'pokemon': len(pokemon), 'level_up_records': counts['level-up'], 'machine_records': counts['machine'], 'no_machine_ids': no_machines, 'evolution_edges': len(edges), 'calculator_no_regular_probe_types': unchecked_types, 'pokemon_with_unchecked_attack_type': [p['id'] for p in pokemon if any(t in unchecked_types for t in p['types_gen1'])], 'location_names_missing': sorted(missing_localized), 'gender_filenames': [file_names[28], file_names[31]], 'files_with_no_machine_acquisition_routes': [a['code'] for a in acquisitions if not a['locations']]}


if __name__ == '__main__':
    try:
        print(json.dumps(audit(), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print('FAIL:', exc, file=sys.stderr)
        raise SystemExit(1)
