#!/usr/bin/env bash
# Replaced by devchain (guide: docs/devchain/README.md). Kept so the old command still works: it builds the packages on
# the checked-out branch, as before. For new work use ./dev feature <stage> <Pn>... (a fresh codex/<pn> per package).
# The LOOP_* and CODEX_* variables are gone; settings live in devchain.toml. Resume: ./dev resume.
# usage: scripts/codex-loop.sh <stage> <Pn>...
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
exec "$root/dev" feature --branch current "$@"
