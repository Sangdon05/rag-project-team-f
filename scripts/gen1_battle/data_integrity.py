"""Integrity pins for the bundled English Red/Blue data copies."""
import hashlib
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / 'data' / 'processed'
HASHES = {
    'pokemon.json': 'd0010f89c3408e3a3b9e8bf80303c40bdd9f42199783b8e143419f2dc69ea716',
    'types.json': 'f75cd12064eef9e6ffec367a59aef40e068952f8a6a7e677b2fb2db87ab8c514',
    'type_chart.json': '278f2a56276cb242020d26a66ac28b3f7e6303d06264ca22e5a9e6c9e1a107c2',
    'moves.json': '617fde5ccf1d1de9b4afb8c3bb7eba0b7ce33d766001efea39c315196c2059bf',
    'red_blue_move_damage_classification.json': 'bf11f3e438176111d68c0972025bf674580aae27e7d97226a9262f3db511c89b',
}


def verify_bundle(data_dir=DATA):
    for name, expected in HASHES.items():
        observed = hashlib.sha256((Path(data_dir) / name).read_bytes()).hexdigest()
        if observed != expected:
            raise ValueError(f'bundled data SHA-256 mismatch: {name}: {observed}')
