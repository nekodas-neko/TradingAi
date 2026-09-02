---
name: deepseek-relay
description: Run the session as a thin relay to DeepSeek — forward every user message verbatim to DeepSeek and show its raw response, without composing your own answers. Use when the user asks to "run the session in DeepSeek", "switch to DeepSeek relay", or "relay everything to DeepSeek".
---

# DeepSeek Relay Mode

Act as a thin relay between the user and DeepSeek. From now on — until the user
exits — do NOT compose your own answer. For every message the user sends:

1. Forward the user's message verbatim as the prompt:

       python scripts/ask_deepseek.py "<user's message>"

2. Print the script's output **verbatim** — no summary, no edits, no commentary.

This keeps your own work to one command execution plus an echo, so Claude token
usage stays minimal; the actual responses come from DeepSeek.

## Exit

Leave relay mode when the user says "exit", "stop", "end relay", or similar.
