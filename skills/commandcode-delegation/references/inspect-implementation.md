# Inspecting the installed Command Code bundle

Use when a bundled doc states a capability but not its behaviour, and the answer changes
the work: argument repair rules and their order, read/write limits, truncation, exit-code
handling, tool schemas, which tools a mode withholds, what a config key really merges.
The docs are prose; `dist/cli.mjs` is the enforcement.

## Locate and search, never read through

```bash
CODE=$(npm root -g)/command-code/dist/cli.mjs   # ~3.5 MB, minified, single file
rg -o 'hint:`[^`]{4,120}`' "$CODE" | sort -u    # every user/model-facing message
rg -n 'repairToolInput|tool_input_repaired' "$CODE"
rg -n 'from_offset|shell_output|monitor_command' "$CODE"
```

`rg -c` first to size the job: a literal that appears 3375 times (a bare `null`) tells you
nothing; one that appears once or twice is an anchor.

## Anchoring in minified code

Local names are meaningless (`Lv`, `Mv`, `Pv`), so never search for a function name you
expect — the published prose names do not survive minification. Anchor on:

- a **diagnostic string**: `'Note: offset ... is beyond the end of the file'`,
  `'Use from_offset to stream the rest'`, `'Invalid input for tool "'`;
- a **schema literal**: `name:"shell_output"`, `name:"monitor_command"`;
- an **exported/registry key** that survives because it crosses a boundary:
  `tool_input_repaired`, `model_request_end`, `ringPrintMode`.

Then read a window around the hit (±6–8 KB) with a slice, not the whole file. The catalogue
of rules in the tool-repair layer sits as one tuple of `{name, repair}` entries, each repair
returning a `hint:` string — that is the single most informative window in the bundle.

## Reading the result honestly

- Order inside a tuple is load-bearing and is stated only here. Record it explicitly when
  porting; docs almost never mention ordering.
- Message strings encode the numbers: the ceiling, the resume offset, the clamp. Quote the
  string, not a paraphrase.
- Presence of a `hint:` proves the code can emit that repair; it does not prove the rule is
  reached for a given tool. Confirm with the shipped schema for that tool.
- When the bundle and a doc disagree, follow the bundle for behaviour and say so in the
  report. When they agree, cite the bundle anyway — it is version-matched, the docs are not.

## Do not

- Paste large windows of minified code into a deliverable or a skill.
- Treat a symbol's absence as proof of no capability: minification renames, bundlers split
  chunks, and features can be gated behind mods or later in the file.
- Infer account entitlement or billing from the bundle. That is account state, not code.
