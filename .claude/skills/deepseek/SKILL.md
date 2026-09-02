---
name: deepseek
description: Send a prompt or collected context to DeepSeek's API and show its raw response. Use when the user asks to send something to DeepSeek — e.g. "send this to DeepSeek", "ask DeepSeek", "send all that information to DeepSeek and paste the response", or "what does DeepSeek say about X".
---

# Ask DeepSeek

Send content to DeepSeek and relay its answer verbatim. This offloads the actual
reasoning/text generation to DeepSeek (billed to the DeepSeek API key), while you
only run one command and echo the result.

## When to use

Use whenever the user asks to hand text, a question, or gathered context to
DeepSeek and show the response. Examples:
- "send all that information to deepseek and paste the response"
- "ask deepseek how to backtest this"
- "what does deepseek say about <topic>"

If the user says "send all that information", gather the relevant text/context
first, then pass it as a single argument.

## How

Run the helper script (at the repo root, not under this skill directory) with
the content to send as one argument:

    python scripts/ask_deepseek.py "<content>"

Then print the script's stdout **verbatim** — do not summarize, edit, or add
commentary. The output is DeepSeek's answer, followed by a line reporting the
prompt/completion/total token usage for that call.

## Notes

- The helper scripts live at the repo root's `scripts/` directory
  (`scripts/ask_deepseek.py`), not inside this skill folder — run the command
  from the repo root, or with a path relative to it.
- Reads `DEEPSEEK_API_KEY` from the environment, falling back to the `env` block
  of `.claude/settings.local.json` (git-ignored), so no shell setup is required.
- Default model is `deepseek-v4-pro`. Pass `deepseek-v4-flash` as a second
  argument for the cheaper/faster model.
- `scripts/ask-deepseek.ps1` is an equivalent PowerShell version. Prefer the
  Python script: it is portable and avoids PowerShell execution-policy blocks.
