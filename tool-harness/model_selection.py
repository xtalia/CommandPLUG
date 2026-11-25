"""Opt-in model selection for fresh Command Code delegation runs."""

import argparse
import json
from pathlib import Path
import re

MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")


def validate(model):
    if not isinstance(model, str) or not MODEL_ID.fullmatch(model):
        raise ValueError("Invalid model ID; use the exact Command Code ID")
    return model


def resolve(task_model, project):
    if task_model is not None:
        return validate(task_model), "task"
    config = project / ".commandplug.json"
    if not config.exists():
        return None, "commandcode"
    data = json.loads(config.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"model"}:
        raise ValueError(".commandplug.json must contain exactly a model field")
    return validate(data["model"]), "project"


def verify(path, exit_code, expected):
    models = []
    result = None
    error = None
    try:
        with path.open(encoding="utf-8") as frames:
            for line in frames:
                if not line.strip():
                    continue
                frame = json.loads(line)
                if result is not None or not isinstance(frame, dict):
                    raise ValueError("unexpected frame")
                if frame.get("type") == "result":
                    result = frame
                event = frame.get("event") if frame.get("type") == "event" else None
                if isinstance(event, dict) and event.get("type") == "model_request_end":
                    model = validate(event.get("model"))
                    if model not in models:
                        models.append(model)
    except (OSError, ValueError):
        error = "Unreadable or invalid Command Code NDJSON"
    if exit_code != 0:
        error = f"Command Code exited with code {exit_code}; no fallback requested"
    elif not error:
        if not result or result.get("subtype") != "success" or result.get("stopReason") != "end_turn":
            error = "No successful final end_turn result"
        elif not models:
            error = "No model evidence in model_request_end events"
        elif expected is not None and models != [expected]:
            error = "Observed model differs from the selected model"
    return {"ok": error is None, "expected_model": expected, "observed_models": models, "error": error}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    select = commands.add_parser("resolve")
    select.add_argument("--project", required=True, type=Path)
    select.add_argument("--model")
    check = commands.add_parser("verify")
    check.add_argument("--events", required=True, type=Path)
    check.add_argument("--exit-code", required=True, type=int)
    check.add_argument("--expected-model")
    args = parser.parse_args()
    try:
        if args.action == "resolve":
            if not args.project.is_dir():
                raise ValueError("Project directory does not exist")
            model, source = resolve(args.model, args.project)
            print(json.dumps({"model": model, "source": source, "argv": ["--model", model] if model else []}))
            return 0
        expected = validate(args.expected_model) if args.expected_model is not None else None
        result = verify(args.events, args.exit_code, expected)
        print(json.dumps(result))
        return 0 if result["ok"] else 1
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
