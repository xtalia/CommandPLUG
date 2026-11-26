"""Repair catalogue for malformed tool-call arguments.

Inspired by Command Code's published deterministic repair patterns. The runtime
plugin enables only a narrow subset of this catalogue.

Design rules taken from that implementation and kept here:

1. Validate-then-repair, never preprocess. Valid input is never touched; repairs run
   only against a key whose declared schema type disagrees with what arrived.
2. Repairs are ordered. ``parse_json_stringified_array`` must run before
   ``wrap_bare_scalar_as_array``, otherwise ``'["a","b"]'`` becomes ``['["a","b"]']``:
   schema-valid, meaning destroyed.
3. Every repair returns a hint. The hint is surfaced to the model in the tool result,
   so a repaired call teaches the model instead of hiding the mistake.
4. A repair that cannot be made unambiguous is skipped, not guessed.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger("tool_harness")

# Function-call arguments that will be used as a filesystem path. A path field must not
# inherit the model's chat habit of auto-linking filenames as markdown.
_PATH_FIELDS = frozenset({
    "path", "file_path", "filepath", "file", "filename", "src", "source", "dest",
    "destination", "output", "output_path", "dir", "directory", "cwd", "workdir",
    "location", "target", "input_path", "notebook_path",
})

_MD_AUTOLINK = re.compile(r"^(?P<prefix>.*?)\[(?P<text>[^\]]*)\]\((?P<url>[^)]+)\)$")
_NUMERIC = re.compile(r"^-?(?:\d+|\d*\.\d+)$")

_Repair = tuple[str, Callable[[str, Any, dict, dict], str | None]]


def _schema_allows_null(prop: dict) -> bool:
    if prop.get("type") == "null":
        return True
    if isinstance(prop.get("type"), list) and "null" in prop["type"]:
        return True
    return any(
        isinstance(branch, dict) and _schema_allows_null(branch)
        for key in ("anyOf", "oneOf")
        for branch in (prop.get(key) or [])
    )


def _types(prop: dict) -> set[str]:
    declared = prop.get("type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list):
        return {t for t in declared if isinstance(t, str)}
    return set()


def repair_drop_null(args: dict, key: str, value: Any, prop: dict, notes: list[str]) -> bool:
    """``{"limit": null}`` where the schema omits null -> drop the key."""
    if value is not None or _schema_allows_null(prop):
        return False
    del args[key]
    notes.append(f"dropped `{key}`: null is not valid here, omit the field instead")
    return True


def repair_drop_empty_object(args: dict, key: str, value: Any, prop: dict, notes: list[str]) -> bool:
    """``{}`` sent as a placeholder for a non-object field."""
    if _types(prop) & {"object"} or not isinstance(value, dict) or value:
        return False
    del args[key]
    notes.append(f"dropped empty-object placeholder `{key}`")
    return True


def repair_coerce_number(args: dict, key: str, value: Any, prop: dict, notes: list[str]) -> bool:
    if not isinstance(value, str) or not _types(prop) & {"number", "integer"}:
        return False
    text = value.strip()
    if not text or not _NUMERIC.match(text):
        return False
    if "integer" in _types(prop):
        if not re.match(r"^-?\d+$", text):
            return False
        args[key] = int(text)
    else:
        args[key] = int(text) if re.match(r"^-?\d+$", text) else float(text)
    notes.append(f"coerced string `{key}` to a number")
    return True


def repair_coerce_boolean(args: dict, key: str, value: Any, prop: dict, notes: list[str]) -> bool:
    if not isinstance(value, str) or "boolean" not in _types(prop):
        return False
    lowered = value.strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        args[key] = True
    elif lowered in ("false", "0", "no", "off"):
        args[key] = False
    else:
        return False
    notes.append(f"coerced string `{key}` to a boolean")
    return True


def repair_parse_json_array(args: dict, key: str, value: Any, prop: dict, notes: list[str]) -> bool:
    """A real array delivered as a JSON *string*."""
    if not isinstance(value, str) or "array" not in _types(prop):
        return False
    text = value.strip()
    if not text.startswith("["):
        return False
    try:
        parsed = json.loads(text)
    except ValueError:
        return False
    if not isinstance(parsed, list):
        return False
    args[key] = parsed
    notes.append(f"parsed JSON-stringified array `{key}`")
    return True


def repair_parse_json_object(args: dict, key: str, value: Any, prop: dict, notes: list[str]) -> bool:
    if not isinstance(value, str) or "object" not in _types(prop):
        return False
    text = value.strip()
    if not text.startswith("{"):
        return False
    try:
        parsed = json.loads(text)
    except ValueError:
        return False
    if not isinstance(parsed, dict):
        return False
    args[key] = parsed
    notes.append(f"parsed JSON-stringified object `{key}`")
    return True


def repair_wrap_scalar(args: dict, key: str, value: Any, prop: dict, notes: list[str]) -> bool:
    """A bare scalar where an array is declared.

    Strings are wrapped only when they carry no obvious list separator: a comma-joined
    path list split by wrapping would silently address one wrong file.
    """
    if "array" not in _types(prop) or isinstance(value, (list, tuple)) or value is None:
        return False
    if isinstance(value, str) and ("," in value or ";" in value):
        return False
    if isinstance(value, str) and value.lstrip().startswith("["):
        return False  # Malformed JSON-looking arrays are not a single scalar.
    args[key] = [value]
    notes.append(f"wrapped scalar `{key}` in a one-element array")
    return True


def repair_markdown_path(args: dict, key: str, value: Any, prop: dict, notes: list[str]) -> bool:
    """``"/p/[notes.md](http://notes.md)"`` -> ``"/p/notes.md"``.

    Only the degenerate case where the link text equals the URL without a scheme is
    rewritten; a real markdown link is left alone. Any directory prefix is preserved.
    """
    if not isinstance(value, str) or key not in _PATH_FIELDS and prop.get("format") != "path":
        return False
    match = _MD_AUTOLINK.match(value.strip())
    if not match:
        return False
    text, url, prefix = match.group("text").strip(), match.group("url").strip(), match.group("prefix")
    bare = re.sub(r"^[a-z][a-z0-9+.-]*://", "", url).split("#", 1)[0].split("?", 1)[0].rstrip("/")
    # Degenerate only: the link text IS the URL minus its scheme.
    if not text or text != bare:
        return False
    args[key] = prefix + text
    notes.append(f"stripped markdown autolink from `{key}`")
    return True


def repair_optional_marker(args: dict, key: str, value: Any, prop: dict, notes: list[str]) -> bool:
    """``"limit?"`` — some tool docs write optional fields with a trailing marker."""
    if not key.endswith(("?", "*")) or len(key) < 2:
        return False
    stripped = key[:-1]
    if stripped in args or not stripped.replace("_", "").isalnum():
        return False
    args[stripped] = args.pop(key)
    notes.append(f"renamed `{key}` to `{stripped}`: the trailing marker is doc notation")
    return True


# Order is load-bearing: parse-stringified before wrap; drop-null before coercion.
CATALOGUE: tuple[_Repair, ...] = (
    ("drop_null", repair_drop_null),
    ("drop_empty_object", repair_drop_empty_object),
    ("coerce_number", repair_coerce_number),
    ("coerce_boolean", repair_coerce_boolean),
    ("parse_json_array", repair_parse_json_array),
    ("parse_json_object", repair_parse_json_object),
    ("wrap_scalar", repair_wrap_scalar),
    ("strip_markdown_path", repair_markdown_path),
    ("optional_marker", repair_optional_marker),
)


class _SchemaView:
    """The slice of a tool schema the repairs need, with local ``$ref`` resolution."""

    def __init__(self, parameters: dict):
        self.parameters = parameters if isinstance(parameters, dict) else {}
        self.properties = self.parameters.get("properties") or {}

    def prop(self, key: str) -> dict | None:
        spec = self.properties.get(key)
        return spec if isinstance(spec, dict) else None

    def accepts(self, key: str) -> bool:
        return key in self.properties


def repair_tool_args(
    tool_name: str, args: Any, *, parameters: dict | None = None,
    aliases: dict[str, dict[str, str]] | None = None,
) -> tuple[Any, list[str]]:
    """Return ``(repaired_args, notes)``.

    Shape repairs run only where the declared schema disagrees with the value, so a valid
    call passes through untouched. ``parameters`` overrides the registered schema (used by
    callers that already hold one). ``aliases`` maps ``{tool: {wrong_key: declared_key}}``
    and is applied only when the declared key is genuinely absent.
    """
    if not isinstance(args, dict) or not args:
        return args, []

    if parameters is None:
        from tools.registry import registry

        entry = None
        try:
            entry = registry.get_entry(tool_name)
        except Exception:
            entry = None
        parameters = ((entry.schema or {}).get("parameters") if entry is not None else None) or {}

    notes: list[str] = []
    if aliases and isinstance(aliases.get(tool_name), dict):
        for wrong, declared in aliases[tool_name].items():
            if wrong in args and declared not in args and args[wrong] not in (None, ""):
                args[declared] = args.pop(wrong)
                notes.append(f"renamed `{wrong}` to `{declared}` for `{tool_name}`")

    view = _SchemaView(parameters)
    if not view.properties:
        # No schema to validate against: only the universally safe path repair.
        for key in list(args):
            if repair_markdown_path(args, key, args[key], {}, notes) and notes:
                notes[-1] = f"strip_markdown_path: {notes[-1]}"
        return args, notes

    for key in list(args):
        if not view.accepts(key):
            stripped = key[:-1] if key.endswith(("?", "*")) else None
            if stripped and view.accepts(stripped) and stripped not in args:
                args[stripped] = args.pop(key)
                notes.append(f"optional_marker: renamed `{key}` to `{stripped}`: the trailing marker is doc notation")
            continue
        prop = view.prop(key) or {}
        # Coercions look at the current value each round; a single repair may expose another.
        for name, repair in CATALOGUE:
            if key not in args:
                break
            before = len(notes)
            if repair(args, key, args[key], prop, notes):
                # Prefix the rule name: telemetry parses it, and the model sees which repair ran.
                if len(notes) > before and not notes[before].startswith(f"{name}:"):
                    notes[before] = f"{name}: {notes[before]}"
                if key in args:
                    continue
                break

    if notes:
        logger.info("tool_harness repaired %s: %s", tool_name, "; ".join(notes))
    return args, notes


def repair_note(tool_name: str, notes: list[str]) -> str:
    """One readable line for the model: what was changed and why it must not recur."""
    if not notes:
        return ""
    return (
        f"[tool-harness] Arguments for `{tool_name}` were repaired before execution: "
        + "; ".join(notes)
        + ". Send the corrected shape next time."
    )
