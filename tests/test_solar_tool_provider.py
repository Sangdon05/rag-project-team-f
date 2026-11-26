"""Exercise the Responses wire contract against fixture transport and stored chunk records."""
import copy
import hashlib
import io
import json
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import Mock, patch

from solar_handoff.src import conversation, providers
from src.pokedex.tools import CLARIFY, MOVE, SEARCH, TEAM, function_tools

MODEL = 'gpt-test-fixture'
ACTUAL_MODEL = MODEL + '-2026-01-01'
GPT_ENV = {
    'OPENAI_CHAT_MODEL': MODEL,
    'OPENAI_API_KEY': 'fixture-only-openai-auth-marker',  # security: allow synthetic fixture, no real credential
}
SOLAR_ENV = {
    'UPSTAGE_EMBEDDING_MODEL': 'document-fixture', 'UPSTAGE_QUERY_MODEL': 'query-fixture',
    'UPSTAGE_API_KEY': 'fixture-only-upstage-auth-marker',  # security: allow synthetic fixture, no real credential
}
TEAM_MEMBERS = ['푸린', '윤겔라', '거북왕', '리자몽']


def tool_item(name, arguments):
    return {'type': 'function_call', 'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False),
            'id': 'fc_fixture', 'call_id': 'call_fixture', 'status': 'completed'}


def selection(*items, **overrides):
    response = {'status': 'completed', 'model': ACTUAL_MODEL, 'truncation': 'disabled',
                'output': list(items), 'error': None, 'incomplete_details': None}
    return response | overrides


def formal_answer(result):
    text = json.dumps(result, ensure_ascii=False)
    return selection({'type': 'message', 'role': 'assistant', 'status': 'completed',
                      'content': [{'type': 'output_text', 'text': text, 'annotations': []}]})


def answer(text, status='answer'):
    return formal_answer({'status': status, 'answer': text})


def roster_args(intent='add', members=TEAM_MEMBERS, replace_member=None, candidate=None):
    return {'intent': intent, 'members': members, 'replace_member': replace_member, 'candidate': candidate}


def question(text):
    return [{'role': 'user', 'content': text}]


def cited_answer(payload):
    data = json.loads(payload['input'])
    return answer('정형 조회에서 제공된 근거입니다. ' + ' '.join(f"[[{row['chunk_id']}]]" for row in data['contexts']))


class FixtureTransport:
    def __init__(self, *replies):
        self.pending = deque(replies)
        self.calls = []

    def __call__(self, url, payload, _key):
        self.calls.append((url, copy.deepcopy(payload)))
        response = self.pending.popleft()
        if isinstance(response, BaseException):
            raise response
        return response(payload) if callable(response) else response


class MemoryCorpus:
    def __init__(self, records, vector_ids=()):
        self.records = records
        self.index_info = [{'id': 'solar', 'config': {'dimension': 1024,
                                                       'document_model': 'document-fixture', 'query_model': 'query-fixture'}}]
        self.rows = [{'chunk_id': cid, 'rank': idx, 'distance': idx / 10} for idx, cid in enumerate(vector_ids, 1)]
        self.opens = 0
        self.searches = 0

    def __enter__(self):
        self.opens += 1
        return self

    def __exit__(self, *_):
        pass

    def search(self, vector):
        self.searches += 1
        if not self.rows:
            raise AssertionError('unexpected similarity search')
        self.last_vector = vector
        return self.rows


class ResponsesToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(conversation.__file__).resolve().parents[1]
        with (root / 'chunks/draft-a-v1/chunks.jsonl').open(encoding='utf-8') as source:
            cls.records = list(map(json.loads, source))

    def service(self, transport, database=None, *, env=None, events=None):
        def database_factory(_env):
            if database is None:
                raise AssertionError('unexpected corpus access')
            return database

        def provider_factory(settings):
            return providers.Providers(settings, require_solar=False, transport=transport)

        return conversation.create_service({**GPT_ENV, **(env or {})}, database_factory=database_factory,
                                           provider_factory=provider_factory,
                                           audit_callback=events.append if events is not None else None)

    def assert_call_counts(self, event, *, answer_calls=1, corpus_reads=1, retrieval=False, method=None, rewrite=0):
        self.assertEqual(event['tool_selection_calls'], 1)
        self.assertEqual(event['tool_calls'], 1)
        self.assertEqual(event['answer_calls'], answer_calls)
        self.assertEqual(event['corpus_reads'], corpus_reads)
        self.assertEqual(event['embedding_calls'], int(retrieval))
        self.assertEqual(event['vector_search_calls'], int(retrieval))
        self.assertEqual(event['bm25_calls'], int(method in ('B', 'C')))
        self.assertEqual(event['rerank_calls'], int(method == 'C'))
        self.assertEqual(event['rewrite_calls'], rewrite)

    def test_required_single_strict_function_tool_and_untouched_json_answer_request(self):
        tools = function_tools()
        self.assertEqual([t['name'] for t in tools], [SEARCH, TEAM, MOVE, CLARIFY])
        expected = [set(), {'intent', 'members', 'replace_member', 'candidate'}, {'move'}, {'reason'}]
        for tool, fields in zip(tools, expected, strict=True):
            self.assertEqual(set(tool), {'type', 'name', 'description', 'parameters', 'strict'})
            self.assertEqual(tool['type'], 'function')
            self.assertIs(tool['strict'], True)
            self.assertIs(tool['parameters']['additionalProperties'], False)
            self.assertEqual(set(tool['parameters']['properties']), fields)
            self.assertEqual(set(tool['parameters']['required']), fields)
        self.assertIn('several Pokémon are named', tools[0]['description'])
        self.assertIn('not opponents', tools[1]['description'])
        reasoning = {'type': 'reasoning', 'id': 'rs_fixture', 'status': None, 'summary': []}
        transport = FixtureTransport(selection(reasoning, tool_item(SEARCH, {})), answer('일반 답변 형식'))
        provider = providers.Providers({**GPT_ENV, **SOLAR_ENV}, transport=transport)
        data = {'question': '피카츄 타입은?'}
        self.assertEqual(provider.choose_tool(conversation.TOOL_SELECTION, data, tools), (SEARCH, {}))
        reply, meta = provider.answer('gpt', data['question'], [])
        self.assertEqual(reply, {'status': 'answer', 'answer': '일반 답변 형식'})
        self.assertEqual(meta['actual_model'], ACTUAL_MODEL)
        (first_url, first), (second_url, second) = transport.calls
        self.assertEqual((first_url, second_url), (providers.OPENAI_URL, providers.OPENAI_URL))
        self.assertEqual(first['tools'], tools)
        self.assertEqual(first['tool_choice'], 'required')
        self.assertIs(first['parallel_tool_calls'], False)
        self.assertNotIn('text', first)
        self.assertEqual(json.loads(first['input']), data)
        self.assertEqual(second['text']['format']['schema'], providers.ANSWER_SCHEMA)
        self.assertEqual(second['instructions'], providers.ANSWER)
        self.assertFalse({'tools', 'tool_choice', 'previous_response_id'} & second.keys())
        self.assertTrue(all(p['model'] == MODEL and p['store'] is False for _, p in transport.calls))

    def test_bad_response_envelopes_never_dispatch_or_retry(self):
        good = tool_item(SEARCH, {})
        invalid = [None, selection(good, status='incomplete'), selection(good, model='not-gpt'),
                   selection(good, model='gpt-'), selection(good, error={'code': 'failure'}),
                   selection(good, truncation='auto'), selection(good, truncated=True),
                   selection(good, incomplete_details={'reason': 'max_output_tokens'}),
                   selection(output={}), selection(), selection('invalid'), selection(good, good),
                   selection(good, {'type': 'message', 'content': [{'type': 'refusal'}]}),
                   selection(good, {'type': 'reasoning', 'id': 'rs_fixture', 'summary': 'no'}),
                   selection(dict(good, status='in_progress')), selection(dict(good, call_id='')),
                   selection(dict(good, name='unregistered')), selection(dict(good, name=[])),
                   selection(dict(good, arguments='{"x": 1, "x": 2}')), selection(dict(good, arguments=[])),
                   selection(dict(good, arguments='[]')), selection(dict(good, arguments='{')),
                   selection(dict(good, arguments='{"x": NaN}')),
                   selection(dict(good, arguments=' ' * (providers.MAX_TOOL_ARGUMENT_BYTES + 1))),
                   TimeoutError('unknown outcome - private raw details')]
        for index, response in enumerate(invalid):
            with self.subTest(index=index):
                database = MemoryCorpus([])
                events = []
                transport = FixtureTransport(response)
                with self.assertRaises(conversation.AnswerGenerationError) as error:
                    self.service(transport, database, events=events).answer(question('피카츄 타입은?'))
                self.assertNotIn('private raw details', str(error.exception))
                self.assertEqual(len(transport.calls), 1)
                self.assertEqual(database.opens, 0)
                self.assertEqual(events, [])

    def test_wire_duplicate_keys_fail_even_before_tool_argument_decoding(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"status":"failed","status":"completed"}')
        with patch.object(providers.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(RuntimeError, 'do not retry automatically'):
                providers.Providers(GPT_ENV, require_solar=False).choose_tool('fixture', {}, function_tools())
        opener.open.assert_called_once()

    def test_tool_arguments_are_independently_validated_before_loading_any_data(self):
        bad_calls = [tool_item(SEARCH, {'query': 'model-generated query'}),
                     tool_item(TEAM, {'intent': 'add', 'members': TEAM_MEMBERS}),
                     tool_item(TEAM, roster_args(members=[True])),
                     tool_item(TEAM, {**roster_args(), 'path': 'data.json'}),
                     tool_item(MOVE, {'move': 7}), tool_item(MOVE, {'move': '불꽃펀치', 'sql': 'ignored'}),
                     tool_item(CLARIFY, {'reason': 'anything'})]
        for call in bad_calls:
            with self.subTest(name=call['name']):
                transport = FixtureTransport(selection(call))
                database = MemoryCorpus([])
                with patch.object(conversation, 'load_store', side_effect=AssertionError('unexpected load')) as load:
                    with self.assertRaises(conversation.AnswerGenerationError):
                        self.service(transport, database).answer(question('확인해 줘'))
                load.assert_not_called()
                self.assertEqual(database.opens, 0)
                self.assertEqual(len(transport.calls), 1)

    def test_team_uses_real_eight_roster_chunks_and_candidate_evidence_without_search(self):
        messages = [*question('푸린 윤겔라 거북왕 리자몽이 내 팀이고 상대는 피카츄야.'),
                    {'role': 'assistant', 'content': '이전 답의 추천은 잠만보예요.'},
                    {'role': 'user', 'content': '내 팀 약점하고 빈자리에 넣을 후보는?'}]
        transport = FixtureTransport(selection(tool_item(TEAM, roster_args())), cited_answer)
        events, database = [], MemoryCorpus(self.records)
        with patch.object(conversation.retrieval, 'bm25', side_effect=AssertionError('BM25 called')) as bm25:
            result = self.service(transport, database, events=events,
                                  env={'SOLAR_RETRIEVAL_METHOD': 'C', 'SOLAR_REWRITE': 'true'}).answer(messages)
        bm25.assert_not_called()
        self.assertEqual((database.opens, database.searches), (1, 0))
        self.assertEqual([url for url, _ in transport.calls], [providers.OPENAI_URL, providers.OPENAI_URL])
        choice, final = [p for _, p in transport.calls]
        self.assertEqual(choice['model'], final['model'])
        self.assertNotIn('previous_response_id', final)
        self.assertNotIn('tools', final)
        data = json.loads(final['input'])
        self.assertEqual(data['messages'], messages)
        self.assertEqual(data['question'], messages[-1]['content'])
        facts = data['verified_facts']
        ids = [r['chunk_id'] for r in data['contexts']]
        expected_roster = [39, 64, 9, 6]
        self.assertEqual([p['pokemon_id'] for p in facts['members']], expected_roster)
        self.assertEqual(ids[:8], [f'pokemon:{n}#{s}' for n in expected_roster for s in ('profile', 'defense_matchup')])
        self.assertEqual(ids[8:], ['pokemon:27#defense_matchup', 'pokemon:28#defense_matchup', 'pokemon:50#defense_matchup'])
        self.assertEqual(ids, [row['chunk_id'] for row in result['sources']])
        self.assertEqual([row['ref'] for row in result['sources']], list(range(1, 12)))
        self.assertEqual({row['source_ref_id'] for row in result['sources']}, {cid.split('#')[0] for cid in ids})
        self.assertEqual(set(result), {'answer', 'mode', 'sources'})
        self.assertEqual(result['mode'], 'rag')
        electric = next(r for r in facts['matchups'] if r['type'] == 'electric')
        self.assertEqual((electric['weak_count'], electric['resists_or_immune_count']), (2, 0))
        event, = events
        self.assertEqual((event['selected_tool'], event['selected_chunk_ids']), (TEAM, ids))
        self.assertEqual((event['retrieval_seed_chunk_ids'], event['expanded_chunk_ids']), ([], []))
        self.assert_call_counts(event)
        self.assertNotIn(messages[-1]['content'], json.dumps(event, ensure_ascii=False))

    def test_regular_move_uses_defense_only_and_keeps_move_source_out_of_numeric_refs(self):
        for label, move_id, expected in [('불꽃펀치', 7, 26), ('10만볼트', 85, 48)]:
            with self.subTest(label=label):
                events, database = [], MemoryCorpus(self.records)
                transport = FixtureTransport(selection(tool_item(MOVE, {'move': label})), cited_answer)
                result = self.service(transport, database, events=events).answer(question(f'{label}에 약한 포켓몬은?'))
                data = json.loads(transport.calls[-1][1]['input'])
                facts = data['verified_facts']
                self.assertEqual(facts['total_weak'], expected)
                self.assertEqual(len(data['contexts']), expected)
                if move_id == 7:
                    four = facts['weakness_groups'][0]
                    self.assertEqual({p['pokemon_id'] for p in four['targets']}, {46, 47})
                    self.assertEqual([g['count'] for g in facts['weakness_groups']], [2, 24])
                self.assertEqual(len(result['sources']), expected)
                self.assertTrue(all(s['chunk_id'].endswith('#defense_matchup') for s in result['sources']))
                self.assertIn(f'`move:{move_id}`', result['answer'])
                self.assertIn(f'red_blue_move_damage_classification.json#/moves/{move_id - 1}', result['answer'])
                self.assertNotIn('embedding', result)
                self.assertEqual((database.opens, database.searches), (1, 0))
                event, = events
                self.assertEqual((event['selected_tool'], event['move_source_id']), (MOVE, f'move:{move_id}'))
                self.assert_call_counts(event)

    def test_full_roster_replacement_uses_outgoing_slot_not_an_addition(self):
        current = [*TEAM_MEMBERS, '이브이', '잠만보']
        selected = roster_args('replace', current, '리자몽', '모래두지')
        transport = FixtureTransport(selection(tool_item(TEAM, selected)), cited_answer)
        messages = question(f"{' '.join(current)}가 우리 팀이야. 리자몽을 모래두지로 바꾸면 어때?")
        result = self.service(transport, MemoryCorpus(self.records)).answer(messages)
        facts = json.loads(transport.calls[1][1]['input'])['verified_facts']
        self.assertEqual((facts['intent'], facts['replace_pokemon_id'], len(facts['members'])), ('replace', 6, 6))
        self.assertEqual(facts['proposed_candidate']['pokemon']['pokemon_id'], 27)
        self.assertEqual(facts['recommendations'], [])
        self.assertEqual(len(result['sources']), 13)
        self.assertEqual(result['sources'][-1]['chunk_id'], 'pokemon:27#defense_matchup')
        self.assertNotIn('embedding', result)

    def test_status_special_unconfirmed_and_zero_targets_do_not_need_db_or_upstage(self):
        cases = [
            ('망각술', 133, '특수가 2단계 오르고 직접 피해는 없어요.', 'answer', 'status', None),
            ('지구던지기', 69, '사용자의 레벨로 정해지는 별도 피해라 일반 상성 배율은 계산하지 않아요.', 'answer', 'special_damage', None),
            ('손가락흔들기', 118, '피해 분류를 확인할 수 없어요.', 'insufficient_evidence', 'unknown', None),
            ('몸통박치기', 33, '방어 상성이 1배를 넘는 대상은 없어요.', 'answer', 'regular_damage', 0),
        ]
        for label, i, text, status, kind, count in cases:
            with self.subTest(label=label):
                events = []
                transport = FixtureTransport(selection(tool_item(MOVE, {'move': label})), answer(text, status))
                result = self.service(transport, events=events).answer(question(f'{label}에 약한 상대가 있어?'))
                self.assertEqual(set(result), {'answer', 'mode', 'sources'})
                self.assertEqual(result['sources'], [])
                self.assertTrue(result['answer'].startswith(text))
                self.assertIn(f'`move:{i}`', result['answer'])
                self.assertIn(f'`{kind}`', result['answer'])
                payload = json.loads(transport.calls[-1][1]['input'])
                self.assertEqual(payload['contexts'], [])
                facts = payload['verified_facts']
                self.assertEqual(facts['total_weak'], count)
                if i == 133:
                    self.assertEqual(facts['effect'], {'stat': 'special', 'applies_to': 'user', 'stage_change': 2})
                    self.assertIn('SPECIAL_UP2_EFFECT', result['answer'])
                if i == 69:
                    self.assertEqual(facts['move']['damage_subtype'], 'user_level')
                self.assertEqual(events[0]['answer_status'], status)
                self.assert_call_counts(events[0], corpus_reads=0)

    def test_unconfirmed_move_does_not_permit_an_affirmative_answer(self):
        transport = FixtureTransport(selection(tool_item(MOVE, {'move': '손가락흔들기'})),
                                     answer('확실한 피해 배율입니다.'))
        with self.assertRaises(conversation.AnswerGenerationError):
            self.service(transport).answer(question('손가락흔들기에 약한 상대가 있어?'))
        self.assertEqual(len(transport.calls), 2)

    def test_ambiguity_invalid_name_and_full_team_return_safe_clarification_only(self):
        full = [*TEAM_MEMBERS, '이브이', '잠만보']
        cases = [(CLARIFY, {'reason': 'team_roster'}, '우리 팀 약점은?', '현재 팀'),
                 (TEAM, roster_args(members=['푸린', 'Jigglypuff']), '푸린 Jigglypuff가 팀이야', '중복 없이'),
                 (TEAM, roster_args(members=['푸린', '피카츄']), '푸린의 팀 약점은?', '현재 팀'),
                 (TEAM, roster_args(members=full), ' '.join(full) + ' 팀에 한 마리 더?', '교체'),
                 (TEAM, roster_args('replace', TEAM_MEMBERS), ' '.join(TEAM_MEMBERS) + ' 중 한 마리 교체', '교체'),
                 (MOVE, {'move': '불꽃펀지'}, '불꽃펀지에 약한 상대?', '기술의 정확한 이름'),
                 (MOVE, {'move': '불꽃펀치'}, '불꽃펀지에 약한 상대?', '기술의 정확한 이름')]
        for tool, arguments, text, expected in cases:
            with self.subTest(tool=tool, text=text):
                transport = FixtureTransport(selection(tool_item(tool, arguments)))
                events = []
                result = self.service(transport, events=events).answer(question(text))
                self.assertIn(expected, result['answer'])
                self.assertEqual(result['sources'], [])
                self.assertNotIn('embedding', result)
                self.assertEqual(len(transport.calls), 1)
                self.assertEqual(events[0]['answer_status'], 'clarification')
                self.assert_call_counts(events[0], answer_calls=0, corpus_reads=0)
        # An earlier assistant-only suggestion is not a confirmed name in the current roster.
        transport = FixtureTransport(selection(tool_item(TEAM, roster_args(members=['푸린', '잠만보']))))
        messages = [*question('우리 팀엔 푸린이 있어.'), {'role': 'assistant', 'content': '잠만보는 어때요?'},
                    {'role': 'user', 'content': '우리 팀 약점은?'}]
        result = self.service(transport).answer(messages)
        self.assertEqual(result['answer'], conversation.CLARIFICATION['team_roster'])
        self.assertEqual(len(transport.calls), 1)

    def test_nested_names_require_confirmation_before_structured_tool_and_corpus(self):
        cases = [
            (TEAM, roster_args('analyze', ['피죤']), '내 팀은 피죤투야. 팀 약점은?', 'team_roster'),
            (TEAM, roster_args('analyze', ['-피죤']), '내 팀은 -피죤투야.', 'team_roster'),
            (TEAM, roster_args('analyze', ['코일']), '레어코일은 내 팀이야.', 'team_roster'),
            (TEAM, roster_args('replace', ['피죤투', '푸린'], '피죤', '모래두지'),
             '피죤투랑 푸린이 내 팀이야. 피죤투를 모래두지로 바꿀까?', 'replacement_target'),
            (TEAM, roster_args('add', ['푸린'], candidate='피죤'),
             '푸린이 내 팀이야. 피죤투를 후보로 넣을까?', 'candidate_name'),
            (MOVE, {'move': '박치기'}, '몸통박치기에 약한 포켓몬은?', 'move_name'),
            (MOVE, {'move': '박치기'}, '로켓박치기를 맞으면 어때?', 'move_name'),
            (MOVE, {'move': '박치기'}, '몸통 박치기에 약한 포켓몬은?', 'move_name'),
            (MOVE, {'move': '박치기-'}, '몸통박치기- 약점은?', 'move_name'),
            (MOVE, {'move': '번개'}, '번개펀치에 약한 포켓몬은?', 'move_name'),
        ]
        for tool, arguments, text, reason in cases:
            with self.subTest(tool=tool, text=text):
                transport = FixtureTransport(selection(tool_item(tool, arguments)), cited_answer)
                events, database = [], MemoryCorpus(self.records)
                with (patch.object(conversation, 'analyze_team', wraps=conversation.analyze_team) as team,
                      patch.object(conversation, 'find_move_weaknesses', wraps=conversation.find_move_weaknesses) as move):
                    result = self.service(transport, database, events=events).answer(question(text))
                self.assertEqual(result, {'answer': conversation.CLARIFICATION[reason], 'mode': 'rag', 'sources': []})
                team.assert_not_called()
                move.assert_not_called()
                self.assertEqual((database.opens, len(transport.calls)), (0, 1))
                event, = events
                self.assertEqual(event['answer_status'], 'clarification')
                self.assert_call_counts(event, answer_calls=0, corpus_reads=0)

    def test_pokemon_names_with_particles_and_independent_mentions_keep_their_ids(self):
        history = [*question('내 팀은 피죤투랑 피죤이야.'),
                   {'role': 'assistant', 'content': '두 마리 모두 확인할게요.'},
                   {'role': 'user', 'content': '그 팀의 약점은?'}]
        candidate_history = [*question('푸린이 내 팀이야.'),
                             {'role': 'assistant', 'content': '피죤투도 있지만, 피죤이 후보예요.'},
                             {'role': 'user', 'content': '그 후보를 넣으면 어때?'}]
        cases = [
            (question('피죤투는 내 팀원이야. 약점은?'), roster_args('analyze', ['피죤투']), [18], None, None),
            (question('피죤이 내 팀원이야. 약점은?'), roster_args('analyze', ['피죤']), [17], None, None),
            (history, roster_args('analyze', ['피죤투', '피죤']), [18, 17], None, None),
            (question('피죤투랑 피죤이 팀이야. 피죤을 푸린으로 바꿀까?'),
             roster_args('replace', ['피죤투', '피죤'], '피죤', '푸린'), [18, 17], 17, 39),
            (candidate_history, roster_args('add', ['푸린'], candidate='피죤'), [39], None, 17),
        ]
        for messages, arguments, members, outgoing, candidate in cases:
            with self.subTest(messages=messages):
                transport = FixtureTransport(selection(tool_item(TEAM, arguments)), cited_answer)
                database = MemoryCorpus(self.records)
                result = self.service(transport, database).answer(messages)
                facts = json.loads(transport.calls[1][1]['input'])['verified_facts']
                self.assertEqual([member['pokemon_id'] for member in facts['members']], members)
                self.assertEqual(facts['replace_pokemon_id'], outgoing)
                proposal = facts['proposed_candidate']
                self.assertEqual(proposal['pokemon']['pokemon_id'] if proposal else None, candidate)
                ids = [f'pokemon:{i}#{section}' for i in members for section in ('profile', 'defense_matchup')]
                if candidate is not None:
                    ids.append(f'pokemon:{candidate}#defense_matchup')
                self.assertEqual([row['chunk_id'] for row in result['sources']], ids)
                self.assertEqual((database.opens, database.searches, len(transport.calls)), (1, 0, 2))

    def test_move_names_with_particles_and_independent_mentions_keep_their_ids(self):
        history = [*question('몸통박치기 말고 박치기를 말하는 거야.'),
                   {'role': 'assistant', 'content': '어떤 점이 궁금하세요?'},
                   {'role': 'user', 'content': '그 기술에 약한 포켓몬은?'}]
        cases = [
            (question('몸통박치기에 약한 포켓몬은?'), '몸통박치기', 33),
            (question('몸통 박치기에 약한 포켓몬은?'), '몸통 박치기', 33),
            (question('로켓박치기에 약한 포켓몬은?'), '로켓박치기', 130),
            (question('박치기를 쓰면 타입 상성은 어때?'), '박치기', 29),
            (history, '박치기', 29),
        ]
        for messages, name, number in cases:
            with self.subTest(name=name, messages=messages):
                transport = FixtureTransport(selection(tool_item(MOVE, {'move': name})), cited_answer)
                result = self.service(transport).answer(messages)
                facts = json.loads(transport.calls[1][1]['input'])['verified_facts']
                self.assertEqual(facts['move']['move_id'], number)
                self.assertIn(f'`move:{number}`', result['answer'])
                self.assertEqual(len(transport.calls), 2)

    def test_missing_over_budget_mismatched_and_unmentioned_sources_are_not_silently_dropped(self):
        select = selection(tool_item(TEAM, roster_args('analyze')))
        messages = question('푸린 윤겔라 거북왕 리자몽의 팀 약점은?')
        missing = [r for r in self.records if r['chunk_id'] != 'pokemon:39#defense_matchup']
        for records, max_bytes in [(missing, conversation.MAX_CONTEXT_BYTES), (self.records, 10)]:
            events = []
            transport = FixtureTransport(select)
            with patch.object(conversation, 'MAX_CONTEXT_BYTES', max_bytes):
                result = self.service(transport, MemoryCorpus(records), events=events).answer(messages)
            self.assertEqual(result['answer'], conversation.MISSING_EXACT_EVIDENCE)
            self.assertEqual(result['sources'], [])
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(events[0]['answer_status'], 'insufficient_evidence')
            self.assert_call_counts(events[0], answer_calls=0)
        def source_with_override(r):
            if r['chunk_id'] != 'pokemon:39#defense_matchup':
                return r
            content = 'Forged exact record'
            return dict(r, content=content, section='learnset_level',
                        content_sha256=hashlib.sha256(content.encode('utf-8')).hexdigest())

        transport = FixtureTransport(select)
        with self.assertRaises(conversation.AnswerGenerationError):
            records = [source_with_override(r) for r in self.records]
            self.service(transport, MemoryCorpus(records)).answer(messages)
        self.assertEqual(len(transport.calls), 1)
        for citation in ('pokemon:39#profile', 'pokemon:39#learnset_level'):
            transport = FixtureTransport(select, answer(f'근거는 [[{citation}]]입니다.'))
            with self.assertRaises(conversation.AnswerGenerationError):
                self.service(transport, MemoryCorpus(self.records)).answer(messages)
            self.assertEqual(len(transport.calls), 2)

    def test_a_then_b_then_c_use_same_original_history_and_c_reranks_exact_b_top_five(self):
        vector_order = [f'pokemon:{i}#profile' for i in (39, 7, 9, 25, 6)]
        messages = [*question('피카츄를 먼저 봤어.'), {'role': 'assistant', 'content': '이전 응답'},
                    {'role': 'user', 'content': '피카츄랑 꼬부기 타입 각각 알려줘.'}]
        original_query = messages[-1]['content'] + '\n\n이전 질문: ' + messages[0]['content']
        solar = {'model': 'query-fixture', 'data': [{'index': 0, 'embedding': [1] + [0] * 1023}],
                 'usage': {'prompt_tokens': 10, 'total_tokens': 10}}
        lexical_queries = []
        b_seeds = []
        actual_bm25 = conversation.retrieval.bm25
        for method in ('A', 'B', 'C'):
            with self.subTest(method=method):
                events, database = [], MemoryCorpus(self.records, vector_order)
                replies: list[object] = [selection(tool_item(SEARCH, {}))]
                if method == 'C':
                    replies.append(formal_answer({'search_query': original_query}))
                replies.append(solar)
                if method == 'C':
                    replies.append(formal_answer({f'rank_{i}': 6 - i for i in range(1, 6)}))
                replies.append(lambda p: answer('첫 번째 근거입니다. [[' + json.loads(p['input'])['contexts'][0]['chunk_id'] + ']]'))
                transport = FixtureTransport(*replies)

                def capture_bm25(corpus, query):
                    lexical_queries.append(query)
                    return actual_bm25(corpus, query)

                with patch.object(conversation.retrieval, 'bm25', side_effect=capture_bm25):
                    result = self.service(transport, database, events=events,
                                          env={**SOLAR_ENV, 'SOLAR_RETRIEVAL_METHOD': method,
                                               'SOLAR_REWRITE': 'true' if method == 'C' else 'false'}).answer(messages)
                self.assertFalse(transport.pending)
                self.assertEqual((database.opens, database.searches), (1, 1))
                payload = json.loads(transport.calls[-1][1]['input'])
                self.assertEqual(payload['question'], messages[-1]['content'])
                self.assertEqual(payload['messages'], messages)
                self.assertNotIn('verified_facts', payload)
                self.assertEqual(result['embedding'], {'query_model': 'query-fixture', 'document_model': 'document-fixture'})
                event, = events
                self.assertEqual(event['selected_tool'], SEARCH)
                self.assert_call_counts(event, retrieval=True, method=method, rewrite=int(method == 'C'))
                self.assertEqual([p['input'] for url, p in transport.calls if url == providers.SOLAR_URL], [[original_query]])
                ids = event['retrieval_seed_chunk_ids']
                self.assertEqual([row['chunk_id'] for row in payload['contexts'][:5]], ids)
                if method == 'A':
                    self.assertEqual(ids, vector_order)
                elif method == 'B':
                    b_seeds = ids
                    self.assertNotEqual(b_seeds, vector_order)
                else:
                    self.assertEqual(len(b_seeds), 5)
                    rerank = json.loads(transport.calls[-2][1]['input'])
                    self.assertEqual(rerank['question'], messages[-1]['content'])
                    self.assertEqual([r['chunk_id'] for r in rerank['candidates']], b_seeds)
                    self.assertEqual(ids, b_seeds[::-1])
                self.assertEqual(result['sources'][0]['chunk_id'], ids[0])
        self.assertEqual(lexical_queries, [original_query, original_query])


if __name__ == '__main__':
    unittest.main()
