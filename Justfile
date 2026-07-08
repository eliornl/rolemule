# Justfile — cross-platform alternative to Makefile (Options A and C).
# Works on macOS, Linux, and Windows (PowerShell / cmd) without WSL2.
#
# No shebang recipes: Windows `just` otherwise requires `cygpath` (Git for Windows).
#
# Install just:
#   macOS/Linux:  brew install just
#   Windows:      winget install Casey.Just
#
# Option A (Docker):  just start   (migrations run inside the app container before uvicorn)
# Option C (Manual):  just setup && just migrate && just dev
#
# One-time sibling copy for safe Just/Docker tests (macOS/Linux; needs python3):
#   just sandbox-for-testing

# Cross-platform paths into the virtual environment
python_cmd := if os() == "windows" { "python" }              else { "python3" }
python     := if os() == "windows" { "venv\\Scripts\\python" } else { "venv/bin/python" }
pip        := if os() == "windows" { "venv\\Scripts\\pip" }    else { "venv/bin/pip" }

# ---------------------------------------------------------------------------
# Generate .env with random secrets if it doesn't exist.
# Windows: PowerShell only (Docker Option A needs no system Python).
# Unix:    scripts/create_dotenv_if_missing.py
# ---------------------------------------------------------------------------
[unix]
[private]
_create-env:
    {{python_cmd}} scripts/create_dotenv_if_missing.py

[windows]
[private]
_create-env:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/create_dotenv_if_missing.ps1

# Sibling clone at ../applypilot-just-sandbox + SANDBOX_README.md (does not touch this repo's .env or DB).
[unix]
sandbox-for-testing:
    {{python_cmd}} scripts/make_just_test_sandbox.py

[windows]
sandbox-for-testing:
    {{python_cmd}} scripts/make_just_test_sandbox.py

# ---------------------------------------------------------------------------
# Option A — Docker
# ---------------------------------------------------------------------------

# Checks that Docker is installed and the daemon is running.
# Does NOT install or start Docker — the user is responsible for that.
[private]
_ensure-docker:
    docker info

# Generate .env + start all services (foreground)
start: _ensure-docker _create-env
    docker compose pull --ignore-buildable
    docker compose up --build

# Generate .env + start all services (background)
start-d: _ensure-docker _create-env
    docker compose pull --ignore-buildable
    docker compose up --build -d

# Stop all services, keep data
docker-down:
    docker compose down

# Stop all services and wipe all data
docker-reset:
    docker compose down -v

# Tail the app logs
docker-logs:
    docker compose logs -f app

# Build the Docker image
docker-build:
    docker compose build

# ---------------------------------------------------------------------------
# Option C — Manual (you run PostgreSQL and Redis yourself)
# ---------------------------------------------------------------------------

# Full setup: venv + Python/Node deps + frontend build + .env
setup: _create-env _npm-install build-frontend
    {{python_cmd}} -m venv venv
    {{python}} -m pip install --upgrade pip
    {{python}} -m pip install -r requirements.txt
    {{pip}} install -e ".[cli]" -q
    @echo ""
    @echo " Setup complete!"
    @echo " Edit .env with your DATABASE_URL and REDIS_URL, then:"
    @echo "   just migrate   - run database migrations"
    @echo "   just dev       - start the app at http://localhost:8000"
    @echo ""
    @echo " CLI: venv/bin/applypilot doctor  (Windows: venv\\Scripts\\applypilot.exe)"

# Install Node dependencies (runs inside ui/ — avoids && which breaks PowerShell 5.x)
[private]
[working-directory: 'ui']
_npm-install:
    npm install

# Build frontend assets (esbuild minify + content-hash)
[working-directory: 'ui']
build-frontend:
    npm run build

# Run Alembic database migrations against the local DB.
# Uses scripts/run_alembic.py so ./alembic/ does not shadow the installed package (see Makefile).
migrate:
    {{python}} scripts/run_alembic.py upgrade

# Show current Alembic revision
migrate-status:
    {{python}} scripts/run_alembic.py current

# Start the FastAPI dev server with auto-reload (services must already be running)
dev: build-frontend
    {{python}} -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run the test suite
test:
    {{python}} -m pytest tests/ -v

# Run CLI tests only (no live server)
cli-test:
    {{pip}} install -e ".[cli]" -q
    {{python}} -m pytest tests/test_cli/ -v --override-ini="addopts="

# Run the linter
lint:
    {{python}} -m ruff check .
