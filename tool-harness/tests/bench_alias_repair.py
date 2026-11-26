"""Deterministic harness-level benchmark: an aliased `read_file` call, before vs after repair.

WHAT THIS MEASURES
------------------
* tool calls to the first successful read, and
* wall-clock elapsed for that call sequence,
running the INSTALLED Hermes ``read_file`` handler through ``registry.dispatch``.

WHAT THIS DOES NOT MEASURE
--------------------------
This is a tool-layer call-count / latency comparison. It is NOT a provider token count and
NOT an LLM retry measurement: no model is called and no tokens are billed. A comparative
model-level token benchmark needs live agent runs against a configured open-weight provider,
which this repository cannot assume; the numbers below must never be reported as "tokens
saved" or "LLM retries avoided".

The scenario scripts a failed call whose only path field is ``filePath``/``file_path``,
followed by a manually supplied correction to ``path``. The other arm applies the plugin's
request middleware first. This does not predict what a model would do after the error.

Run from a Hermes workspace (the dir containing ``run_agent.py``):
    python "$HERMES_HOME/plugins/tool-harness/tests/bench_alias_repair.py"
Skips cleanly (exit 0) when the Hermes tools package is not importable, so CI stays offline.
"""

from __future__ import annotations

import importlib.util
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

_temporary_env = []
for _key in ("HERMES_HOME", "TERMINAL_CWD"):
    if not os.environ.get(_key):
        _directory = tempfile.TemporaryDirectory(prefix="th-bench-")
        _temporary_env.append(_directory)
        os.environ[_key] = _directory.name

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "commandplug_bench", PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _succeeded(result) -> bool:
    import json
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        return False
    return isinstance(payload, dict) and not payload.get("error") and "content" in payload


def main() -> int:
    try:
        import tools.file_tools  # noqa: F401  (registers read_file)
        from tools.registry import registry
    except ModuleNotFoundError as exc:
        print(f"SKIP: Hermes tools package not importable here ({exc.name}); "
              "run inside a Hermes workspace to benchmark.")
        return 0

    plugin = _load_plugin()
    temporary_files = tempfile.TemporaryDirectory(prefix="th-bench-file-")
    workdir = temporary_files.name

    rounds = 20

    # A distinct file per measurement, and separate file sets for the two arms: a fresh
    # (path, offset, limit) key each read, so Hermes' per-task read dedup (a real, separate
    # optimization) cannot mask the effect, while ONE warmed task avoids per-round env setup.
    def make_file(label: str) -> str:
        path = os.path.join(workdir, f"{label}.txt")
        Path(path).write_text("\n".join(f"line {j}" for j in range(1, 51)) + "\n", encoding="utf-8")
        return path

    baseline_files = [make_file(f"base-{i}") for i in range(rounds)]
    repaired_files = [make_file(f"fix-{i}") for i in range(rounds)]
    warmup_file = make_file("warmup")

    task_id = "bench-task"

    def baseline_once(target: str) -> int:
        """A model that sent the alias: refused, then corrected to `path`."""
        calls = 0
        first = registry.dispatch("read_file", {"filePath": target}, task_id=task_id)
        calls += 1
        if _succeeded(first):
            return calls
        second = registry.dispatch("read_file", {"path": target}, task_id=task_id)
        calls += 1
        assert _succeeded(second), second
        return calls

    def repaired_once(target: str, call_index: int) -> int:
        """The plugin renames the key before dispatch: one call succeeds."""
        calls = 0
        args = {"filePath": target}
        # A unique call id per call, as the agent loop emits; reusing one id would (correctly)
        # be treated by the plugin as a duplicate in-flight call.
        changed = plugin._on_tool_request(tool_name="read_file", args=args,
                                          session_id=task_id, tool_call_id=f"bench-{call_index}")
        effective = changed["args"] if changed else args
        result = registry.dispatch("read_file", effective, task_id=task_id)
        calls += 1
        assert _succeeded(result), result
        return calls

    baseline_calls, repaired_calls = [], []
    baseline_t, repaired_t = [], []
    # Warm the file/terminal environment once on a throwaway file so creation is not timed.
    registry.dispatch("read_file", {"path": warmup_file}, task_id=task_id)
    for index, (b_target, r_target) in enumerate(zip(baseline_files, repaired_files)):
        t0 = time.perf_counter()
        baseline_calls.append(baseline_once(b_target))
        baseline_t.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        repaired_calls.append(repaired_once(r_target, index))
        repaired_t.append(time.perf_counter() - t0)

    def summary(name, calls, elapsed):
        med_calls = statistics.median(calls)
        med_ms = statistics.median(elapsed) * 1000
        print(f"{name}: tool calls to success = {med_calls:g} (min {min(calls)}, max {max(calls)}); "
              f"median elapsed = {med_ms:.3f} ms over {rounds} rounds")

    print(f"files: {rounds} x 50-line text files in {workdir}")
    summary("baseline (no repair)", baseline_calls, baseline_t)
    summary("with field-alias repair", repaired_calls, repaired_t)
    print("NOTE: call-count and wall-clock only. Not provider tokens, not LLM retries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
