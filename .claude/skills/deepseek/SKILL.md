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

Run the helper script with the content to send as one argument:

    powershell -NoProfile -File scripts/ask-deepseek.ps1 "<content>"

Then print the script's stdout **verbatim** — do not summarize, edit, or add
commentary. The output is DeepSeek's answer.

## Notes

- Needs `DEEPSEEK_API_KEY` set (a real env var, or in `.claude/settings.local.json`'s `env` block).
- Default model is `deepseek-v4-pro`. Pass `deepseek-v4-flash` as a second argument to use the fast model.
- If PowerShell blocks the script (execution policy), run once:
  `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.
