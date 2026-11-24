import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.gen1_battle.gen1_battle_rules import BattleRules, DATA


class BattleRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = BattleRules()

    def calc(self, user: object = 'pikachu', target: object = 'gyarados', move: object = 'thunderbolt', **kwargs):
        return self.rules.calculate(version='red-blue', user=user, target=target, move=move, **kwargs)

    def test_four_times_and_stab(self):
        result = self.calc()
        self.assertEqual((result['type_effectiveness'], result['stab'], result['combined_factor']), (4, 1.5, 6))
        self.assertEqual([x['factor'] for x in result['per_type_effectiveness']], [2, 2])

    def test_immune_normal_ghost(self):
        result = self.calc(user='snorlax', target='gastly', move='tackle')
        self.assertEqual(result['type_effectiveness'], 0)
        self.assertEqual(result['combined_factor'], 0)
        self.assertTrue(result['type_immunity'])

    def test_status_immunity_not_assumed(self):
        result = self.calc(target='geodude', move='thunder-wave')
        self.assertEqual(result['calculation'], 'not_applicable')
        for key in ('stab', 'type_effectiveness', 'combined_factor', 'type_immunity', 'per_type_effectiveness'):
            self.assertIsNone(result[key])

    def test_special_damage_and_called_move_unsupported(self):
        for move, kind in [('sonic-boom', 'special_damage'), ('counter', 'special_damage'), ('metronome', 'unknown'), ('mirror-move', 'unknown')]:
            with self.subTest(move=move):
                result = self.calc(move=move)
                self.assertEqual(result['move']['classification'], kind)
                self.assertEqual(result['calculation'], 'unsupported')
                self.assertIsNone(result['combined_factor'])
                self.assertIsNone(result['type_immunity'])

    def test_type_overrides_korean_and_id(self):
        result = self.calc(user=25, target='130', move='85', user_types=['노말'], target_types=[5, '비행'])
        self.assertEqual(result['user']['types'], ['normal'])
        self.assertEqual(result['target']['types'], ['ground', 'flying'])
        self.assertEqual((result['stab'], result['type_effectiveness']), (1, 0))
        self.assertEqual(result['target']['types_source'], 'override')
        same = self.calc(user='피카츄', target='갸라도스', move='10만볼트')
        self.assertEqual(same['move']['id'], 85)
        self.assertEqual(same['combined_factor'], 6)

    def test_gen1_chart_not_modern(self):
        # Generation I: Ghost attacks do not affect Psychic, and Poison/Bug are mutually super effective.
        self.assertEqual(self.calc(user='gastly', target='abra', move='lick')['type_effectiveness'], 0)
        self.assertEqual(self.calc(target='paras', move='poison-sting')['type_effectiveness'], 4)

    def test_invalid_inputs(self):
        for kwargs in ({'user': 'missing'}, {'target': 999}, {'move': 'missing'}, {'user_types': []},
                       {'target_types': ['fire', '불꽃']}, {'target_types': ['fairy']}, {'user_types': ['fire', 'water', 'grass']}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.calc(**kwargs)
        with self.assertRaisesRegex(ValueError, 'Unsupported version'):
            self.rules.calculate(version='yellow', user=25, target=130, move=85)

    def test_cli_json_and_error(self):
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        cmd = [sys.executable, str(ROOT / 'scripts/gen1_battle/gen1_battle_rules.py'), '--version', 'red-blue', '--user', '피카츄', '--target', '갸라도스', '--move', '10만볼트']
        good = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env=env)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)['combined_factor'], 6)
        cmd[3] = 'yellow'
        bad = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env=env)
        self.assertEqual(bad.returncode, 2)
        self.assertIn('Unsupported version', json.loads(bad.stderr)['error'])

    def test_default_data_and_bundle_integrity(self):
        from scripts.gen1_battle.data_integrity import verify_bundle
        verify_bundle()
        self.assertEqual(DATA, ROOT / 'data/processed')
        self.assertEqual(self.rules.moves['135']['values_by_version_group']['red-blue']['pp'], 10)

    @unittest.skipUnless((ROOT / 'pokeapi/tools').exists(), 'optional pokeapi/tools absent; compatibility entry point unavailable')
    def test_relocated_compatibility_entry_point(self):
        cmd = [sys.executable, str(ROOT / 'pokeapi/tools/compat/gen1_battle_rules.py'), '--version', 'red-blue', '--user', '25', '--target', '130', '--move', '85']
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['combined_factor'], 6)


if __name__ == '__main__':
    unittest.main()
