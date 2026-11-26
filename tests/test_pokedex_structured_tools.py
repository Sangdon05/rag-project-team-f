"""Offline correctness of Red/Blue calculations and evidence selection."""
import json
import unittest
from pathlib import Path
from unicodedata import normalize
from unittest.mock import patch

from scripts.gen1_battle.data_integrity import DATA, verify_bundle
from scripts.gen1_battle.gen1_battle_rules import COMMIT, BattleRules
from src.pokedex.store import CLASSIFICATION_PATH, PokedexStore, load_store
from src.pokedex.tools import MoveArguments, TeamArguments
from src.pokedex.tools.move import find_move_weaknesses
from src.pokedex.tools.team import analyze_team

ROOT = Path(__file__).resolve().parents[1]
TEAM = ['푸린', '윤겔라', '거북왕', '리자몽']


class StructuredToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = load_store()
        cls.rules = BattleRules()
        base = ROOT / 'solar_handoff/chunks/draft-a-v1/chunks.jsonl'
        with base.open(encoding='utf-8') as stream:
            cls.chunks = {row['chunk_id']: row for row in map(json.loads, stream)}
        cls.classifications = json.loads((ROOT / CLASSIFICATION_PATH).read_text(encoding='utf-8'))

    def team(self, intent='analyze', members=TEAM, replace_member=None, candidate=None):
        return analyze_team(self.store, TeamArguments.model_validate(
            {'intent': intent, 'members': members, 'replace_member': replace_member, 'candidate': candidate}))

    def move(self, name):
        return find_move_weaknesses(self.store, MoveArguments(move=name))

    def assert_move_record(self, facts, number, kind):
        evidence = facts['move_evidence']
        self.assertEqual(evidence['source_commit'], COMMIT)
        self.assertEqual(evidence['record_id'], f'move:{number}')
        self.assertEqual(evidence['path'], CLASSIFICATION_PATH)
        record = self.classifications['moves'][int(evidence['pointer'].split('/')[-1])]
        self.assertEqual((record['id'], record['classification']), (number, kind))
        self.assertEqual(record['raw_effect'], evidence['raw_effect'])
        self.assertEqual(record['evidence']['move_table'], evidence['move_table'])
        self.assertEqual(record['evidence']['execution'], list(evidence['execution_refs']))

    def test_loader_uses_the_root_hash_pins_and_fails_closed(self):
        with patch('scripts.gen1_battle.gen1_battle_rules.verify_bundle', wraps=verify_bundle) as spy:
            PokedexStore()
        spy.assert_called_once_with(DATA)
        self.assertEqual(DATA, ROOT / 'data/processed')
        self.assertEqual(self.store.pokemon_ids, tuple(range(1, 152)))
        with patch('scripts.gen1_battle.gen1_battle_rules.verify_bundle', side_effect=ValueError('bad digest')):
            with self.assertRaisesRegex(ValueError, 'bad digest'):
                PokedexStore()

    def test_names_are_exact_after_normalization_and_nidoran_is_not_guessed(self):
        for label, expected in [(' ＫＡＤＡＢＲＡ ', 64), (normalize('NFD', '리자몽'), 6),
                                ('Mr. Mime', 122), ('Farfetch’d', 83), ('니드런♀', 29),
                                ('Nidoran ♂', 32), ('니드런', None), ('Nidoran', None),
                                ('06', None), ('리자못', None), ('리자몽\x00', None), ('../리자몽', None)]:
            with self.subTest(label=label):
                self.assertEqual(self.store.resolve_pokemon(label), expected)
        for name in ('불꽃 펀치', ' ＦＩＲＥ_PUNCH ', 'Fire Punch'):
            self.assertEqual(self.store.resolve_move(name), 7)
        self.assertEqual(self.move('불꽃펀지'), {'error': 'clarification_required', 'reason': 'move_name'})

    def test_team_roster_uses_eight_direct_chunks_and_covers_repeated_electric_gap(self):
        result = self.team(intent='add')
        roster = [39, 64, 9, 6]
        members = result['members']
        self.assertEqual([p['pokemon_id'] for p in members], roster)
        self.assertEqual([p['types'] for p in members], [['normal'], ['psychic'], ['water'], ['fire', 'flying']])
        member_ids = [f'pokemon:{i}#{s}' for i in roster for s in ('profile', 'defense_matchup')]
        self.assertEqual(result['evidence_chunk_ids'][:8], member_ids)
        for chunk_id in member_ids:
            row = self.chunks[chunk_id]
            self.assertEqual(row['document_id'], chunk_id.split('#')[0])
            self.assertIn(self.store.pokemon(row['pokemon_id']).name_ko, row['content'])
        self.assertEqual(len(result['matchups']), 15)
        electric = next(row for row in result['matchups'] if row['type'] == 'electric')
        self.assertEqual(electric['weak'], [{'pokemon_id': 9, 'multiplier': 2}, {'pokemon_id': 6, 'multiplier': 2}])
        self.assertEqual((electric['weak_count'], electric['resists_or_immune_count']), (2, 0))
        self.assertEqual(electric['resists_or_immune'], [])
        self.assertEqual(result['uncovered_types'], ['electric', 'rock'])
        ghost = next(row for row in result['matchups'] if row['type'] == 'ghost')
        self.assertIn({'pokemon_id': 39, 'multiplier': 0}, ghost['resists_or_immune'])
        recommendations = result['recommendations']
        self.assertEqual([p['pokemon']['pokemon_id'] for p in recommendations], [27, 28, 50])
        for candidate in recommendations:
            i = candidate['pokemon']['pokemon_id']
            cid = f'pokemon:{i}#defense_matchup'
            self.assertNotIn(i, roster)
            self.assertEqual(candidate['covers_gaps'][0], {'type': 'electric', 'multiplier': 0})
            self.assertEqual(candidate['defense_chunk_id'], cid)
            self.assertIn(cid, result['evidence_chunk_ids'][8:])
            self.assertIn('전기', self.chunks[cid]['content'])
            self.assertIn('0배', self.chunks[cid]['content'])
            self.assertEqual(candidate['increased_weak_slots'][0], {'type': 'water', 'before': 1, 'after': 2})
        self.assertEqual(result, self.team(intent='add'))
        self.assertEqual(self.team()['recommendations'], [])

    def test_invalid_roster_full_team_and_swap_target_ask_for_confirmation(self):
        for members in ([], ['푸린', 'Jigglypuff'], ['니드런'], ['피카추'], ['피카츄'] * 7):
            with self.subTest(members=members):
                self.assertEqual(self.team(members=members), {'error': 'clarification_required', 'reason': 'team_roster'})
        full = [*TEAM, '이브이', '잠만보']
        for intent, outgoing in [('add', None), ('replace', None), ('replace', '피카츄')]:
            self.assertEqual(self.team(intent, full, outgoing),
                             {'error': 'clarification_required', 'reason': 'replacement_target'})
        self.assertEqual(self.team('replace', full, '리자몽', '거북왕')['reason'], 'candidate_name')
        swapped = self.team('replace', full, '리자몽', '모래두지')
        self.assertEqual((len(swapped['members']), swapped['replace_pokemon_id']), (6, 6))
        self.assertEqual(swapped['recommendations'], [])
        self.assertEqual(swapped['proposed_candidate']['pokemon']['pokemon_id'], 27)
        self.assertIn({'type': 'electric', 'multiplier': 0}, swapped['proposed_candidate']['covers_gaps'])
        self.assertIn('pokemon:27#defense_matchup', swapped['evidence_chunk_ids'])

    def test_candidate_exposes_new_gaps_without_calling_them_coverage(self):
        # Pinsir accepts some attacks less well than the current mono-Normal team.
        facts = self.team('add', ['푸린'], candidate='쁘사이저')
        proposed = facts['proposed_candidate']
        self.assertIn('rock', proposed['new_uncovered_types'])
        self.assertIn({'type': 'fighting', 'multiplier': 0.5}, proposed['covers_gaps'])
        self.assertIn({'type': 'fire', 'before': 0, 'after': 1}, proposed['increased_weak_slots'])
        facts = self.team('add', ['푸린'], candidate='잠만보')
        self.assertEqual(facts['proposed_candidate']['covers_gaps'], [])
        self.assertEqual(facts['recommendations'], [])

    def test_fire_punch_groups_match_battle_rules_and_real_defense_chunks(self):
        facts = self.move('불꽃펀치')
        self.assertEqual((facts['move']['move_id'], facts['move']['type'], facts['move']['classification']),
                         (7, 'fire', 'regular_damage'))
        self.assertEqual(facts['calculation'], 'defense_type_chart_only')
        self.assert_move_record(facts, 7, 'regular_damage')
        expected = {2: set(), 4: set()}
        for i in range(1, 152):
            factor = self.rules.calculate(version='red-blue', user=25, target=i, move=7)['type_effectiveness']
            if factor > 1:
                expected[factor].add(i)
        groups = facts['weakness_groups']
        self.assertEqual([(g['multiplier'], g['count']) for g in groups], [(4, 2), (2, 24)])
        self.assertEqual(expected[4], {46, 47})
        self.assertEqual(facts['total_weak'], 26)
        self.assertEqual(len(set(facts['evidence_chunk_ids'])), 26)
        for group in groups:
            self.assertEqual({r['pokemon_id'] for r in group['targets']}, expected[group['multiplier']])
            for target in group['targets']:
                i = target['pokemon_id']
                row = self.chunks[target['defense_chunk_id']]
                self.assertEqual((row['pokemon_id'], row['section'], row['version_group']), (i, 'defense_matchup', 'red-blue'))
                self.assertIn('불꽃', row['content'])

    def test_empty_and_maximum_regular_target_lists_are_not_truncated(self):
        no_weak = self.move('몸통박치기')
        self.assertEqual((no_weak['total_weak'], no_weak['weakness_groups'], no_weak['evidence_chunk_ids']), (0, [], []))
        counts = [self.move(row['name'])['total_weak'] for row in self.classifications['moves']
                  if row['classification'] == 'regular_damage']
        self.assertEqual(max(counts), 48)
        self.assertEqual(len(self.move('10만볼트')['evidence_chunk_ids']), 48)

    def test_status_special_and_unconfirmed_never_get_ordinary_multipliers(self):
        for name, i, kind, subtype, calculation in [
            ('망각술', 133, 'status', 'no_direct_attack_damage', 'not_applicable'),
            ('지구던지기', 69, 'special_damage', 'user_level', 'unsupported'),
            ('손가락흔들기', 118, 'unknown', None, 'unconfirmed'),
        ]:
            with self.subTest(name=name):
                result = self.move(name)
                self.assertEqual((result['move']['move_id'], result['move']['classification'], result['calculation']),
                                 (i, kind, calculation))
                if subtype is not None:
                    self.assertEqual(result['move']['damage_subtype'], subtype)
                self.assertEqual((result['weakness_groups'], result['total_weak'], result['evidence_chunk_ids']),
                                 (None, None, []))
                self.assert_move_record(result, i, kind)
        status = self.move('망각술')
        self.assertEqual(status['effect'], {'stat': 'special', 'applies_to': 'user', 'stage_change': 2})
        self.assertEqual(status['move_evidence']['raw_effect'], 'SPECIAL_UP2_EFFECT')
        self.assertTrue(any(ref.endswith('/engine/battle/effects.asm#L351-L538')
                            for ref in status['move_evidence']['execution_refs']))
        self.assertIsNone(self.move('손가락흔들기')['effect'])


if __name__ == '__main__':
    unittest.main()
