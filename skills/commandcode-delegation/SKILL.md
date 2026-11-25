---
name: commandcode-delegation
description: "Delegate dev tasks to Command Code («командкод») CLI."
version: 1.1.1
author: xtalia, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, CommandCode, Delegation, Headless]
---

# Command Code CLI delegation

Hand development tasks to [Command Code](https://commandcode.ai) via the
`commandcode` binary. It is an autonomous coding agent (read/write/patch,
shell, git). Model access and cost depend on the user's current plan or BYOK;
a catalog entry or stored default is not proof of account entitlement.

## When to Use

Use when the user asks to delegate implementation, refactoring, bug-fixing, or
multi-file code work to Command Code, or when a task is too large to do inline
in the main session. Also use for Command Code configuration, product capabilities,
extensions, or questions about which coding agents are wired up. For product facts,
load the matching installed reference via [product docs routing](references/product-docs.md).

### Command names

Every one of these refers to the Command Code CLI — treat them as `commandcode`:

- **«командкод»**, «комманд код», «команд-код», «команд код», «кмдкод», «cmd код»
- English: `commandcode`, `command code`, `cmd` (when the context is a coding agent)
- NOT to be confused with the `codex` skill (OpenAI Codex CLI) or with Hermes
  `delegate_task` subagents — «командкод» refers to Command Code.

A request like «закинь это в командкод» / «пусть командкод сделает» means: run the
headless invocation below with the task and repo the user named, then verify the diff.

## Prerequisites

```bash
commandcode --version        # installed?
commandcode status           # "Authentication verified" means ready
commandcode --list-models    # current catalog, not an entitlement check
```

If `status` reports expired/invalid authentication, ask the user to re-authenticate
interactively; do not script login or alter credentials. Distinguish network failures
from invalid auth. `COMMAND_CODE_API_KEY`, if supplied, overrides the local login.

On Windows the npm package installs the alias as **`cmdc`**, because `cmd` is the
command shell. In scripts and `terminal` calls always use the full `commandcode`
binary; a bare `cmd` reaches the shell, not the agent.

## Default model and configuration (read before changing)

Respect the user’s chosen executor and model. Use the effective repository default
unless the user specified a model; then use `-m <exact-model-id>` for a fresh run
rather than changing persistent settings. A resumed session can restore a different
model. If the requested model is unavailable, report it before switching.

Use deterministic, non-inference reads through `terminal` with explicit `workdir`:

```bash
commandcode config list --scope effective --json
commandcode config get model --scope effective --json
```

Do not run a paid “say ok” query to inspect config. A config read verifies the
configured default, not the model actually used by a resumed/phase/sub-agent run;
for real delegated work inspect `model_request_end` events and the transcript.
Reasoning effort is model-dependent, **not verified as high**: the audited legacy
`reasoningEffort` map was `{}`, and settings layers can merge/override it.
`reasoningEffort` is not a registered `config get` key in 1.93.2.

Load [product docs routing and config workflow](references/product-docs.md) for
layer precedence, supported keys/scopes, per-model effort and authorized changes.
Do not edit configuration as a side effect of delegation.

## Bundled assets worth raiding (offline, authoritative)

### Optional CommandPLUG model selector

If CommandPLUG is installed, use its `tool-harness/model_selection.py` helper for
an explicitly requested task model or a trusted project pin (`.commandplug.json`
at the project root, containing only `{"model":"provider/model"}`). Call
`resolve --project <project-root> [--model <exact-id>]`. Treat the result as data:
validate the choice with the user’s authorization and pass `argv` as separate
tokens on a fresh run, never as shell text. Do not launch on resolver error or
assume catalog membership proves access. Capture stdout NDJSON and the real exit
code, then call `verify --events <file> --exit-code <code>` with `--expected-model`
when pinned. Report observed models even on mismatch; do not switch silently.
Without the helper, use the standard CLI workflow below.

The install ships its own docs and playbooks — read them instead of guessing, and
mine them for ideas:

For npm installs, resolve `npm root -g` and append
`command-code/dist/bundled/`. Check `commandcode --version` after upgrades.
Do not copy generated product docs into Hermes: read the installed, version-matched
files on demand. The [routing reference](references/product-docs.md) maps topics to paths.

| Path | What's in it |
|------|--------------|
| `command-code-knowledge/SKILL.md` + `reference/*.md` | Product index; headless, permissions, sessions, models/plans, BYOK, hooks, tools, skills and custom agents |
| `config/SKILL.md` + `config/references/settings.md` | Validated settings registry, exact keys, scopes and deterministic CLI workflow |
| `design/SKILL.md` + `design/references/*.md` | A serious design reviewer: severity scale, AI-tell ("smell") catalog, a11y/color/type/motion/responsive discipline, report templates |
| `mod-builder/` | `ModApi` reference + runnable TS examples (`model-router.ts`, `permission-policy.ts`, `custom-tool.ts`, `lifecycle-hooks.ts`) |
| `skill-builder/SKILL.md` | How the agentskills.io standard shapes a SKILL.md (name↔dir match, description carries discovery) |
| `agent-browser/SKILL.md` | Stub that defers to `agent-browser skills get core` so instructions never go stale |

CLI-side extras: `commandcode skills add <repo>` installs skills from GitHub,
`commandcode mods` manages TypeScript mods, `commandcode acp` runs it as an ACP
agent (Zed). Read installed docs/help first; installation is a separate authorized write.

`commandcode skills list` is the discovery command — it prints Project, Global and
Bundled sections; bundled ones live only under that `dist/bundled/` path; user and
project skills are in `~/.commandcode/skills/<name>/` and a repo's `.commandcode/skills/`.
Before porting any of them to Hermes, check the destination library first — several
are already installed there and the copy is wasted context.

### When the docs are thin, read the shipped implementation

The bundled docs describe behaviour; they do not enumerate it. For "what does it actually
do with X" — repair rules, read/write limits, exit-code handling, tool schemas — search the
packaged `command-code/dist/cli.mjs`. Recipe and anchoring technique:
[inspecting the installed bundle](references/inspect-implementation.md).

## Pattern: adversarial read-only review of your own diagnosis

The CLI is a cheap second opinion on *reasoning*, not only a coder. Before
implementing a change whose analysis you did yourself, hand it the same facts and
explicitly ask it to verify your premises and correct you. This routinely catches
misread code paths that would otherwise become the whole implementation plan.

Use **no `--yolo`**, optionally `--permission-mode dont-ask`, to retain the
headless gate on built-in file writes/edits and shell tools. This is not a complete
sandbox: inspect loaded mods, hooks, MCP/custom tools and credentials first; use an
isolated environment with no side-effecting integrations for strict read-only work.
A prompt prohibition is useful task shaping, **not structural enforcement**:

1. Open the prompt with an explicit prohibition — no modifying, creating or deleting
   files, no commits, no builds; output analysis only.
2. List the exact files to read and what role each plays, so it does not wander.
3. State your own understanding as a numbered/observed-behaviour block and ask for it
   to be marked wrong per item. Premises you assert are the ones worth disproving.
4. Ask for the deliverable shape you can act on: verdict per point, the exact
   functions to change by name (not diffs), failure modes to accept, tests to add.
5. Cap output — require short code excerpts, no full diffs.

Treat the report as a hypothesis with evidence, not settled fact: it may be right
about the mechanism while still being your call whether the change is worth making.

## Pattern: staged implementation in one isolated worktree

When the work is a multi-part change — a feature plus a follow-up fix, or a defect
whose second layer only becomes visible once the first lands — chain the runs in one
worktree off the ref you will publish instead of one run per concern:

- Create the worktree from the exact remote ref (`git worktree add -b <branch> <path>
  origin/main`) so a stale local clone can never supply the base.
- Open each later prompt with the current HEAD and an explicit instruction not to
  revert it. If commits are authorized, each run commits its task-owned change on top;
  otherwise leave an inspectable diff. Independent runs in the same tree collide
  on the same files.
- Put the defect in the prompt as a table: scenario, **measured** values, expectation.
  "`scrollTop=0` after reload, expected at bottom" gets fixed; "autoscroll is broken"
  gets the wrong thing rewritten. Include the command or probe that produced the numbers.
- Name the files and functions to change and an explicit do-not-touch list (business
  modules, release metadata, other repos/worktrees). Assign the version bump to exactly
  one run so it is not applied twice.
- Say that tests encoding the replaced behaviour must be rewritten rather than bent to
  stay green, and that a smoke script failing against the new contract must be repaired,
  not deleted, skipped or force-passed.
- Ask for exact command results and, when a commit was authorized, its SHA in the
  report; check the SHA and changed-file ownership yourself. Delegation alone does
  not authorize commit, push or publication.

Verification before publishing:

- Write your own probe of the user's actual request **before** reading the agent's green
  report, and run it against the agent's build. A coding agent authors the tests it is
  graded on, and it may also edit the smoke suite — both can be green while the
  requested behaviour is still broken. Independent measurement with numbers is the only
  check that survives.
- Prefer a probe that measures state after an innocent user action (switch a tab, visit
  another site, reload the document) over one that re-poses the agent's own assertions.
- Dependency installation may rewrite lockfiles; Windows checkouts may expose
  line-ending-only diffs. Inspect each diff and compare with the pre-run baseline.
  Preserve user changes and required dependency updates; restore only specifically
  identified agent-generated noise after review, never blanket `git checkout --`.
  Before committing/publishing, account for every changed file and check
  `git status --short` against the intended final state.

## Pitfall: long or multi-line prompts break inline `-p`

`-p "<task>"` is fine for correctly quoted one-liners. For long/multiline text,
backticks, `$`, or nested quotes, use `write_file` to save UTF-8 under the Hermes
scratch dir (not the repo), then redirect stdin with **no query argument**:

```bash
commandcode -t --skip-onboarding --yolo -p --output-format json \
  < "C:/path/to/hermes-scratch/prompt.txt"
```

Use the current scratch path, not a literal `/tmp` on Windows. This avoids shell
expansion of the prompt and Windows argv length limits. Do not supply both stdin
and an inline query; the inline query takes precedence.

## Isolated headless smoke checks

For a real coding smoke test (not a configuration check), use a fresh scratch
workspace with a small synthetic task and independent tests fixed before dispatch.
On Windows CLI 1.93.3, `--safe-mode --no-skills --no-session` skips installed mods,
skill discovery and transcript persistence, but does not disable user MCP. In a
throwaway workspace, shadow each enabled user server in its `.mcp.json` with
`{"mcpServers":{"<exact-name>":{"command":"unused","enabled":false}}}` (one
entry per server). Run `commandcode mcp list` in that exact workspace and abort
if any server is still enabled or expected entries are missing; local overrides can
win over project overrides. Inspect hooks separately. Keep global settings and
credentials untouched, use stdin + NDJSON and verify the declared file, model and
exit independently. A scratch workspace and these flags are not an OS sandbox.

## Working headless invocation (the one that actually writes files)

```bash
terminal(
  command='commandcode -t --skip-onboarding --yolo -p "<task>"',
  workdir='C:/path/to/repo', timeout=600)
```

Flag rationale:
- `-p` / `--print` — non-interactive: runs, prints the answer, exits. **Does not
  need `pty=true`**. Treat other agents' interactive and exec modes separately;
  do not infer a universal Codex PTY requirement from this comparison.
- `-t` / `--trust` — skips the initial "trust this project?" prompt (otherwise
  headless runs stall).
- `--skip-onboarding` — skips taste onboarding on fresh workspaces.
- `--yolo` — lifts the print-mode built-in write/edit/shell gate and requests
  permission bypass. Use **only for authorized mutating work** in a trusted/isolated
  workspace; deny/ask rules and bypass-disable safeguards still apply.
- `--max-turns N` — deliberately bounded probe only. Omitted in normal work, where
the CLI's own default applies; hitting the default cap exits 8 with partial work
(saved files remain usable, see Rules 3).

## Pitfall: text is buffered; JSON events stream

Default `--output-format text` prints the final answer at exit, so an empty stdout
log during a run does not prove a hang. `--output-format json` streams NDJSON events
as work progresses; `--verbose` adds progress to **stderr**. Keep stdout and stderr
separate for parsing. Check process state, `git status` and intended artifacts via
`search_files` when progress is unclear; do not infer completion from log size.

## Pattern: two parallel passes, disjoint file allowlists

For "read the whole repo and write N documents", split the documents into two
prompts and state an explicit **allowlist of files each run may create**, plus an
explicit ban on everything else (code, tests, deploy, the other run's files).
For new-document-only work, both may run with `background=true` in the same
workdir if their targets and side effects are genuinely disjoint. A prompt allowlist
is not an enforced file boundary under `--yolo`; use separate worktrees whenever
build/install/commit or overlapping file changes are possible.
Then reconcile centrally: a link checker (every `path:line` ref must resolve and
stay within the file's length, every relative `.md` link must exist) catches the
usual off-by-a-few-lines drift, and the two runs' indexes will each claim the
other's files are missing — fix the index yourself.

## Pitfall: big repos need background runs

A read-only repo audit on a ~1 GB working tree does not finish inside the 600 s
foreground cap — the first `-p` run just timed out with exit 124. For audits or
anything touching many files, launch with `background=true, notify=true` and poll
with `process_manage` using its current schema; a bounded log window can cut a JSON
record. Persist full stdout NDJSON separately, parse complete records and verify the
process exit code instead of trusting a truncated tail.

## Pitfall: a capped run re-audits instead of continuing

When a run ends on the turn cap, its worktree is a valid continuation point, not a fresh task. The next prompt must state in its first lines that the work is under way, list exactly what already exists (files created, tests red/green, what is installed) and forbid re-deriving it — otherwise the agent spends the new budget re-reading the repo and re-planning, and lands at the same wall with nothing new written. Give the remaining delta as numbered items and say which files it may touch. Run the existing red test yourself before dispatching, so the prompt carries observed failure text instead of a description.

Because `--max-turns` cannot be changed on a running process, treat a cap-hit as pause-and-continue: keep its diff, never launch a second writer into that worktree while it runs, and resume without the override so the CLI's own default applies.

## Pitfall: provider/tool-schema compatibility is version-specific

A prior run hit `400 ... tools.function.parameters is not a valid moonshot flavored
json schema ... schema exceeds maximum allowed size`; switching that run to
`deepseek/deepseek-v4-pro` worked. This is a historical failure, **not a ban on a
model family**. Record exact CLI/model/provider/toolset/error and usage from the
failed run, consult current docs/catalog, and choose an authorized alternative or
reduce the incompatible toolset. Do not retry blindly or promise zero billing.

## Pitfall: modes do not lift the headless write gate

In **1.93.2 `-p`**, only explicit `--yolo` (alias
`--dangerously-skip-permissions`) lifts the built-in write/edit/shell gate.
**Neither `--accept-edits` nor `--permission-mode yolo` is sufficient**;
`dont-ask` is a fail-closed allowlist mode, not auto-approval. Permission rules still
apply after the print gate; do not conflate interactive mode semantics with `-p`.

No-yolo is not a complete sandbox for hooks/mods/custom/MCP side effects. For edits,
use authorized bypass only with explicit `workdir`, a recorded `git status`/diff
baseline, narrow scope, isolation where needed, and independent artifact/diff review.
Do not enable `--tools-all` or add integrations just to evade a blocked tool.

## Machine-readable output

```bash
commandcode -t --skip-onboarding --yolo -p "<task>" \
  --output-format json
```

NDJSON `event` frames stream before the final `type: "result"` frame. Parse stdout
line-by-line, ignore unknown event types, and retain the final result rather than
dumping the large `run_end` state into context. Never merge stderr with NDJSON.

Completion requires **all** of: process exit code 0, a complete final result,
`subtype == "success"`, an appropriate `stopReason` (normally `end_turn`), and
independently verified requested artifacts/tests. In 1.93.2 `runPrintMode` can emit
`subtype: "success"` even when `classifyPrintOutcome` returns a nonzero exit
(refusal/empty response); subtype alone is not success. Missing/truncated result,
nonzero exit, cap-hit (`8` / `max_turns`), or interruption means failure/partial work,
even if saved files can be recovered.

`usage`, `durationMs`, `finalText` are result fields; `sessionId` and `stopReason`
are **optional**, notably on early errors. Handle `subtype: "error"` and its `error`
field without indexing missing keys. Resume only if a persisted session id exists.

## Task-shaping flags

| Flag | Use |
|------|-----|
| `-m, --model <name>` | override the default for this run only when needed; use an exact current id from `reference/models.md` |
| `--effort <level>` | session reasoning effort; accepted levels depend on the exact model, not universally low/medium/high |
| `--plan` | start in plan mode: propose before editing |
| `--permission-mode <m>` | default, plan, accept-edits, yolo, dont-ask |
| `-w, --worktree [name]` | run in an isolated managed git worktree |
| `--add-dir <dir>` | extra workspace context (monorepos, shared libs) |
| `--skill <path>` / `--mod <path>` | load extra skills or a mod for the session |
| `--mod-option <name=value>` | set a mod-declared flag (mod must expose it via `cmd.addFlag`; this is an API identifier, not the Windows shell) |
| `--config key=value` | headless CLI form of `/config` |
| `--cloud [msg]` | beta cloud session (`commandcode cloud list/status/stop`) |

## Sessions

Both interactive and `-p` runs persist transcripts by default under
`~/.commandcode/projects/<project-slug>/`. Headless runs are hidden from the
interactive picker/interactive `--continue`, but exact ids remain resumable.

```bash
commandcode -p --resume <sessionId> "<follow-up>"
commandcode -p --continue "<follow-up>"
commandcode -c                      # interactive: last interactive session here
commandcode -r <id|name>            # interactive: id or display name
commandcode --session <path|id>     # transcript .jsonl or unique id prefix
commandcode --no-session -p "..."   # no transcript persistence
```

In `-p`, `--continue` selects the latest **headless** session in this cwd (or starts
fresh); explicit `--resume <sessionId>` is safer for parallel/staged jobs. A bare
`--resume` errors headlessly. Add `-t --skip-onboarding` for automation and explicit
`--yolo` only when that follow-up is authorized to mutate. Resume may restore the
session model; do not assume the current default pin controls it. `--no-session`
disables transcript history, not every possible config/cache/artifact side effect.

Interactive mode (`commandcode` with no `-p`) needs `pty=true` +
`process_manage(action='submit', ...)` on Windows; do not send a bare LF.

## Parallel work

One process per git worktree, each in the background:

```bash
terminal(command='commandcode -t --skip-onboarding --yolo -p "<task>"',
         workdir='C:/repo/.wt/feature-a', background=True, notify=True)
```

Mirrors the Codex worktree pattern in the `codex` skill.

## Interop with other agents (CLI / ACP / MCP / A2A)

The CLI is not an HTTP service, so "can it talk to agent X?" is answered by which
surface exists, not by configuration. Establish the surface before promising a
transport:

- **Headless CLI — one integration surface.** `-p --output-format json` streams
  events and ends with a result; validate process exit, result, stop reason and
  artifacts together. If persisted `sessionId` is available, `-p --resume <sessionId>`
  continues that conversation. A thin wrapper can expose this to other agents.
- **ACP** — `commandcode acp` runs the agent over **stdio** (Zed and other ACP
  clients). Native, but not routable over HTTP.
- **MCP** — `commandcode mcp` configures MCP servers it *consumes*; it does not serve one.

Verify protocol claims against `commandcode --help`, `commandcode acp --help` and
installed references first; consult source/current official docs if they conflict.
For an explicitly named A2A endpoint, inspect its agent card and actual protocol
response. A 404 at one hosted URL does **not** prove the product has no A2A surface.

See `references/interop.md` for the community A2A mod, its Windows breakage, and the
wrapper recipe.

## Rules

1. `-p` mode is safe to call directly from `terminal` — no PTY needed, but use
   `background=true` for long audits (foreground cap is 600 s).
2. Read-only analysis: omit `--yolo` and assess integrations/isolation. Authorized
   headless edits: explicit `--yolo`, then review the diff; other modes do not lift
   the built-in gate. Prompts are not permission boundaries.
3. Use Command Code's own headless turn limit for normal work (omit `--max-turns`; verify the installed default with `commandcode --help`). Do not translate Hermes's `agent.max_turns` into a Command Code cap or impose a smaller budget. Commands elsewhere in this guide that pass a cap illustrate explicitly bounded probes only. For a running process the CLI arguments cannot be changed; if it stops at the old cap, keep its diff and continue without the override, never start a second writer in that worktree while it is active.
4. Give an explicit `workdir`; never let it default to the home directory.
5. Verify the artifact yourself (inspect the directory with `search_files`, run the
   test) — the CLI's summary is a self-report. When the task was "make behaviour X
   happen", re-measure X with a probe you wrote yourself; the agent's own passing
   suite is not evidence about behaviour it chose how to test.
6. «Командкод» = Command Code, not Codex. When the wording is ambiguous, ask
   which agent — don't silently pick one.
7. Follow the user’s chosen model. Never infer plan or entitlement from the pin.
   For an authorized persistent change, use `commandcode config set` with the
   documented explicit scope and read it back; do not hand-edit JSON or run a
   paid probe just to inspect config.
