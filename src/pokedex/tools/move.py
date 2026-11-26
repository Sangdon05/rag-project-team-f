"""Move damage class and nominal defensive type weaknesses in Red/Blue."""
import re
from typing import Any

from ..store import VERSION, PokedexStore
from . import MoveArguments

# The classification table records pointers to the pinned stat handler. Only
# the unambiguous, source-reviewed stat-stage tags are interpreted here; the
# other status effects' mechanics are outside this lookup's verified scope.
STAT_EFFECT = re.compile(r'(ATTACK|DEFENSE|SPEED|SPECIAL|ACCURACY|EVASION)_(UP|DOWN)([12])_EFFECT\Z')
STAT_HANDLER = '/engine/battle/effects.asm#L351-L538'


def _stat_effect(evidence):
    match = STAT_EFFECT.fullmatch(evidence['raw_effect'])
    if (match is None or evidence['review_grade'] != 'source_reviewed'
            or not any(ref.endswith(STAT_HANDLER) for ref in evidence['execution_refs'])):
        return None
    stat, direction, stages = match.groups()
    return {'stat': stat.lower(), 'applies_to': 'user' if direction == 'UP' else 'target',
            'stage_change': int(stages) * (1 if direction == 'UP' else -1)}


def find_move_weaknesses(store: PokedexStore, args: MoveArguments) -> dict[str, Any]:
    number = store.resolve_move(args.move)
    if number is None:
        return {'error': 'clarification_required', 'reason': 'move_name'}
    move, evidence = store.move(number)
    kind = move['classification']
    result = {'version': VERSION, 'move': move, 'move_evidence': evidence,
              'calculation': 'unconfirmed' if kind == 'unknown' else 'unsupported',
              'effect': None, 'weakness_groups': None,
              'total_weak': None, 'evidence_chunk_ids': []}
    if kind == 'status':
        result.update(calculation='not_applicable', effect=_stat_effect(evidence))
    elif kind == 'regular_damage':
        groups = {}
        for i in store.pokemon_ids:
            factor = store.defense_multiplier(i, move['type'])
            if factor > 1:
                target = store.pokemon(i)
                groups.setdefault(factor, []).append(dict(target.facts(),
                                                          defense_chunk_id=target.chunk_id('defense_matchup')))
        grouped = [{'multiplier': factor, 'targets': targets, 'count': len(targets)}
                   for factor, targets in sorted(groups.items(), reverse=True)]
        result.update(calculation='defense_type_chart_only', weakness_groups=grouped,
                      total_weak=sum(row['count'] for row in grouped),
                      evidence_chunk_ids=[target['defense_chunk_id'] for row in grouped for target in row['targets']])
    return result
