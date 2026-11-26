# CommandPLUG

![CommandPLUG cover: marble Hermes in pink sunglasses presses a yellow toy-laptop key amid Greek columns and blue-to-coral digital rain](assets/commandplug.webp)

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin inspired by [Command Code’s harness engineering](https://commandcode.ai/docs/harness-engineering). Fewer busted tool calls, fewer reruns.

## What it does

- Validates calls against the registered tool schema, repairs allowlisted invalid fields, and validates again before applying a repair. It handles numeric controls in `read_file`, `search_files`, `terminal`, and `web_extract`, JSON-stringified arrays in `web_extract.urls`, and the most common read-path synonyms (`file_path`, `filePath`, `absolutePath`, `target_file`, …) for `read_file.path`. It can tell the model what changed. It does not rewrite commands, paths, or file contents. The execution middleware rejects invalid calls it observes and returns a retry error; checks that cannot run fail open.
- Runs in the Hermes backend, not just Desktop. Use `/commandplug` for status and local repair counts. Desktop has an optional status-bar badge.

## How tool-call repair works

When a model wants to use a tool, it sends Hermes the tool name and arguments. For the fields listed below, CommandPLUG checks the arguments it receives against the tool's effective schema before the handler runs. Some Hermes dispatch paths may already have coerced the model's original arguments before the plugin sees them.

1. **Validate.** An already-valid call is left unchanged. If the schema is missing or cannot be checked, the plugin skips the repair.
2. **Repair.** For an allowlisted field with a type error, try a deterministic conversion on a copy. For example, `read_file({"path":"notes.md","limit":"30"})` becomes `read_file({"path":"notes.md","limit":30})`; `web_extract({"urls":"[\"https://example.com\"]"})` can become `web_extract({"urls":["https://example.com"]})`.
3. **Validate again.** Apply the candidate only if the *whole* call passes the same schema, including required fields and limits. Otherwise, leave the original arguments untouched.
4. **Explain when possible.** The tool result can include a `_tool_harness` note describing the change, so the model can use the right shape next time. The note is best effort: missing identifiers, blocked calls or result shapes that cannot safely carry metadata can prevent it. `/commandplug` shows local counts for the covered tools and whether validation is available; these are not counts of prevented errors or confirmed executions.

Each request check has an explicit outcome: **Valid** (already valid), **Repaired** (a separate candidate passed validation), **Unrepairable** (no safe candidate), or **Unavailable** (the schema or validator is unavailable or checking failed). Outcomes describe the proposal, not whether a tool ran. Structured diagnostics identify the schema rule and field without recording argument values. The execution middleware checks the arguments it receives for the four covered tools; if they are invalid, it returns a model-readable error instead of calling the next handler. If checking is unavailable, it passes the call through and counts `unavailable` separately.

| Tool | Fields eligible for repair |
| --- | --- |
| `read_file` | `offset`, `limit`: numeric strings to integers; `path`: recognized read-path synonyms (`file_path`, `filePath`, `filepath`, `absolute_path`, `absolutePath`, `target_file`, `filename`, `file_name`, `file`) renamed to `path` |
| `search_files` | `offset`, `limit`, `context`: numeric strings to integers |
| `terminal` | `timeout`: numeric strings to integers; the command is never rewritten |
| `web_extract` | `char_limit`: numeric strings to integers; `urls`: a JSON-stringified array to an array |

A path alias is a **key rename only**: it fires solely when `path` is missing, exactly one recognized synonym is present at all, that synonym is not itself a schema property, its value is a non-empty string, and the whole call re-validates afterwards. Presence is counted before values are inspected, so a second spelling — even one holding `null`, a number, or whitespace — makes the call ambiguous and blocks the rename. An empty value, a canonical `path` already present, and several synonyms at once are all left untouched — the plugin never guesses which path was meant. Because the rename is pure (no I/O, no value change), the real `read_file` still runs its device-path blocklist, sandbox backend, read ledger, and secret redaction exactly as before.

The plugin does **not** guess paths, turn a bare string into a URL list, or remove `null` / `{}` to substitute defaults. Other tools and nested fields are outside its repair scope. The repair catalogue also contains experimental rules that are **not enabled** in the runtime.

This is a best-effort repair and execution-check layer, **not a universal final-dispatch guarantee**. Depending on the route, Hermes may coerce arguments before the plugin sees them, or code and other middleware may transform them after the check. For example, direct dispatch can turn a malformed array string into a schema-valid single-element list before the plugin can inspect the original. An unavailable check also passes through by policy. A guarantee requires a core-level check after all transformations immediately before every handler. No claim of a measured reduction in failures is made without a comparative benchmark.

## What’s next — and why

- **[Taste](https://commandcode.ai/docs/taste):** keep reusable coding preferences so you don’t have to repeat the same corrections.
- **[Design](https://commandcode.ai/docs/design):** bring design, review, and refinement into the coding workflow so UI work gets fewer rounds of rework.
- **[Read](https://commandcode.ai/docs/harness-engineering/read-tool) and [shell](https://commandcode.ai/docs/harness-engineering/shell-tool):** this release adds read-path alias repair (`filePath`/`file_path` → `path`), which current Hermes otherwise rejects as "missing required argument(s): path". The capability inventory, current-source checks and remaining candidates are in [`docs/read-shell-comparison.md`](docs/read-shell-comparison.md). Multi-file batch reads are **not** implemented: dispatching underlying tools from a plugin does not establish equivalent per-call guards and session gating. The scripted [`tool-harness/tests/bench_alias_repair.py`](tool-harness/tests/bench_alias_repair.py) compares local tool-call counts and wall-clock with a manually supplied correction; it does **not** measure model retries or provider tokens. Comparative open-weight, GPT and Claude runs remain future work.

## Install

**Tool-call repair:** requires Hermes Agent with `tool_request` and `tool_execution` middleware and `jsonschema>=4.18,<5` installed in Hermes's Python environment. No Command Code or npm is needed for repair. If schema validation is unavailable, the plugin fails open and leaves arguments unchanged.

1. Copy the [`tool-harness`](tool-harness) folder into the active Hermes profile’s `plugins/` directory, then run `hermes plugins enable tool-harness`.
2. **Optional, Desktop:** copy [`tool-harness/desktop/plugin.js`](tool-harness/desktop/plugin.js) to `<Hermes home>/desktop-plugins/tool-harness/plugin.js`. The badge reports the connected profile’s status; it doesn’t enable the backend.

## Optional: delegate coding to Command Code

The [`commandcode-delegation` skill](skills/commandcode-delegation/SKILL.md) lets Hermes scope the task and verify the result while Command Code writes the code. To use it, copy the entire [`commandcode-delegation`](skills/commandcode-delegation) folder into the active Hermes profile’s `skills/` directory and start a new session. Install and authenticate the Command Code CLI separately. The skill and plugin can be used independently.

- **macOS / Linux / Windows:** for delegation, install the [Command Code CLI](https://commandcode.ai/docs/quickstart) on the machine where the delegated command runs. For npm installs, use Node.js 22 or later and run `npm install -g command-code`, then `commandcode --version`, `commandcode login`, and `commandcode status`. Use `commandcode` (or `cmdc`) on Windows, not `cmd`. See the [Windows guide](https://commandcode.ai/docs/windows) for native Windows and WSL. Git is needed if you use the skill’s isolated worktree workflow.
- `/commandplug` and the optional Desktop badge report whether the CLI is on the **Hermes backend’s** `PATH`. This check does not launch Command Code or verify login, Node, or model access. If the CLI works in your terminal but not in Hermes, check the backend service’s `PATH` and restart it after updating the environment. A remote backend or WSL uses its own environment.

Early preview. Tested on Hermes `0.23.4+349.gc004ce2`; requires a build with `tool_request` and `tool_execution` middleware. Enable it separately on any other profile or remote Hermes instance. Independent project, not affiliated with Command Code or Nous Research. [MIT](LICENSE).

### Experimental: choose the coding model

The optional [`model_selection.py`](tool-harness/model_selection.py) helper does not start Command Code. Run it with `resolve --project <trusted-project-path> [--model <exact-id>]`. A task override wins over a trusted project’s `.commandplug.json` (`{"model":"provider/model"}`); without either, leave the CLI default alone. Treat a project-requested model as a proposed choice, not authorization to run it or incur extra cost.

Pass the returned `argv` to a fresh Command Code run as separate arguments and capture `--output-format json` stdout. Run the helper with `verify --events <file> --exit-code <real-code> [--expected-model <exact-id>]` to check the reported model. A mismatch or missing evidence fails verification; there is no automatic fallback. This does not replace reviewing the diff and running acceptance tests.
