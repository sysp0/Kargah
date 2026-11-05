#!/usr/bin/env bash
# Print the coder prompt for one plan package. Stdout only, so it can be piped.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: scripts/pkg-prompt.sh <stage> <Pn>" >&2
  exit 2
fi

stage="$1"
pkg="$2"
if [[ ! "$stage" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || [[ ! "$pkg" =~ ^[A-Za-z][A-Za-z0-9-]*$ ]]; then
  echo "usage: scripts/pkg-prompt.sh <stage> <Pn>" >&2
  exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
row="^[|][[:space:]]*${pkg}[[:space:]|(]"
if [[ -d "$root/docs/devchain-plan/${stage}" ]]; then
  # Plan folder: the part file (01-*.md, 02-*.md, ...) that holds the package row; 00-overview.md has none.
  plan_rel="$(cd "$root" && grep -lE "$row" "docs/devchain-plan/${stage}"/[0-9][0-9]-*.md 2>/dev/null | grep -v '/00-' | head -1 || true)"
  if [[ -z "$plan_rel" ]]; then
    echo "pkg-prompt: package ${pkg} not found in docs/devchain-plan/${stage}/" >&2
    exit 1
  fi
else
  plan_rel="docs/plan/${stage}.md"
  if [[ ! -f "$root/$plan_rel" ]]; then
    echo "pkg-prompt: no plan folder docs/devchain-plan/${stage}/ and no stage file ${plan_rel}" >&2
    exit 1
  fi
  if ! grep -Eq "^#{1,6}[[:space:]]+${pkg}([^[:alnum:]]|$)|$row" "$root/$plan_rel"; then
    echo "pkg-prompt: package ${pkg} not found in ${plan_rel}" >&2
    exit 1
  fi
fi

cat <<EOF
Read AGENTS.md.
Execute ONLY package ${pkg} in ${plan_rel}.
Read that package only. Do not open other packages or full PM docs.
Touch only the files listed on that package.
Start by writing the failing test, then make the change.
Run the acceptance command from the package (scripts/check.sh <path>).
Update the Pkgs: line in docs/progress.md (${pkg} done, next package next).
Print a summary of at most 10 lines.
Do not commit. Do not push.
EOF
