"""Exercise the Responses wire contract against fixture transport and stored chunk records."""
import copy
import hashlib
import io
import json
import logging
import re
import unittest
from collections import deque
from contextlib import ExitStack, redirect_stderr
from http.client import HTTPMessage
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.concurrency import run_in_threadpool

from api.chat.application.service import AskService
from api.chat.domain.conversation import ConversationLimits
from api.chat.infrastructure.rag_generator import RagAnswerGenerator
from api.chat.presentation.dependencies import provide_ask_service
from api.chat.presentation.router import router as chat_router
from api.error_handlers import register_exception_handlers
from solar_handoff.src import cli, conversation, providers
from src.pokedex.tools import CLARIFY, MOVE, SEARCH, TEAM, MoveArguments, function_tools

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
EMBEDDING = {'query_model': 'query-fixture', 'document_model': 'document-fixture'}
SOLAR_RESPONSE = {'model': 'query-fixture', 'data': [{'index': 0, 'embedding': [1] + [0] * 1023}],
                  'usage': {'prompt_tokens': 10, 'total_tokens': 10}}
TEAM_MEMBERS = ['푸린', '윤겔라', '거북왕', '리자몽']


def tool_item(name, arguments):
    return {'type': 'function_call', 'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False),
            'id': 'fc_fixture', 'call_id': 'call_fixture', 'status': 'completed'}


def selection(*items, **overrides):
    response = {'status': 'completed', 'model': ACTUAL_MODEL, 'truncation': 'disabled',
                'output': list(items), 'error': None, 'incomplete_details': None}
    return response | overrides


def raw_answer(text):
    return selection({'type': 'message', 'role': 'assistant', 'status': 'completed',
                      'content': [{'type': 'output_text', 'text': text, 'annotations': []}]})


def formal_answer(result):
    return raw_answer(json.dumps(result, ensure_ascii=False))


def answer(text, status='answer'):
    return formal_answer({'status': status, 'answer': text})


def claim(text, *chunk_ids):
    return {'text': text, 'source_ids': list(chunk_ids)}


def chat_answer(*claims, status='answer'):
    return formal_answer({'status': status, 'claims': list(claims)})


def roster_args(intent='add', members=TEAM_MEMBERS, replace_member=None, candidate=None):
    return {'intent': intent, 'members': members, 'replace_member': replace_member, 'candidate': candidate}


def question(text):
    return [{'role': 'user', 'content': text}]


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

    def assert_numbered_sources(self, result, ids):
        self.assertEqual(result['sources'], [
            {'ref': n, 'chunk_id': cid, 'source_ref_id': cid.split('#')[0]} for n, cid in enumerate(ids, 1)
        ])
        visible = list(dict.fromkeys(map(int, re.findall(r'\[([0-9]+)\]', result['answer']))))
        self.assertEqual(visible, list(range(1, len(ids) + 1)))

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

    def test_cli_trace_still_validates_its_original_answer_text_and_citations(self):
        cid = 'pokemon:25#profile'
        records = [row for row in self.records if row['chunk_id'] == cid]
        text = f'피카츄는 전기 타입이에요. [[{cid}]]'
        transport = FixtureTransport(SOLAR_RESPONSE, answer(text))

        class CliDatabase(MemoryCorpus, cli.retrieval.Database):
            def __init__(self, _env):
                super().__init__(records, (cid,))

        class CliProvider(providers.Providers):
            def __init__(self, env):
                super().__init__(env, transport=transport)

        trace = cli.execute('피카츄 타입은?', 'A', 'gpt', False, {**GPT_ENV, **SOLAR_ENV},
                            database_factory=CliDatabase, provider_factory=CliProvider)
        self.assertEqual((trace['status'], trace['answer']), ('completed', text))
        self.assertEqual(trace['citations']['cited_ids'], [cid])
        self.assertEqual(trace['citations']['status'], 'ids_valid_claim_support_unreviewed')
        self.assertEqual([url for url, _ in transport.calls], [providers.SOLAR_URL, providers.OPENAI_URL])
        wire = transport.calls[1][1]
        self.assertEqual(wire['text']['format']['schema']['required'], ['status', 'answer'])
        self.assertFalse({'tools', 'tool_choice'} & wire.keys())
        self.assertFalse(transport.pending)

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
        transport = FixtureTransport(selection(tool_item(TEAM, roster_args())))
        events, database = [], MemoryCorpus(self.records)
        with patch.object(conversation.retrieval, 'bm25', side_effect=AssertionError('BM25 called')) as bm25:
            result = self.service(transport, database, events=events,
                                  env={'SOLAR_RETRIEVAL_METHOD': 'C', 'SOLAR_REWRITE': 'true'}).answer(messages)
        bm25.assert_not_called()
        self.assertEqual((database.opens, database.searches), (1, 0))
        (url, choice), = transport.calls
        self.assertEqual(url, providers.OPENAI_URL)
        self.assertNotIn('text', choice)
        data = json.loads(choice['input'])
        self.assertEqual(set(data), {'messages', 'question'})
        self.assertEqual(data['messages'], messages)
        self.assertEqual(data['question'], messages[-1]['content'])
        expected_roster = [39, 64, 9, 6]
        ids = [f'pokemon:{n}#{s}' for n in expected_roster for s in ('profile', 'defense_matchup')]
        ids.extend(['pokemon:27#defense_matchup', 'pokemon:28#defense_matchup', 'pokemon:50#defense_matchup'])
        self.assert_numbered_sources(result, ids)
        self.assertEqual(set(result), {'answer', 'mode', 'sources'})
        self.assertEqual(result['mode'], 'rag')
        text = result['answer']
        self.assertNotIn('**', text)
        self.assertIn('푸린: 노말 [1] · 방어 상성표 [2]', text)
        self.assertIn('리자몽: 불꽃/비행 [7] · 방어 상성표 [8]', text)
        self.assertIn('전기: 약점 거북왕 2배 [6], 리자몽 2배 [8]', text)
        self.assertIn('바위: 약점 리자몽 4배 [8]', text)
        self.assertIn('저항 리자몽 0.25배 [8]', text)
        self.assertIn('고스트: 면역 푸린 0배 [2]', text)
        self.assertIn('전기 2마리, 바위 1마리 [2] [4] [6] [8]', text)
        self.assertIn('각각 한 마리씩', text)
        for label, ref in [('모래두지', 9), ('고지', 10), ('디그다', 11)]:
            line = next(row for row in text.splitlines() if row.startswith(f'- {label} — '))
            self.assertIn('전기 0배(면역), 바위 0.5배(저항)', line)
            self.assertIn('약점 팀원 증가: 물 1→2마리', line)
            self.assertTrue(line.endswith(f'[{ref}]'))
        self.assertNotIn('피카츄', text)
        self.assertNotIn('잠만보', text)
        event, = events
        self.assertEqual((event['selected_tool'], event['selected_chunk_ids']), (TEAM, ids))
        self.assertEqual((event['retrieval_seed_chunk_ids'], event['expanded_chunk_ids']), ([], []))
        self.assert_call_counts(event, answer_calls=0)
        self.assertNotIn(messages[-1]['content'], json.dumps(event, ensure_ascii=False))

    def test_regular_move_uses_defense_only_and_keeps_move_source_out_of_numeric_refs(self):
        for label, move_id, expected in [('불꽃펀치', 7, 26), ('10만볼트', 85, 48)]:
            with self.subTest(label=label):
                events, database = [], MemoryCorpus(self.records)
                transport = FixtureTransport(selection(tool_item(MOVE, {'move': label})))
                result = self.service(transport, database, events=events).answer(question(f'{label}에 약한 포켓몬은?'))
                store = conversation.load_store()
                facts = conversation.find_move_weaknesses(store, MoveArguments(move=label))
                self.assertEqual(facts['total_weak'], expected)
                self.assertIn(f'총 {expected}마리', result['answer'])
                if move_id == 7:
                    four = facts['weakness_groups'][0]
                    self.assertEqual({p['pokemon_id'] for p in four['targets']}, {46, 47})
                    self.assertEqual([g['count'] for g in facts['weakness_groups']], [2, 24])
                self.assertEqual(len(result['sources']), expected)
                self.assertTrue(all(s['chunk_id'].endswith('#defense_matchup') for s in result['sources']))
                self.assert_numbered_sources(result, facts['evidence_chunk_ids'])
                ref_by_id = {row['chunk_id']: row['ref'] for row in result['sources']}
                expected_groups = []
                for group in facts['weakness_groups']:
                    targets = ', '.join(f"{p['name_ko']} [{ref_by_id[p['defense_chunk_id']]}]" for p in group['targets'])
                    expected_groups.append(f"- {group['multiplier']:g}배 ({group['count']}마리): {targets}")
                self.assertEqual([line for line in result['answer'].splitlines() if line.startswith('- ')],
                                 expected_groups)
                self.assertIn(f'`move:{move_id}`', result['answer'])
                self.assertIn(f'red_blue_move_damage_classification.json#/moves/{move_id - 1}', result['answer'])
                self.assertNotIn('embedding', result)
                self.assertEqual((database.opens, database.searches), (1, 0))
                self.assertEqual([url for url, _ in transport.calls], [providers.OPENAI_URL])
                event, = events
                self.assertEqual((event['selected_tool'], event['move_source_id']), (MOVE, f'move:{move_id}'))
                self.assert_call_counts(event, answer_calls=0)

    def test_full_roster_replacement_uses_outgoing_slot_not_an_addition(self):
        current = [*TEAM_MEMBERS, '이브이', '잠만보']
        selected = roster_args('replace', current, '리자몽', '모래두지')
        transport = FixtureTransport(selection(tool_item(TEAM, selected)))
        messages = question(f"{' '.join(current)}가 우리 팀이야. 리자몽을 모래두지로 바꾸면 어때?")
        result = self.service(transport, MemoryCorpus(self.records)).answer(messages)
        ids = [f'pokemon:{n}#{s}' for n in (39, 64, 9, 6, 133, 143) for s in ('profile', 'defense_matchup')]
        self.assert_numbered_sources(result, [*ids, 'pokemon:27#defense_matchup'])
        self.assertIn('교체 대상: 리자몽 [8]', result['answer'].splitlines())
        self.assertIn('지정 후보의 방어 변화:', result['answer'])
        self.assertIn('모래두지 — 기존 방어 공백 보완: 전기 0배', result['answer'])
        self.assertIn('새 방어 공백: 풀, 벌레; 약점 팀원 증가: 풀 1→2마리 [13]', result['answer'])
        self.assertNotIn('빈자리에 한 마리 추가', result['answer'])
        self.assertNotIn('고지', result['answer'])
        self.assertEqual(len(transport.calls), 1)
        self.assertNotIn('embedding', result)

    def test_swap_distinguishes_removing_a_gap_from_new_resistance(self):
        args = roster_args('replace', ['푸린', '리자몽'], '리자몽', '잠만보')
        transport = FixtureTransport(selection(tool_item(TEAM, args)))
        result = self.service(transport, MemoryCorpus(self.records)).answer(
            question('푸린과 리자몽 중 리자몽을 잠만보로 교체하면 어때?'))
        self.assert_numbered_sources(result, ['pokemon:39#profile', 'pokemon:39#defense_matchup',
                                             'pokemon:6#profile', 'pokemon:6#defense_matchup',
                                             'pokemon:143#defense_matchup'])
        candidate = next(line for line in result['answer'].splitlines() if line.startswith('- 잠만보'))
        self.assertIn('저항·면역으로 보완하는 기존 방어 공백 없음', candidate)
        self.assertIn('새 저항·면역 없이 해소되는 공백: 바위, 전기, 얼음, 물', candidate)
        self.assertIn('새 방어 공백: 격투; 약점 팀원 증가: 격투 1→2마리 [5]', candidate)
        self.assertEqual(len(transport.calls), 1)

    def test_status_special_unconfirmed_and_zero_targets_do_not_need_db_or_upstage(self):
        cases = [
            ('망각술', 133, '사용자의 특수 2단계 상승', 'answer', 'status'),
            ('최면술', 95, '세부 효과를 확인하지 못했어요', 'answer', 'status'),
            ('지구던지기', 69, '피해값을 사용자 레벨로 정하는 분류', 'answer', 'special_damage'),
            ('용의분노', 82, '피해값이 40으로 정해진 분류', 'answer', 'special_damage'),
            ('손가락흔들기', 118, '피해 분류가 미확정', 'insufficient_evidence', 'unknown'),
            ('몸통박치기', 33, '기본 방어 상성이 1배를 넘는 대상은 총 0마리', 'answer', 'regular_damage'),
        ]
        for label, i, text, status, kind in cases:
            with self.subTest(label=label):
                events = []
                transport = FixtureTransport(selection(tool_item(MOVE, {'move': label})))
                result = self.service(transport, events=events).answer(question(f'{label}에 약한 상대가 있어?'))
                self.assertEqual(set(result), {'answer', 'mode', 'sources'})
                self.assert_numbered_sources(result, [])
                self.assertIn(text, result['answer'])
                self.assertIn(f'`move:{i}`', result['answer'])
                self.assertIn(f'`{kind}`', result['answer'])
                self.assertIn(f'red_blue_move_damage_classification.json#/moves/{i - 1}', result['answer'])
                self.assertEqual([url for url, _ in transport.calls], [providers.OPENAI_URL])
                if kind == 'status':
                    self.assertIn('직접 피해를 주지 않아요', result['answer'])
                if kind == 'special_damage':
                    self.assertIn('일반 타입 배율을 적용해 약점 대상이나 실제 HP 피해량을 계산하지 않는', result['answer'])
                if kind != 'regular_damage':
                    self.assertNotRegex(result['answer'], r'\d+마리|\d+배')
                if i == 133:
                    self.assertIn('SPECIAL_UP2_EFFECT', result['answer'])
                self.assertEqual(events[0]['answer_status'], status)
                self.assert_call_counts(events[0], corpus_reads=0, answer_calls=0)

    def test_unconfirmed_move_does_not_permit_an_affirmative_answer(self):
        transport = FixtureTransport(selection(tool_item(MOVE, {'move': '손가락흔들기'})),
                                     answer('확실한 피해 배율입니다.'))
        result = self.service(transport).answer(question('손가락흔들기에 약한 상대가 있어?'))
        self.assertIn('피해 규칙·배율·약점 대상을 확인할 수 없어요', result['answer'])
        self.assertNotIn('확실한 피해 배율', result['answer'])
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(len(transport.pending), 1)

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
                transport = FixtureTransport(selection(tool_item(tool, arguments)))
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
                transport = FixtureTransport(selection(tool_item(TEAM, arguments)))
                database = MemoryCorpus(self.records)
                result = self.service(transport, database).answer(messages)
                store = conversation.load_store()
                if outgoing is not None:
                    self.assertIn(f'교체 대상: {store.pokemon(outgoing).name_ko} ', result['answer'])
                else:
                    self.assertNotIn('교체 대상:', result['answer'])
                ids = [f'pokemon:{i}#{section}' for i in members for section in ('profile', 'defense_matchup')]
                if candidate is not None:
                    self.assertIn(f'- {store.pokemon(candidate).name_ko} — ', result['answer'])
                    ids.append(f'pokemon:{candidate}#defense_matchup')
                self.assert_numbered_sources(result, ids)
                self.assertEqual((database.opens, database.searches, len(transport.calls)), (1, 0, 1))

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
                transport = FixtureTransport(selection(tool_item(MOVE, {'move': name})))
                result = self.service(transport).answer(messages)
                self.assertIn(f'`move:{number}`', result['answer'])
                self.assertEqual(len(transport.calls), 1)

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
        # Even a valid but unrelated defense chunk cannot replace a required one.
        analyze = conversation.analyze_team

        def wrong_evidence(store, args):
            facts = analyze(store, args)
            facts['evidence_chunk_ids'].remove('pokemon:39#defense_matchup')
            facts['evidence_chunk_ids'].append('pokemon:7#defense_matchup')
            return facts

        transport = FixtureTransport(select)
        with patch.object(conversation, 'analyze_team', side_effect=wrong_evidence):
            result = self.service(transport, MemoryCorpus(self.records)).answer(messages)
        self.assertEqual(result, {'answer': conversation.MISSING_EXACT_EVIDENCE, 'mode': 'rag', 'sources': []})
        self.assertEqual(len(transport.calls), 1)

    def test_missing_candidate_or_move_target_evidence_never_produces_a_partial_list(self):
        cases = [(tool_item(TEAM, roster_args()), ' '.join(TEAM_MEMBERS) + ' 팀의 추가 후보는?',
                  'pokemon:27#defense_matchup'),
                 (tool_item(MOVE, {'move': '불꽃펀치'}), '불꽃펀치 약점 대상은?', 'pokemon:46#defense_matchup')]
        for item, text, missing in cases:
            with self.subTest(tool=item['name']):
                records = [row for row in self.records if row['chunk_id'] != missing]
                transport = FixtureTransport(selection(item))
                result = self.service(transport, MemoryCorpus(records)).answer(question(text))
                self.assertEqual(result, {'answer': conversation.MISSING_EXACT_EVIDENCE, 'mode': 'rag', 'sources': []})
                self.assertEqual(len(transport.calls), 1)

    def test_a_then_b_then_c_use_same_original_history_and_c_reranks_exact_b_top_five(self):
        vector_order = [f'pokemon:{i}#profile' for i in (39, 7, 9, 25, 6)]
        messages = [*question('피카츄를 먼저 봤어.'), {'role': 'assistant', 'content': '이전 응답'},
                    {'role': 'user', 'content': '피카츄랑 꼬부기 타입 각각 알려줘.'}]
        original_query = messages[-1]['content'] + '\n\n이전 질문: ' + messages[0]['content']
        lexical_queries = []
        b_seeds = []
        actual_bm25 = conversation.retrieval.bm25

        def answer_from_contexts(payload):
            ids = [row['chunk_id'] for row in json.loads(payload['input'])['contexts']]
            return chat_answer(claim('첫 번째 근거입니다.', ids[0]), claim('두 번째 근거입니다.', ids[1]))

        for method in ('A', 'B', 'C'):
            with self.subTest(method=method):
                events, database = [], MemoryCorpus(self.records, vector_order)
                replies: list[object] = [selection(tool_item(SEARCH, {}))]
                if method == 'C':
                    replies.append(formal_answer({'search_query': original_query}))
                replies.append(SOLAR_RESPONSE)
                if method == 'C':
                    replies.append(formal_answer({f'rank_{i}': 6 - i for i in range(1, 6)}))
                replies.append(answer_from_contexts)
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
                wire = transport.calls[-1][1]
                payload = json.loads(wire['input'])
                self.assertEqual(payload['question'], messages[-1]['content'])
                self.assertEqual(payload['messages'], messages)
                self.assertNotIn('verified_facts', payload)
                self.assertFalse({'tools', 'tool_choice', 'previous_response_id'} & wire.keys())
                output_format = wire['text']['format']
                self.assertIs(output_format['strict'], True)
                self.assertEqual(output_format['type'], 'json_schema')
                schema = output_format['schema']
                block = schema['properties']['claims']['items']
                for obj, fields in ((schema, {'status', 'claims'}), (block, {'text', 'source_ids'})):
                    self.assertEqual(set(obj['required']), fields)
                    self.assertEqual(set(obj['properties']), fields)
                    self.assertIs(obj['additionalProperties'], False)
                allowed = [row['chunk_id'] for row in payload['contexts']]
                self.assertEqual(block['properties']['source_ids']['items'], {'type': 'string', 'enum': allowed})
                self.assertNotIn('pokemon:151#profile', allowed)
                self.assertEqual(result['embedding'], EMBEDDING)
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
                self.assert_numbered_sources(result, ids[:2])
                self.assertEqual(result['answer'], '첫 번째 근거입니다. [1]\n\n두 번째 근거입니다. [2]')
        self.assertEqual(lexical_queries, [original_query, original_query])

    def chat_client(self, service):
        # Use the real route, adapter and error mapping without loading api.main or .env.
        app = FastAPI()
        app.include_router(chat_router)
        register_exception_handlers(app)
        generator = RagAnswerGenerator(lambda: service, run_in_threadpool)
        ask_service = AskService(generator, ConversationLimits(20))
        app.dependency_overrides[provide_ask_service] = lambda: ask_service
        return TestClient(app)

    def followup(self, client, text='후속 질문용 원문 표식'):
        first = question('피카츄 타입은?')
        with self.assertNoLogs('uvicorn.error', level='WARNING'):
            reply = client.post('/api/v1/chat', json={'messages': first})
        self.assertEqual(reply.status_code, 200)
        return [*first, {'role': 'assistant', 'content': reply.json()['data']['answer']}, *question(text)]

    def assert_failed_http(self, response):
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {
            'success': False, 'error_code': 'ANSWER_GENERATION_FAILED',
            'message': '답변을 생성하지 못했습니다. 잠시 후 다시 시도하세요.',
        })

    def assert_failure_log(self, logs, stage, failure_type, **extra):
        record, = logs.records
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertIsNone(record.exc_info)
        self.assertIsNone(record.stack_info)
        self.assertEqual(json.loads(record.getMessage()), {
            'event': 'conversation_answer_failed', 'stage': stage, 'failure_type': failure_type, **extra,
        })

    def test_http_structured_sources_keep_numbering_and_document_keys_without_embedding(self):
        team = selection(tool_item(TEAM, roster_args('analyze', ['푸린'])))
        move = selection(tool_item(MOVE, {'move': '10만볼트'}))
        status = selection(tool_item(MOVE, {'move': '망각술'}))
        transport = FixtureTransport(team, move, status)
        db = MemoryCorpus(self.records)
        with (self.chat_client(self.service(transport, db)) as client,
              self.assertNoLogs('uvicorn.error', level='WARNING')):
            replies = [client.post('/api/v1/chat', json={'messages': question(text)}) for text in (
                '푸린이 내 팀원이야. 약점은?', '10만볼트에 약한 포켓몬은?', '망각술에 약한 포켓몬은?',
            )]
        self.assertEqual([reply.status_code for reply in replies], [200, 200, 200])
        first, second, third = [reply.json()['data'] for reply in replies]
        for data in (first, second, third):
            self.assertEqual(set(data), {'answer', 'mode', 'sources'})
            self.assertEqual(data['mode'], 'rag')
            self.assertNotIn('**', data['answer'])
        self.assertEqual(first['sources'], [
            {'ref': n, 'chunk_id': f'pokemon:39#{section}', 'source_ref_id': '039'}
            for n, section in enumerate(('profile', 'defense_matchup'), 1)
        ])
        self.assertIn('격투: 약점 푸린 2배 [2]', first['answer'])
        self.assertIn('총 48마리', second['answer'])
        self.assertEqual([row['ref'] for row in second['sources']], list(range(1, 49)))
        self.assertTrue(all(row['source_ref_id'] == row['chunk_id'].split(':')[1].split('#')[0].zfill(3)
                            for row in second['sources']))
        self.assertEqual(third['sources'], [])
        self.assertIn('`move:133`', third['answer'])
        self.assertEqual([url for url, _ in transport.calls], [providers.OPENAI_URL] * 3)
        self.assertEqual((db.opens, db.searches), (2, 0))

    def test_http_followup_citation_only_rejection_is_one_warning_and_a_safe_200(self):
        cid, previous = 'pokemon:7#profile', 'pokemon:25#profile'
        private_text, private_chunk = 'fixture-unverified-model-body', 'fixture-private-chunk-body'
        prior = '피카츄는 전기 타입이에요.'
        partial = 'fixture-valid-claim-that-must-also-be-discarded'
        malformed_id = 'fixture-invalid-source-token'
        fixture_dsn = 'postgresql://fixture.invalid/fixture'
        select = selection(tool_item(SEARCH, {}))
        records = [dict(row, content=private_chunk) for row in self.records if row['chunk_id'] in (cid, previous)]
        self.assertEqual({row['chunk_id'] for row in records}, {cid, previous})
        cases = [
            ('missing_field', 'missing_citation', {'text': private_text}),
            ('empty_list', 'missing_citation', claim(private_text)),
            ('empty_answer', 'missing_citation', None),
            ('markup', 'invalid_citation_format', claim(private_text + ' [987]', cid)),
            ('malformed_id', 'invalid_citation_format', claim(private_text, malformed_id)),
            ('unselected', 'citation_not_selected', claim(private_text, previous)),
        ]
        for case, reason, bad_claim in cases:
            with self.subTest(case=case):
                bad = chat_answer(claim(partial, cid), bad_claim) if bad_claim is not None else chat_answer()
                bad['usage'] = {'raw': [fixture_dsn, GPT_ENV['OPENAI_API_KEY']]}
                first = chat_answer(claim(prior, previous))
                first['output'].insert(0, {'type': 'reasoning', 'id': 'rs_fixture', 'summary': []})
                transport = FixtureTransport(select, SOLAR_RESPONSE, first, select, SOLAR_RESPONSE, bad)
                db = MemoryCorpus(records, (previous,))
                service = self.service(transport, db, env={**SOLAR_ENV, 'SOLAR_RETRIEVAL_METHOD': 'A',
                                                          'DATABASE_URL': fixture_dsn})
                with self.chat_client(service) as client:
                    messages = self.followup(client)
                    self.assertEqual(messages[1]['content'], prior + ' [1]')
                    # The first turn's citation still exists in storage but isn't allowed on this turn.
                    db.rows = [{'chunk_id': cid, 'rank': 1, 'distance': 0.1}]
                    with (self.assertLogs('uvicorn.error', level='WARNING') as logs,
                          self.assertNoLogs('api.error_handlers', level='ERROR'),
                          self.assertNoLogs('solar_handoff.conversation.audit', level='INFO')):
                        reply = client.post('/api/v1/chat', json={'messages': messages})
                self.assertEqual(reply.status_code, 200)
                self.assertEqual(reply.json(), {'success': True, 'data': {
                    'answer': conversation.UNVERIFIED_EVIDENCE, 'mode': 'rag', 'sources': [], 'embedding': EMBEDDING,
                }})
                record, = logs.records
                self.assertEqual(record.levelno, logging.WARNING)
                self.assertIsNone(record.exc_info)
                self.assertIsNone(record.stack_info)
                self.assertEqual(json.loads(record.getMessage()), {
                    'event': 'conversation_citation_rejected', 'stage': 'citation_validation', 'reason': reason,
                })
                output = reply.text + '\n'.join(logs.output)
                for marker in (cid, previous, private_text, private_chunk, partial, malformed_id,
                               fixture_dsn, GPT_ENV['OPENAI_API_KEY'], messages[-1]['content']):
                    self.assertNotIn(marker, output)
                self.assertEqual((db.opens, db.searches), (2, 2))
                self.assertEqual([url for url, _ in transport.calls],
                                 [providers.OPENAI_URL, providers.SOLAR_URL, providers.OPENAI_URL] * 2)
                self.assertFalse(transport.pending)

    def test_http_followup_failure_is_logged_once_at_the_failing_stage(self):
        private = 'fixture-only-private-detail'
        search = selection(tool_item(SEARCH, {}))
        clarify = selection(tool_item(CLARIFY, {'reason': 'reference'}))
        solar = SOLAR_RESPONSE
        no_citation = chat_answer(claim(private))
        vector_ids = [f'pokemon:{i}#profile' for i in (39, 7, 9, 25, 6)]
        records = [dict(row, content=private) for row in self.records if row['chunk_id'] in vector_ids]
        cases = [
            ('selection', 'tool_selection', 'response_not_completed',
             [selection(status='failed', error={'message': private})], {}),
            ('tool_arguments', 'tool_selection', 'validation_error',
             [selection(tool_item(SEARCH, {'query': private}))], {}),
            ('unlisted', 'tool_selection', 'provider_response_error',
             [providers.ProviderResponseError(private, private, {'raw': private})], {}),
            ('config', 'configuration', 'validation_error', [search], {}),
            ('db_open', 'database', 'io_error', [search], {}),
            ('db_lookup', 'database', 'io_error', [search, solar], {}),
            ('db_close', 'database', 'io_error',
             [search, solar, chat_answer(claim('확인했습니다.', 'pokemon:39#profile'))], {}),
            ('db_close_after_citation_rejection', 'database', 'io_error', [search, solar, no_citation], {}),
            ('index', 'index_validation', 'validation_error', [search], {}),
            ('rewrite', 'rewrite', 'invalid_model', [search, selection(model=private)], {'SOLAR_REWRITE': 'true'}),
            ('embedding', 'embedding', 'validation_error', [search, dict(solar, model=private)], {}),
            ('retrieval', 'retrieval', 'validation_error', [search, solar], {}),
            ('rerank', 'rerank', 'validation_error',
             [search, solar, formal_answer({f'rank_{i}': 1 for i in range(1, 6)})], {'SOLAR_RETRIEVAL_METHOD': 'C'}),
            ('structured', 'structured_lookup', 'io_error', [selection(tool_item(MOVE, {'move': '망각술'}))], {}),
            ('answer', 'answer_generation', 'invalid_structure', [search, solar, selection()], {}),
            ('answer_timeout', 'answer_generation', 'timeout', [search, solar, TimeoutError(private)], {}),
            ('answer_incomplete', 'answer_generation', 'response_not_completed',
             [search, solar, dict(no_citation, status='incomplete', incomplete_details={'reason': private})], {}),
            ('answer_error_envelope', 'answer_generation', 'invalid_structure',
             [search, solar, dict(no_citation, error={'message': private})], {}),
            ('answer_truncated', 'answer_generation', 'invalid_structure',
             [search, solar, dict(no_citation, truncated=True)], {}),
            ('answer_wrong_output', 'answer_generation', 'invalid_structure',
             [search, solar, selection(tool_item(SEARCH, {}), *no_citation['output'])], {}),
            ('answer_refusal', 'answer_generation', 'refusal', [search, solar, selection(
                {'type': 'message', 'role': 'assistant', 'status': 'completed',
                 'content': [{'type': 'refusal', 'refusal': private}]})], {}),
            ('answer_json', 'answer_generation', 'invalid_structure',
             [search, solar, raw_answer('{"status":"answer","status":"answer","claims":[]}')], {}),
            ('answer_legacy_shape', 'answer_generation', 'validation_error', [search, solar, answer(private)], {}),
            ('answer_wrong_status', 'answer_generation', 'validation_error',
             [search, solar, chat_answer(claim(private), status=private)], {}),
            ('answer_bad_block', 'answer_generation', 'validation_error',
             [search, solar, chat_answer(claim(private), {'source_ids': []})], {}),
            ('answer_extra_field', 'answer_generation', 'validation_error',
             [search, solar, chat_answer(claim(private) | {'explanation': private})], {}),
            ('answer_bad_text', 'answer_generation', 'validation_error',
             [search, solar, chat_answer(claim(private), claim(private + '\x00'))], {}),
            ('answer_sensitive', 'answer_generation', 'validation_error',
             [search, solar, chat_answer(claim(GPT_ENV['OPENAI_API_KEY']))], {}),
        ]
        for case, stage, kind, replies, env in cases:
            with self.subTest(case=case), ExitStack() as stack:
                transport = FixtureTransport(clarify, *replies)
                database = MemoryCorpus(records, vector_ids)
                if case == 'config':
                    stack.enter_context(patch.object(conversation, 'config', side_effect=ValueError(private)))
                elif case == 'db_open':
                    stack.enter_context(patch.object(MemoryCorpus, '__enter__', side_effect=OSError(private)))
                elif case == 'db_lookup':
                    database.search = Mock(side_effect=OSError(private))
                elif case in ('db_close', 'db_close_after_citation_rejection'):
                    stack.enter_context(patch.object(MemoryCorpus, '__exit__', side_effect=OSError(private)))
                elif case == 'index':
                    database.index_info[0]['config']['query_model'] = private
                elif case == 'retrieval':
                    stack.enter_context(patch.object(conversation.retrieval, 'bm25', side_effect=ValueError(private)))
                elif case == 'structured':
                    stack.enter_context(patch.object(conversation, 'load_store', side_effect=OSError(private)))
                service = self.service(transport, database, env={**SOLAR_ENV, **env})
                with self.chat_client(service) as client:
                    messages = self.followup(client, '망각술 후속 질문용 원문 표식')
                    with (self.assertLogs('uvicorn.error', level='WARNING') as logs,
                          self.assertLogs('api.error_handlers', level='ERROR') as api_logs):
                        reply = client.post('/api/v1/chat', json={'messages': messages})
                self.assert_failed_http(reply)
                self.assert_failure_log(logs, stage, kind)
                output = reply.text + '\n'.join(logs.output + api_logs.output)
                for marker in (private, messages[-1]['content'], MODEL, GPT_ENV['OPENAI_API_KEY']):
                    self.assertNotIn(marker, output)
                self.assertFalse(transport.pending)
                self.assertEqual(len(transport.calls), len(replies) + 1)

    def test_http_transport_diagnostics_only_include_valid_integer_status(self):
        private = 'fixture-only-upstream-detail'
        url = f'https://fixture.invalid/{private}'
        clarify = selection(tool_item(CLARIFY, {'reason': 'reference'}))

        def http_error(code):
            error = HTTPError(url, 429, private, HTTPMessage(), None)
            setattr(error, 'code', code)  # Include malformed status values in the fixture.
            return error

        cases = [
            *((http_error(code), b'', 'http_error', extra)
              for code, extra in [(429, {'upstream_status': 429}), (600, {}), (True, {}), (private, {})]),
            (TimeoutError(private), b'', 'timeout', {}),
            (URLError(TimeoutError(private)), b'', 'timeout', {}),
            (URLError(ConnectionRefusedError(private)), b'', 'connection_error', {}),
            (ConnectionResetError(private), b'', 'connection_error', {}),
            (None, private.encode(), 'response_decode_error', {}),
            (None, b'\xff', 'response_decode_error', {}),
            (ValueError(private), b'', 'transport_error', {}),
        ]
        for index, (error, raw, kind, extra) in enumerate(cases):
            with self.subTest(index=index, kind=kind):
                opener = Mock()
                opener.open.side_effect = error
                opener.open.return_value = io.BytesIO(raw)
                transport = FixtureTransport(clarify, lambda payload: providers.request(url, payload))
                with patch.object(providers.urllib.request, 'build_opener', return_value=opener):
                    with self.chat_client(self.service(transport)) as client:
                        messages = self.followup(client)
                        with (self.assertLogs('uvicorn.error', level='WARNING') as logs,
                              self.assertLogs('api.error_handlers', level='ERROR') as api_logs):
                            reply = client.post('/api/v1/chat', json={'messages': messages})
                self.assert_failed_http(reply)
                self.assert_failure_log(logs, 'tool_selection', kind, **extra)
                self.assertNotIn(private, '\n'.join(logs.output + api_logs.output))
                opener.open.assert_called_once()
                self.assertFalse(transport.pending)

    def test_http_success_rewrite_fallback_and_input_rejection_do_not_log_failure(self):
        cid = 'pokemon:39#profile'
        database = MemoryCorpus([row for row in self.records if row['chunk_id'] == cid], (cid,))
        transport = FixtureTransport(selection(tool_item(CLARIFY, {'reason': 'reference'})),
                                     selection(tool_item(SEARCH, {})), formal_answer({'wrong_field': 'fixture'}),
                                     SOLAR_RESPONSE, chat_answer(claim('근거입니다.', cid)))
        service = self.service(transport, database, env={**SOLAR_ENV, 'SOLAR_REWRITE': 'true'})
        with self.chat_client(service) as client:
            messages = self.followup(client)
            with self.assertNoLogs('uvicorn.error', level='WARNING'):
                invalid = [*messages[:-1], *question(GPT_ENV['OPENAI_API_KEY'])]
                bad = client.post('/api/v1/chat', json={'messages': invalid})
                self.assertEqual(bad.status_code, 400)
                self.assertEqual(bad.json()['error_code'], 'VALIDATION_ERROR')
                self.assertEqual(len(transport.calls), 1)
                good = client.post('/api/v1/chat', json={'messages': messages})
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.json()['data']['sources'], [{'ref': 1, 'chunk_id': cid, 'source_ref_id': '039'}])
        embedded = [p['input'] for url, p in transport.calls if url == providers.SOLAR_URL]
        self.assertEqual(embedded, [[messages[-1]['content'] + '\n\n이전 질문: ' + messages[0]['content']]])
        self.assertFalse(transport.pending)

    def test_http_citation_fallback_survives_a_broken_log_formatter(self):
        class BrokenFormatter(logging.Formatter):
            def format(self, record):
                raise OSError('fixture citation log formatter error')

        cid, private = 'pokemon:25#profile', 'fixture-private-unverified-claim'
        db = MemoryCorpus([row for row in self.records if row['chunk_id'] == cid], (cid,))
        search = selection(tool_item(SEARCH, {}))
        transport = FixtureTransport(search, SOLAR_RESPONSE, chat_answer(claim(private, 'pokemon:151#profile')))
        logger = logging.getLogger('uvicorn.error')
        stderr = io.StringIO()
        handler = logging.StreamHandler(io.StringIO())
        handler.setFormatter(BrokenFormatter())
        with (self.chat_client(self.service(transport, db, env=SOLAR_ENV)) as client,
              patch.object(logger, 'handlers', [handler]), patch.object(logger, 'propagate', False),
              patch.object(logging, 'raiseExceptions', True), redirect_stderr(stderr)):
            reply = client.post('/api/v1/chat', json={'messages': question('피카츄 타입은?')})
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.json()['data']['answer'], conversation.UNVERIFIED_EVIDENCE)
        self.assertEqual(reply.json()['data']['sources'], [])
        logged = stderr.getvalue()
        self.assertIn('fixture citation log formatter error', logged)
        self.assertNotIn(private, logged)
        self.assertNotIn('pokemon:151#profile', logged)
        self.assertNotIn('During handling of the above exception', logged)
        self.assertFalse(transport.pending)

    def test_http_logger_failure_preserves_public_error(self):
        class BrokenFormatter(logging.Formatter):
            def format(self, record):
                raise OSError('fixture log formatter error')

        private = 'fixture-only-upstream-detail'
        clarify = selection(tool_item(CLARIFY, {'reason': 'reference'}))
        transport = FixtureTransport(clarify, TimeoutError(private), TimeoutError(private), clarify)
        logger = logging.getLogger('uvicorn.error')
        stderr = io.StringIO()
        handler = logging.StreamHandler(io.StringIO())
        handler.setFormatter(BrokenFormatter())
        with self.chat_client(self.service(transport)) as client:
            messages = self.followup(client)
            with (patch.object(logger, 'warning', side_effect=RuntimeError('fixture logger error')) as log,
                  self.assertLogs('api.error_handlers', level='ERROR')):
                self.assert_failed_http(client.post('/api/v1/chat', json={'messages': messages}))
            log.assert_called_once()
            with (patch.object(logger, 'handlers', [handler]), patch.object(logger, 'propagate', False),
                  patch.object(logging, 'raiseExceptions', True), redirect_stderr(stderr),
                  self.assertLogs('api.error_handlers', level='ERROR')):
                self.assert_failed_http(client.post('/api/v1/chat', json={'messages': messages}))
            self.assertIn('fixture log formatter error', stderr.getvalue())
            self.assertNotIn(private, stderr.getvalue())
            with self.assertNoLogs('uvicorn.error', level='WARNING'):
                self.assertEqual(client.post('/api/v1/chat', json={'messages': messages}).status_code, 200)
        self.assertFalse(transport.pending)


if __name__ == '__main__':
    unittest.main()
