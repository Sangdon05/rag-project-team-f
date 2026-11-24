"""Basic type-chart and STAB factors for English Red/Blue, not a damage simulator."""
import argparse
import json
import math
import re
import sys
from pathlib import Path

if __package__:
    from .data_integrity import DATA, verify_bundle
else:
    from data_integrity import DATA, verify_bundle
COMMIT = 'ba9c0568f64ae602fadda577a08c66639f93082a'


def _key(value):
    return re.sub(r'[\s_-]+', '', str(value).strip().casefold())


class BattleRules:
    def __init__(self, data_dir=DATA):
        path = Path(data_dir)
        try:
            if path.resolve() == DATA.resolve():
                verify_bundle(path)
            def load(name):
                return json.loads((path / name).read_text(encoding='utf-8'))
            pokemon, moves, types = (load(name) for name in ('pokemon.json', 'moves.json', 'types.json'))
            self.chart = load('type_chart.json')
            classification = load('red_blue_move_damage_classification.json')
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f'Cannot load battle data: {exc}') from exc
        if classification.get('source_commit') != COMMIT:
            raise ValueError('Classification source commit mismatch')
        self.pokemon = self._index(pokemon, 'pokemon')
        self.moves = self._index(moves, 'move')
        self.types = self._index(types, 'type')
        names = {row['name'] for row in types}
        if len(names) != 15 or set(self.chart) != names:
            raise ValueError('Type chart attack types are incomplete')
        for attack, row in self.chart.items():
            if set(row) != names or any(type(value) not in (int, float) or value not in (0, 0.5, 1, 2) for value in row.values()):
                raise ValueError(f'Invalid type chart row: {attack}')
        self.classifications = {}
        for row in classification['moves']:
            move = self.moves.get(_key(row['id']))
            if move is None or move['id'] in self.classifications or row['name'] != move['name']:
                raise ValueError(f'Classification identity mismatch: {row.get("id")}')
            source_type = row['source_move']['type'].lower().removesuffix('_type')
            local_type = move['values_by_version_group']['red-blue']['type']
            if source_type != local_type:
                raise ValueError(f'Move type differs from Red/Blue source: {move["name"]}')
            if row['classification'] not in ('regular_damage', 'status', 'special_damage', 'unknown'):
                raise ValueError(f'Unknown classification: {move["name"]}')
            self.classifications[move['id']] = row
        if set(self.classifications) != {row['id'] for row in moves}:
            raise ValueError('Move classification coverage incomplete')

    @staticmethod
    def _index(rows, label):
        index = {}
        for row in rows:
            for value in (row['id'], row['name'], row['name_ko']):
                if value is None or value == '':
                    continue
                key = _key(value)
                if key in index and index[key] is not row:
                    raise ValueError(f'Ambiguous {label} identifier: {value}')
                index[key] = row
        return index

    @staticmethod
    def _resolve(index, value, label):
        if not isinstance(value, (str, int)) or isinstance(value, bool) or not _key(value):
            raise ValueError(f'Invalid {label} identifier: {value!r}')
        result = index.get(_key(value))
        if result is None:
            raise ValueError(f'Unknown {label}: {value!r}')
        return result

    def _types(self, values, label):
        if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 2:
            raise ValueError(f'{label} must contain one or two types')
        result = [self._resolve(self.types, value, 'type')['name'] for value in values]
        if len(set(result)) != len(result):
            raise ValueError(f'{label} contains duplicate types')
        return result

    def calculate(self, *, version, user, target, move, user_types=None, target_types=None):
        if version != 'red-blue':
            raise ValueError(f'Unsupported version: {version!r}; expected red-blue')
        attacker = self._resolve(self.pokemon, user, 'user pokemon')
        defender = self._resolve(self.pokemon, target, 'target pokemon')
        technique = self._resolve(self.moves, move, 'move')
        attack_types = self._types(attacker['types_gen1'] if user_types is None else user_types, 'user_types')
        defense_types = self._types(defender['types_gen1'] if target_types is None else target_types, 'target_types')
        move_type = self._resolve(self.types, technique['values_by_version_group'][version]['type'], 'move type')['name']
        entry = self.classifications[technique['id']]
        kind = entry['classification']
        result = {
            'version': version,
            'user': {'id': attacker['id'], 'name': attacker['name'], 'name_ko': attacker['name_ko'], 'types': attack_types, 'types_source': 'base_gen1' if user_types is None else 'override'},
            'target': {'id': defender['id'], 'name': defender['name'], 'name_ko': defender['name_ko'], 'types': defense_types, 'types_source': 'base_gen1' if target_types is None else 'override'},
            'move': {'id': technique['id'], 'name': technique['name'], 'name_ko': technique['name_ko'], 'type': move_type, 'classification': kind, 'damage_subtype': entry['damage_subtype']},
            'calculation': 'basic_type_and_stab' if kind == 'regular_damage' else ('not_applicable' if kind == 'status' else 'unsupported'),
            'stab': None, 'type_effectiveness': None, 'combined_factor': None, 'type_immunity': None,
            'per_type_effectiveness': None,
            'notice': 'Nominal type-chart and STAB factors only; not actual damage, move ownership, hit success, or full battle effects.'
        }
        if kind == 'regular_damage':
            factors = [{'defending_type': typ, 'factor': self.chart[move_type][typ]} for typ in defense_types]
            effect = math.prod(x['factor'] for x in factors)
            stab = 1.5 if move_type in attack_types else 1.0
            result.update(stab=stab, type_effectiveness=effect, combined_factor=stab * effect,
                          type_immunity=(effect == 0), per_type_effectiveness=factors)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, help='Only red-blue is supported')
    parser.add_argument('--user', required=True, help='Pokemon ID or English/Korean name')
    parser.add_argument('--target', required=True, help='Pokemon ID or English/Korean name')
    parser.add_argument('--move', required=True, help='Move ID or English/Korean name')
    parser.add_argument('--user-types', nargs='+', help='Override current user type(s), 1 or 2 IDs/names')
    parser.add_argument('--target-types', nargs='+', help='Override current target type(s), 1 or 2 IDs/names')
    parser.add_argument('--data-dir', type=Path, default=DATA, help='Data directory (default: bundled, hash-checked data)')
    args = parser.parse_args(argv)
    try:
        result = BattleRules(args.data_dir).calculate(version=args.version, user=args.user, target=args.target, move=args.move,
                                         user_types=args.user_types, target_types=args.target_types)
    except (ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
