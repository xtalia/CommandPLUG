import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / "model_selection.py"
spec = importlib.util.spec_from_file_location("model_selection", HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ModelSelection(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name)
        self.events = self.project / "run.jsonl"

    def test_precedence_and_cli_argv(self):
        self.assertEqual(module.resolve(None, self.project), (None, "commandcode"))
        (self.project / ".commandplug.json").write_text('{"model":"vendor/project"}')
        self.assertEqual(module.resolve(None, self.project), ("vendor/project", "project"))
        output = subprocess.check_output([sys.executable, str(HELPER), "resolve", "--project", str(self.project), "--model", "vendor/task"])
        self.assertEqual(json.loads(output), {"model": "vendor/task", "source": "task", "argv": ["--model", "vendor/task"]})

    def test_invalid_selection_does_not_fall_back(self):
        config = self.project / ".commandplug.json"
        config.write_text('{"model":"vendor/project"}')
        for value in ("", "-flag", " vendor/id", "vendor/id;echo", "модель"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.resolve(value, self.project)
        config.write_text('{"model":null}')
        with self.assertRaises(ValueError):
            module.resolve(None, self.project)

    def test_verifies_wire_frames_and_rejects_fallback(self):
        event = {"type":"event", "event":{"type":"model_request_end", "model":"vendor/observed"}}
        final = {"type":"result", "subtype":"success", "stopReason":"end_turn"}
        self.events.write_text("\n".join(map(json.dumps, [event, event, final])))
        self.assertTrue(module.verify(self.events, 0, "vendor/observed")["ok"])
        self.assertTrue(module.verify(self.events, 0, None)["ok"])
        mismatch = module.verify(self.events, 0, "vendor/requested")
        self.assertFalse(mismatch["ok"])
        self.assertEqual(mismatch["observed_models"], ["vendor/observed"])
        self.assertFalse(module.verify(self.events, 8, None)["ok"])

    def test_missing_and_malformed_evidence_fails(self):
        self.assertFalse(module.verify(self.events, 0, None)["ok"])
        final = {"type":"result", "subtype":"success", "stopReason":"end_turn"}
        for text in (json.dumps(final), json.dumps(final) + '\n{}', 'not json'):
            self.events.write_text(text)
            self.assertFalse(module.verify(self.events, 0, None)["ok"])


if __name__ == "__main__":
    unittest.main()
