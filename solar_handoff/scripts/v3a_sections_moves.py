"""Render the v3a moves section from the portable, local Red/Blue snapshot.

This module only reads inputs and returns text. It neither creates documents nor
marks them approved. Machine acquisition coverage is explicitly partial.
"""
import json
import re
from pathlib import Path

_METHODS = {
    'ground_item': '바닥 아이템',
    'reward_npc': 'NPC 보상',
    'shop': '상점',
    'game_corner_prize': '게임코너 경품 교환',
}


def _read(root, name):
    return json.loads((root / 'data' / 'processed' / (name + '.json')).read_text(encoding='utf-8'))


def _index(records, key, label):
    result = {}
    for record in records:
        value = record[key]
        if value in result:
            raise ValueError(f'duplicate {label}: {value}')
        result[value] = record
    return result


def _cell(value, label):
    if not isinstance(value, str) or not value.strip() or any(c in value for c in '|\r\n'):
        raise ValueError(f'invalid {label}: {value!r}')
    return value


def render_moves(root: Path, pokemon_id: int) -> str:
    """Return only the v3a technology section, ending in two LF characters.

    ``root`` is the portable pokedex_v3a directory. Unknown or inconsistent
    source mappings raise an error rather than being inferred.
    """
    root = Path(root)
    if type(pokemon_id) is not int or not 1 <= pokemon_id <= 151:
        raise ValueError('pokemon_id must be an integer from 1 to 151')
    pokemon = _index(_read(root, 'pokemon'), 'id', 'pokemon ID')
    if pokemon_id not in pokemon:
        raise ValueError(f'missing pokemon ID: {pokemon_id}')
    moves = _index(_read(root, 'moves'), 'name', 'move')
    types = _index(_read(root, 'types'), 'name', 'type')
    machines = _index(_read(root, 'machines_red_blue')['machines'], 'code', 'machine code')
    acquisitions = _index(_read(root, 'machine_acquisition_red_blue')['machines'], 'code', 'acquisition code')
    locations = _index(_read(root, 'location_names_ko_red_blue')['entries'], 'id', 'location ID')

    by_move = {}
    for code, machine in machines.items():
        if not re.fullmatch(r'(?:TM(?:0[1-9]|[1-4][0-9]|50)|HM0[1-5])', code):
            raise ValueError(f'invalid machine code: {code}')
        if machine['version_group'] != 'red-blue' or machine['kind'] != code[:2] or machine['number'] != int(code[2:]):
            raise ValueError(f'invalid machine mapping: {code}')
        move = moves.get(machine['move'])
        if move is None or machine['move_id'] != move['id']:
            raise ValueError(f'invalid machine move mapping: {code}')
        if machine['move'] in by_move:
            raise ValueError(f'duplicate machine move mapping: {machine["move"]}')
        by_move[machine['move']] = code
        if code not in acquisitions or acquisitions[code]['move'] != machine['move']:
            raise ValueError(f'machine acquisition join mismatch: {code}')
    if set(machines) != set(acquisitions):
        raise ValueError('machine acquisition code set mismatch')

    def move_fields(name):
        if name not in moves:
            raise ValueError(f'unknown move: {name}')
        move = moves[name]
        move_name = _cell(move['name_ko'], 'move name')
        type_id = move['values_by_version_group']['red-blue']['type']
        if type_id not in types:
            raise ValueError(f'unknown red-blue move type: {type_id}')
        return move_name, _cell(types[type_id]['name_ko'], 'type name')

    learns = [r for r in pokemon[pokemon_id]['learnset']
              if r['version_group'] == 'red-blue' and r['method'] in ('level-up', 'machine')]
    level = [r for r in learns if r['method'] == 'level-up']
    machine_rows = [r for r in learns if r['method'] == 'machine']
    for row in level:
        if type(row['level']) is not int or row['level'] < 1:
            raise ValueError(f'invalid learn level: {row["level"]!r}')
        if row['order'] is not None and type(row['order']) is not int:
            raise ValueError('invalid learn order')
        move_fields(row['move'])
    for row in machine_rows:
        move_fields(row['move'])
        if row['move'] not in by_move:
            raise ValueError(f'missing machine mapping: {row["move"]}')
    level.sort(key=lambda r: (r['level'], r['order'] if r['order'] is not None else 10**9, r['move']))
    machine_rows.sort(key=lambda r: by_move[r['move']])

    lines = ['## 기술', '', '### 레벨업으로 배우는 기술', '',
             '영문 Red·Blue 습득 데이터에 기록된 레벨업 기술 전체입니다.', '']
    if level:
        lines += ['| 습득 레벨 | 기술 | 타입 |', '|---:|---|---|']
        for row in level:
            name, type_name = move_fields(row['move'])
            lines.append(f'| {row["level"]} | {name} | {type_name} |')
    else:
        lines.append('레벨업으로 배우는 기술 기록이 없습니다.')
    lines += ['', '### 기술머신·비전머신으로 배우는 기술', '',
              '영문 Red·Blue 습득 데이터에 기록된 머신 기술 전체입니다.', '']
    if machine_rows:
        lines += ['| 머신 | 기술 | 타입 |', '|---|---|---|']
        for row in machine_rows:
            name, type_name = move_fields(row['move'])
            lines.append(f'| {by_move[row["move"]]} | {name} | {type_name} |')
    else:
        lines.append('머신으로 배우는 기술 기록이 없습니다.')
    lines += ['', f'레벨업 {len(level)}건과 머신 {len(machine_rows)}건을 합치면 습득 기록은 {len(learns)}건이고, 중복을 제외하면 기술은 {len({r["move"] for r in learns})}개입니다. 목록은 **배울 수 있는 기술**을 뜻하며, 지금 보유한 기술을 뜻하지는 않습니다.']
    if machine_rows:
        lines += ['', '### 머신은 어디서 얻나요?', '',
                  '아래는 각 머신의 확인된 장소와 방법입니다. 장소는 한국어판 게임의 장소 이름으로 표시했습니다. 출처는 일부 경로만 담고 있으며 도달 조건은 모두 확인되지 않았으므로 빠진 경로가 있을 수 있습니다.', '',
                  '| 머신 | 장소와 방법 |', '|---|---|']
        for code in dict.fromkeys(by_move[r['move']] for r in machine_rows):
            entries = []
            for loc in acquisitions[code]['locations']:
                key = 'pokered_map:' + loc['map_id_raw']
                if key not in locations:
                    raise ValueError(f'unknown machine location: {key}')
                place = locations[key]
                if place['review_status'] != 'approved':
                    raise ValueError(f'unapproved machine location: {key}')
                name = _cell(place['name_ko'], 'location name')
                method = loc['method']
                if method not in _METHODS:
                    raise ValueError(f'unknown machine acquisition method: {method}')
                versions = loc['versions']
                if len(versions) != len(set(versions)) or not versions or not set(versions) <= {'red', 'blue'}:
                    raise ValueError(f'invalid machine acquisition versions: {versions!r}')
                prefix = '' if set(versions) == {'red', 'blue'} else ('Red: ' if versions == ['red'] else 'Blue: ')
                entries.append(f'{prefix}{name} — {_METHODS[method]}')
            lines.append(f'| {code} | {"; ".join(entries) if entries else "확인된 획득 기록 없음 (획득 불가를 뜻하지 않음)"} |')
    return '\n'.join(lines) + '\n\n'
