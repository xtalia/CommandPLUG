import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "commandcode_status", Path(__file__).resolve().parents[1] / "commandcode_status.py"
)
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class CommandCodeStatus(unittest.TestCase):
    def test_real_path_with_spaces_does_not_execute_candidate(self):
        with tempfile.TemporaryDirectory(prefix="CommandPLUG spaces ") as path:
            root = Path(path)
            self.assertEqual(status.availability(path), "missing")
            candidate = root / ("cmdc.cmd" if os.name == "nt" else "commandcode")
            candidate.write_text("This is deliberately not a program.", encoding="utf-8")
            candidate.chmod(0o755)
            with patch.dict(os.environ, {"PATH": path}):
                self.assertEqual(status.availability(), "found")
            candidate.unlink()
            (root / ("cmd.exe" if os.name == "nt" else "cmd")).touch()
            self.assertEqual(status.availability(path), "missing")

    def test_explicit_path_rules(self):
        with patch.object(status, "_has_command", return_value=True) as probe:
            self.assertEqual(status.availability(';.\\bin;"C:\\A B"', windows=True), "found")
            self.assertEqual(probe.call_args.args[0], "C:\\A B")
            probe.reset_mock()
            self.assertEqual(status.availability(":.:bin", windows=False), "missing")
            probe.assert_not_called()

    @unittest.skipIf(os.name == "nt", "POSIX executable permission")
    def test_requires_posix_executable(self):
        with tempfile.TemporaryDirectory() as path:
            candidate = Path(path) / "commandcode"
            candidate.touch()
            candidate.chmod(0o644)
            self.assertEqual(status.availability(path), "missing")


if __name__ == "__main__":
    unittest.main()
