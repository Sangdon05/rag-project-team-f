"""Portable Red/Blue battle-section renderer; metadata is returned separately.

`root` is the portable pokedex_v3a directory. No network, parent-repository
inputs, or writable state are used. Chart values are nominal type factors.
"""
from math import prod
from pathlib import Path

try:
    from .gen1_battle.gen1_battle_rules import BattleRules
except ImportError:  # Also usable when scripts/ is explicitly on sys.path.
    from gen1_battle.gen1_battle_rules import BattleRules


ATTACK_TERMS = ((2, '효과가 굉장한'), (0.5, '효과가 별로인'), (0, '효과가 없는'))
DEFENSE_ROWS = (('약점', 4), ('약점', 2), ('저항', 0.5), ('저항', 0.25), ('무효', 0))


def _josa(name, consonant, vowel):
    stem = name.rstrip('♀♂')
    if not stem or not 0 <= ord(stem[-1]) - 0xAC00 <= 0x2BA3:
        raise ValueError(f'Cannot determine Korean particle: {name!r}')
    return name + (consonant if (ord(stem[-1]) - 0xAC00) % 28 else vowel)


def _build(root, pokemon_id):
    if type(pokemon_id) is not int or not 1 <= pokemon_id <= 151:
        raise ValueError('pokemon_id must be an integer from 1 to 151')
    rules = BattleRules(Path(root) / 'data' / 'processed')
    pokemon = rules._resolve(rules.pokemon, pokemon_id, 'pokemon')
    own = rules._types(pokemon['types_gen1'], 'types_gen1')
    name = pokemon['name_ko']
    type_rows = {row['name']: row for row in rules.types.values()}
    labels = {key: row['name_ko'] for key, row in type_rows.items()}
    if any(not value for value in labels.values()):
        raise ValueError('Missing Korean type name')
    types = sorted(labels)  # English identifier ordering is stable and matches the pilot.
    moves = sorted({row['id']: row for row in rules.moves.values()}.values(), key=lambda m: m['id'])
    probes = {}
    for move in moves:
        typ = move['values_by_version_group']['red-blue']['type']
        if rules.classifications[move['id']]['classification'] == 'regular_damage':
            probes.setdefault(typ, move)

    # Only level-up and machine records count as the ordinary Red/Blue learnset.
    learned = {}
    by_name = {m['name']: m for m in moves}
    for entry in pokemon['learnset']:
        if entry['version_group'] != 'red-blue' or entry['method'] not in ('level-up', 'machine'):
            continue
        move = by_name[entry['move']]
        typ = move['values_by_version_group']['red-blue']['type']
        if rules.classifications[move['id']]['classification'] == 'regular_damage':
            rank = (entry['method'] != 'level-up', entry['level'] if entry['method'] == 'level-up' else 0, move['id'])
            if typ not in learned or rank < learned[typ][0]:
                learned[typ] = (rank, move)

    unchecked_attack, unchecked_defense = [], []
    for attack in own:
        probe = probes.get(attack)
        if probe is None:
            unchecked_attack.append(attack)
            continue
        for defense in types:
            result = rules.calculate(version='red-blue', user=pokemon_id, target=pokemon_id,
                                     move=probe['id'], target_types=[defense])
            if result['calculation'] != 'basic_type_and_stab' or result['type_effectiveness'] != rules.chart[attack][defense]:
                raise ValueError(f'Attack chart/calculator mismatch: {attack} -> {defense}')
    factors = {}
    for attack in types:
        factor = prod(rules.chart[attack][t] for t in own)
        factors[attack] = factor
        probe = probes.get(attack)
        if probe is None:
            unchecked_defense.append(attack)
            continue
        result = rules.calculate(version='red-blue', user=pokemon_id, target=pokemon_id, move=probe['id'])
        if result['calculation'] != 'basic_type_and_stab' or result['type_effectiveness'] != factor:
            raise ValueError(f'Defense chart/calculator mismatch: {attack}')

    lines = ['## 타입 · 상성', '', '### 자속 보정 (같은 타입 기술 1.5배)', '',
             f"{_josa(name, '이', '가')} 자신의 타입과 같은 **{' 또는 '.join(labels[t] for t in own)} 타입의 일반적인 공격 기술**을 사용하면 자속 보정을 받아 기본 배율에 1.5배가 적용됩니다.", '']
    examples = []
    hypothetical = []
    for typ in own:
        if typ in learned:
            move = learned[typ][1]
            result = rules.calculate(version='red-blue', user=pokemon_id, target=pokemon_id, move=move['id'])
            if result['calculation'] != 'basic_type_and_stab' or result['stab'] != 1.5:
                raise ValueError(f'STAB calculator mismatch: {move["name"]}')
            lines.append(f"- **{labels[typ]} 타입 예시:** {_josa(move['name_ko'], '을', '를')} 사용하면 자속 보정을 받습니다.")
            examples.append({'type': typ, 'move_id': move['id'], 'kind': 'learnable'})
        elif typ in probes:
            move = probes[typ]
            result = rules.calculate(version='red-blue', user=pokemon_id, target=pokemon_id, move=move['id'])
            if result['calculation'] != 'basic_type_and_stab' or result['stab'] != 1.5:
                raise ValueError(f'STAB calculator mismatch: {move["name"]}')
            lines.append(f"- **{labels[typ]} 타입 가정 예시:** {_josa(move['name_ko'], '을', '를')} 사용할 수 있다면 자속 보정을 받습니다. 현재 Red·Blue 습득 데이터에 이 기술을 배우는 기록은 없어 가정입니다.")
            examples.append({'type': typ, 'move_id': move['id'], 'kind': 'hypothetical'})
            hypothetical.append(typ)
        else:
            lines.append(f"- **{labels[typ]} 타입:** 일반적인 공격 기술에 해당하는 자속 보정을 설명한 것이며, 확인된 일반 피해 기술 예시는 없습니다.")
            examples.append({'type': typ, 'move_id': None, 'kind': 'no_regular_damage_probe'})
            hypothetical.append(typ)

    lines += ['', f"### 공격 상성 ({_josa(name, '과', '와')} 같은 타입 기술이 잘 통하는 타입)", '',
              '사용하는 **기술의 타입**에 따라 상대에게 주는 효과가 달라집니다. 표는 상대가 단일 타입일 때의 기본 상성이며, 표에 없는 타입은 1배입니다.', '',
              '| 기술 타입 | 효과가 굉장한(2배) 상대 타입 | 효과가 별로인(0.5배) 상대 타입 | 효과가 없는(0배) 상대 타입 |', '|---|---|---|---|']
    columns = [[] for _ in ATTACK_TERMS]
    for attack in own:
        cells = []
        for i, (factor, _) in enumerate(ATTACK_TERMS):
            names = [labels[t] for t in types if rules.chart[attack][t] == factor]
            columns[i].append((labels[attack], names))
            cells.append(', '.join(names) or '없음')
        lines.append('| ' + ' | '.join([labels[attack], *cells]) + ' |')
    sentences = []
    for (factor, term), column in zip(ATTACK_TERMS, columns):
        prefix = f'{term}({factor}배) 상대 타입은'
        if not any(names for _, names in column):
            sentences.append(prefix + ' 없습니다.')
        else:
            parts = ', '.join(f"{typ} 기술이 {'·'.join(names) if names else '없음'}" for typ, names in column)
            sentences.append(f'{prefix} {parts}입니다.')
    lines += ['', '요약: ' + ' '.join(sentences)]
    if hypothetical:
        lines += ['', f"{'·'.join(labels[t] for t in hypothetical)} 타입 공격 행은 상성을 이해하기 위한 가정입니다."]

    factors_by_row = [(label, factor, [labels[t] for t in types if factors[t] == factor]) for label, factor in DEFENSE_ROWS]
    type_description = (_josa(labels[own[0]], '과', '와') + f' {labels[own[1]]}에 대한 배율을 각각 곱한 값입니다.' if len(own) == 2
                        else f'{labels[own[0]]} 타입에 대한 배율입니다.')
    lines += ['', '### 방어 상성 (약점과 저항)', '',
              f"상대가 어떤 타입의 기술을 쓰는지에 따라 {_josa(name, '이', '가')} 받는 기본 상성 배율이 달라집니다. {type_description}", '',
              '| 구분 | 상대 기술의 타입 | 받는 피해 |', '|---|---|---:|']
    for label, factor, names in factors_by_row:
        lines.append(f"| {label} | {', '.join(names) or '없음'} | {factor}배 |")
    def group(label):
        parts = [f"{'·'.join(names)}({factor}배)" for row_label, factor, names in factors_by_row if label == row_label and names]
        return ', '.join(parts) or '없음'
    immune = factors_by_row[-1][2]
    tail = '·'.join(immune) + '입니다.' if immune else '없습니다.'
    lines += ['', f"요약: {name}의 약점은 {group('약점')}이고, 저항은 {group('저항')}이며, 무효(0배)인 타입은 {tail}", '',
              '위에 없는 타입의 기본 배율은 1배입니다. 실제 피해량은 레벨과 능력치 등 전투 상황에 따라 달라집니다.']
    metadata = {'pokemon_id': pokemon_id, 'calculator_unchecked_attack_types': unchecked_attack,
                'calculator_unchecked_defense_types': unchecked_defense, 'stab_examples': examples}
    return '\n'.join(lines) + '\n\n', metadata


def render_battle(root: Path, pokemon_id: int) -> str:
    """Return the v3a battle Markdown section, with no embedded metadata."""
    return _build(root, pokemon_id)[0]


def battle_metadata(root: Path, pokemon_id: int) -> dict:
    """Expose calculator coverage and example provenance outside Markdown."""
    return _build(root, pokemon_id)[1]
