#!/usr/bin/env bash
# Optional live smoke test for the RoleMule CLI.
# Requires: server running (make start-local), logged-in user with complete profile.
#
# Usage:
#   ./scripts/cli_smoke.sh
#   BASE_URL=http://localhost:8000 ./scripts/cli_smoke.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v rolemule >/dev/null 2>&1; then
  pip install -e ".[cli]" -q
fi

echo "== rolemule version =="
rolemule version

echo "== rolemule --help =="
rolemule --help >/dev/null

echo "== rolemule doctor =="
rolemule doctor

if rolemule auth whoami >/dev/null 2>&1; then
  echo "== authenticated: profile status =="
  rolemule profile status || true
  echo "== apps list (first page) =="
  rolemule apps list --per-page 3 || true
else
  echo "== skip authenticated checks (run: rolemule auth login) =="
fi

echo "CLI smoke finished OK."
