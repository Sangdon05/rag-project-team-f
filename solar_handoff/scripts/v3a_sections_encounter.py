"""Render a v3a Red/Blue acquisition section from the portable processed data.

Usage: render_encounter(Path('pokedex_v3a'), 1). The return value includes
its heading and trailing newline. Unknown conditions (including fossil items)
are retained as backticked identifiers, not translated or inferred.
"""

import json
import re
from pathlib import Path


_METHODS = {
    'walk': ('wild', '야생(풀숲·동굴)'),
    'old-rod': ('wild', '야생(낡은낚싯대 낚시)'),
    'good-rod': ('wild', '야생(좋은낚싯대 낚시)'),
    'super-rod': ('wild', '야생(대단한낚싯대 낚시)'),
    'surf': ('wild', '야생(파도타기)'),
    'static': ('wild', '야생(고정 출현)'),
    'pokeflute': ('wild', '야생(포켓몬 피리)'),
    'gift': ('gift', '선물'),
    'npc-trade': ('npc-trade', 'NPC 교환'),
}
_GROUPS = (('wild', '야생 포켓몬으로 만나는'), ('gift', '선물로 받는'),
           ('npc-trade', 'NPC 교환으로 받는'))
_VERSIONS = ('red', 'blue')
_SCOPE = 'PokéAPI의 등장·획득 기록 기준이며, 기록이 없다고 해서 얻을 수 없다는 뜻은 아닙니다.'


def _read(root, name):
    return json.loads((Path(root) / 'data' / 'processed' / name).read_text(encoding='utf-8'))


def _josa(name, consonant, vowel):
    stem = name.rstrip('♀♂')
    if not stem or not 0 <= ord(stem[-1]) - 0xAC00 <= 0x2BA3:
        raise ValueError(f'조사를 정할 수 없는 이름: {name!r}')
    return name + (consonant if (ord(stem[-1]) - 0xAC00) % 28 else vowel)


def _condition(value, pokemon_by_name):
    match = re.fullmatch(r'coins-(\d+)', value)
    if match:
        return f'코인 {int(match.group(1))}개'
    match = re.fullmatch(r'trade-(.+)', value)
    if match and match.group(1) in pokemon_by_name:
        return _josa(pokemon_by_name[match.group(1)]['name_ko'], '과', '와') + ' 교환'
    return f'`{value}`'


def _clauses(groups):
    if not groups:
        return [('등장·획득 기록이', '없'), ('야생에서 만나는 기록도', '없')]
    clauses = []
    for group, verb in _GROUPS:
        names = groups.get(group, [])
        if names:
            where = '·'.join(names) if len(names) <= 3 else f'{len(names)}곳'
            clauses.append((f'{where}에서 {verb} 기록이', '있'))
    if 'wild' not in groups:
        clauses.append(('야생에서 만나는 기록은', '없'))
    return clauses


def _render_clauses(clauses):
    return ', '.join(f"{subject} {stem}{'습니다' if i == len(clauses) - 1 else '고'}"
                     for i, (subject, stem) in enumerate(clauses))


def _normalize_intervals(intervals):
    """Merge overlapping or adjacent inclusive intervals, preserving gaps."""
    merged = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return tuple(merged)


def render_encounter(root: Path, pokemon_id: int) -> str:
    """Return the complete acquisition section, based only on root's portable data.

    Missing IDs, mappings or unsupported methods raise; absent encounter records
    are not evidence that a Pokémon cannot be obtained. No files are written.
    """
    pokemon = _read(root, 'pokemon.json')
    encounters = _read(root, 'encounters_red_blue.json')['pokemon']
    locations = _read(root, 'location_names_ko_red_blue.json')['entries']
    records = [p for p in pokemon if p['id'] == pokemon_id]
    entries = [p for p in encounters if p['id'] == pokemon_id]
    if len(records) != 1 or len(entries) != 1:
        raise ValueError(f'포켓몬 ID가 없거나 중복됨: {pokemon_id}')
    record, entry = records[0], entries[0]
    if record['name'] != entry['name'] or record['name_ko'] != entry['name_ko']:
        raise ValueError(f'포켓몬 이름 불일치: {pokemon_id}')
    by_name = {p['name']: p for p in pokemon}
    by_location = {p['id']: p['name_ko'] for p in locations}

    # Insertion order is Red's keys followed by keys first seen in Blue.
    order = {}
    levels = {version: {} for version in _VERSIONS}
    for version in _VERSIONS:
        for item in entry['versions'][version]['encounters']:
            area = item['location_area']['name']
            for detail in item['version_detail']['encounter_details']:
                method = detail['method']['name']
                if method not in _METHODS:
                    raise ValueError(f'표기 규칙이 없는 획득 방법: {method} ({version} {area})')
                conditions = tuple(sorted(c['name'] for c in detail['condition_values']))
                key = (area, method, conditions)
                low, high = detail['min_level'], detail['max_level']
                levels[version].setdefault(key, []).append((low, high))
                order.setdefault(key, None)

    for version in _VERSIONS:
        for key, intervals in levels[version].items():
            levels[version][key] = _normalize_intervals(intervals)

    rows = []
    groups = {version: {} for version in _VERSIONS}
    has_conditions = any(key[2] for key in order)
    for key in order:
        area, method, conditions = key
        location_id = 'pokeapi_location_area:' + area
        if location_id not in by_location:
            raise ValueError(f'장소 대응표에 없는 식별자: {location_id}')
        place = by_location[location_id] or f'`{area}`'
        present = [(v, levels[v][key]) for v in _VERSIONS if key in levels[v]]
        for version, _ in present:
            names = groups[version].setdefault(_METHODS[method][0], [])
            if place not in names:
                names.append(place)
        if len(present) == 2 and present[0][1] == present[1][1]:
            present = [('Red·Blue', present[0][1])]
        else:
            present = [(v.title(), bounds) for v, bounds in present]
        condition = ', '.join(_condition(value, by_name) for value in conditions) or '없음'
        for label, intervals in present:
            level = ', '.join(str(low) if low == high else f'{low}~{high}'
                              for low, high in intervals)
            rows.append([label, place, _METHODS[method][1], level, condition])

    red, blue = (_clauses(groups[v]) for v in _VERSIONS)
    if red == blue:
        facts = f'Red와 Blue 모두 {_render_clauses(red)}.'
    else:
        facts = f'Red에서는 {_render_clauses(red)}. Blue에서는 {_render_clauses(blue)}.'
    summary = f"요약: {_josa(record['name_ko'], '을', '를')} 얻는 방법(잡는 곳·받는 곳)과 장소입니다. {facts}"
    lines = ['## 획득처', '', summary, '']
    if rows:
        header = ['버전', '장소', '방법', '레벨'] + (['조건'] if has_conditions else [])
        lines.extend(['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)])
        lines.extend('| ' + ' | '.join(row[:len(header)]) + ' |' for row in rows)
        lines.extend(['', '장소는 한국어판 게임의 장소 이름입니다. ' + _SCOPE])
    else:
        lines.append(_SCOPE)
    return '\n'.join(lines) + '\n'
