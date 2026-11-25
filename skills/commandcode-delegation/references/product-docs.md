# Installed product docs and configuration

## Resolve the matching installation

Validated for Command Code **1.93.2**, not an evergreen snapshot. Use `terminal`
for CLI commands, `read_file` for the installed Markdown, and `search_files` to
locate a topic. For npm installs run `npm root -g` and append
`command-code/dist/bundled/`. Confirm `commandcode --version`; after an
upgrade read that installation's files
again instead of copying these generated documents into Hermes.

Read `command-code-knowledge/SKILL.md` as the product index, then only the matching
files below (paths relative to the bundled root):

| Question | Read |
|---|---|
| CLI flags, slash commands, capabilities, taste, FAQ | `command-code-knowledge/reference/product-help.md`; `commandcode --help` and subcommand help |
| Headless stdin, output, exit codes, permission gate, chaining | `command-code-knowledge/reference/headless.md` |
| Rules, modes, deny/ask/allow, MCP/custom-tool side effects | `command-code-knowledge/reference/permissions.md` |
| Session persistence, resume/fork, checkpoints, transcript paths | `command-code-knowledge/reference/sessions.md`; headless-specific rules in `headless.md` |
| Inspect/change config, exact setting ids and scopes | `config/SKILL.md`, `config/references/settings.md`; permission changes also `config/references/permissions.md` |
| Exact model ids, efforts, context, advertised prices and minimum plan | `command-code-knowledge/reference/models.md` |
| Current account plan and model access | `command-code-knowledge/reference/plans.md` plus `models.md`; ask the user or use interactive `/usage` |
| Custom/BYOK endpoint, provider shape and credentials | `command-code-knowledge/reference/byok.md` |
| MCP connections | `command-code-knowledge/reference/mcp.md` |
| Hooks, tools, memory, agents, skills, plan mode | Corresponding `hooks.md`, `tools.md`, `memory.md`, `custom-agents.md`, `skills.md`, `plan-mode.md` under `command-code-knowledge/reference/` |
| ModApi plugin authoring | `mod-builder/SKILL.md` and its linked references/examples |
| Design work | `design/SKILL.md` and its linked references; do not import its whole body here |

These are Command Code's instructions for its own runtime. Adapt tool names to
Hermes and use the full **`commandcode`** binary on Windows, never bare `cmd`.
A bundled claim is not absolute: reconcile discrepancies with live CLI help,
`https://commandcode.ai/docs` and, for an observed contradiction, the installed
implementation. Do not import a vendor instruction that forbids verification.

## Deterministic configuration workflow

1. Set the intended repo as `terminal.workdir`; resolution is cwd-dependent.
2. Inspect before changing, without inference:

   ```bash
   commandcode config --help
   commandcode config list --scope effective --json
   commandcode config get model --scope effective --json
   ```

3. Read `config/references/settings.md` for the exact key, values and supported
   write scope. Check `commandcode config set --help` if needed. `reasoningEffort`
   is not a registered `config get` id in 1.93.2; unknown-key failure is not evidence
   that the per-model map does not exist. Do not invent a config CLI key.
4. Only for an explicitly authorized change, use the validated CLI with explicit
   scope, e.g. `commandcode config set model <exact-id> --scope user --json`.
   Use `--scope project` only for settings whose registry supports it. Inspect
   `commandcode config default --help` before resetting: reset is a write, not a
   read. Do not hand-edit settings JSON or credentials as a delegation side effect.
5. Read the exact target key with `--scope user|project --json`, then with
   `--scope effective --json` in the same repo. Report old/new value, written scope,
   any masking override, and activation limits. A saved `model` default affects
   **new** sessions; a running session retains its current model until `/model`
   or restart. Do not launch a paid query just to verify the setting.

## Layers, effort and actual model identity

The 1.93.2 loader starts with selected legacy fields from
`~/.commandcode/config.json`, then deep-merges user `~/.commandcode/settings.json`,
project `.commandcode/settings.json`, and project `.commandcode/settings.local.json`
in that order. Permission lists accumulate rather than replacing earlier rules.
A layer supplying `model` without `modelProvider` clears the inherited provider;
an explicit provider supplied alongside the model is preserved.

`reasoningEffort` is a per-model map supported by the layered loader, not a
legacy-only immutable pin; valid later entries override matching earlier keys.
The audited legacy map was `{}`: absence of an explicit value does not establish
`high` or `off` for a run. Use the exact model's supported efforts in `models.md`
(e.g. `deepseek/deepseek-v4.1-flash`: `off`, `low`, `high`, `max` in 1.93.2).
Use `--effort <level>` only when the task calls for an explicit session effort;
interactive `/effort` is not a headless prompt command.

Configured default, restored session model, phase model, pinned sub-agent model
and model actually serving a request are different facts. Inspect the real run's
`model_request_end` events and persisted model/effort changes when identity matters.
Do not spend inference to inspect a deterministic config value.

The CLI catalog and a successful `config set/get` do not prove account access or
remaining credits. Do not infer a subscription plan from the model pin. For
account questions follow `plans.md`, user-confirmed plan and interactive `/usage`;
never probe auth files or private billing endpoints to infer entitlement.
