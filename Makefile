.PHONY: start start-d start-local stop-local setup dev test lint clean build-frontend \
        docker-build docker-up docker-up-d docker-down docker-logs docker-reset \
        _create_env _create_env_system _macos_sign_venv _macos_sign_node _ensure_docker

VENV := venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

# =============================================================================
# ONE-COMMAND START — No Docker (macOS via Homebrew)
# =============================================================================
# First run (~3 min): installs PostgreSQL and Redis via Homebrew, creates the
# database and user, runs migrations, then starts the app.
# Subsequent runs (~5 sec): services already installed, just starts everything.
start-local:
	@if [ "$$(uname)" != "Darwin" ]; then \
		echo ""; \
		echo "ERROR: make start-local requires macOS with Homebrew."; \
		echo "On Linux, install PostgreSQL and Redis via your package manager,"; \
		echo "update DATABASE_URL and REDIS_URL in .env, then run: make dev"; \
		echo ""; \
		exit 1; \
	fi
	@echo "Checking prerequisites..."
	@{ \
		if ! command -v brew &>/dev/null; then \
			echo "Installing Homebrew (you may be prompted for your sudo password)..."; \
			NONINTERACTIVE=1 /bin/bash -c "$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; \
			if [ -f /opt/homebrew/bin/brew ]; then \
				eval "$$(/opt/homebrew/bin/brew shellenv)"; \
			elif [ -f /usr/local/bin/brew ]; then \
				eval "$$(/usr/local/bin/brew shellenv)"; \
			fi; \
		fi; \
		if ! command -v python3 &>/dev/null; then \
			echo "Installing Python 3..."; \
			brew install python; \
		fi; \
		if ! command -v node &>/dev/null; then \
			echo "Installing Node.js..."; \
			brew install node; \
		fi; \
	}
	@$(MAKE) setup
	@echo ""
	@echo "Starting PostgreSQL and Redis..."
	@brew list postgresql@17 &>/dev/null || brew install postgresql@17
	@brew list redis &>/dev/null || brew install redis
	@brew services start postgresql@17 2>/dev/null || true
	@brew services start redis 2>/dev/null || true
	@sleep 2
	@echo "Setting up database..."
	@psql postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='applypilot'" 2>/dev/null | grep -q 1 || \
		psql postgres -c "CREATE ROLE applypilot WITH LOGIN PASSWORD 'applypilot';" 2>/dev/null || true
	@psql postgres -tc "SELECT 1 FROM pg_database WHERE datname='applypilot'" 2>/dev/null | grep -q 1 || \
		psql postgres -c "CREATE DATABASE applypilot OWNER applypilot;" 2>/dev/null || true
	@echo "Running migrations..."
	@$(MAKE) migrate
	@echo ""
	@echo "=============================================="
	@echo " ApplyPilot is running at http://localhost:8000"
	@echo " Stop with Ctrl+C, then: make stop-local"
	@echo "=============================================="
	@echo ""
	$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Stop PostgreSQL and Redis Homebrew services.
stop-local:
	@brew services stop postgresql@17 2>/dev/null || true
	@brew services stop redis 2>/dev/null || true
	@echo "PostgreSQL and Redis stopped."

# =============================================================================
# ONE-COMMAND START — Docker (all platforms)
# =============================================================================
# Creates .env with auto-generated secrets on first run, then starts the app.
# Docker handles Python, Node, PostgreSQL and Redis — nothing else to install.
# The app container runs Alembic (docker-entrypoint.sh) before uvicorn — no separate `make migrate`.
# `up --build` keeps the image in sync with the repo after `git pull` (first run is slower; later runs are cached).
start:
	@$(MAKE) _ensure_docker
	@$(MAKE) _create_env_system
	docker compose pull --ignore-buildable
	docker compose up --build

# Same but runs in the background (detached).
start-d:
	@$(MAKE) _ensure_docker
	@$(MAKE) _create_env_system
	docker compose pull --ignore-buildable
	docker compose up --build -d

# Checks that Docker is installed and the daemon is running.
# Does NOT install or start Docker — the user is responsible for that.
_ensure_docker:
	@if ! command -v docker >/dev/null 2>&1; then \
		echo ""; \
		echo "ERROR: Docker is not installed."; \
		echo ""; \
		echo "  → Download Docker Desktop from https://www.docker.com/products/docker-desktop/"; \
		echo "    Once installed and running, re-run: make start"; \
		echo ""; \
		exit 1; \
	fi
	@if ! docker info >/dev/null 2>&1; then \
		echo ""; \
		echo "ERROR: Docker is not running."; \
		echo ""; \
		echo "  → Open Docker Desktop and wait until the menu bar icon shows"; \
		echo "    'Docker Desktop is running', then re-run: make start"; \
		echo ""; \
		exit 1; \
	fi

# Creates .env using system python3 (no venv required).
# Safe to call multiple times — skips if .env already exists.
_create_env_system:
	@if [ ! -f .env ]; then \
		cp .env.local.example .env; \
		python3 -c "\
import base64, os, secrets; \
content = open('.env').read(); \
jwt_val = secrets.token_urlsafe(48); \
enc_val = base64.urlsafe_b64encode(os.urandom(32)).decode(); \
content = content.replace('REPLACE_WITH_STRONG_SECRET_AT_LEAST_32_CHARS', jwt_val); \
content = content.replace('REPLACE_WITH_FERNET_KEY', enc_val); \
open('.env', 'w').write(content); \
"; \
		echo "  .env created with auto-generated secrets."; \
	else \
		echo "  .env already exists — skipping."; \
	fi
# =============================================================================

# Strips macOS quarantine flags AND ad-hoc re-signs all native extensions so
# Gatekeeper and the kernel's library-load policy both accept them.
_macos_sign_venv:
	@if [ "$$(uname)" = "Darwin" ]; then \
		echo "macOS: removing quarantine flags..."; \
		xattr -r -d com.apple.quarantine $(VENV) 2>/dev/null || true; \
		echo "macOS: ad-hoc re-signing native extensions..."; \
		find $(VENV) \( -name "*.so" -o -name "*.dylib" \) \
			-exec codesign --force --sign - {} \; 2>/dev/null || true; \
		echo "macOS: done."; \
	fi

# Strips macOS quarantine from all node_modules binaries (esbuild, etc.)
_macos_sign_node:
	@if [ "$$(uname)" = "Darwin" ] && [ -d "ui/node_modules" ]; then \
		echo "macOS: removing quarantine flags from node_modules..."; \
		xattr -r -d com.apple.quarantine ui/node_modules 2>/dev/null || true; \
		echo "macOS: done."; \
	fi

# Full local dev setup — creates venv, installs deps, fixes macOS signing,
# and creates .env with auto-generated secrets (only JWT_SECRET + ENCRYPTION_KEY).
# After this runs, just add your GEMINI_API_KEY to .env, then: docker compose up
setup:
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	@$(MAKE) _macos_sign_venv
	@if [ -f "ui/package.json" ]; then cd ui && npm install; fi
	@$(MAKE) _macos_sign_node
	@$(MAKE) build-frontend
	@$(MAKE) _create_env
	@echo ""
	@echo "=============================================="
	@echo " Setup complete!"
	@echo "=============================================="
	@echo ""
	@echo " Start the app:"
	@echo "   make start-local         (no Docker, macOS)"
	@echo "   docker compose up        (Docker, all platforms)"
	@echo "   make dev                 (app only, services already running)"
	@echo ""
	@echo " Then open http://localhost:8000"
	@echo " Create your account and go to Settings → AI Setup"
	@echo " to add your Gemini API key."
	@echo ""
	@echo " Get a key at: https://aistudio.google.com/app/apikey"
	@echo "=============================================="

# Auto-creates .env from the local template and injects generated secrets.
# Skipped entirely if .env already exists.
_create_env:
	@if [ ! -f .env ]; then \
		cp .env.local.example .env; \
		$(PYTHON) -c "\
import base64, os, secrets; \
content = open('.env').read(); \
jwt_val = secrets.token_urlsafe(48); \
enc_val = base64.urlsafe_b64encode(os.urandom(32)).decode(); \
content = content.replace('REPLACE_WITH_STRONG_SECRET_AT_LEAST_32_CHARS', jwt_val); \
content = content.replace('REPLACE_WITH_FERNET_KEY', enc_val); \
open('.env', 'w').write(content); \
"; \
		echo "  .env created — JWT_SECRET and ENCRYPTION_KEY auto-generated."; \
	else \
		echo "  .env already exists — skipping (not overwritten)."; \
	fi

# Build the frontend (esbuild minify + content-hash).
build-frontend:
	@$(MAKE) _macos_sign_node
	cd ui && npm run build

# Start the development server.
# Re-strips quarantine and re-signs on every run so new pip installs are covered.
dev:
	@$(MAKE) _macos_sign_venv
	@$(MAKE) _macos_sign_node
	@$(MAKE) build-frontend
	$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run Alembic migrations against the local DB (DATABASE_URL from .env).
# Runs from /tmp to prevent the local alembic/ folder from shadowing the
# installed alembic package (Python namespace package shadowing issue).
migrate:
	@PROJECT=$$(pwd); \
	cd /tmp && $$PROJECT/venv/bin/python -c "\
import sys; sys.path.append('$$PROJECT'); \
from dotenv import load_dotenv; load_dotenv('$$PROJECT/.env'); \
from alembic.config import Config; from alembic import command; \
cfg = Config('$$PROJECT/alembic.ini'); \
cfg.set_main_option('script_location', '$$PROJECT/alembic'); \
command.upgrade(cfg, 'head'); \
print('Migrations applied.');"

# Show current Alembic revision
migrate-status:
	@PROJECT=$$(pwd); \
	cd /tmp && $$PROJECT/venv/bin/python -c "\
import sys; sys.path.append('$$PROJECT'); \
from dotenv import load_dotenv; load_dotenv('$$PROJECT/.env'); \
from alembic.config import Config; from alembic import command; \
cfg = Config('$$PROJECT/alembic.ini'); \
cfg.set_main_option('script_location', '$$PROJECT/alembic'); \
command.current(cfg, verbose=True);"

# Run unit tests
test:
	$(PYTHON) -m pytest tests/ -v

# Run linter
lint:
	$(PYTHON) -m ruff check .

# Remove venv and compiled artefacts
clean:
	rm -rf $(VENV) __pycache__ .pytest_cache .ruff_cache
	find . -name "*.pyc" -delete

# Remove frontend build output (node_modules kept — run npm install to restore)
clean-frontend:
	rm -rf ui/static/dist

# =============================================================================
# DOCKER COMPOSE — self-hosted local deployment
# =============================================================================

# Build the Docker image (re-runs the Node + Python multi-stage build).
docker-build:
	docker compose build

# Start all services (postgres, redis, app) in the foreground.
# First run will build the image automatically.
docker-up:
	docker compose up

# Start all services in the background (detached).
docker-up-d:
	docker compose up -d

# Stop all services (keeps volumes/data intact).
docker-down:
	docker compose down

# Tail the app logs.
docker-logs:
	docker compose logs -f app

# Stop all services AND delete all data volumes (full reset).
docker-reset:
	docker compose down -v

# =============================================================================

# Wipe all user data from the local dev DB (useful before manual testing runs).
# Reads DATABASE_URL from .env and converts asyncpg:// → standard psql:// scheme.
db-reset:
	@DB_URL=$$(grep '^DATABASE_URL=' .env | cut -d= -f2- | sed 's|postgresql+asyncpg://|postgresql://|'); \
	echo "Resetting local DB: $$DB_URL"; \
	psql "$$DB_URL" -c "TRUNCATE TABLE workflow_sessions, job_applications, user_workflow_preferences, user_settings, user_profiles, users CASCADE;" && \
	echo "Done — all user data cleared."
