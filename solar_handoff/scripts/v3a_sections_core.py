"""Render the data-backed profile, stats and Red/Blue evolution sections.

The caller supplies the portable v3a root; this module neither writes documents
nor marks them reviewed. Evolution edges come only from the Red/Blue graph.
"""
import json
from pathlib import Path


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


def _particle(name, consonant, vowel):
    # Gender symbols are not pronounced; use the final Hangul syllable.
    last = name.rstrip('♀♂')[-1]
    code = ord(last) - 0xAC00
    return name + (consonant if 0 <= code < 11172 and code % 28 else vowel)


def _direction(name):
    last = name.rstrip('♀♂')[-1]
    code = ord(last) - 0xAC00
    final = code % 28 if 0 <= code < 11172 else 0
    return name + ('으로' if final and final != 8 else '로')


def _condition(edge, items):
    trigger = edge.get('trigger')
    if trigger == 'level-up':
        level = edge.get('min_level')
        return f'레벨 {level}' if type(level) is int and level > 0 else '조건 미확인'
    if trigger == 'use-item':
        item = items.get(edge.get('item'))
        return item['name_ko'] if item and item.get('name_ko') else '조건 미확인'
    if trigger == 'trade':
        return '통신 교환'
    return '조건 미확인'


def _graph(pokemon, records):
    """Validate both sides of every edge, then build directed adjacency."""
    if set(records) != set(pokemon):
        raise ValueError('pokemon and evolution IDs differ')
    outgoing = {i: [] for i in records}
    incoming = {i: [] for i in records}
    seen_out, seen_in = {}, {}
    for i, record in records.items():
        if record.get('version_group') != 'red-blue':
            raise ValueError(f'wrong evolution version: {i}')
        for side, seen in (('evolves_to', seen_out), ('evolves_from', seen_in)):
            for edge in record[side]:
                a, b = edge['from_id'], edge['to_id']
                if a not in records or b not in records or (side == 'evolves_to' and a != i) or (side == 'evolves_from' and b != i):
                    raise ValueError('invalid evolution endpoint')
                if (a, b) in seen:
                    raise ValueError('duplicate evolution edge')
                seen[a, b] = edge
    if seen_out != seen_in:
        raise ValueError('evolution reverse edge mismatch')
    for (a, b), edge in sorted(seen_out.items()):
        outgoing[a].append(edge)
        incoming[b].append(edge)
    return outgoing, incoming


def _component(target, outgoing, incoming):
    component, pending = set(), [target]
    while pending:
        node = pending.pop()
        if node in component:
            continue
        component.add(node)
        pending.extend(e['to_id'] for e in outgoing[node])
        pending.extend(e['from_id'] for e in incoming[node])
    # Topological traversal both detects cycles and produces deterministic roots.
    indegree = {i: len(incoming[i]) for i in component}
    roots = sorted(i for i in component if not indegree[i])
    queue, visited = list(roots), 0
    while queue:
        node = queue.pop()
        visited += 1
        for edge in outgoing[node]:
            child = edge['to_id']
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(component):
        raise ValueError('cyclic evolution graph')
    return roots


def render_core(root: Path, pokemon_id: int) -> str:
    """Return Markdown through evolution, ending in a blank line for ## 기술."""
    root = Path(root)
    pokemon = _index(_read(root, 'pokemon'), 'id', 'pokemon ID')
    records = _index(_read(root, 'evolutions_red_blue')['records'], 'id', 'evolution ID')
    items = _index(_read(root, 'evolution_items_red_blue')['items'], 'name', 'item')
    types = _index(_read(root, 'types'), 'name', 'type')
    if type(pokemon_id) is not int or pokemon_id not in pokemon:
        raise ValueError(f'unknown pokemon ID: {pokemon_id}')
    outgoing, incoming = _graph(pokemon, records)
    roots = _component(pokemon_id, outgoing, incoming)
    p = pokemon[pokemon_id]
    name = p['name_ko']
    if not name or not p['types_gen1']:
        raise ValueError('missing pokemon name or types')
    type_names = [types[t]['name_ko'] for t in p['types_gen1']]
    if not all(type_names):
        raise ValueError('missing Korean type name')
    if len(type_names) == 1:
        intro = f"{_particle(name, '은', '는')} {type_names[0]} 타입 포켓몬입니다."
    else:
        type_phrase = ' · '.join(type_names)
        intro = f"{_particle(name, '은', '는')} {type_phrase}의 복합 타입 포켓몬입니다."
    stats = p['stats_gen1']
    values = [stats[k] for k in ('hp', 'attack', 'defense', 'speed', 'special')]
    if any(type(v) is not int or v < 1 for v in values):
        raise ValueError('invalid generation 1 stats')
    lines = [f'# {name}', '', '영문 Pokémon Red·Blue 기준', '',
             f'- **도감번호:** {pokemon_id:03d}', f"- **타입:** {' · '.join(type_names)}", '',
             '## 어떤 포켓몬인가요?', '', intro, '', '## 종족치', '',
             '| HP | 공격 | 방어 | 스피드 | 특수 |', '|---:|---:|---:|---:|---:|',
             '| ' + ' | '.join(map(str, values)) + ' |', '', '## 진화', '']
    if not incoming[pokemon_id] and not outgoing[pokemon_id]:
        lines.append(f"{_particle(name, '은', '는')} 영문 Red·Blue에서 진화 관계가 없습니다.")
    else:
        for edge in incoming[pokemon_id]:
            source = pokemon[edge['from_id']]['name_ko']
            lines.append(f"{_particle(name, '은', '는')} {source}에서 진화합니다 (조건: {_condition(edge, items)}).")
        for edge in outgoing[pokemon_id]:
            dest = pokemon[edge['to_id']]['name_ko']
            lines.append(f"{_particle(name, '은', '는')} {_direction(dest)} 진화합니다 (조건: {_condition(edge, items)}).")
        lines.extend(['', '```text'])
        # Enumerate root-to-leaf paths; branches are always shown separately.
        def paths(node, text):
            if not outgoing[node]:
                lines.append(text)
            for edge in outgoing[node]:
                child = edge['to_id']
                paths(child, text + f" ── {_condition(edge, items)} ──▶ " + pokemon[child]['name_ko'])
        for root_id in roots:
            paths(root_id, pokemon[root_id]['name_ko'])
        lines.append('```')
    return '\n'.join(lines) + '\n\n'
