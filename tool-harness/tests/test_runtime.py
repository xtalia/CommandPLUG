"""Regression tests for validated repairs and reliable telemetry."""
import importlib.util
import sys
import tempfile
import unittest
import copy
from pathlib import Path
from unittest.mock import patch

try:
    import tools.file_tools  # register the real file-tool schemas
    import tools.terminal_tool  # register terminal
    import tools.web_tools  # register web tools
except ModuleNotFoundError as exc:
    if exc.name != 'tools':
        raise
    from registry_fixture import install
    install()

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("commandplug_test", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        plugin._counters.clear()
        plugin._pending.clear()
        plugin._repairs_since_flush = 0
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "metrics.jsonl"

    def test_flush_failure_retains_snapshot_and_reports_failure(self):
        plugin._counters['read_file'] = {'calls': 1, 'repaired': 1}
        plugin._repairs_since_flush = 1
        with patch.object(plugin, '_log_path', side_effect=OSError('not writable')):
            self.assertEqual(plugin._flush(), 0)
        self.assertEqual(plugin._counters['read_file']['repaired'], 1)
        with patch.object(plugin, '_log_path', return_value=self.path):
            self.assertEqual(plugin._flush(), 1)
            self.assertIn('1/1', plugin._summary())

    def test_counts_description_is_scoped(self):
        with patch.object(plugin, '_log_path', return_value=self.path):
            text = plugin._summary()
        self.assertNotIn('every call', text)

    def test_validator_unavailable_is_visible_and_calls_are_counted(self):
        with patch.object(plugin, '_validation_library', return_value=None), patch.object(plugin, '_log_path', return_value=self.path):
            self.assertIsNone(plugin._on_tool_request(tool_name='read_file', args={'path': 'a', 'limit': '30'}, session_id='s', tool_call_id='c'))
            self.assertEqual(plugin._counters['read_file']['calls'], 1)
            self.assertIn('validation unavailable', plugin._summary().lower())
            self.assertNotEqual(plugin._command('status'), 'CommandPLUG: active')

    def test_summary_discloses_unpersisted_counts(self):
        plugin._counters['read_file'] = {'calls': 1, 'repaired': 1}
        plugin._repairs_since_flush = 1
        with patch.object(plugin, '_log_path', side_effect=OSError('not writable')):
            summary = plugin._summary()
        self.assertIn('1/1', summary)
        self.assertIn('not persisted', summary)

    def test_summary_reads_log_and_memory_under_same_lock_as_flush(self):
        self.path.write_text('{"tools":{"read_file":{"calls":1,"repaired":1}}}\n', encoding='utf-8')
        original = Path.read_text
        def check_locked(path, *args, **kwargs):
            if path == self.path:
                self.assertTrue(plugin._lock.locked())
            return original(path, *args, **kwargs)
        with patch.object(plugin, '_log_path', return_value=self.path), patch.object(Path, 'read_text', check_locked):
            self.assertIn('1/1', plugin._summary())

    def test_validate_repair_revalidate_and_never_guess_required_values(self):
        ids = {'session_id': 's', 'tool_call_id': 'c'}
        with patch.object(plugin, '_log_path', return_value=self.path):
            changed = plugin._on_tool_request(tool_name='read_file', args={'path': 'a', 'limit': '30'}, **ids)
            self.assertEqual(changed['args'], {'path': 'a', 'limit': 30})
            plugin._pending.clear()
            self.assertIsNone(plugin._on_tool_request(tool_name='read_file', args={'path': 'a', 'limit': '3000'}, **ids))
            self.assertIsNone(plugin._on_tool_request(tool_name='read_file', args={'limit': '30'}, **ids))
            self.assertIsNone(plugin._on_tool_request(tool_name='read_file', args={'path': 'a', 'limit': 30}, **ids))

    def test_web_extract_array_repairs_are_validated_and_unambiguous(self):
        ids = {'session_id': 's', 'tool_call_id': 'c'}
        for raw, expected in [('["https://a.test", "https://b.test"]', ['https://a.test', 'https://b.test'])]:
            plugin._pending.clear()
            changed = plugin._on_tool_request(tool_name='web_extract', args={'urls': raw}, **ids)
            self.assertEqual(changed['args']['urls'], expected)
        plugin._pending.clear()
        self.assertIsNone(plugin._on_tool_request(tool_name='web_extract', args={'urls': 'https://a.test, https://b.test'}, **ids))
        self.assertIsNone(plugin._on_tool_request(tool_name='web_extract', args={'urls': None}, **ids))
        for ambiguous in ('https://example.com', 'not a url', 'https://a.test b.test', '{"url":"https://a.test"}'):
            self.assertIsNone(plugin._on_tool_request(tool_name='web_extract', args={'urls': ambiguous}, **ids))

    def test_blocked_call_discards_pending_note_without_touching_success(self):
        ids = {'session_id': 's', 'tool_call_id': 'c', 'tool_name': 'read_file'}
        self.assertIsNotNone(plugin._on_tool_request(args={'path': 'a', 'limit': '30'}, **ids))
        plugin._on_post_tool_call(status='ok', **ids)
        self.assertTrue(plugin._pending)
        plugin._on_post_tool_call(status='blocked', **ids)
        self.assertFalse(plugin._pending)

    def test_telemetry_rollover_survives_cleared_memory(self):
        with patch.object(plugin, '_log_path', return_value=self.path):
            for i in range(25):
                self.assertIsNotNone(plugin._on_tool_request(
                    tool_name='read_file', args={'path': 'a', 'limit': '30'},
                    session_id='s', tool_call_id=str(i)))
            plugin._maybe_flush()
            self.assertEqual(plugin._counters, {})
            self.assertIn('25/25', plugin._summary())

    def test_repair_matrix_preserves_intent_and_never_mutates_input(self):
        cases = [
            ('read_file', {'path': 'report.md', 'offset': '12', 'limit': '20'}, {'path': 'report.md', 'offset': 12, 'limit': 20}),
            ('read_file', {'path': 'report.md', 'offset': None, 'limit': {}}, None),
            ('read_file', {'path': 'report.md', 'limit': None}, None),
            ('read_file', {'path': 'report.md', 'limit': {}}, None),
            ('search_files', {'pattern': 'x', 'limit': None}, None),
            ('read_file', {'path': 'report.md', 'offset': '-1'}, None),
            ('read_file', {'path': 'report.md', 'limit': '2.5'}, None),
            ('read_file', {'path': 'report.md', 'limit': '1e2'}, None),
            ('read_file', {'path': 'report.md', 'limit': True}, None),
            ('read_file', {'path': 'report.md', 'limit': 'nan'}, None),
            ('read_file', {'path': 'report.md', 'limit': '3000'}, None),
            ('read_file', {'path': 'report.md', 'limit': '12', 'offset': False}, None),
            ('read_file', {'path': None, 'limit': '12'}, None),
            ('read_file', {'path': '[report.md](http://report.md)'}, None),
            ('search_files', {'pattern': 'a.*', 'limit': '4', 'context': '2'}, {'pattern': 'a.*', 'limit': 4, 'context': 2}),
            ('search_files', {'pattern': 'a', 'target': 'wrong', 'limit': '4'}, None),
            ('terminal', {'command': 'printf safe', 'timeout': '90'}, {'command': 'printf safe', 'timeout': 90}),
            ('terminal', {'command': 'printf safe', 'timeout': None}, None),
            ('terminal', {'command': 'printf safe', 'timeout': '-1'}, None),
            ('terminal', {'command': None, 'timeout': '90'}, None),
            ('web_extract', {'urls': '["https://a.test","https://b.test"]'}, {'urls': ['https://a.test', 'https://b.test']}),
            ('web_extract', {'urls': '[bad'}, None),
            ('web_extract', {'urls': '["https://a.test", 42]'}, None),
            ('web_extract', {'urls': '[1,2,3,4,5,6]'}, None),
            ('web_extract', {'urls': '["https://1.test","https://2.test","https://3.test","https://4.test","https://5.test","https://6.test"]'}, None),
            ('web_extract', {'urls': 'https://a.test, https://b.test'}, None),
            ('web_extract', {'urls': []}, None),
            ('write_file', {'path': 'a', 'content': None}, None),
        ]
        for index, (name, args, expected) in enumerate(cases):
            with self.subTest(name=name, args=args):
                original = copy.deepcopy(args)
                result = plugin._on_tool_request(tool_name=name, args=args, session_id='matrix', tool_call_id=str(index))
                self.assertEqual(args, original)
                self.assertEqual(result['args'] if result else None, expected)

    def test_ids_with_separators_cannot_cross_sessions(self):
        a = {'session_id': 'a|b', 'tool_call_id': 'c', 'tool_name': 'read_file'}
        b = {'session_id': 'a', 'tool_call_id': 'b|c', 'tool_name': 'read_file'}
        self.assertIsNotNone(plugin._on_tool_request(args={'path': 'a', 'limit': '3'}, **a))
        self.assertIsNone(plugin._on_transform_result(result='{}', **b))
        self.assertIn('coerce_number', plugin._on_transform_result(result='{}', **a))

    def test_external_schema_references_are_never_resolved(self):
        from tools.registry import registry
        schema = {'type': 'object', 'properties': {'path': {'type': 'string'},
                  'limit': {'$ref': 'https://invalid.example/schema'}}, 'required': ['path']}
        definition = {'type': 'function', 'function': {'parameters': schema}}
        with patch.object(registry, 'definition_for', return_value=definition):
            self.assertIsNone(plugin._on_tool_request(tool_name='read_file',
                              args={'path': 'a', 'limit': '3'}, session_id='s', tool_call_id='x'))

    def test_four_outcomes_and_input_snapshots(self):
        outcomes = [
            ({'path': 'a', 'limit': 3}, plugin.OutcomeKind.VALID),
            ({'path': 'a', 'limit': '3'}, plugin.OutcomeKind.REPAIRED),
            ({'path': 'a', 'limit': 'too many'}, plugin.OutcomeKind.UNREPAIRABLE),
        ]
        for args, kind in outcomes:
            with self.subTest(kind=kind):
                original = copy.deepcopy(args)
                outcome = plugin._evaluate('read_file', args)
                self.assertEqual(outcome.kind, kind)
                self.assertEqual(args, original)
                self.assertEqual(outcome.original, original)
                if kind is plugin.OutcomeKind.REPAIRED:
                    self.assertEqual(outcome.candidate, {'path': 'a', 'limit': 3})
                    self.assertTrue(outcome.changes)
                if kind is plugin.OutcomeKind.UNREPAIRABLE:
                    self.assertIsNone(outcome.candidate)
                    self.assertTrue(outcome.issues)
                    self.assertEqual(outcome.issues[0].path, ('limit',))
                    self.assertEqual(outcome.issues[0].code, 'type')
                    self.assertNotIn('too many', repr(outcome.issues))
        with patch.object(plugin, '_validation_library', return_value=None):
            result = plugin._evaluate('read_file', {'path': 'a', 'limit': '3'})
            self.assertEqual(result.kind, plugin.OutcomeKind.UNAVAILABLE)
            self.assertEqual(result.reason, 'validator_unavailable')

    def test_outcome_rejects_inconsistent_states_and_hides_payload_in_repr(self):
        with self.assertRaises(ValueError):
            plugin.Outcome(plugin.OutcomeKind.REPAIRED, {'secret': 'a'})
        with self.assertRaises(ValueError):
            plugin.Outcome(plugin.OutcomeKind.UNAVAILABLE, {})
        with self.assertRaises(ValueError):
            plugin.Outcome(plugin.OutcomeKind.UNREPAIRABLE, {})
        with self.assertRaises(ValueError):
            plugin.Outcome('valid', {})
        result = plugin._evaluate('read_file', {'path': 'private-name', 'limit': '3'})
        self.assertNotIn('private-name', repr(result))

    def test_missing_required_field_has_actionable_diagnostic(self):
        result = plugin._evaluate('read_file', {'limit': '3'})
        self.assertEqual(result.kind, plugin.OutcomeKind.UNREPAIRABLE)
        self.assertTrue(any(issue.path == ('path',) and issue.code == 'required' for issue in result.issues))

    def test_four_outcomes_counted_without_argument_values(self):
        for index, args in enumerate(({'path':'private-name', 'limit':3}, {'path':'private-name', 'limit':'3'},
                                      {'path':'private-name', 'limit':'bad'})):
            plugin._on_tool_request(tool_name='read_file', args=args, session_id='s', tool_call_id=str(index))
        with patch.object(plugin, '_validation_library', return_value=None):
            plugin._on_tool_request(tool_name='read_file', args={'path':'private-name'}, session_id='s', tool_call_id='x')
        self.assertEqual([plugin._counters['read_file'].get('outcome:' + x) for x in ('valid','repaired','unrepairable','unavailable')], [1,1,1,1])
        with patch.object(plugin, '_log_path', return_value=self.path):
            summary = plugin._summary()
            self.assertIn('unrepairable=1', summary)
            self.assertIn('unavailable=1', summary)
            self.assertNotIn('private-name', self.path.read_text(encoding='utf-8'))

    def test_execution_guard_blocks_invalid_without_calling_handler(self):
        called = []
        result = plugin._on_tool_execution(tool_name='read_file',
                    args={'path': 'private-name', 'limit': 3000},
                    next_call=lambda args: called.append(args))
        self.assertEqual(called, [])
        self.assertIn('limit', result)
        self.assertIn('2000', result)
        self.assertNotIn('private-name', result)

    def test_execution_guard_passes_valid_and_fails_open_when_unavailable(self):
        called = []
        def handler(args):
            called.append(args)
            return 'handler result'
        self.assertEqual(plugin._on_tool_execution(tool_name='read_file', args={'path': 'a', 'limit': 3}, next_call=handler), 'handler result')
        with patch.object(plugin, '_validation_library', return_value=None):
            self.assertEqual(plugin._on_tool_execution(tool_name='read_file', args={'path': 'a', 'limit': 3000}, next_call=handler), 'handler result')
        self.assertEqual(len(called), 2)
        self.assertEqual(plugin._counters['read_file']['guard:unavailable'], 1)

    def test_execution_guard_does_not_retry_a_failing_handler(self):
        called = []
        def handler(args):
            called.append(args)
            raise RuntimeError('handler failed')
        with self.assertRaisesRegex(RuntimeError, 'handler failed'):
            plugin._on_tool_execution(tool_name='read_file', args={'path': 'a'}, next_call=handler)
        self.assertEqual(len(called), 1)


if __name__ == '__main__':
    unittest.main()
