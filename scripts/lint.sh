#!/usr/bin/env bash
# Run ruff linting and (optionally) auto-fix safe issues.
#
# Usage:
#   ./scripts/lint              # check only — non-zero exit if errors found
#   ./scripts/lint --fix        # apply safe auto-fixes (ruff --fix)
#   ./scripts/lint --unsafe-fix # apply safe + unsafe auto-fixes

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------
FIX_FLAG=""

for arg in "$@"; do
  case "$arg" in
    --fix)        FIX_FLAG="--fix" ;;
    --unsafe-fix) FIX_FLAG="--fix --unsafe-fixes" ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--fix | --unsafe-fix]" >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Locate ruff — prefer the project venv so the version is pinned
# ---------------------------------------------------------------------------
RUFF=""
if [[ -x "$REPO_ROOT/.venv/bin/ruff" ]]; then
  RUFF="$REPO_ROOT/.venv/bin/ruff"
elif command -v ruff &>/dev/null; then
  RUFF="ruff"
else
  echo "ruff not found. Install it with: pip install ruff" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
echo "==> ruff check $FIX_FLAG ."
# shellcheck disable=SC2086
"$RUFF" check $FIX_FLAG .

echo ""
echo "==> ruff format --check ."
"$RUFF" format --check .

echo ""
echo "All lint checks passed."
