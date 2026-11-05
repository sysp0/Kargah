#!/usr/bin/env bash
# Status line: branch · running Codex package · last done/next line under ## Current of docs/progress.md
root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
branch="$(git -C "$root" branch --show-current 2>/dev/null)"
run="$(cat "$root/.claude/codex/current" 2>/dev/null)"
pkgs="$(sed -n '/^## Current/,/^## /p' "$root/docs/progress.md" 2>/dev/null | grep -E ' done| next' | tail -n 1 | cut -c1-70)"
printf '⎇ %s%s · %s' "$branch" "${run:+ · ⚙ $run}" "$pkgs"
