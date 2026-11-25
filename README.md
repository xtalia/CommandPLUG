# CommandPLUG

![CommandPLUG mixtape cover: a teal plug raps into a gold mic while a winged robot works the beat pad](assets/commandplug.png)

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin inspired by [Command Code’s harness engineering](https://commandcode.ai/docs/harness-engineering). Fewer busted tool calls, fewer reruns.

## What it does

- Repairs numeric argument formatting in `read_file`, `search_files`, and `terminal`, like `"30"` instead of `30` or an unwanted `null` in a pagination field. It can tell the model what changed. It does not rewrite commands, paths, or file contents.
- Runs in the Hermes backend, not just Desktop. Use `/commandplug` for status and local repair counts. Desktop has an optional status-bar badge.

## What’s next — and why

- **[Taste](https://commandcode.ai/docs/taste):** keep reusable coding preferences so you don’t have to repeat the same corrections.
- **[Design](https://commandcode.ai/docs/design):** bring design, review, and refinement into the coding workflow so UI work gets fewer rounds of rework.
- **[Read](https://commandcode.ai/docs/harness-engineering/read-tool) and [shell](https://commandcode.ai/docs/harness-engineering/shell-tool):** try targeted file reads and better handling of noisy command output. Measure retries, elapsed time, and tokens on the same tasks. Start with open-weight models; test whether GPT and Claude benefit too.

## Install

1. Copy the [`tool-harness`](tool-harness) folder into the active Hermes profile’s `plugins/` directory, then run `hermes plugins enable tool-harness`.
2. **Optional, Desktop:** copy [`tool-harness/desktop/plugin.js`](tool-harness/desktop/plugin.js) to `<Hermes home>/desktop-plugins/tool-harness/plugin.js`. The badge reports the connected profile’s status; it doesn’t enable the backend.

Early preview. Tested on Hermes `0.23.4+349.gc004ce2`; requires a build with `tool_request` middleware. Enable it separately on any other profile or remote Hermes instance. Independent project, not affiliated with Command Code or Nous Research. [MIT](LICENSE).
