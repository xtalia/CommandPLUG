"""Acceptance tests for the tool-harness repair catalogue.

Each case states what the model actually sends and what the schema declares, then asserts
the repaired value AND the note (a repair without a note silently corrupts the call).

Schemas are passed explicitly so the catalogue is tested independently of which tools this
Hermes install happens to register; the last case exercises the live registry path.

Run: python plugins/tool-harness/tests/test_repairs.py
"""

from __future__ import annotations

import os
import sys
import tempfile

os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="tool-harness-test-")

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))  # the plugin dir, for ``repairs``
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))))

from repairs import repair_tool_args  # noqa: E402

FAILS: list[str] = []

READ = {"type": "object", "properties": {
    "path": {"type": "string"},
    "offset": {"type": "integer"},
    "limit": {"type": "integer"},
}}
DELEGATE = {"type": "object", "properties": {
    "tasks": {"type": "array", "items": {"type": "object"}},
    "goal": {"type": "string"},
}}
TODO = {"type": "object", "properties": {"completed": {"type": "boolean"}}}
SCHEDULE = {"type": "object", "properties": {
    "when": {"type": "object", "properties": {"at": {"type": "string"}}},
}}


def check(label: str, tool: str, schema: dict, sent: dict, want: dict, want_note: str | None) -> None:
    got, notes = repair_tool_args(tool, dict(sent), parameters=schema)
    matched = want_note is None or any(want_note in n for n in notes)
    ok = got == want and matched
    if not ok:
        FAILS.append(f"{label}: got {got} notes={notes}; wanted {want} note~{want_note!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got} {notes}")


# --- the four shape mistakes Command Code prices as ~90% of open-model tool failures
check("null-for-optional", "read_file", READ, {"path": "a.py", "offset": None, "limit": None},
      {"path": "a.py"}, "dropped `offset`")
check("json-array-parse", "delegate_task", DELEGATE, {"tasks": '[{"goal":"g"}]'},
      {"tasks": [{"goal": "g"}]}, "parsed JSON-stringified array")
check("bare-string-wrap", "delegate_task", DELEGATE, {"tasks": "do the thing"},
      {"tasks": ["do the thing"]}, "wrapped scalar")
check("string-number", "read_file", READ, {"path": "a.py", "limit": "30"},
      {"path": "a.py", "limit": 30}, "coerced string `limit` to a number")
check("json-object-parse", "schedule", SCHEDULE, {"when": '{"at":"9am"}'},
      {"when": {"at": "9am"}}, "parsed JSON-stringified object")

# --- ordering: parse-stringified must run before wrap, or the array becomes a string in a list
got, _ = repair_tool_args("delegate_task", {"tasks": '["a","b"]'}, parameters=DELEGATE)
if got != {"tasks": ["a", "b"]}:
    FAILS.append(f'ordering: ["a","b"] as a string became {got}')

# --- path repairs: the model's chat habit leaking across the tool boundary
check("markdown-autolink", "read_file", READ, {"path": "[notes.md](http://notes.md)"},
      {"path": "notes.md"}, "stripped markdown autolink")
check("markdown-autolink-in-dir", "read_file", READ, {"path": "/p/[notes.md](http://notes.md)"},
      {"path": "/p/notes.md"}, "stripped markdown autolink")
check("real-markdown-link-kept", "read_file", READ, {"path": "[click](https://x.com/page)"},
      {"path": "[click](https://x.com/page)"}, None)

# --- ambiguity is refused, never guessed
check("comma-list-not-wrapped", "delegate_task", DELEGATE, {"tasks": "a.py, b.py"},
      {"tasks": "a.py, b.py"}, None)
check("non-numeric-string-kept", "read_file", READ, {"path": "a.py", "limit": "thirty"},
      {"path": "a.py", "limit": "thirty"}, None)
check("null-kept-when-schema-allows", "read_file",
      {"type": "object", "properties": {"path": {"type": "string"},
                                        "offset": {"type": ["integer", "null"]}}},
      {"path": "a.py", "offset": None}, {"path": "a.py", "offset": None}, None)

# --- doc-notation keys and placeholders
check("optional-marker-key", "read_file", READ, {"path": "a.py", "limit?": 5},
      {"path": "a.py", "limit": 5}, "renamed `limit?`")
check("empty-object-placeholder", "read_file", READ, {"path": "a.py", "offset": {}},
      {"path": "a.py"}, "empty-object placeholder")

# --- a valid call must pass through byte-identical, and unknown schemas stay untouched
check("valid-call-untouched", "read_file", READ, {"path": "a.py", "offset": 10, "limit": 20},
      {"path": "a.py", "offset": 10, "limit": 20}, None)
check("unknown-schema-untouched", "no_such_tool", {}, {"whatever": 1}, {"whatever": 1}, None)

# --- booleans open models actually emit
check("bool-yes", "todo_list", TODO, {"completed": "yes"}, {"completed": True}, "coerced string `completed`")
check("bool-off", "todo_list", TODO, {"completed": "off"}, {"completed": False}, "coerced string `completed`")

# --- live registry path: the plugin must read the real schema, not a guess
import tools.file_tools  # noqa: E402,F401  (registers read_file)
live, live_notes = repair_tool_args("read_file", {"path": "a.py", "limit": "40"})
if live == {"path": "a.py", "limit": 40} and live_notes:
    print(f"ok   live-registry read_file: {live} {live_notes}")
else:
    FAILS.append(f"live registry: got {live} notes={live_notes}")

print()
if FAILS:
    print(f"FAILED {len(FAILS)}:")
    for line in FAILS:
        print(" -", line)
    sys.exit(1)
print("all tool-harness repair cases passed")
