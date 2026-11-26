# CommandPLUG

![CommandPLUG cover: marble Hermes in pink sunglasses presses a yellow toy-laptop key amid Greek columns and blue-to-coral digital rain](assets/commandplug.webp)

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin inspired by [Command Code’s harness engineering](https://commandcode.ai/docs/harness-engineering). Fewer busted tool calls, fewer reruns.

## What it does

- Validates calls against the registered tool schema, repairs allowlisted invalid fields, and validates again before applying a repair. It handles numeric controls in `read_file`, `search_files`, `terminal`, and `web_extract`, as well as JSON-stringified arrays in `web_extract.urls`. It can tell the model what changed. It does not rewrite commands, paths, or file contents; ambiguous or still-invalid calls pass through unchanged.
- Runs in the Hermes backend, not just Desktop. Use `/commandplug` for status and local repair counts. Desktop has an optional status-bar badge.

Validation governs only the plugin's own candidate repairs; it is not an enforcement layer. Hermes may independently coerce the original arguments on another dispatch path, including cases CommandPLUG declined. Repair explanations are best effort: missing call identifiers, blocked calls or result shapes that cannot safely carry metadata can prevent delivery. Counts are observations for covered tools, not prevented errors or confirmed executions.

## What’s next — and why

- **[Taste](https://commandcode.ai/docs/taste):** keep reusable coding preferences so you don’t have to repeat the same corrections.
- **[Design](https://commandcode.ai/docs/design):** bring design, review, and refinement into the coding workflow so UI work gets fewer rounds of rework.
- **[Read](https://commandcode.ai/docs/harness-engineering/read-tool) and [shell](https://commandcode.ai/docs/harness-engineering/shell-tool):** try targeted file reads and better handling of noisy command output. Measure retries, elapsed time, and tokens on the same tasks. Start with open-weight models; test whether GPT and Claude benefit too.

## Install

**Tool-call repair:** requires Hermes Agent with `tool_request` middleware and `jsonschema>=4.18,<5` installed in Hermes's Python environment. No Command Code or npm is needed for repair. If schema validation is unavailable, the plugin fails open and leaves arguments unchanged.

1. Copy the [`tool-harness`](tool-harness) folder into the active Hermes profile’s `plugins/` directory, then run `hermes plugins enable tool-harness`.
2. **Optional, Desktop:** copy [`tool-harness/desktop/plugin.js`](tool-harness/desktop/plugin.js) to `<Hermes home>/desktop-plugins/tool-harness/plugin.js`. The badge reports the connected profile’s status; it doesn’t enable the backend.

## Optional: delegate coding to Command Code

The [`commandcode-delegation` skill](skills/commandcode-delegation/SKILL.md) lets Hermes scope the task and verify the result while Command Code writes the code. To use it, copy the entire [`commandcode-delegation`](skills/commandcode-delegation) folder into the active Hermes profile’s `skills/` directory and start a new session. Install and authenticate the Command Code CLI separately. The skill and plugin can be used independently.

- **macOS / Linux / Windows:** for delegation, install the [Command Code CLI](https://commandcode.ai/docs/quickstart) on the machine where the delegated command runs. For npm installs, use Node.js 22 or later and run `npm install -g command-code`, then `commandcode --version`, `commandcode login`, and `commandcode status`. Use `commandcode` (or `cmdc`) on Windows, not `cmd`. See the [Windows guide](https://commandcode.ai/docs/windows) for native Windows and WSL. Git is needed if you use the skill’s isolated worktree workflow.
- `/commandplug` and the optional Desktop badge report whether the CLI is on the **Hermes backend’s** `PATH`. This check does not launch Command Code or verify login, Node, or model access. If the CLI works in your terminal but not in Hermes, check the backend service’s `PATH` and restart it after updating the environment. A remote backend or WSL uses its own environment.

Early preview. Tested on Hermes `0.23.4+349.gc004ce2`; requires a build with `tool_request` middleware. Enable it separately on any other profile or remote Hermes instance. Independent project, not affiliated with Command Code or Nous Research. [MIT](LICENSE).

### Experimental: choose the coding model

The optional [`model_selection.py`](tool-harness/model_selection.py) helper does not start Command Code. Run it with `resolve --project <trusted-project-path> [--model <exact-id>]`. A task override wins over a trusted project’s `.commandplug.json` (`{"model":"provider/model"}`); without either, leave the CLI default alone. Treat a project-requested model as a proposed choice, not authorization to run it or incur extra cost.

Pass the returned `argv` to a fresh Command Code run as separate arguments and capture `--output-format json` stdout. Run the helper with `verify --events <file> --exit-code <real-code> [--expected-model <exact-id>]` to check the reported model. A mismatch or missing evidence fails verification; there is no automatic fallback. This does not replace reviewing the diff and running acceptance tests.
