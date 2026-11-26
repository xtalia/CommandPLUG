# Command Code vs Hermes: read tool and shell tool

Side-by-side extracts of the two published comparison tables, restricted to the
**Command Code** and **Hermes** columns, plus a short evidence-based note on what
Hermes actually does today.

Source articles:

- Read tool: https://commandcode.ai/docs/harness-engineering/read-tool
- Shell tool: https://commandcode.ai/docs/harness-engineering/shell-tool

How the tables below were produced: the nearby cells were copied mechanically from
the article markdown, column-for-column, and only the leading status badge was
separated from its detail text. Nothing was re-measured, re-scored, or re-ordered,
and no row was dropped. In the article markup a cell such as `yes2,000` is a
`yes` badge fused with the detail `2,000`; here that becomes `Yes — 2,000`, and
`—no` becomes `No`. `◐partial` becomes `Partial`. A lone em dash means the source
cell was empty.

Status of the Hermes column: it is a **snapshot of the named commit, not a statement
about current Hermes**. The read table was taken on 10 August 2026 at
`hermes-agent 8359e760`; the shell table is also labelled
**historical** below. Where the current source contradicts a historical row, the
correction is given in section 3.

## 1. Read tool

Columns: Feature | Command Code as reported | Hermes as reported.
Hermes snapshot: 10 August 2026, `hermes-agent 8359e760`.

| Feature | Command Code as reported | Hermes as reported |
| --- | --- | --- |
| **Bounded window** |  |  |
| Default line window | Yes — 2,000 | Yes — 2,000 |
| Second ceiling | Yes — 128 KB | Yes — 100K ch |
| Per-line clamp | Yes — 2,000 | Yes — 2,000 |
| **Output contract** |  |  |
| 1-indexed line prefixes | Yes | Yes |
| Resume offset in truncation note | Yes | Yes |
| Empty-file note | Yes | Yes |
| Offset-past-EOF is a note, not an error | Yes | No |
| **Memory + streaming** |  |  |
| Streaming, memory-capped read | Yes | No |
| Deferred chunk-boundary truncation | Yes | No |
| **Session state** |  |  |
| Unchanged-read dedup | Yes — consume | Yes — block |
| Read-before-write ledger | Yes | Yes |
| Ledger tracks _partial_ views | Yes | Yes — cross-agent |
| **Recovering from a miss** |  |  |
| Did-you-mean suggestions | Yes — +levenshtein | Yes — scored |
| Unicode filename retry | Yes — 7 spellings | No |
| Unicode confusables in content | No | No |
| **Beyond text** |  |  |
| Image to vision | Yes | Yes |
| Downscale coordinate mapping | Yes | No |
| Magic-byte sniff, not extension | Yes | No |
| Notebook rendering | Yes | Yes — cells + outputs |
| **Documents** |  |  |
| Word (.docx) as markdown | Yes | Yes — plain text |
| PowerPoint (.pptx) with speaker notes | Yes | Yes |
| Excel (.xlsx) as tables | Yes | Yes — tsv rows |
| OpenDocument (.odt/.ods/.odp) | Yes | Yes |
| RTF and EPUB | Yes | Yes |
| PDF text layer inline | Yes | Yes |
| Scanned PDF names its pages + a recovery | Yes | Partial — partial scans |
| Documents windowed by offset/limit | Yes | Yes |
| Documents in a bulk read | Yes | No |
| Converter fetched on first use, not installed | Yes | Partial — pinned dep |
| **Bulk reads** |  |  |
| Many files in one call | Yes — in read\_file | No |
| Glob patterns in the read | Yes | No |
| Per-file line range in a bulk read | No | No |
| Exclusions + gitignore in the read | Yes | No |
| Aggregate cap across matched files | Yes — ~100 KB | No |
| **Input + safety** |  |  |
| Lenient / aliased tool input | Yes — 10 aliases | Yes |
| Negative offset (read the tail) | Yes — -N lines | No |
| Device path blocklist | Yes | Yes — +/proc |


## 2. Shell tool (historical)

**Historical table.** These rows are what the article recorded at publication, not
verified current behaviour. The article read `hermes-agent dce2ecb` on 30 August 2026.
Any row here whose Hermes value is now unknown should be treated as unknown: it is
not evidence that the capability is present today, and it is equally not evidence
that it is absent. Default assumption for anything not re-checked against current
source: **unknown**.

Columns: Feature | Command Code as reported | Hermes as reported.

| Feature | Command Code as reported | Hermes as reported |
| --- | --- | --- |
| **Execution model** |  |  |
| Native background mode | Yes | Yes |
| Timeout default + cap + settable | Yes — 30s/600s | Yes — 180s/600s |
| Persistent shell session | Partial — pwsh cwd | Yes — emulated |
| First-class PowerShell | Yes | No |
| **Output contract** |  |  |
| Middle-out truncation | Yes | Yes — 40/60 |
| Full log on disk, path in result | Yes | Yes — redacted |
| Omitted counts + recovery note | Yes | Yes |
| 128+N signal honesty | Yes — 137/143 | Yes — +OOM |
| Benign-exit annotation | Yes — grep 1 | Yes |
| Untrusted-output fencing | Yes | No |
| **Background management** |  |  |
| Background output reader | Yes | Yes |
| Wait modes: now / output / exit | Yes — all 3 | Partial |
| Cursor / delta reads | Yes — offset | Partial — pages |
| List running tasks | Yes | Yes |
| Kill by task id | Yes | Yes |
| Kill by pid / port | Yes — both | No |
| SIGTERM → SIGKILL escalation | Yes | Yes — 2s |
| Group-kill safety | Yes | Yes — pid-reuse |
| **Anti-polling** |  |  |
| Monitor / wake-ups | Yes — scheduled | Yes — patterns |
| Sleep tool, wake on input | Yes | No |
| Cron / scheduling | Yes — durable | Yes |
| Bg sub-agents + wait tool | Yes | Partial — no wait |
| **Boundaries** |  |  |
| Safe-command classification | Partial — tokenizer | Partial — regex+llm |
| Workspace boundary on shell | Yes | Partial — chars |

## 3. Evidence-based current Hermes corrections

These are the only places where the current Hermes source is known to diverge from,
or to confirm more precisely, the snapshot above. Line references are to the Hermes
tree; they are cited from the known source, not re-derived here.

| Topic | Article value | Current source evidence | Reading |
| --- | --- | --- | --- |
| Device path guards | read: `Yes — +/proc` | `tools/file_tools.py:638-714` | Confirmed: device-path guards are in the read path. |
| Document extraction | read: docx/pptx/xlsx/odt/rtf/epub `Yes` | `tools/file_tools.py:638-714` | Confirmed: document extraction lives in this block. |
| Document pagination | read: `Yes` (windowed by offset/limit) | `tools/file_tools.py:638-714` | Confirmed: pagination over extracted documents. |
| Unchanged-read dedup | read: `Yes — consume` | `tools/file_tools.py:638-714` | Confirmed: dedup of repeated identical reads. |
| Read budget and continuation | read: `Yes — 100K ch` second ceiling | `tools/file_tools.py:726-769` | Confirmed: budget plus `next_offset` continuation. |
| Truncation redaction | shell: `Yes — redacted` full log | `tools/file_tools.py:726-769` | Confirmed for file reads: redaction is applied. |
| Read ledger, partial views | read: `Yes` / `Yes — cross-agent` | `tools/file_tools.py:726-769` | Confirmed: ledger state maintained alongside the budget. |
| Lenient tool input | read: `Yes` | `agent/inline_tool_executors.py:356-367` | Confirmed: argument coercion happens here. |
| Untrusted-output fencing | shell: `No` | `agent/tool_dispatch_helpers.py:473-475` | Partial reality: fencing is applied to web/MCP content, **not** to terminal output. |
| Path aliasing | read: `Yes` (lenient/aliased input) | plugin code | The plugin currently implements only a selected path alias fix, not the full aliased-input surface. |

Rows outside this table carry the article's date, not today's, and remain unverified.

## 4. What the plugin does and does not implement

Not implemented here:

- **Multi-read** (many files or globs in one `read_file` call). The article's
  `Yes — in read_file` row for Command Code does not describe this plugin, and the
  Hermes column's `No` still holds for the plugin's own read path.
- **Negative offsets** (`offset=-N` tail reads). Not implemented. The CLI 1.93.4
  bundle contains negative-offset strings; that is static evidence that the code path
  exists in the bundle, not a live end-to-end proof that the tool accepts and honours
  a negative offset through this plugin.
- **Terminal fencing** (untrusted-output fence around shell results). Not implemented
  in the plugin. What exists is the web/MCP fence at
  `agent/tool_dispatch_helpers.py:473-475`, which does not cover terminal output.
- **`from_offset` string handling** in shell output reads: strings are present in the
  CLI 1.93.4 bundle, same caveat as above — static evidence only.

### Candidates and priorities

1. **High — multi-read and targeted windows:** reduce round trips, but require a
   composition API preserving each read's scope, policy, session identity, ledger,
   backend and aggregate output cap. Direct filesystem access or dispatch around
   per-tool guardrails is not equivalent.
2. **High — terminal untrusted-output boundaries:** explore a lossless presentation
   boundary preserving structured results, exact output and log recovery. Delimiters
   are advisory, not a security guarantee; handle spoofing and compatibility first.
3. **Medium — negative offset:** needs a backend-native bounded tail read with correct
   line numbers and ledger updates; host-side reads would break remote backends.
4. **Medium — resumable process output:** compare current Hermes pagination and delta
   APIs with the Command Code cursor on actual long-running workloads.
5. **Later or core-level:** Unicode filename retries, image coordinate mapping and
   document conversion involve filesystem or multimodal internals. Kill-by-port and
   workspace confinement require explicit ownership and a core-level safety design.

The plugin's contribution is limited to the selected path alias fix; the remaining
rows are an inventory, not a claim that each capability is missing today.

## 5. What is not measured

- **No real-model comparison.** Token counts, retry behaviour, and latency were not
  measured for any comparative open-weight, GPT, or Claude model. Nothing in this
  document should be read as a per-model cost or speed claim.
- **The benchmark is scripted only.** It exercises the tools through a fixed script;
  it does not drive a live agent session, does not reproduce long-session context
  pressure, and does not measure model-side retries.
- **Static bundle evidence is not a live proof.** The negative-offset,
  untrusted-fence, and `from_offset` strings observed in the CLI 1.93.4 bundle show
  that code exists in the shipped artifact. They do not show that the feature is
  reachable, correct, or enabled through this plugin.
- **The historical column is not current behaviour.** Where a shell-table row could
  not be checked against current source, its current state is unknown, and it is
  recorded as unknown rather than as a pass or a fail.

No precision beyond what the sources state is implied anywhere in this document.
