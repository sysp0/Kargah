#!/usr/bin/env bash
# Point this clone at scripts/hooks (local git config only).
set -euo pipefail
root=$(git rev-parse --show-toplevel)
git -C "$root" config core.hooksPath scripts/hooks
echo "core.hooksPath=scripts/hooks"
