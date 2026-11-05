#!/usr/bin/env python3
"""Fake `claude -p`: writes the next verdict from $FAKE_DIR/claude.json, prints a stream-json result."""
import json
import os
import re
import sys
from pathlib import Path

state = Path(os.environ["FAKE_DIR"])
actions = json.loads((state / "claude.json").read_text())
count_file = state / "claude.count"
n = int(count_file.read_text()) if count_file.exists() else 0
count_file.write_text(str(n + 1))
prompt = sys.argv[sys.argv.index("-p") + 1]
(state / f"claude-prompt-{n}.txt").write_text(prompt)
(state / f"claude-argv-{n}.txt").write_text(" ".join(sys.argv[1:]).replace(prompt, "<prompt>"))
action = actions[min(n, len(actions) - 1)]
if action.get("limit"):  # the account is at its session limit
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": action["limit"]}]}}))
    print(json.dumps({"type": "result", "is_error": True, "result": action["limit"]}))
    sys.exit(1)
if action.get("exit"):  # the CLI failed before any work, e.g. an expired login
    print(action.get("say", ""))
    sys.exit(action["exit"])
match = re.search(r"(?:Verdict file:|verdict file) (\S+)", prompt)
if match and action.get("verdict") is not None:
    Path(match.group(1)).write_text(action["verdict"])
fix_plan = re.search(r"(docs/plan/qa-fix-\S+?\.md)", prompt)
for path, text in (action.get("append") or {}).items():
    if path == "__FIX_PLAN__":
        if not fix_plan:
            continue
        path = fix_plan.group(1)
    target = Path.cwd() / path
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as fh:
        fh.write(text)
for path, (old, new) in (action.get("replace") or {}).items():
    target = Path.cwd() / path
    target.write_text(target.read_text().replace(old, new))
print(json.dumps({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Read", "input": {"file_path": "docs/plan/x.md"}}]}}))
print(json.dumps({"type": "result", "result": "ok", "total_cost_usd": 0.25, "usage": {
    "input_tokens": 100, "cache_read_input_tokens": 900, "cache_creation_input_tokens": 300, "output_tokens": 40}}))
