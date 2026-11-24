"""Integrity pins for the bundled English Red/Blue data copies."""
import hashlib
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / 'data' / 'processed'
HASHES = {
    'pokemon.json': 'd22b59c07ac37ddf3921aaaeaec2e0a9b267e0e20496c7ddd66fc3fca495eb19',
    'types.json': 'c2b7d025d042b39b07d184abf800fa40e5121cd26badd9c3cd95b4d00aa654e0',
    'type_chart.json': 'ffb8346a5e22d2ff4474558cc0378938b28bc2de1bdddb9722c4758f853272ef',
    'moves.json': '617fde5ccf1d1de9b4afb8c3bb7eba0b7ce33d766001efea39c315196c2059bf',
    'red_blue_move_damage_classification.json': 'bf11f3e438176111d68c0972025bf674580aae27e7d97226a9262f3db511c89b',
}


def verify_bundle(data_dir=DATA):
    for name, expected in HASHES.items():
        observed = hashlib.sha256((Path(data_dir) / name).read_bytes()).hexdigest()
        if observed != expected:
            raise ValueError(f'bundled data SHA-256 mismatch: {name}: {observed}')
