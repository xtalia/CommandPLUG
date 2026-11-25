"""CommandPLUG — Hermes middleware inspired by Command Code's repair layer.

What it does, in the order Hermes runs it:

* ``tool_request`` middleware repairs the argument dict after the model produced it and
  before the handler. The public preview limits changes to optional numeric controls.
* The repair notes are stashed per tool call and appended to the tool's result by the
  ``transform_tool_result`` hook, as a machine-readable field plus one prose line. The
  model therefore learns the correct shape from the same turn, instead of repeating the
  mistake until the turn cap.
* Counters (calls, repairs per rule, per tool) are kept in memory and flushed to
  ``$HERMES_HOME/logs/tool-harness.jsonl``; ``/tool-harness`` prints them.

Fail-open everywhere: any error in this plugin returns the model's original args and the
original result.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("tool_harness")


_MAX_PENDING = 512
_FLUSH_EVERY = 25

_lock = threading.Lock()
_pending: dict[str, list[str]] = {}
_counters: dict[str, dict[str, int]] = {}
_repairs_since_flush = 0
_CONTROLS = {
    "read_file": frozenset({"offset", "limit"}),
    "search_files": frozenset({"offset", "limit", "context"}),
    "terminal": frozenset({"timeout"}),
}


def _key(kwargs: dict) -> str:
    return "|".join(str(kwargs.get(part) or "") for part in ("session_id", "tool_call_id", "tool_name"))


def _on_tool_request(**kwargs: Any) -> dict | None:
    """Repair only the numeric controls enabled for the public preview."""
    try:
        from .repairs import repair_tool_args

        tool_name = str(kwargs.get("tool_name") or "")
        args = kwargs.get("args")
        controls = _CONTROLS.get(tool_name)
        if not controls or not isinstance(args, dict):
            return None

        key = _key(kwargs)
        call_id = str(kwargs.get("tool_call_id") or "")
        with _lock:
            stats = _counters.setdefault(tool_name, {"calls": 0, "repaired": 0})
            stats["calls"] += 1
            if call_id and key in _pending:
                return None

        selected = {k: v for k, v in args.items() if k in controls}
        normalized, notes = repair_tool_args(tool_name, dict(selected))
        allowed_rules = ("coerce_number:",) if tool_name == "terminal" else (
            "coerce_number:", "drop_null:", "drop_empty_object:",
        )
        if not notes:
            return None
        if not all(note.startswith(allowed_rules) for note in notes):
            return None
        if not all(type(value) is int for value in normalized.values()):
            return None
        if tool_name == "terminal" and set(normalized) != set(selected):
            return None
        repaired = {k: v for k, v in args.items() if k not in selected}
        repaired.update(normalized)

        with _lock:
            _counters[tool_name]["repaired"] += 1
            for note in notes:
                rule = note.split(":", 1)[0].strip().replace(" ", "_")
                counter_key = f"rule:{rule}"
                _counters[tool_name][counter_key] = _counters[tool_name].get(counter_key, 0) + 1
            if call_id and kwargs.get("session_id"):
                # Bounded: a note is only meaningful for the call that produced it, and a chain
                # that never fires the result hook must not grow this dict without limit.
                if len(_pending) >= _MAX_PENDING:
                    _pending.pop(next(iter(_pending)))
                _pending[key] = notes

            globals()["_repairs_since_flush"] = _repairs_since_flush + 1

        return {"args": repaired, "source": "tool-harness", "reason": "; ".join(notes)}
    except Exception:
        logger.debug("tool-harness request middleware failed; passing args through", exc_info=True)
        return None


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


def _log_path() -> Path:
    from hermes_constants import get_hermes_home

    return Path(get_hermes_home()) / "logs" / "tool-harness.jsonl"


def _flush() -> int:
    with _lock:
        snapshot = {tool: dict(stats) for tool, stats in _counters.items()}
        _counters.clear()
        globals()["_repairs_since_flush"] = 0
    if not snapshot:
        return 0
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "tools": snapshot}, ensure_ascii=False) + "\n")
    except Exception:
        logger.debug("tool-harness could not flush counters", exc_info=True)
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
    read: dict[str, dict[str, int]] = {}
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
    if not read:
        return (
            "tool-harness: no tool calls counted yet (it counts every call, repaired or not).\n"
            + _commandcode_line()
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
    if flushed:
        lines.append(f"(flushed {flushed} more repairs this call)")
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
            return _SENTINEL
        if argument == "dependencies":
            return json.dumps({"commandcode": _commandcode_state()}, separators=(",", ":"))
        return f"{_SENTINEL} — tool-harness is repairing tool-call arguments.\n{_summary()}"
    except Exception:
        logger.debug("tool-harness command failed", exc_info=True)
        return f"{_SENTINEL} — summary unavailable."


def register(ctx):
    ctx.register_middleware("tool_request", _on_tool_request)
    ctx.register_hook("transform_tool_result", _on_transform_result)
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
