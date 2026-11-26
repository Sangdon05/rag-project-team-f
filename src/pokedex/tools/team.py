"""Deterministic roster coverage, from defensive type multipliers only."""
from typing import Any

from ..store import VERSION, PokedexStore
from . import TeamArguments

MAX_TEAM = 6
MAX_RECOMMENDATIONS = 3


def _clarify(reason):
    return {'error': 'clarification_required', 'reason': reason}


def _defense(store, roster):
    summary = []
    for attack in store.attack_types:
        weak, covered = [], []
        for number in roster:
            factor = store.defense_multiplier(number, attack)
            if factor != 1:
                (weak if factor > 1 else covered).append({'pokemon_id': number, 'multiplier': factor})
        summary.append({'type': attack, 'name_ko': store.type_label(attack),
                        'weak': weak, 'weak_count': len(weak),
                        'resists_or_immune': covered, 'resists_or_immune_count': len(covered)})
    return summary


def _uncovered(summary):
    rows = [row for row in summary if row['weak'] and not row['resists_or_immune']]
    rows.sort(key=lambda row: (-len(row['weak']), -sum(p['multiplier'] == 4 for p in row['weak']), row['type']))
    return {row['type']: len(row['weak']) for row in rows}


def _candidate(store, before, remaining, gaps, incoming):
    after = _defense(store, (*remaining, incoming))
    after_gaps = _uncovered(after)
    covers = [{'type': attack, 'multiplier': store.defense_multiplier(incoming, attack)}
              for attack in gaps if store.defense_multiplier(incoming, attack) < 1]
    removed = [attack for attack in gaps if attack not in after_gaps
               and store.defense_multiplier(incoming, attack) >= 1]
    opened = [attack for attack in after_gaps if attack not in gaps]
    more_weak = [{'type': new['type'], 'before': len(old['weak']), 'after': len(new['weak'])}
                 for old, new in zip(before, after, strict=True) if len(new['weak']) > len(old['weak'])]
    # First prefer coverage of more frequently repeated weaknesses. Break ties
    # by new uncovered exposure, added weak slots, stronger coverage, then Pokédex ID.
    covered_counts = [gaps[row['type']] for row in covers]
    score = (tuple(-covered_counts.count(n) for n in range(MAX_TEAM, 0, -1)),
             sum(after_gaps[t] for t in opened), len(opened),
             sum(row['after'] - row['before'] for row in more_weak),
             sum(row['multiplier'] for row in covers), incoming)
    pokemon = store.pokemon(incoming)
    return score, {'pokemon': pokemon.facts(), 'covers_gaps': covers,
                   'gaps_removed_without_new_resistance': removed, 'new_uncovered_types': opened,
                   'increased_weak_slots': more_weak, 'defense_chunk_id': pokemon.chunk_id('defense_matchup')}


def analyze_team(store: PokedexStore, args: TeamArguments) -> dict[str, Any]:
    """Validate the entire team before computing any facts or offering a swap."""
    if not 1 <= len(args.members) <= MAX_TEAM:
        return _clarify('team_roster')
    roster = [store.resolve_pokemon(name) for name in args.members]
    if None in roster or len(set(roster)) != len(roster):
        return _clarify('team_roster')
    outgoing, proposed = None, None
    if args.intent == 'replace':
        outgoing = store.resolve_pokemon(args.replace_member)
        if outgoing not in roster:
            return _clarify('replacement_target')
    elif args.replace_member is not None or (args.intent == 'add' and len(roster) == MAX_TEAM):
        return _clarify('replacement_target')
    if args.candidate is not None:
        proposed = store.resolve_pokemon(args.candidate)
        if proposed is None or proposed in roster or args.intent == 'analyze':
            return _clarify('candidate_name')

    members = []
    for number in roster:
        member = store.pokemon(number)
        members.append(dict(member.facts(), profile_chunk_id=member.chunk_id('profile'),
                            defense_chunk_id=member.chunk_id('defense_matchup')))
    evidence = [member[key] for member in members for key in ('profile_chunk_id', 'defense_chunk_id')]
    before = _defense(store, roster)
    gaps = _uncovered(before)
    recommendations = []
    proposal = None
    if args.intent != 'analyze' and (gaps or proposed is not None):
        remaining = tuple(number for number in roster if number != outgoing)
        if proposed is not None:
            _, proposal = _candidate(store, before, remaining, gaps, proposed)
            evidence.append(proposal['defense_chunk_id'])
        else:
            ranked = [_candidate(store, before, remaining, gaps, i) for i in store.pokemon_ids if i not in roster]
            recommendations = [row for _, row in sorted(ranked, key=lambda item: item[0])
                               if row['covers_gaps']][:MAX_RECOMMENDATIONS]
            evidence.extend(row['defense_chunk_id'] for row in recommendations)

    return {'version': VERSION, 'basis': 'defense_type_chart_only', 'intent': args.intent,
            'members': members, 'matchups': before, 'uncovered_types': list(gaps),
            'replace_pokemon_id': outgoing, 'recommendations': recommendations,
            'proposed_candidate': proposal, 'evidence_chunk_ids': evidence}
