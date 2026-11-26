"""End-to-end probe through Hermes' real plugin manager and middleware chain.

Not a simulation of the plugin's internals: this discovers the plugin the way the gateway
does, then calls the same ``apply_tool_request_middleware`` and ``transform_tool_result``
seams the agent loop calls, and asserts the observable outcome.

Run from the Hermes workspace (the dir containing ``run_agent.py``):
    python "$HERMES_HOME/plugins/tool-harness/tests/e2e_middleware.py"
"""

import json
import os
import sys
import tempfile

os.environ["HERMES_HOME"] = os.environ.get("HERMES_HOME") or tempfile.mkdtemp(prefix="th-probe-")

import tools.file_tools  # noqa: F401  (registers read_file)
import tools.web_tools  # noqa: F401  (registers web_extract)
from hermes_cli.middleware import apply_tool_request_middleware, run_tool_execution_middleware
from hermes_cli.plugins import has_hook, has_middleware

assert has_middleware("tool_request"), "plugin middleware not discovered — is tool-harness enabled?"
assert has_middleware("tool_execution"), "plugin execution middleware not discovered"
assert has_hook("transform_tool_result"), "plugin hook not discovered"

ids = {"session_id": "probe-session", "tool_call_id": "call-1"}

broken = {"path": "a.py", "limit": "30"}
result = apply_tool_request_middleware("read_file", dict(broken), **ids)
print("changed:", result.changed, "trace:", result.trace)
assert result.payload == {"path": "a.py", "limit": 30}, result.payload
assert result.changed and result.trace[0].get("source") == "tool-harness", result.trace

clean = apply_tool_request_middleware("read_file", {"path": "a.py", "limit": 30}, **ids)
assert not clean.changed and clean.payload == {"path": "a.py", "limit": 30}, (clean.changed, clean.payload)
print("valid call untouched, changed:", clean.changed)

from hermes_cli.plugins import invoke_hook  # imported late so discovery has run

res = invoke_hook(
    "transform_tool_result", tool_name="read_file", args={"path": "a.py", "limit": 30},
    result=json.dumps({"content": "1|hi", "total_lines": 1}), **ids,
)
out = next((r for r in res if isinstance(r, str)), None)
print("result the model sees:", out)
assert out and "_tool_harness" in out, out
parsed = json.loads(out)
assert parsed["content"] == "1|hi", parsed
assert "repaired before execution" in parsed["_tool_harness"], parsed["_tool_harness"]

again = invoke_hook("transform_tool_result", tool_name="read_file", args={"path": "a.py"}, result="plain", **ids)
assert not any(isinstance(r, str) for r in again), again
print("note applied once; second result untouched")

web_ids = {"session_id": "probe-session", "tool_call_id": "web-1"}
web = apply_tool_request_middleware("web_extract", {"urls": '["https://a.test", "https://b.test"]'}, **web_ids)
assert web.changed and web.payload == {"urls": ["https://a.test", "https://b.test"]}, web
web_result = invoke_hook("transform_tool_result", tool_name="web_extract", args=web.payload,
                         result='{"results": []}', **web_ids)
assert any(isinstance(item, str) and "parse_json_array" in item for item in web_result), web_result
invalid = apply_tool_request_middleware("read_file", {"path": "a.py", "limit": "3000"}, **web_ids)
assert not invalid.changed, invalid

called = []
def handler(args):
    called.append(args)
    return '{"content":"ok"}'

guarded = run_tool_execution_middleware("read_file", {"path": "a.py", "limit": 3000}, handler, **web_ids)
assert not called and json.loads(guarded)["error_type"] == "tool_validation", guarded
assert run_tool_execution_middleware("read_file", {"path": "a.py", "limit": 3}, handler, **web_ids) == '{"content":"ok"}'
assert len(called) == 1

# Exercise real direct and agent dispatch paths without running a real tool handler.
from unittest.mock import patch
from tools.registry import registry
from model_tools import handle_function_call
from agent.agent_runtime_helpers import invoke_tool
from types import SimpleNamespace

agent = SimpleNamespace(session_id="fixture", valid_tool_names=None, enabled_toolsets=None, disabled_toolsets=None)
with patch.object(registry, "dispatch", return_value='{"content":"fixture"}') as dispatch:
    direct = json.loads(handle_function_call("read_file", {"path": "fixture", "limit": "3000"},
                                            session_id="fixture", tool_call_id="direct"))
    assert direct.get("error_type") == "tool_validation" and dispatch.call_count == 0, direct
    via_agent = json.loads(invoke_tool(agent, "read_file", {"path": "fixture", "limit": "3000"},
                                       "fixture", tool_call_id="agent"))
    assert via_agent.get("error_type") == "tool_validation" and dispatch.call_count == 0, via_agent
    valid_agent = json.loads(invoke_tool(agent, "read_file", {"path": "fixture", "limit": "3"},
                                         "fixture", tool_call_id="agent-ok"))
    assert valid_agent.get("content") == "fixture" and dispatch.call_count == 1, valid_agent
    assert "coerce_number" in valid_agent.get("_tool_harness", ""), valid_agent
    # Direct dispatch coerces this malformed array string to a schema-valid list
    # before plugin middleware sees it. The original intent cannot be recovered.
    before = dispatch.call_count
    handle_function_call("web_extract", {"urls": "[broken"}, session_id="fixture", tool_call_id="direct-loss")
    assert dispatch.call_count == before + 1
    assert dispatch.call_args.args[1]["urls"] == ["[broken"]
print("direct and agent dispatch guard probes passed; handler mocked")

# Public-preview scope: no path/content/command rewrites or unknown-tool repair.
for tool, args in (
    ("read_file", {"path": "[notes.md](http://notes.md)"}),
    ("write_file", {"path": "x", "content": None}),
    ("terminal", {"command": "git status", "timeout": None}),
):
    probe = apply_tool_request_middleware(tool, args, **ids)
    assert not probe.changed and probe.payload == args

# A repair without a session identifier must not leak a note into another call.
bare_ids = {"tool_call_id": "call-2"}
assert apply_tool_request_middleware("read_file", dict(broken), **bare_ids).changed
assert not any(isinstance(x, str) for x in invoke_hook(
    "transform_tool_result", tool_name="read_file", args={}, result="{}", **bare_ids,
))

for i, original in enumerate((' [1, 2]', '"JSON string"', '{"_tool_harness":"existing"}')):
    scoped = {"tool_call_id": f"json-{i}", "session_id": "probe-session"}
    assert apply_tool_request_middleware("read_file", dict(broken), **scoped).changed
    outputs = invoke_hook("transform_tool_result", tool_name="read_file", args={}, result=original, **scoped)
    assert next((x for x in outputs if isinstance(x, str)), original) == original
print("PROBE OK")
