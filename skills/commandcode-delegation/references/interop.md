# Command Code interop: A2A, ACP, and wrappers

## Does Command Code speak A2A?

No native A2A command is advertised by the verified **1.93.2** CLI/help and
installed product index. A historical 404 at
`https://api.commandcode.ai/.well-known/agent-card.json` describes that endpoint,
not every product surface; do not use it as proof of permanent A2A absence.

**Native ACP exists:** `commandcode acp` is an ACP agent over stdio (confirmed by
`commandcode acp --help`); `commandcode mcp` manages MCP servers it consumes.
The third-party quote claiming “no ACP” is stale/incorrect for this version.
Use the [installed product docs](product-docs.md) before promising a transport;
verify the caller's protocol as well as Command Code's surface.

## The community A2A mod

[`PremModhaOfficial/cmd-mod-a2a`](https://github.com/PremModhaOfficial/cmd-mod-a2a)
(single file `a2a.ts`, Node built-ins) attempts to turn a session into an A2A v1.0
peer: agent card, JSON-RPC `SendMessage`/`GetTask`/`ListTasks`/`CancelTask`, REST
aliases, SSE subscribe, push-notification configs. These are source claims, not
proof of end-to-end interoperability.

Treat this as a historical reference, not an install or launch recommendation.
Review and pin any third-party code before using it.

### Known breakage on Windows

1. **The fan-out worker path is not Windows-safe.** `handleSendMessage` can answer
   texts under 140 chars without the listed action verbs with `ack: …`, which tests
   no worker. Nontrivial tasks go through `deliverToLoop` (queue/start the live loop,
   or fall back to `fanOut`); not every task necessarily uses a spawned worker.
   `fanOut` shells out to `sh -c "cmd --cwd ... -p ... >/tmp/a2a-worker-<id>.log"`.
   Bare `cmd` reaches the Windows shell, native Windows paths cannot assume `/tmp`,
   and **`--cwd` is not a supported 1.93.2 CLI flag**. It also omits **`--yolo`**,
   so merely fixing the executable/path still leaves built-in writes/shell blocked.
   A reviewed port must spawn the resolved CLI/Node entrypoint with an argv array,
   explicit process `cwd`, real scratch paths, separate stdout/stderr, observed
   process exit, and an authorized permission policy. Never add bypass silently.
2. The agent card advertises `streaming: true` while `SendStreamingMessage` returns
   `UnsupportedOp` in the JSON-RPC body — streaming is only via the SSE
   `GET /tasks/<id>:subscribe` endpoint. Verify the caller uses that exact surface.
3. Mod `onRunEnd` infers completion from response text/question marks and turn count,
   not validated exit/stop reason/artifacts; a reported COMPLETED is not task proof.

Treat the mod as a demo, not a production transport: it is one unreviewed file whose
fan-out path is not validated here.

## Wrapper pattern (preferred)

Do not host the mod. Put Command Code behind an A2A-compatible facade that the
`a2a_agents` config can call, and have it map one A2A `SendMessage` to one CLI run:

- A2A `contextId` → persisted CLI `sessionId`: first turn runs without `--resume`;
  later turns pass `--resume <sessionId>` only if the previous result supplied a
  durable id. Never manufacture one when an early failure omitted it.
- A2A task state ← **process exit + complete final result + subtype + stopReason
  + independent artifact checks**. `subtype: success` alone is insufficient in
  1.93.2; cap-hit/exit 8, nonzero exit, missing result or interruption is failed or
  partial work. Retain recovered files separately from a clean completion claim.
- Call `commandcode -t --skip-onboarding -p --max-turns N --output-format json`
  with prompt on stdin and explicit process `cwd`; add `--yolo` only for authorized
  edits. Parse stdout NDJSON line-by-line, retain its final result, and keep stderr
  separate. Handle missing `sessionId`/`stopReason` on errors; `--no-session` means
  there is no durable transcript to resume.
- Authenticate the facade, constrain cwd/task scope, propagate cancellation to the
  worker and serialize continuations per session; a prompt allowlist is not a
  sandbox. Creating a facade is a separate implementation task, not a shipped service.
- Use native `commandcode acp` when the caller is an ACP client. ACP is stdio;
  a network caller needs an appropriate bridge rather than an HTTP request to it.
