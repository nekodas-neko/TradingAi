#!/usr/bin/env python3
"""Send a prompt to DeepSeek's API and print the response.

Usage:
    python scripts/ask_deepseek.py "your prompt"
    python scripts/ask_deepseek.py "your prompt" deepseek-v4-flash

Reads DEEPSEEK_API_KEY from the environment, falling back to the `env` block
of .claude/settings.local.json so it works without shell setup.
Optionally set DEEPSEEK_MODEL to change the default model.

Portable: standard library only, no PowerShell execution-policy issues.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-pro"


def find_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    # Fall back to the git-ignored local settings file.
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local = os.path.join(here, ".claude", "settings.local.json")
    try:
        with open(local, encoding="utf-8") as fh:
            return json.load(fh).get("env", {}).get("DEEPSEEK_API_KEY")
    except (OSError, ValueError):
        return None


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit("usage: ask_deepseek.py \"<prompt>\" [model]")

    prompt = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else os.environ.get(
        "DEEPSEEK_MODEL", DEFAULT_MODEL)

    key = find_key()
    if not key:
        sys.exit("DEEPSEEK_API_KEY is not set (env var or "
                 ".claude/settings.local.json)")

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        sys.exit("DeepSeek request failed (HTTP %s): %s"
                 % (exc.code, exc.read().decode("utf-8", "replace")[:500]))
    except urllib.error.URLError as exc:
        sys.exit("DeepSeek request failed: %s" % exc.reason)

    print(body["choices"][0]["message"]["content"])


if __name__ == "__main__":
    main()
