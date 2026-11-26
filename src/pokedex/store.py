"""Single read boundary for the root, hash-pinned English Red/Blue battle bundle."""
from dataclasses import dataclass
from functools import lru_cache
from math import prod
from unicodedata import category, normalize

from scripts.gen1_battle.gen1_battle_rules import COMMIT, BattleRules, _key

VERSION = 'red-blue'
DEX_SIZE = 151
MOVE_COUNT = 165
CLASSIFICATION_PATH = 'data/processed/red_blue_move_damage_classification.json'
CLASSIFICATION_SOURCE = 'processed:red_blue_move_damage_classification'


def name_key(value):
    """Use BattleRules' separators and case folding, with Unicode composition."""
    if (not isinstance(value, str) or not 1 <= len(value) <= 80
            or any(category(char).startswith('C') for char in value)):
        return ''
    return _key(normalize('NFKC', value).replace('’', "'"))


def _names(records, aliases=None):
    names = {}
    pairs = [(name, row['id']) for row in records.values() for name in (row['name'], row['name_ko'])]
    for name, number in pairs + list((aliases or {}).items()):
        key = name_key(name)
        if not key or number not in records or names.setdefault(key, number) != number:
            raise ValueError('invalid or ambiguous Pokédex name data')
    return names


def _containing_aliases(names, value):
    key = name_key(value)
    number = names.get(key)
    if number is None:
        return ()
    return tuple(alias for alias, other in names.items()
                 if other != number and len(alias) > len(key) and key in alias)


@dataclass(frozen=True, slots=True)
class Pokemon:
    id: int
    name: str
    name_ko: str
    types: tuple[str, ...]

    def chunk_id(self, section):
        return f'pokemon:{self.id}#{section}'

    def facts(self):
        return {'pokemon_id': self.id, 'name': self.name, 'name_ko': self.name_ko,
                'types': list(self.types)}


class PokedexStore:
    def __init__(self):
        # The default BattleRules data path is root data/processed/. BattleRules
        # calls verify_bundle() before loading and checks the pinned source revision.
        rules = BattleRules()
        pokemon_rows = {row['id']: row for row in rules.pokemon.values()}
        self._move_rows = {row['id']: row for row in rules.moves.values()}
        self.pokemon_ids = tuple(range(1, DEX_SIZE + 1))
        if set(pokemon_rows) != set(self.pokemon_ids) or set(self._move_rows) != set(range(1, MOVE_COUNT + 1)):
            raise ValueError('incomplete Pokédex battle data')
        self._pokemon_names = _names(pokemon_rows, {
            'Nidoran♀': 29, 'Nidoran♂': 32, 'Mr. Mime': 122, "Farfetch'd": 83,
        })
        self._move_names = _names(self._move_rows)
        self._pokemon = {i: Pokemon(i, row['name'], row['name_ko'], tuple(row['types_gen1']))
                         for i, row in pokemon_rows.items()}
        self.attack_types = tuple(rules.chart)
        self._type_labels = {row['name']: row['name_ko'] for row in rules.types.values()}
        for row in self._pokemon.values():
            if (not 1 <= len(row.types) <= 2 or len(set(row.types)) != len(row.types)
                    or any(t not in self._type_labels for t in row.types)):
                raise ValueError('invalid Red/Blue defense types')
        # Same per-defending-type product as BattleRules.calculate, without an
        # invented attacker/move when the requested quantity is defense alone.
        self._defense = {i: {attack: prod(chart[t] for t in row.types)
                            for attack, chart in rules.chart.items()}
                         for i, row in self._pokemon.items()}
        self._classifications = rules.classifications
        # BattleRules inserts each classification in its source array order.
        self._classification_positions = {i: pos for pos, i in enumerate(self._classifications)}

    def pokemon(self, number):
        return self._pokemon[number]

    def resolve_pokemon(self, value):
        return self._pokemon_names.get(name_key(value))

    def resolve_move(self, value):
        return self._move_names.get(name_key(value))

    def longer_pokemon_aliases(self, value):
        """Normalized names of distinct Pokémon that can contain this name."""
        return _containing_aliases(self._pokemon_names, value)

    def longer_move_aliases(self, value):
        """Normalized names of distinct moves that can contain this name."""
        return _containing_aliases(self._move_names, value)

    def type_label(self, attack):
        return self._type_labels[attack]

    def defense_multiplier(self, number, attack):
        return self._defense[number][attack]

    def move(self, number):
        row = self._move_rows[number]
        classification = self._classifications[number]
        return {
            'move_id': number, 'name': row['name'], 'name_ko': row['name_ko'],
            'type': row['values_by_version_group'][VERSION]['type'],
            'classification': classification['classification'],
            'damage_subtype': classification['damage_subtype'],
        }, {
            'record_id': f'move:{number}', 'source_id': CLASSIFICATION_SOURCE,
            'path': CLASSIFICATION_PATH, 'pointer': f'/moves/{self._classification_positions[number]}',
            'source_commit': COMMIT, 'review_grade': classification['review_grade'],
            'raw_effect': classification['raw_effect'], 'move_table': classification['evidence']['move_table'],
            'execution_refs': tuple(classification['evidence']['execution']),
        }


@lru_cache(maxsize=1)
def load_store():
    """Validate the bundled snapshot on first use; no external data paths are accepted."""
    return PokedexStore()
