#!/usr/bin/env bash
# Enforce ApplyPilot security and style conventions that are easy to grep.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0

check_absent() {
  local label="$1"
  local pattern="$2"
  shift 2
  if rg -n --glob '*.py' "$pattern" "$@" >/dev/null 2>&1; then
    echo "::error title=${label}::Found forbidden pattern: ${pattern}"
    rg -n --glob '*.py' "$pattern" "$@" || true
    fail=1
  fi
}

check_absent "No bare HTTPException" 'raise HTTPException' api agents utils workflows
check_absent "No silent except pass" 'except Exception:\s*pass' api agents utils workflows

if rg -n 'onclick=|onchange=' ui --glob '*.html' >/dev/null 2>&1; then
  echo "::error title=No inline handlers::Found onclick= or onchange= in HTML templates"
  rg -n 'onclick=|onchange=' ui --glob '*.html' || true
  fail=1
fi

if rg -n 'style="' ui --glob '*.html' >/dev/null 2>&1; then
  echo "::error title=No inline styles::Found style=\" in HTML templates (CSP blocks inline styles)"
  rg -n 'style="' ui --glob '*.html' || true
  fail=1
fi

if rg -n 'window\.confirm\(' ui/static/js --glob '*.js' >/dev/null 2>&1; then
  echo "::error title=No native dialogs::Use window.showConfirm() instead of window.confirm()"
  rg -n 'window\.confirm\(' ui/static/js --glob '*.js' || true
  fail=1
fi

if rg -n '(?<![\w.])alert\(' ui/static/js --glob '*.js' >/dev/null 2>&1; then
  echo "::error title=No native dialogs::Use notify() / showNotification() instead of alert()"
  rg -n '(?<![\w.])alert\(' ui/static/js --glob '*.js' || true
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

echo "Security grep checks passed."
