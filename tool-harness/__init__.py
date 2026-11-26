"""CommandPLUG — Hermes middleware inspired by Command Code's repair layer.

What it does, in the order Hermes runs it:

* ``tool_request`` middleware validates the original call, repairs allowlisted invalid
  fields and validates again before the handler.
* ``tool_execution`` checks the arguments visible at that middleware boundary and
  returns a retry error for invalid calls; this is not a universal final-dispatch gate.
* The repair notes are stashed per tool call and appended to the tool's result by the
  ``transform_tool_result`` hook, as a machine-readable field plus one prose line. The
  model therefore learns the correct shape from the same turn, instead of repeating the
  mistake until the turn cap.
* Counters (calls, repairs per rule, per tool) are kept in memory and flushed to
  ``$HERMES_HOME/logs/tool-harness.jsonl``; ``/tool-harness`` prints them.

Unavailable checks fail open; explicitly invalid calls observed by the execution check
are rejected. Hermes may transform arguments before or after this middleware boundary.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("tool_harness")


_MAX_PENDING = 512
_FLUSH_EVERY = 25

_lock = threading.Lock()
_pending: dict[tuple[str, str, str], list[str]] = {}
_counters: dict[str, dict[str, int]] = {}
_repairs_since_flush = 0
_CONTROLS = {
    "read_file": frozenset({"offset", "limit"}),
    "search_files": frozenset({"offset", "limit", "context"}),
    "terminal": frozenset({"timeout"}),
    "web_extract": frozenset({"urls", "char_limit"}),
}


def _has_external_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return any((key in ("$ref", "$dynamicRef") and isinstance(child, str) and not child.startswith("#"))
                   or _has_external_reference(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_has_external_reference(child) for child in value)
    return False


def _validation_library():
    try:
        from jsonschema.validators import validator_for
        return validator_for
    except ImportError:
        return None


def _key(kwargs: dict) -> tuple[str, str, str]:
    return tuple(str(kwargs.get(part) or "") for part in ("session_id", "tool_call_id", "tool_name"))


class OutcomeKind(str, Enum):
    VALID = "valid"
    REPAIRED = "repaired"
    UNREPAIRABLE = "unrepairable"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Issue:
    path: tuple[str, ...]
    code: str
    expected: str


@dataclass(frozen=True)
class Outcome:
    kind: OutcomeKind
    original: Any = field(repr=False)
    candidate: dict | None = field(default=None, repr=False)
    issues: tuple[Issue, ...] = ()
    changes: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OutcomeKind):
            raise ValueError("outcome kind must be an OutcomeKind")
        if self.kind is OutcomeKind.REPAIRED:
            if self.candidate is None or not self.changes:
                raise ValueError("repaired outcome needs a candidate and changes")
        elif self.candidate is not None or self.changes:
            raise ValueError("only repaired outcomes may carry a candidate or changes")
        if self.kind is OutcomeKind.UNREPAIRABLE and not self.issues:
            raise ValueError("unrepairable outcome needs diagnostic issues")
        if self.kind is OutcomeKind.UNAVAILABLE and not self.reason:
            raise ValueError("unavailable outcome needs a reason")
        if self.kind is OutcomeKind.VALID and (self.issues or self.reason):
            raise ValueError("valid outcomes cannot carry issues or a failure reason")


def _issues(errors: list) -> tuple[Issue, ...]:
    """Describe schema failures without copying actual argument values into diagnostics."""
    result = []
    for error in errors:
        code = str(error.validator or "schema")
        path = tuple(str(part) for part in error.absolute_path)
        if code == "required" and isinstance(error.instance, dict) and isinstance(error.validator_value, list):
            for name in error.validator_value:
                if isinstance(name, str) and name not in error.instance:
                    issue = Issue(path + (name,), "required", "required field")
                    if issue not in result:
                        result.append(issue)
            continue
        expected = "follow the tool schema"
        if code == "type":
            declared = error.validator_value
            if isinstance(declared, str):
                expected = declared
            elif isinstance(declared, list) and all(isinstance(x, str) for x in declared):
                expected = " or ".join(declared)
        elif code in ("minimum", "maximum", "minItems", "maxItems"):
            value = error.validator_value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                expected = f"{code} {value}"
        result.append(Issue(path, code, expected))
    return tuple(result)


def _evaluate(tool_name: str, args: Any) -> Outcome:
    """Produce a typed proposal, never execute a tool or mutate the caller's arguments."""
    original = None
    try:
        from tools.registry import registry
        from .repairs import repair_tool_args
        original = deepcopy(args)
        controls = _CONTROLS.get(tool_name)
        if not controls:
            return Outcome(OutcomeKind.UNAVAILABLE, original, reason="unsupported_tool")
        if not isinstance(original, dict):
            return Outcome(OutcomeKind.UNREPAIRABLE, original, issues=(Issue((), "type", "object"),), reason="invalid_arguments")
        validator_for = _validation_library()
        if validator_for is None:
            return Outcome(OutcomeKind.UNAVAILABLE, original, reason="validator_unavailable")
        definition = registry.definition_for(tool_name) or {}
        schema = (definition.get("function") or {}).get("parameters")
        if not isinstance(schema, dict):
            return Outcome(OutcomeKind.UNAVAILABLE, original, reason="schema_unavailable")
        if _has_external_reference(schema):
            return Outcome(OutcomeKind.UNAVAILABLE, original, reason="external_schema_reference")
        validator_type = validator_for(schema)
        validator_type.check_schema(schema)
        validator = validator_type(schema)
        errors = list(validator.iter_errors(original))
        if not errors:
            return Outcome(OutcomeKind.VALID, original)
        issues = _issues(errors)
        invalid = {error.path[0] for error in errors
                   if error.validator == "type" and len(error.path) == 1 and error.path[0] in controls}
        if not invalid:
            return Outcome(OutcomeKind.UNREPAIRABLE, original, issues=issues, reason="no_safe_rule")
        selected = {k: deepcopy(v) for k, v in original.items() if k in invalid}
        normalized, notes = repair_tool_args(tool_name, selected, parameters=schema)
        allowed_rules = ("coerce_number:", "parse_json_array:")
        if not notes or not all(note.startswith(allowed_rules) for note in notes):
            return Outcome(OutcomeKind.UNREPAIRABLE, original, issues=issues, reason="no_safe_rule")
        if tool_name == "terminal" and set(normalized) != invalid:
            return Outcome(OutcomeKind.UNREPAIRABLE, original, issues=issues, reason="no_safe_rule")
        repaired = {k: deepcopy(v) for k, v in original.items() if k not in invalid}
        repaired.update(normalized)
        candidate_errors = list(validator.iter_errors(repaired))
        if candidate_errors:
            return Outcome(OutcomeKind.UNREPAIRABLE, original, issues=issues + _issues(candidate_errors), reason="candidate_invalid")
        return Outcome(OutcomeKind.REPAIRED, original, candidate=repaired, issues=issues, changes=tuple(notes))
    except Exception:
        # Validation exceptions can contain argument values; do not log their text.
        logger.debug("tool-harness evaluation failed")
        return Outcome(OutcomeKind.UNAVAILABLE, original, reason="evaluation_failed")


def _on_tool_request(**kwargs: Any) -> dict | None:
    """Adapt the typed proposal to Hermes' request-middleware contract."""
    try:
        tool_name = str(kwargs.get("tool_name") or "")
        args = kwargs.get("args")
        if tool_name not in _CONTROLS or not isinstance(args, dict):
            return None
        key = _key(kwargs)
        call_id = str(kwargs.get("tool_call_id") or "")
        with _lock:
            if call_id and key in _pending:
                return None
        outcome = _evaluate(tool_name, args)

        with _lock:
            if call_id and key in _pending:
                return None
            stats = _counters.setdefault(tool_name, {"calls": 0, "repaired": 0})
            stats["calls"] += 1
            outcome_key = f"outcome:{outcome.kind.value}"
            stats[outcome_key] = stats.get(outcome_key, 0) + 1
            if outcome.kind is not OutcomeKind.REPAIRED:
                return None
            notes = outcome.changes
            stats["repaired"] += 1
            for note in notes:
                rule = note.split(":", 1)[0].strip().replace(" ", "_")
                counter_key = f"rule:{rule}"
                stats[counter_key] = stats.get(counter_key, 0) + 1
            if call_id and kwargs.get("session_id"):
                # Bounded: a note is only meaningful for the call that produced it, and a chain
                # that never fires the result hook must not grow this dict without limit.
                if len(_pending) >= _MAX_PENDING:
                    _pending.pop(next(iter(_pending)))
                _pending[key] = list(notes)

            globals()["_repairs_since_flush"] = _repairs_since_flush + 1

        return {"args": deepcopy(outcome.candidate), "source": "tool-harness", "reason": "; ".join(notes)}
    except Exception:
        logger.debug("tool-harness request middleware failed; passing args through", exc_info=True)
        return None


def _on_tool_execution(**kwargs: Any) -> Any:
    """Check the effective arguments at the execution middleware boundary.

    Unavailable checks pass through, per the selected policy. Never catch handler
    exceptions: the execution chain owns them and must never invoke a handler twice.
    """
    tool_name = str(kwargs.get("tool_name") or "")
    args = kwargs.get("args")
    next_call = kwargs["next_call"]
    if tool_name not in _CONTROLS:
        return next_call(args)
    outcome = _evaluate(tool_name, args)
    blocked = outcome.kind in (OutcomeKind.REPAIRED, OutcomeKind.UNREPAIRABLE)
    guard = "blocked" if blocked else outcome.kind.value
    with _lock:
        stats = _counters.setdefault(tool_name, {"calls": 0, "repaired": 0})
        counter = f"guard:{guard}"
        stats[counter] = stats.get(counter, 0) + 1
    if blocked:
        details = [{"path": list(issue.path), "code": issue.code, "expected": issue.expected}
                   for issue in outcome.issues]
        return json.dumps({"error": f"{tool_name} arguments did not pass schema validation. The handler was not invoked. Correct the fields and retry.",
                           "error_type": "tool_validation", "issues": details}, ensure_ascii=False)
    return next_call(args)


def _append_note(result: Any, note: str) -> Any:
    """Add the repair note without breaking JSON-shaped tool results."""
    if not isinstance(result, str):
        return result
    try:
        parsed = json.loads(result)
    except ValueError:
        return result + ("\n" if result and not result.endswith("\n") else "") + note
    if not isinstance(parsed, dict) or "_tool_harness" in parsed:
        return result
    parsed["_tool_harness"] = note
    return json.dumps(parsed, ensure_ascii=False)


def _on_transform_result(**kwargs: Any) -> Any:
    try:
        key = _key(kwargs)
        tool_name = str(kwargs.get("tool_name") or "")
        with _lock:
            notes = _pending.pop(key, None)

        if not notes:
            return None
        from .repairs import repair_note

        return _append_note(kwargs.get("result"), repair_note(tool_name, notes))
    except Exception:
        logger.debug("tool-harness transform hook failed", exc_info=True)
        return None


def _on_post_tool_call(**kwargs: Any) -> None:
    # Blocked calls return before transform_tool_result in the Hermes agent loop.
    if kwargs.get("status") == "blocked":
        with _lock:
            _pending.pop(_key(kwargs), None)


def _log_path() -> Path:
    from hermes_constants import get_hermes_home

    return Path(get_hermes_home()) / "logs" / "tool-harness.jsonl"


def _flush() -> int:
    with _lock:
        snapshot = {tool: dict(stats) for tool, stats in _counters.items()}
        if not snapshot:
            return 0
        try:
            path = _log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": time.time(), "tools": snapshot}, ensure_ascii=False) + "\n")
        except Exception:
            logger.warning("tool-harness could not flush counters; retaining them in memory", exc_info=True)
            return 0
        _counters.clear()
        globals()["_repairs_since_flush"] = 0
        return sum(stats.get("repaired", 0) for stats in snapshot.values())


def _maybe_flush() -> None:
    with _lock:
        due = _repairs_since_flush >= _FLUSH_EVERY
    if due:
        _flush()


def _commandcode_state() -> str:
    try:
        from .commandcode_status import availability

        return availability()
    except Exception:
        return "unknown"


def _commandcode_line() -> str:
    state = _commandcode_state()
    if state == "found":
        return "Command Code CLI: found on backend PATH"
    if state == "missing":
        return "Command Code CLI: not found on backend PATH (optional for repair)"
    return "Command Code CLI: status unknown"


def _summary() -> str:
    flushed = _flush()
    validation = "Validation: available" if _validation_library() is not None else "Validation unavailable: jsonschema is not installed; repairs are skipped"
    read: dict[str, dict[str, int]] = {}
    with _lock:
        try:
            path = _log_path()
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        payload = json.loads(line)
                    except ValueError:
                        continue
                    for tool, stats in (payload.get("tools") or {}).items():
                        agg = read.setdefault(tool, {})
                        for name, value in stats.items():
                            agg[name] = agg.get(name, 0) + int(value)
        except Exception:
            read = {}
        unpersisted = {tool: dict(stats) for tool, stats in _counters.items()}
    for tool, stats in unpersisted.items():
        agg = read.setdefault(tool, {})
        for name, value in stats.items():
            agg[name] = agg.get(name, 0) + value
    if not read:
        return (
            "tool-harness: no calls counted yet for the configured tools.\n"
            + validation + "\n" + _commandcode_line()
        )
    lines = ["tool-harness — repairs / calls per tool:"]
    for tool in sorted(read):
        stats = read[tool]
        calls, repaired = stats.get("calls", 0), stats.get("repaired", 0)
        rate = f"{100 * repaired / calls:.1f}%" if calls else "—"
        rules = ", ".join(
            f"{name.split(':', 1)[1]}={value}" for name, value in sorted(stats.items())
            if name.startswith("rule:")
        )
        lines.append(f"  {tool}: {repaired}/{calls} ({rate})" + (f" — {rules}" if rules else ""))
        outcomes = ", ".join(f"{kind.value}={stats.get('outcome:' + kind.value, 0)}" for kind in OutcomeKind)
        if any(name.startswith("outcome:") for name in stats):
            lines.append(f"    proposals: {outcomes} (not execution results)")
        guards = ", ".join(f"{name.split(':', 1)[1]}={value}" for name, value in sorted(stats.items()) if name.startswith("guard:"))
        if guards:
            lines.append(f"    execution check: {guards}")
    if flushed:
        lines.append(f"(flushed {flushed} more repairs this call)")
    if unpersisted:
        lines.append("(some counts are not persisted; retry after fixing log access)")
    lines.append(validation)
    lines.append(_commandcode_line())
    return "\n".join(lines)


_SENTINEL = "CommandPLUG: active"


def _command(raw_args: str = "", **kwargs: Any) -> str:
    """``/tool-harness`` entry point.

    ``status`` is a pure liveness probe: no counters are flushed, no log is read, so a
    status chip polling every 20s never perturbs the metrics it reports. ``dependencies``
    is likewise side-effect free and reports the optional CLI as JSON.
    """
    try:
        argument = str(raw_args or "").strip().lower()
        if argument == "status":
            return _SENTINEL if _validation_library() is not None else "CommandPLUG: validation unavailable"
        if argument == "dependencies":
            return json.dumps({"commandcode": _commandcode_state()}, separators=(",", ":"))
        headline = _SENTINEL if _validation_library() is not None else "CommandPLUG: validation unavailable"
        return f"{headline}\n{_summary()}"
    except Exception:
        logger.debug("tool-harness command failed", exc_info=True)
        return "CommandPLUG: status unconfirmed — summary unavailable."


def register(ctx):
    ctx.register_middleware("tool_request", _on_tool_request)
    ctx.register_middleware("tool_execution", _on_tool_execution)
    ctx.register_hook("transform_tool_result", _on_transform_result)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("on_session_end", lambda **kw: _flush())
    ctx.register_command(
        "commandplug",
        _command,
        "Show CommandPLUG status and tool-call repair counts.",
    )
    ctx.register_command("tool-harness", _command, "Alias for /commandplug.")
    try:
        ctx.register_hook("agent_loop_stopped", lambda **kw: _maybe_flush())
    except Exception:
        pass
