"""Offline conversation contract tests; no network, real DB, or real credentials."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from solar_handoff.src import conversation, providers


def claim(text, *source_ids):
    return {'text': text, 'source_ids': list(source_ids)}


class FakeDatabase:
    def __init__(self, records):
        self.records = copy.deepcopy(records)
        self.index_info = [{'id': 'solar', 'config': {
            'dimension': 1024, 'document_model': 'document-fixture', 'query_model': 'query-fixture'}}]
        self.search_count = 0
        self.rows = [{'chunk_id': row['chunk_id'], 'rank': i, 'distance': i / 10}
                     for i, row in enumerate(self.records, 1)]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def search(self, vector):
        self.search_count += 1
        return self.rows


class FakeProvider:
    document_model = 'document-fixture'
    query_model = 'query-fixture'

    def __init__(self):
        self.calls = []
        self.payload = None
        self.tool_payload = {}
        self.selection = (conversation.SEARCH, {})
        self.result = {'status': 'answer', 'claims': [claim('자료에 확인된 내용이에요.', 'pokemon:1#profile')]}
        self.failure: str | None = None

    def choose_tool(self, instructions, data, tools):
        self.calls.append(('choose_tool',))
        self.tool_payload = copy.deepcopy(data)
        if self.failure == 'choose_tool':
            raise RuntimeError('private provider details')
        return self.selection

    def preflight(self, method, answer_provider, rewrite):
        self.calls.append(('preflight', method, answer_provider, rewrite))

    def embed(self, query):
        self.calls.append(('embed', query))
        if self.failure == 'embed':
            raise RuntimeError('private provider details')
        return [1.0] + [0.0] * 1023, {}

    def openai(self, instructions, data, schema, *, strict_envelope):
        self.calls.append(('openai',))
        self.payload = copy.deepcopy(data)
        self.instructions = instructions
        self.strict_envelope = strict_envelope
        if self.failure == 'openai':
            raise RuntimeError('private provider details')
        return self.result, {}

    def rerank(self, question, selected):
        self.calls.append(('rerank', question))
        return [5, 4, 3, 2, 1], {}

    def rewrite(self, query):
        self.calls.append(('rewrite', query))
        if self.failure == 'rewrite':
            raise RuntimeError('private provider details')
        if self.failure == 'rewrite-format':
            raise providers.ProviderResponseError('completed', 'invalid_structure')
        return '재작성 검색어', {}


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.documents = self.base / 'documents'
        self.documents.mkdir()
        self.register = self.base / 'register.json'
        self.entries, self.records = [], []
        for number in range(1, 6):
            name = f'{number:03d}_fixture.md'
            raw = f'# 문서 {number}\n\n검증용 내용\n'.encode('utf-8')
            (self.documents / name).write_bytes(raw)
            self.entries.append({'pokemon_id': number, 'path': f'documents/{name}',
                                 'sha256': hashlib.sha256(raw).hexdigest()})
            self.records.append({'chunk_id': f'pokemon:{number}#profile', 'document_id': f'pokemon:{number}',
                                 'content': f'피카츄 검증용 내용 {number}', 'source_document': f'documents/{name}',
                                 'heading': '기본 정보', 'source_lines': [2, 3], 'source_heading_lines': [1]})
        self.write_register()
        self.database = FakeDatabase(self.records)
        self.provider = FakeProvider()
        self.env = {'SOLAR_RETRIEVAL_METHOD': 'B', 'SOLAR_REWRITE': 'false'}
        self.factory_calls = []

    def write_register(self):
        self.register.write_text(json.dumps({'schema_version': 1, 'documents': self.entries}), encoding='utf-8')

    def service(self, **overrides):
        def database_factory(env):
            self.factory_calls.append('database')
            return self.database

        def provider_factory(env):
            self.factory_calls.append('provider')
            return self.provider

        return conversation.create_service(self.env, database_factory=database_factory,
                                           provider_factory=provider_factory, document_root=self.documents,
                                           register_path=self.register, **overrides)

    def question(self, text='피카츄 타입은?'):
        return [{'role': 'user', 'content': text}]

    def test_embedding_identity_is_supplied_by_verified_provider_metadata_only(self):
        original = self.provider.embed
        def embed(query):
            vector, _ = original(query)
            return vector, {'actual_model': self.provider.query_model,
                            'document_model': self.provider.document_model,
                            'usage': {'ignored': True}, 'answer_model': 'not-an-embedding'}
        self.provider.embed = embed
        result = self.service().answer(self.question())
        self.assertEqual(result['embedding'], {'query_model': 'query-fixture', 'document_model': 'document-fixture'})
        self.assertNotIn('usage', result['embedding'])
        self.assertNotIn('answer_model', result['embedding'])

    def test_mismatched_embedding_metadata_stops_before_answer_generation(self):
        for meta in ({'actual_model': 'another-model', 'document_model': 'document-fixture'},
                     {'actual_model': 'query-fixture'}, {'document_model': 'document-fixture'}):
            with self.subTest(meta=meta):
                self.provider = FakeProvider()
                self.provider.embed = lambda query, value=meta: ([1.0] + [0.0] * 1023, value)
                with self.assertRaises(conversation.AnswerGenerationError):
                    self.service().answer(self.question())
                self.assertIsNone(self.provider.payload)

    def test_missing_embedding_identity_is_not_filled_from_settings(self):
        result = self.service().answer(self.question())
        self.assertNotIn('embedding', result)

    def test_embedding_identity_rejects_unicode_controls_and_oversize_raw_names(self):
        for value in ['model\u0085', 'model\u202e', 'model\ud800', 'model\ue000', ' ' * 200 + 'x']:
            with self.subTest(value=ascii(value)):
                self.provider.query_model = value
                with self.assertRaises(ValueError):
                    conversation._embedding_metadata({'actual_model': value, 'document_model': self.provider.document_model}, self.provider)

    def use_registered_pokemon(self, numbers, seed_ids):
        """Read committed source passages, without using any evaluation or provider data."""
        base = Path(conversation.__file__).resolve().parents[1]
        register = json.loads((base / 'data/document_register.json').read_text(encoding='utf-8'))
        self.entries = [row for row in register['documents'] if row['pokemon_id'] in numbers]
        for row in self.entries:
            filename = Path(row['path']).name
            (self.documents / filename).write_bytes((base / row['path']).read_bytes())
        self.write_register()
        corpus = [json.loads(line) for line in
                  (base / 'chunks/draft-a-v1/chunks.jsonl').read_text(encoding='utf-8').splitlines()]
        self.records = [row for row in corpus if row['pokemon_id'] in numbers]
        self.database = FakeDatabase(self.records)
        self.database.rows = [{'chunk_id': cid, 'rank': index, 'distance': index / 10}
                              for index, cid in enumerate(seed_ids, 1)]

    def test_topic_switch_supplies_actual_learnset_siblings_missing_from_retrieval_seeds(self):
        # These are the five IDs captured in the failing live selection, without either learnset.
        seeds = ['pokemon:7#profile', 'pokemon:7#defense_matchup', 'pokemon:25#profile',
                 'pokemon:25#attack_matchup', 'pokemon:7#stab']
        self.use_registered_pokemon({7, 25}, seeds)
        history = [{'role': 'user', 'content': '피카츄는 무슨 타입이야?'},
                   {'role': 'assistant', 'content': '피카츄는 전기 타입 포켓몬입니다. [1]'},
                   {'role': 'user', 'content': '꼬부기는 어떤 기술 써?'}]
        self.provider.result = {'status': 'answer', 'claims': [
            claim('레벨업 기술을 확인할 수 있어요.', 'pokemon:7#learnset_level'),
            claim('머신 기술을 확인할 수 있어요.', 'pokemon:7#learnset_machine'),
        ]}
        events = []
        # Pin the observed seed selection to isolate expansion from lexical/vector ranking.
        with patch.object(conversation.retrieval, 'bm25', return_value=[]):
            response = self.service(audit_callback=events.append).answer(history)
        contexts = self.provider.payload['contexts']
        ids = [row['chunk_id'] for row in contexts]
        self.assertEqual(ids[:5], seeds)
        self.assertEqual(len(ids), len(set(ids)))
        for cid in ('pokemon:7#learnset_level', 'pokemon:7#learnset_machine'):
            supplied = next(row for row in contexts if row['chunk_id'] == cid)
            source = next(row for row in self.records if row['chunk_id'] == cid)
            self.assertEqual(supplied['content'], source['content'])
        self.assertEqual(self.provider.payload['messages'], history)
        embedded_query = next(call[1] for call in self.provider.calls if call[0] == 'embed')
        self.assertTrue(embedded_query.startswith(history[-1]['content']))
        self.assertIn(history[0]['content'], embedded_query)
        self.assertEqual(response['sources'], [
            {'ref': 1, 'chunk_id': 'pokemon:7#learnset_level', 'source_ref_id': 'pokemon:7'},
            {'ref': 2, 'chunk_id': 'pokemon:7#learnset_machine', 'source_ref_id': 'pokemon:7'}])
        self.assertEqual(events[0]['retrieval_seed_chunk_ids'], seeds)
        self.assertEqual(events[0]['selected_chunk_ids'], ids)
        self.assertEqual(events[0]['expanded_chunk_ids'], ids[5:])
        self.assertEqual(events[0]['answer_status'], 'answer')
        self.assertEqual(events[0]['context_expansion']['omitted_sibling_count'], 0)
        self.assertLessEqual(events[0]['context_expansion']['context_bytes'], conversation.MAX_CONTEXT_BYTES)
        self.assertLessEqual(len(ids), conversation.MAX_CONTEXT_CHUNKS)
        self.assertEqual(sum(call[0] == 'embed' for call in self.provider.calls), 1)
        self.assertEqual(sum(call[0] == 'openai' for call in self.provider.calls), 1)

    def test_expansion_does_not_invent_missing_or_unretrieved_pokemon_evidence(self):
        # Squirtle exists in the corpus but none of its document's sections were retrieved.
        self.use_registered_pokemon({7, 25}, ['pokemon:25#profile'])
        self.provider.result = {'status': 'insufficient_evidence', 'claims': []}
        events = []
        with patch.object(conversation.retrieval, 'bm25', return_value=[]):
            response = self.service(audit_callback=events.append).answer(self.question('꼬부기는 어떤 기술 써?'))
        self.assertTrue(all(row['document_id'] == 'pokemon:25' for row in self.provider.payload['contexts']))
        self.assertEqual(response['sources'], [])
        self.assertEqual(events[0]['answer_status'], 'insufficient_evidence')
        self.provider.result = {'status': 'answer', 'claims': [claim('알아요.', 'pokemon:7#learnset_level')]}
        with patch.object(conversation.retrieval, 'bm25', return_value=[]):
            with self.assertLogs('uvicorn.error', level='WARNING') as logs:
                rejected = self.service().answer(self.question('꼬부기는 어떤 기술 써?'))
        self.assertEqual(rejected, {'answer': conversation.UNVERIFIED_EVIDENCE, 'mode': 'rag', 'sources': []})
        self.assertIn('citation_not_selected', logs.output[0])
        # Removing the absent entity's corpus rows still never manufactures a section for it.
        self.database.records = [row for row in self.records if row['pokemon_id'] == 25]
        self.provider.result = {'status': 'insufficient_evidence', 'claims': []}
        with patch.object(conversation.retrieval, 'bm25', return_value=[]):
            self.service().answer(self.question('꼬부기는 어떤 기술 써?'))
        self.assertTrue(all(row['document_id'] == 'pokemon:25' for row in self.provider.payload['contexts']))

    def test_conversation_list_exception_is_scoped_and_does_not_change_cli_prompt(self):
        self.service().answer(self.question())
        self.assertTrue(self.provider.strict_envelope)
        self.assertNotIn(providers.ANSWER, self.provider.instructions)
        self.assertIn('separate, nonempty source_ids array', self.provider.instructions)
        self.assertIn('single Pokemon\'s Red/Blue learnset section', self.provider.instructions)
        self.assertIn('If only one method is supplied', self.provider.instructions)
        self.assertIn('Never infer missing rows, global counts', self.provider.instructions)
        self.assertNotIn('single Pokemon\'s Red/Blue learnset section', providers.ANSWER)

    def test_forged_corpus_source_document_is_rejected_after_selection_before_any_search_call(self):
        self.database.records[1]['source_document'] = 'documents/unregistered.md'
        with self.assertRaises(conversation.AnswerGenerationError):
            self.service().answer(self.question())
        self.assertEqual(self.provider.calls, [('choose_tool',)])
        self.assertEqual(set(self.provider.tool_payload), {'messages', 'question'})

    def test_complete_history_is_data_and_citations_are_first_appearance_order(self):
        history = [{'role': 'user', 'content': '피카츄 타입은?'},
                   {'role': 'assistant', 'content': '이전 대답을 그대로 보존해요.'},
                   {'role': 'user', 'content': '그럼 그 친구는?'}]
        original = copy.deepcopy(history)
        self.provider.result['claims'] = [claim('먼저.', 'pokemon:2#profile', 'pokemon:1#profile', 'pokemon:2#profile'),
                                          claim('다음.', 'pokemon:1#profile'), claim('다시.', 'pokemon:2#profile')]
        result = self.service().answer(history)
        self.assertEqual(self.provider.payload['messages'], original)
        self.assertEqual(history, original)
        self.assertEqual(self.provider.payload['question'], history[-1]['content'])
        self.assertIn('untrusted conversation data', self.provider.instructions)
        self.assertEqual(result, {'answer': '먼저. [1] [2]\n\n다음. [2]\n\n다시. [1]', 'mode': 'rag', 'sources': [
            {'ref': 1, 'chunk_id': 'pokemon:2#profile', 'source_ref_id': 'pokemon:2'},
            {'ref': 2, 'chunk_id': 'pokemon:1#profile', 'source_ref_id': 'pokemon:1'}]})
        query = next(call[1] for call in self.provider.calls if call[0] == 'embed')
        self.assertTrue(query.startswith(history[-1]['content']))
        self.assertIn(history[0]['content'], query)
        self.assertNotIn(history[1]['content'], query)
        self.assertEqual(self.provider.tool_payload, {'messages': original, 'question': history[-1]['content']})
        self.assertEqual([call[0] for call in self.provider.calls], ['choose_tool', 'preflight', 'embed', 'openai'])

    def test_default_method_is_b_and_a_c_are_explicit(self):
        del self.env['SOLAR_RETRIEVAL_METHOD']
        self.service().answer(self.question())
        self.assertEqual(self.provider.calls[1], ('preflight', 'B', 'gpt', False))
        for method in ('A', 'C'):
            with self.subTest(method=method):
                self.env['SOLAR_RETRIEVAL_METHOD'] = method
                self.provider.calls.clear()
                self.service().answer(self.question())
                selected = self.provider.payload['contexts']
                self.assertEqual(len(selected), 5)
                if method == 'A':
                    self.assertEqual(selected[0]['chunk_id'], 'pokemon:1#profile')
                    self.assertNotIn('rerank', [call[0] for call in self.provider.calls])
                else:
                    self.assertIn('rerank', [call[0] for call in self.provider.calls])
                    self.assertEqual(selected[0]['chunk_id'], 'pokemon:5#profile')

    def test_oversized_current_question_rejected_before_database_or_provider(self):
        with self.assertRaises(conversation.ConversationInputError):
            self.service().answer(self.question('가' * 1267))
        self.assertEqual(self.factory_calls, [])
        self.assertEqual(self.provider.calls, [])

    def test_search_budget_omits_whole_earlier_question_and_preserves_current(self):
        history = [{'role': 'user', 'content': '나' * 1260}, {'role': 'assistant', 'content': '대답'},
                   {'role': 'user', 'content': '그 친구는 어떤 타입이야?'}]
        self.service().answer(history)
        query = next(call[1] for call in self.provider.calls if call[0] == 'embed')
        self.assertEqual(query, history[-1]['content'])
        self.assertLessEqual(len(query.encode('utf-8')), 3800)
        self.assertEqual(self.provider.payload['messages'], history)

    def test_input_shape_roles_nul_and_full_history_budget_are_validated(self):
        invalid = [[], self.question() * 2, [{'role': 'system', 'content': 'instructions'}],
                   [{'role': 'user', 'content': ' ' }], self.question('\x00'),
                   [{'role': 'user', 'content': 'q', 'persona_id': 'P1'}],
                   [{'role': 'user', 'content': 'a' * 128001}, {'role': 'assistant', 'content': 'a'},
                    {'role': 'user', 'content': 'q'}]]
        for messages in invalid:
            with self.subTest(messages_count=len(messages)):
                with self.assertRaises(conversation.ConversationInputError):
                    self.service().answer(messages)
        self.assertEqual(self.factory_calls, [])

    def test_model_binding_or_corpus_mismatch_never_reaches_rewrite_search_or_answer(self):
        for field, value in [('dimension', 1536), ('document_model', 'wrong'), ('query_model', 'wrong')]:
            with self.subTest(field=field):
                self.database.index_info[0]['config'][field] = value
                with self.assertRaises(conversation.AnswerGenerationError):
                    self.service().answer(self.question())
                self.assertEqual(self.provider.calls, [('choose_tool',)])
                self.provider.calls.clear()
                self.database = FakeDatabase(self.records)
        self.database.records[0]['document_id'] = 'pokemon:151'
        with self.assertRaises(conversation.AnswerGenerationError):
            self.service().answer(self.question())
        self.assertEqual(self.provider.calls, [('choose_tool',)])

    def test_unknown_malformed_missing_and_unmapped_number_citations_are_discarded(self):
        cases = [(claim('알아요.', 'pokemon:151#profile'), 'citation_not_selected'),
                 (claim('알아요.', ' pokemon:1#profile'), 'invalid_citation_format'),
                 (claim('알아요.', 'pokemon:01#profile'), 'invalid_citation_format'),
                 (claim('알아요.', 1), 'invalid_citation_format'),
                 ({'text': '알아요.', 'source_ids': None}, 'invalid_citation_format'),
                 (claim('알아요.'), 'missing_citation'),
                 ({'text': '알아요.'}, 'missing_citation')]
        cases.extend((claim(text, 'pokemon:1#profile'), 'invalid_citation_format') for text in (
            '알아요[[pokemon:151#profile]].', '알아요[[pokemon:1#profile].',
            '알아요[pokemon:1#profile].', '알아요[1].', '알아요［１］.', '알아요&#91;1&#93;.',
            '근거pokemon:1#profile이에요.', '근거<cite>1</cite>예요.'))
        for block, reason in cases:
            with self.subTest(block=block):
                self.provider.result = {'status': 'answer', 'claims': [block]}
                with self.assertLogs('uvicorn.error', level='WARNING') as logs:
                    result = self.service().answer(self.question())
                self.assertEqual(result, {'answer': conversation.UNVERIFIED_EVIDENCE, 'mode': 'rag', 'sources': []})
                record, = logs.records
                self.assertEqual(json.loads(record.getMessage())['reason'], reason)

    def test_mixed_duplicate_single_bracket_citation_is_rejected(self):
        self.provider.result['claims'] = [claim('먼저 확인된 내용.', 'pokemon:1#profile'),
                                          claim('a[[pokemon:1#profile]] b[pokemon:1#profile]', 'pokemon:1#profile')]
        events = []
        with self.assertLogs('uvicorn.error', level='WARNING'):
            result = self.service(audit_callback=events.append).answer(self.question())
        self.assertEqual(result, {'answer': conversation.UNVERIFIED_EVIDENCE, 'mode': 'rag', 'sources': []})
        self.assertEqual(events, [])

    def test_success_audit_has_only_safe_metadata_and_does_not_change_response(self):
        events = []
        history = [{'role': 'user', 'content': '이전 질문'}, {'role': 'assistant', 'content': '이전 대답'},
                   {'role': 'user', 'content': '현재 질문'}]
        with self.assertLogs('solar_handoff.conversation.audit', level='INFO') as captured:
            result = self.service(audit_callback=events.append).answer(history)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(set(event), {'event', 'input_message_count', 'method', 'rewrite',
                                     'retrieval_seed_chunk_ids', 'selected_chunk_ids', 'expanded_chunk_ids',
                                     'context_expansion', 'answer_status', 'cited_chunk_ids',
                                     'selected_tool', 'move_source_id', 'tool_selection_calls', 'tool_calls',
                                     'corpus_reads', 'rewrite_calls', 'embedding_calls', 'vector_search_calls',
                                     'bm25_calls', 'rerank_calls', 'answer_calls'})
        self.assertEqual(event['input_message_count'], 3)
        self.assertEqual(event['method'], 'B')
        self.assertIs(event['rewrite'], False)
        self.assertEqual(event['selected_tool'], conversation.SEARCH)
        self.assertEqual(event['tool_selection_calls'], 1)
        self.assertEqual(event['tool_calls'], 1)
        self.assertEqual(event['corpus_reads'], 1)
        self.assertEqual(event['vector_search_calls'], 1)
        self.assertEqual(event['bm25_calls'], 1)
        self.assertEqual(event['rewrite_calls'], 0)
        self.assertEqual(event['rerank_calls'], 0)
        self.assertEqual(event['embedding_calls'], 1)
        self.assertEqual(event['answer_calls'], 1)
        self.assertEqual(event['answer_status'], 'answer')
        self.assertEqual(event['retrieval_seed_chunk_ids'], event['selected_chunk_ids'])
        self.assertEqual(event['expanded_chunk_ids'], [])
        self.assertEqual(event['cited_chunk_ids'], ['pokemon:1#profile'])
        self.assertTrue(set(event['cited_chunk_ids']).issubset(event['selected_chunk_ids']))
        encoded = json.dumps(event, ensure_ascii=False)
        for message in history:
            self.assertNotIn(message['content'], encoded)
            self.assertNotIn(message['content'], captured.output[0])
        self.assertEqual(set(result), {'answer', 'mode', 'sources'})

    def test_audit_callback_or_logging_failure_does_not_fail_or_repeat_answer(self):
        from unittest.mock import patch
        def broken_callback(event):
            event['selected_chunk_ids'].clear()
            raise RuntimeError('observer failed')
        with patch.object(conversation.AUDIT_LOGGER, 'info', side_effect=RuntimeError('log failed')):
            result = self.service(audit_callback=broken_callback).answer(self.question())
        self.assertEqual(result['sources'][0]['chunk_id'], 'pokemon:1#profile')
        self.assertEqual(sum(call[0] == 'embed' for call in self.provider.calls), 1)
        self.assertEqual(sum(call[0] == 'openai' for call in self.provider.calls), 1)

    def test_insufficient_evidence_can_have_no_citations(self):
        self.provider.result = {'status': 'insufficient_evidence', 'claims': []}
        with self.assertNoLogs('uvicorn.error', level='WARNING'):
            result = self.service().answer(self.question())
        self.assertEqual(result, {'answer': conversation.UNVERIFIED_EVIDENCE, 'mode': 'rag', 'sources': []})

    def test_insufficient_evidence_only_displays_supported_blocks_and_fixed_notice(self):
        self.provider.result = {'status': 'insufficient_evidence', 'claims': [
            claim('확인된 내용이에요.', 'pokemon:1#profile')]}
        with self.assertNoLogs('uvicorn.error', level='WARNING'):
            result = self.service().answer(self.question())
        self.assertEqual(result['answer'], '확인된 내용이에요. [1]\n\n' + conversation.PARTIAL_EVIDENCE)
        self.assertEqual([row['chunk_id'] for row in result['sources']], ['pokemon:1#profile'])
        self.provider.result['claims'].append(claim('뒤의 주장은 확인되지 않았어요.'))
        with self.assertLogs('uvicorn.error', level='WARNING'):
            result = self.service().answer(self.question())
        self.assertEqual(result, {'answer': conversation.UNVERIFIED_EVIDENCE, 'mode': 'rag', 'sources': []})

    def test_failures_do_not_retry_and_messages_do_not_expose_internal_details(self):
        for failure in ('choose_tool', 'embed', 'openai'):
            with self.subTest(failure=failure):
                self.provider.calls.clear()
                self.provider.failure = failure
                with self.assertRaises(conversation.AnswerGenerationError) as caught:
                    self.service().answer(self.question())
                self.assertNotIn('private provider details', str(caught.exception))
                self.assertEqual(sum(call[0] == failure for call in self.provider.calls), 1)

    def test_c_requires_exactly_five_candidates(self):
        self.env['SOLAR_RETRIEVAL_METHOD'] = 'C'
        self.database = FakeDatabase(self.records[:2])
        with self.assertRaises(conversation.AnswerGenerationError):
            self.service().answer(self.question())
        self.assertNotIn('rerank', [call[0] for call in self.provider.calls])
        self.assertNotIn('openai', [call[0] for call in self.provider.calls])

    def test_rewrite_explicit_and_only_known_format_failure_falls_back(self):
        self.env['SOLAR_REWRITE'] = 'true'
        self.provider.failure = 'rewrite-format'
        self.service().answer(self.question())
        self.assertEqual(sum(call[0] == 'rewrite' for call in self.provider.calls), 1)
        self.assertIn(('embed', '피카츄 타입은?'), self.provider.calls)
        self.provider.calls.clear()
        self.provider.failure = 'rewrite'
        with self.assertRaises(conversation.AnswerGenerationError):
            self.service().answer(self.question())
        self.assertEqual(sum(call[0] == 'rewrite' for call in self.provider.calls), 1)
        self.assertNotIn('embed', [call[0] for call in self.provider.calls])

    def test_configured_secret_input_corpus_and_output_never_escape(self):
        secret = 'unittest-only-sensitive-value'  # security: allow synthetic fixture used only to test secret redaction
        self.env['TEST_SECRET'] = secret
        with self.assertRaises(conversation.ConversationInputError) as caught:
            self.service().answer(self.question(secret))
        self.assertNotIn(secret, str(caught.exception))
        self.assertEqual(self.factory_calls, [])
        self.provider.result['claims'] = [claim(secret, 'pokemon:1#profile')]
        with self.assertRaises(conversation.AnswerGenerationError) as caught:
            self.service().answer(self.question())
        self.assertNotIn(secret, str(caught.exception))
        self.provider.calls.clear()
        self.database.records[0]['content'] = secret
        with self.assertRaises(conversation.AnswerGenerationError):
            self.service().answer(self.question())
        self.assertEqual(self.provider.calls, [('choose_tool',)])
        self.assertNotIn(secret, json.dumps(self.provider.tool_payload))

    def test_documents_work_without_database_provider_or_configuration(self):
        service = self.service()
        result = service.get_document('pokemon:1')
        self.assertEqual(result['source_ref_id'], 'pokemon:1')
        self.assertEqual(result['markdown'], '# 문서 1\n\n검증용 내용\n')
        self.assertEqual(self.factory_calls, [])
        self.assertEqual(self.provider.calls, [])

    def test_unknown_and_path_attack_identifiers_are_not_found(self):
        for value in ['pokemon:151', '../register.json', 'pokemon:01', 'pokemon:1/profile',
                      'pokemon:1\\profile', '%2e%2e%2f', '/etc/passwd', 'C:\\secret', None]:
            with self.subTest(value=value):
                with self.assertRaises(conversation.DocumentNotFoundError):
                    self.service().get_document(value)

    def test_missing_hash_changed_or_corrupt_sources_are_distinct_from_unknown_id(self):
        (self.documents / '001_fixture.md').write_text('changed', encoding='utf-8')
        with self.assertRaises(conversation.DocumentSourceError):
            self.service().get_document('pokemon:1')
        (self.documents / '001_fixture.md').unlink()
        with self.assertRaises(conversation.DocumentSourceError):
            self.service().get_document('pokemon:1')
        self.register.write_text('{', encoding='utf-8')
        with self.assertRaises(conversation.DocumentSourceError):
            self.service().get_document('pokemon:1')

    def test_register_path_escape_rejected_and_response_not_stale_cached(self):
        service = self.service()
        service.get_document('pokemon:1')
        self.entries[0]['path'] = 'documents/../../outside.md'
        self.write_register()
        with self.assertRaises(conversation.DocumentSourceError):
            service.get_document('pokemon:1')

    def test_symlink_escape_is_rejected(self):
        target = self.base / 'outside.md'
        target.write_text('outside', encoding='utf-8')
        path = self.documents / '001_fixture.md'
        path.unlink()
        try:
            path.symlink_to(target)
        except OSError:
            # Windows without developer-mode privilege: verify resolved containment with a fake Path.
            from unittest.mock import patch
            original = Path.resolve
            def redirected(current, *args, **kwargs):
                if current == path:
                    return target.resolve()
                return original(current, *args, **kwargs)
            with patch.object(Path, 'resolve', redirected):
                with self.assertRaises(conversation.DocumentSourceError):
                    self.service().get_document('pokemon:1')
        else:
            with self.assertRaises(conversation.DocumentSourceError):
                self.service().get_document('pokemon:1')


class ContextExpansionBudgetTests(unittest.TestCase):
    def row(self, chunk_id, content='검증용 전체 문단'):
        return {'chunk_id': chunk_id, 'document_id': chunk_id.split('#')[0], 'content': content,
                'source_document': 'documents/fixture.md', 'heading': '검증용',
                'source_lines': [1, 2], 'source_heading_lines': [1]}

    def size(self, rows):
        return len(json.dumps(conversation._context_payload(rows), ensure_ascii=False).encode('utf-8'))

    def test_chunk_budget_preserves_seeds_and_is_independent_of_corpus_order(self):
        seed = self.row('pokemon:2#profile')
        rows = [self.row('pokemon:1#profile'), self.row('pokemon:2#b'),
                seed, self.row('pokemon:2#a')]
        corpus = {row['chunk_id']: row for row in rows}
        result, meta = conversation._expand_source_context([seed], corpus, max_chunks=2, max_bytes=10000)
        reversed_result, reversed_meta = conversation._expand_source_context(
            [seed], dict(reversed(list(corpus.items()))), max_chunks=2, max_bytes=10000)
        self.assertEqual([row['chunk_id'] for row in result], ['pokemon:2#profile', 'pokemon:2#a'])
        self.assertEqual(result, reversed_result)
        self.assertEqual(meta, reversed_meta)
        self.assertEqual(meta['omitted_sibling_count'], 1)
        self.assertEqual(meta['context_bytes'], self.size(result))
        self.assertEqual(seed, result[0])
        self.assertEqual(corpus['pokemon:2#a'], result[1])

    def test_byte_budget_uses_utf8_and_skips_oversized_siblings_without_slicing(self):
        seed = self.row('pokemon:2#profile', '씨앗 문단')
        long_row = self.row('pokemon:2#a', '가' * 1000)
        short_row = self.row('pokemon:2#b', '작은 전체 문단')
        corpus = {row['chunk_id']: row for row in [long_row, short_row, seed]}
        exact_budget = self.size([seed, short_row])
        result, meta = conversation._expand_source_context([seed], corpus, max_bytes=exact_budget)
        self.assertEqual(result, [seed, short_row])
        self.assertEqual(meta['context_bytes'], exact_budget)
        self.assertEqual(meta['omitted_sibling_count'], 1)
        result, meta = conversation._expand_source_context([seed], corpus, max_bytes=exact_budget - 1)
        self.assertEqual(result, [seed])
        self.assertEqual(meta['omitted_sibling_count'], 2)

    def test_oversized_or_invalid_seed_set_fails_instead_of_discarding_seeds(self):
        seeds = [self.row('pokemon:2#profile'), self.row('pokemon:1#profile')]
        corpus = {row['chunk_id']: row for row in seeds}
        for kwargs in [{'max_chunks': 1}, {'max_bytes': self.size(seeds) - 1},
                       {'max_chunks': 0}, {'max_bytes': True}]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    conversation._expand_source_context(seeds, corpus, **kwargs)
        with self.assertRaises(ValueError):
            conversation._expand_source_context([seeds[0], seeds[0]], corpus)
        with self.assertRaises(ValueError):
            conversation._expand_source_context([self.row('pokemon:3#profile')], corpus)

    def test_first_seen_document_order_retains_all_seed_passages(self):
        seeds = [self.row('pokemon:2#profile'), self.row('pokemon:1#profile')]
        rows = [self.row('pokemon:1#a'), *seeds, self.row('pokemon:2#a'), self.row('pokemon:3#a')]
        result, meta = conversation._expand_source_context(seeds, {row['chunk_id']: row for row in rows})
        self.assertEqual([row['chunk_id'] for row in result],
                         ['pokemon:2#profile', 'pokemon:1#profile', 'pokemon:2#a', 'pokemon:1#a'])
        self.assertEqual(meta['omitted_sibling_count'], 0)


if __name__ == '__main__':
    unittest.main()
