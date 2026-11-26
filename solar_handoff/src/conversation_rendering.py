"""Server-owned citation numbering and Red/Blue battle summaries for chat."""


class UnselectedSourceError(ValueError):
    """Rendering required a source that was not verified for this answer."""


class NumberedSources:
    def __init__(self, selected):
        self._documents = {row['chunk_id']: row['document_id'] for row in selected}
        self._numbers = {}

    def refs(self, *chunk_ids):
        numbers = []
        for cid in dict.fromkeys(chunk_ids):
            if cid not in self._documents:
                raise UnselectedSourceError('missing selected source')
            numbers.append(self._numbers.setdefault(cid, len(self._numbers) + 1))
        return ' '.join(f'[{n}]' for n in numbers)

    def sources(self):
        return [{'ref': n, 'chunk_id': cid, 'source_ref_id': self._documents[cid]}
                for cid, n in self._numbers.items()]


BATTLE_LIMIT = '기본 방어 상성만 비교하며, 기술 습득 여부나 실제 HP 피해량·승패를 판단하지 않아요.'
STAT_LABELS = {'attack': '공격', 'defense': '방어', 'speed': '스피드', 'special': '특수',
               'accuracy': '명중률', 'evasion': '회피율'}
SPECIAL_DAMAGE = {
    'fixed_20': '피해값이 20으로 정해진 분류예요.',
    'fixed_40': '피해값이 40으로 정해진 분류예요.',
    'user_level': '피해값을 사용자 레벨로 정하는 분류예요.',
    'random_by_level': '사용자 레벨을 기준으로 피해값이 달라지는 분류예요.',
    'half_current_hp_min_1': '상대의 현재 HP 절반(최소 1)을 기준으로 하는 분류예요.',
    'counter': '받은 피해를 바탕으로 반격하는 분류예요.',
    'stored_damage': '누적된 피해를 바탕으로 하는 분류예요.',
    'one_hit_ko': '일격기에 해당해요.',
}


def _candidate_line(candidate, types, refs):
    changes = []
    if candidate['covers_gaps']:
        covered = []
        for row in candidate['covers_gaps']:
            factor = row['multiplier']
            mechanism = '면역' if factor == 0 else '저항'
            covered.append(f"{types[row['type']]} {factor:g}배({mechanism})")
        changes.append(f"기존 방어 공백 보완: {', '.join(covered)}")
    else:
        changes.append('저항·면역으로 보완하는 기존 방어 공백 없음')
    if candidate['gaps_removed_without_new_resistance']:
        removed = ', '.join(types[t] for t in candidate['gaps_removed_without_new_resistance'])
        changes.append(f'새 저항·면역 없이 해소되는 공백: {removed}')
    if candidate['new_uncovered_types']:
        opened = ', '.join(types[t] for t in candidate['new_uncovered_types'])
        changes.append(f'새 방어 공백: {opened}')
    if candidate['increased_weak_slots']:
        increased = ', '.join(f"{types[row['type']]} {row['before']}→{row['after']}마리"
                              for row in candidate['increased_weak_slots'])
        changes.append(f'약점 팀원 증가: {increased}')
    name, evidence = candidate['pokemon']['name_ko'], refs(candidate['defense_chunk_id'])
    return f"- {name} — {'; '.join(changes)} {evidence}"


def render_team(facts, numbering):
    refs = numbering.refs
    members = {row['pokemon_id']: row for row in facts['members']}
    matchups = {row['type']: row for row in facts['matchups']}
    types = {attack: row['name_ko'] for attack, row in matchups.items()}
    lines = ['영문 Red·Blue 팀 명단과 타입']
    for row in members.values():
        labels = '/'.join(types[t] for t in row['types'])
        lines.append(f"- {row['name_ko']}: {labels} {refs(row['profile_chunk_id'])}"
                     f" · 방어 상성표 {refs(row['defense_chunk_id'])}")

    def defender(entry):
        member = members[entry['pokemon_id']]
        return f"{member['name_ko']} {entry['multiplier']:g}배 {refs(member['defense_chunk_id'])}"

    lines.extend(['', '공격 타입별 방어 상성 (1배 제외)'])
    for attack, row in matchups.items():
        coverage = row['resists_or_immune']
        groups = [('약점', row['weak']), ('저항', [p for p in coverage if p['multiplier'] > 0]),
                  ('면역', [p for p in coverage if p['multiplier'] == 0])]
        parts = [f"{label} {', '.join(map(defender, entries))}" for label, entries in groups if entries]
        if parts:
            lines.append(f"- {types[attack]}: {' · '.join(parts)}")
    gaps = facts['uncovered_types']
    summary = ', '.join(f"{types[t]} {matchups[t]['weak_count']}마리" for t in gaps) or '없음'
    defense = refs(*(row['defense_chunk_id'] for row in members.values()))
    lines.extend(['', f'방어 공백 (저항·면역 팀원이 없는 약점, 반복 약점 우선): {summary} {defense}'])

    if facts['intent'] != 'analyze':
        lines.append('')
        if facts['intent'] == 'replace':
            old = members[facts['replace_pokemon_id']]
            lines.append(f"교체 대상: {old['name_ko']} {refs(old['defense_chunk_id'])}")
        else:
            lines.append('빈자리에 한 마리 추가')
        proposal, alternatives = facts['proposed_candidate'], facts['recommendations']
        if proposal is not None:
            lines.append('지정 후보의 방어 변화:')
            lines.append(_candidate_line(proposal, types, refs))
        elif alternatives:
            lines.append('각각 한 마리씩 넣어 비교한 대안 (동시에 넣는 조합이 아니에요):')
            lines.extend(_candidate_line(candidate, types, refs) for candidate in alternatives)
        elif gaps:
            lines.append(f'기존 방어 공백을 저항·면역으로 보완하는 추천 후보가 없어요. {defense}')
        else:
            lines.append(f'현재 방어 공백이 없어 보완 후보를 따로 추천하지 않아요. {defense}')
    lines.extend(['', BATTLE_LIMIT])
    return '\n'.join(lines)


def render_move(facts, numbering, type_label):
    move, evidence = facts['move'], facts['move_evidence']
    kind = move['classification']
    lines = [f"{move['name_ko']} ({type_label} 타입, 영문 Red·Blue)"]
    status = 'answer'
    if kind == 'regular_damage':
        lines.append(f"일반 피해 기술이에요. 기본 방어 상성이 1배를 넘는 대상은 총 {facts['total_weak']}마리예요.")
        for group in facts['weakness_groups']:
            targets = ', '.join(f"{p['name_ko']} {numbering.refs(p['defense_chunk_id'])}"
                                for p in group['targets'])
            lines.append(f"- {group['multiplier']:g}배 ({group['count']}마리): {targets}")
        lines.extend(['', BATTLE_LIMIT])
    elif kind == 'status':
        lines.append('변화기라 직접 피해를 주지 않아요.')
        effect = facts['effect']
        if effect is not None:
            who = {'user': '사용자', 'target': '대상'}[effect['applies_to']]
            delta = effect['stage_change']
            direction = '상승' if delta > 0 else '하락'
            lines.append(f"확인된 효과: {who}의 {STAT_LABELS[effect['stat']]} {abs(delta)}단계 {direction}.")
        else:
            lines.append('이 조회에서는 세부 효과를 확인하지 못했어요.')
    elif kind == 'special_damage':
        lines.append('일반 타입 배율을 적용해 약점 대상이나 실제 HP 피해량을 계산하지 않는 별도 피해 기술이에요.')
        lines.append(SPECIAL_DAMAGE.get(move['damage_subtype'], '세부 피해 규칙은 이 조회에서 확인하지 못했어요.'))
    elif kind == 'unknown':
        status = 'insufficient_evidence'
        lines.append('피해 분류가 미확정이라 피해 규칙·배율·약점 대상을 확인할 수 없어요.')
    else:
        raise ValueError('invalid structured move classification')
    # The move table is not a Pokémon document and never receives a number.
    lines.extend(['', f"기술 분류 근거: `{evidence['record_id']}` · `{evidence['path']}#{evidence['pointer']}` · "
                  f"`{kind}` (`{evidence['raw_effect']}`)."])
    return '\n'.join(lines), status
