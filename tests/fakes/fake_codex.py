#!/usr/bin/env python3
"""Fake `codex exec`: replays the next action from $FAKE_DIR/codex.json, prints a --json stream."""
import json
import os
import sys
import time
from pathlib import Path

state = Path(os.environ["FAKE_DIR"])
actions = json.loads((state / "codex.json").read_text())
count_file = state / "codex.count"
n = int(count_file.read_text()) if count_file.exists() else 0
count_file.write_text(str(n + 1))
prompt = sys.stdin.read()
(state / f"codex-prompt-{n}.txt").write_text(prompt)
(state / f"codex-argv-{n}.txt").write_text(" ".join(sys.argv[1:]))
action = actions[min(n, len(actions) - 1)]
args = sys.argv[1:]
last = args[args.index("--output-last-message") + 1] if "--output-last-message" in args else None
print(json.dumps({"type": "thread.started", "thread_id": "t"}))
if action.get("busy"):
    print(json.dumps({"type": "error", "message": "Selected model is at capacity. Please try a different model."}))
    sys.exit(1)
if action.get("limit"):
    print("ERROR: You've hit your usage limit. Please try again in 1 seconds.")
    sys.exit(1)
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
for path, text in (action.get("write") or {}).items():
    target = Path.cwd() / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    print(json.dumps({"type": "item.completed", "item": {"type": "file_change", "changes": [{"path": path}]}}))
for path in action.get("delete") or []:
    (Path.cwd() / path).unlink()
print(json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "pytest -q"}}))
if action.get("blocked"):
    progress = Path.cwd() / "docs/progress.md"
    progress.write_text(progress.read_text().replace("Blocked: none", f"Blocked: {action['blocked']}"))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 800,
                                                       "output_tokens": 50, "reasoning_output_tokens": 20}}))
if last:
    Path(last).write_text(action.get("reply", "done"))
sys.exit(action.get("rc", 0))
