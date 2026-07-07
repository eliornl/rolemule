#!/usr/bin/env bash
# Apply Alembic migrations in CI (and locally).
# Runs from /tmp so the repo's alembic/ folder does not shadow the alembic package.
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
export PROJECT_ROOT="$PROJECT"

if [[ -x "${PROJECT}/venv/bin/python" ]]; then
  PYTHON="${PROJECT}/venv/bin/python"
else
  PYTHON="python"
fi

cd /tmp
"${PYTHON}" -c "
import os
import sys

project = os.environ['PROJECT_ROOT']
sys.path.append(project)

from dotenv import load_dotenv
load_dotenv(os.path.join(project, '.env'))

from alembic.config import Config
from alembic import command

cfg = Config(os.path.join(project, 'alembic.ini'))
cfg.set_main_option('script_location', os.path.join(project, 'alembic'))
command.upgrade(cfg, 'head')
print('Migrations applied.')
"
