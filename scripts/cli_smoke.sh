#!/usr/bin/env bash
# Optional live smoke test for the ApplyPilot CLI.
# Requires: server running (make start-local), logged-in user with complete profile.
#
# Usage:
#   ./scripts/cli_smoke.sh
#   BASE_URL=http://localhost:8000 ./scripts/cli_smoke.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v applypilot >/dev/null 2>&1; then
  pip install -e ".[cli]" -q
fi

echo "== applypilot version =="
applypilot version

echo "== applypilot --help =="
applypilot --help >/dev/null

echo "== applypilot doctor =="
applypilot doctor

if applypilot auth whoami >/dev/null 2>&1; then
  echo "== authenticated: profile status =="
  applypilot profile status || true
  echo "== apps list (first page) =="
  applypilot apps list --per-page 3 || true
else
  echo "== skip authenticated checks (run: applypilot auth login) =="
fi

echo "CLI smoke finished OK."
