#!/usr/bin/env bash
# Stop at first failure: repo-rules → optional ruff → pytest (real runner only).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PATH_ARG="${1:-}"
PATH_ARG="${PATH_ARG#"$ROOT"/}"   # devchain passes an absolute path
cd "$ROOT"

echo_lines() { head -n 10; }

# --- 1) repo rules (full engine, or PATH only if under app/engine) ---
RULES_CMD=(python3 "$ROOT/scripts/check_repo_rules.py" --root "$ROOT")
if [[ -n "$PATH_ARG" ]] && { [[ "$PATH_ARG" == *"/engine/"* ]] || [[ "$PATH_ARG" == *"app/engine"* ]]; }; then
  RULES_CMD+=("$PATH_ARG")
fi
set +e
RULES_OUT="$("${RULES_CMD[@]}" 2>&1)"
RULES_RC=$?
set -e
if [[ -n "$RULES_OUT" ]]; then printf '%s\n' "$RULES_OUT" | echo_lines; fi
if [[ $RULES_RC -ne 0 ]]; then
  echo "CHECK fail: repo-rules"
  exit 1
fi

# --- standalone top-level Python package ---
if [[ -n "$PATH_ARG" ]]; then
  TOP="${PATH_ARG%%/*}"
  if [[ -f "$ROOT/$TOP/pyproject.toml" ]]; then
    PYTHON=python3
    if [[ -x "$ROOT/$TOP/.venv/bin/python" ]]; then
      PYTHON="$ROOT/$TOP/.venv/bin/python"
    fi
    if [[ "$TOP" == project-b-pusher ]] && ! "$PYTHON" -c 'import psycopg' 2>/dev/null; then
      echo "psycopg missing for $PYTHON. Once: $PYTHON -m pip install -e '$ROOT/$TOP[test]'"
      echo "CHECK fail: setup"
      exit 1
    fi
    PACKAGE_ARGS=()
    if [[ "$PATH_ARG" == */* ]]; then
      REST="${PATH_ARG#*/}"
      [[ -n "$REST" ]] && PACKAGE_ARGS+=("$REST")
    fi
    OUT="$(mktemp)"
    set +e
    (cd "$ROOT/$TOP" && "$PYTHON" -m pytest -q --maxfail=3 --tb=line -p no:warnings "${PACKAGE_ARGS[@]}") >"$OUT" 2>&1
    RC=$?
    set -e
    if [[ $RC -eq 0 ]]; then
      N="$(grep -oE '[0-9]+ passed' "$OUT" | head -1 | awk '{print $1}')"
      echo "CHECK ok (${N:-0} tests)"
      rm -f "$OUT"
      exit 0
    fi
    {
      grep -E 'FAILED|ERROR|^[A-Za-z].*Error|:[0-9]+:' "$OUT" | head -8
      echo "CHECK fail: pytest"
    } | echo_lines
    rm -f "$OUT"
    exit 1
  fi
fi

# --- package dir (project-a/app or app) ---
PKG=""
for d in project-a/app app; do
  if [[ -f "$ROOT/$d/pyproject.toml" ]]; then PKG="$ROOT/$d"; break; fi
done
if [[ -z "$PKG" ]]; then
  echo "CHECK ok (0 tests) — no pyproject package found"
  exit 0
fi

# --- 2) ruff only if configured ---
if grep -qE '\[tool\.ruff\]|^ruff' "$PKG/pyproject.toml" 2>/dev/null; then
  if command -v ruff >/dev/null 2>&1; then
    RUFF_ARGS=("$PKG")
    [[ -n "$PATH_ARG" ]] && RUFF_ARGS=("$PATH_ARG")
    if ! ruff check "${RUFF_ARGS[@]}" 2>&1 | echo_lines; then
      echo "CHECK fail: ruff"
      exit 1
    fi
  fi
fi

# --- 3) pytest via detected runner; never invent make test ---
PYTEST_FLAGS=(-q --maxfail=3 --tb=line -p no:warnings)
[[ -n "$PATH_ARG" ]] && PYTEST_FLAGS+=("$PATH_ARG")

# project-a tests need Postgres and ClickHouse: run them in docker compose, 2 workers, low priority.
run_docker_pytest() {
  local svc=app rel env=()
  case "$PATH_ARG" in
    project-a/demo_api*) svc=api; rel="${PATH_ARG#project-a/}"; env=(-e ME_DB=project_a_test -e DEMO_PYTEST=1) ;;
    *) rel="${PATH_ARG#project-a}"; rel="${rel#/}"; rel="${rel#app}"; rel="${rel#/}"; rel="${rel:-tests}" ;;
  esac
  cd "$ROOT/project-a"
  [[ -f .env ]] || ./scripts/gen-env.sh >/dev/null
  docker compose up -d --wait postgres clickhouse || return 1
  docker compose run --rm --env-from-file .env -e TEST_WORKERS=2 app python migrate.py --db test || return 1
  docker compose run --rm --env-from-file .env "${env[@]}" "$svc" \
    nice -n 10 python -m pytest -q --maxfail=3 --tb=line -p no:warnings -n 2 --dist loadfile "$rel" || return 1
}

run_pytest() {
  if [[ -z "$PATH_ARG" || "$PATH_ARG" == project-a* ]]; then
    run_docker_pytest
  elif [[ -f "$PKG/uv.lock" ]] && command -v uv >/dev/null 2>&1; then
    (cd "$PKG" && uv run python -m pytest "${PYTEST_FLAGS[@]}")
  elif grep -q 'pytest' "$PKG/pyproject.toml" 2>/dev/null; then
    (cd "$PKG" && python -m pytest "${PYTEST_FLAGS[@]}")
  else
    echo "CHECK ok (0 tests) — pytest not configured"
    return 0
  fi
}

OUT="$(mktemp)"
set +e
run_pytest >"$OUT" 2>&1
RC=$?
set -e
# pass: "N passed" / fail: names + file:line
if [[ $RC -eq 0 ]]; then
  N="$(grep -oE '[0-9]+ passed' "$OUT" | head -1 | awk '{print $1}')"
  N="${N:-0}"
  echo "CHECK ok ($N tests)"
  rm -f "$OUT"
  exit 0
fi
# compact fail (≤10 lines)
{
  L="$(grep -E 'FAILED|ERROR|^[A-Za-z].*Error|:[0-9]+:' "$OUT" | grep -v '^{' | head -8 || true)"   # drop JSON log lines
  [[ -n "$L" ]] || L="$(grep -v '^{' "$OUT" | tail -n 3)"
  printf '%s\n' "$L"
  echo "CHECK fail: pytest"
} | echo_lines
rm -f "$OUT"
exit 1
