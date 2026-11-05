#!/usr/bin/env bash
# Run Codex on one plan package and keep its session, so a later call continues the same conversation.
# usage: scripts/codex-pkg.sh <plan> <Pn> [note-file]
#   no saved session: starts Codex with the scripts/pkg-prompt.sh prompt
#   saved session:    resumes it with the note file (check failure or review must-fix)
# Prints Codex's last message. Exit: 0 ok, 1 Codex failed, 2 usage, 3 usage limit.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: scripts/codex-pkg.sh <plan> <Pn> [note-file]" >&2
  exit 2
fi
plan="$1"; pkg="$2"; note="${3:-}"
root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/.claude/codex"
mkdir -p "$dir"
id_file="$dir/$plan-$pkg.id"
log="$dir/$plan-$pkg.jsonl"
flags=(--sandbox workspace-write --json)
resume_flags=(--json -c 'sandbox_mode="workspace-write"')

echo "codex $pkg running" > "$dir/current"
trap 'rm -f "$dir/current"' EXIT

# stdin closed (codex otherwise waits on it); watchdog kills Codex when the log has not grown for 10 minutes.
run_codex() {
  "$@" </dev/null >>"$log" 2>&1 &
  local pid=$! size last=-1 idle=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 10
    size=$(stat -c %s "$log")
    if [[ "$size" == "$last" ]]; then idle=$((idle + 10)); else idle=0; last=$size; fi
    if (( idle >= 600 )); then
      kill "$pid" 2>/dev/null
      echo "codex-pkg: $pkg log idle for 10 minutes; Codex killed" >&2
      wait "$pid" 2>/dev/null
      return 124
    fi
  done
  wait "$pid"
}

cd "$root"
set +e
if [[ -s "$id_file" ]]; then
  if [[ -z "$note" || ! -f "$note" ]]; then
    echo "codex-pkg: $pkg has a session; pass a note file to resume it" >&2
    exit 2
  fi
  run_codex codex exec resume "${resume_flags[@]}" "$(cat "$id_file")" "$(cat "$note")"
else
  prompt="$("$root/scripts/pkg-prompt.sh" "$plan" "$pkg")" || exit 2
  prompt="$prompt"$'\n\n'"Your sandbox has no Docker or database access, so the acceptance command cannot run here. Do NOT stop for that: write the failing test, then implement the change, and leave acceptance to the coordinator, who runs it and sends failures back."
  [[ -n "$note" && -f "$note" ]] && prompt="$prompt"$'\n\n'"$(cat "$note")"
  run_codex codex exec "${flags[@]}" "$prompt"
fi
rc=$?
set -e

python3 - "$log" "$id_file" <<'PY'
import json, sys
log, id_file = sys.argv[1], sys.argv[2]
last = ""
for line in open(log, encoding="utf-8", errors="replace"):
    try:
        ev = json.loads(line)
    except ValueError:
        continue
    if ev.get("type") == "thread.started" and ev.get("thread_id"):
        open(id_file, "w").write(str(ev["thread_id"]))
    item = ev.get("item") or {}
    if ev.get("type") == "item.completed" and item.get("type") == "agent_message":
        last = item.get("text", "")
print(last.strip()[-3000:] or "(no Codex message; see " + log + ")")
PY

if tail -n 20 "$log" | grep -qiE 'usage limit|rate limit|limit reached'; then
  exit 3
fi
[[ $rc -eq 0 ]] || exit 1
