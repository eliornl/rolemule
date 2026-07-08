# Contributing to ApplyPilot

First off — thank you for taking the time to contribute! 🚀

ApplyPilot is a personal open-source project. All contributions are welcome: bug reports, feature ideas, documentation improvements, and code. Please read the relevant section before opening an issue or PR — it makes things faster for everyone.

> Not ready to contribute code yet? You can still help by **starring the repo**, sharing it with others, or opening an issue with feedback.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to Contribute](#ways-to-contribute)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Security Vulnerabilities](#security-vulnerabilities)
- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Adding New Features](#adding-new-features)
- [Pull Request Process](#pull-request-process)
- [Commit Messages](#commit-messages)
- [Questions](#questions)
- [For maintainers](#for-maintainers)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it. Report violations to the repository maintainer via their [GitHub profile](https://github.com/eliornl).

---

## Ways to Contribute

You don't have to write code to contribute:

| Type | How |
|------|-----|
| 🐛 **Bug report** | Open a GitHub issue with reproduction steps |
| 💡 **Feature idea** | Open a GitHub issue describing the use case |
| 📝 **Documentation** | Fix typos, clarify instructions, improve examples |
| 🔧 **Code** | Fix a bug or implement a feature (open an issue first for large changes) |
| ⭐ **Star** | Helps others discover the project |

---

## Reporting Bugs

Use the **Bug Report** issue template when opening a new issue — it asks for reproduction steps, runtime, and environment details.

Before filing a bug report:
- Check you're on the latest version
- Search [existing issues](../../issues) — it may already be reported
- Make sure it's not a configuration problem (check [`.env.local.example`](.env.local.example) and the [README](README.md))

**To file a good bug report, include:**

1. **What you expected to happen**
2. **What actually happened** — include the full error message or stack trace
3. **Steps to reproduce** — the minimal sequence that triggers the bug
4. **Environment:**
   - OS (macOS 14, Windows 11, Ubuntu 22.04…)
   - How you're running the app (Docker / local dev)
   - Python version (if running locally): `python --version`
   - Browser (if it's a UI issue)

> **For Docker users:** attach the app log output: `make docker-logs` or `docker compose logs app`

---

## Suggesting Features

Open a GitHub issue and describe:

1. **The problem you're trying to solve** — what are you unable to do today?
2. **Your proposed solution** — how would it work?
3. **Alternatives you considered** — other ways to solve the problem

Before suggesting, check if the feature might conflict with the self-hosted / privacy-first design of the app (e.g. features that require external services or cloud infrastructure are out of scope for the default build).

---

## Security Vulnerabilities

**Do not open a public GitHub issue for security vulnerabilities.**

See [SECURITY.md](SECURITY.md) for supported versions, scope, private reporting channels, and response expectations.

---

## Development Setup

### Prerequisites

| | Option A — Docker | Option B — macOS no-Docker | Option C — Manual |
|--|-------------------|----------------------------|-------------------|
| **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** | Required | Not needed | Not needed |
| **[Homebrew](https://brew.sh)** | Not needed | Required (macOS only) | Not needed |
| **Python 3.13+** | Pre-installed on macOS/Linux | Required | Required |
| **Node.js 22+** | For running tests locally | Required (auto-installed) | Required |
| **PostgreSQL 17 + Redis 7.4** | Docker provides them | Auto-installed by Homebrew | You provide them |

---

### Option A — Docker (all platforms)

`make start` (macOS/Linux) or `just start` (Windows) creates `.env` with auto-generated secrets on first run, then starts all services.

**macOS / Linux:**
```bash
git clone https://github.com/eliornl/applypilot.git
cd applypilot
make start
```

**Windows** — install [`just`](https://just.systems) (`winget install Casey.Just`), then:
```powershell
git clone https://github.com/eliornl/applypilot.git
cd applypilot
just start
```

The app is ready at **http://localhost:8000** when you see:
```
INFO:     Application startup complete.
```

```bash
make start-d  / just start-d      # run in background
make docker-logs / just docker-logs  # tail app logs
make docker-down / just docker-down  # stop (data preserved)
make docker-reset / just docker-reset  # stop + wipe all data
```

---

### Option B — macOS no-Docker (Homebrew)

One command installs PostgreSQL and Redis via Homebrew, creates the database, and starts the app:

```bash
git clone https://github.com/eliornl/applypilot.git
cd applypilot
make start-local
```

```bash
make start-local    # start everything
make stop-local     # stop PostgreSQL and Redis when done
make dev            # restart just the app (services already running)
```

---

### Option C — Manual (you provide PostgreSQL and Redis)

Use this if you already have PostgreSQL and Redis running. **Windows users:** use `just` instead of `make` (`winget install Casey.Just`).

```bash
git clone https://github.com/eliornl/applypilot.git
cd applypilot
make setup       # or: just setup   (Windows) — includes applypilot CLI in venv
```

Edit `.env` — update `DATABASE_URL` and `REDIS_URL` to point at your local instances. `JWT_SECRET` and `ENCRYPTION_KEY` are already filled in by `make setup`.

```bash
make migrate     # or: just migrate   — run database migrations
make dev         # or: just dev       — start at http://localhost:8000
```

> **macOS:** Always use `make setup` / `make dev` rather than bare `pip install`. They strip the `com.apple.quarantine` flag from venv `.so` files and esbuild binaries so Gatekeeper doesn't block them.

---

## Running Tests

### Unit & Integration Tests

```bash
# Run all CI-safe tests (no live server required)
pytest tests/test_api/ tests/test_agents/ -v

# With coverage report
pytest tests/test_api/ tests/test_agents/ --cov=. --cov-report=html

# Single module
pytest tests/test_api/test_auth.py -v
```

> **Note:** `tests/test_api/` contains integration tests (no live server needed — uses an in-process ASGI client). The root-level `tests/test_*.py` files are **live-server tests** that require a running instance at `localhost:8000` — do not run these in CI.

### E2E Browser Tests (Playwright)

Most E2E tests are mocked (Tier 1) and run without a live server.

```bash
cd e2e
npm install
npx playwright install chromium   # first time only

npm run test:ci       # full Tier 1 suite (no server needed)
npm run test:smoke    # critical path only (~3 min)
npm run test:headed   # visible browser
npm run test:ui       # interactive step-through UI
```

See [`e2e/README.md`](e2e/README.md) for the full command reference and test tier explanations.

### Frontend Build

After changing any JS or CSS:

```bash
make build-frontend   # macOS / Linux
just build-frontend   # Windows
```

This runs esbuild, content-hashes all assets, and updates `manifest.json`. The dev server re-reads the manifest on every request in `DEBUG=true` mode — a hard browser refresh is all that's needed.

---

## Code Style

### Python

- Follow **PEP 8**
- **Type hints** on all function parameters and return values
- **`async/await`** consistently for all I/O
- Imports grouped: stdlib → third-party → local (blank line between groups)

#### API endpoint pattern

Never raise bare `HTTPException` — always use `APIError` or the factory helpers from `utils/error_responses.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from utils.auth import get_current_user
from utils.database import get_database
from utils.error_responses import not_found_error, rate_limit_error

router = APIRouter()

@router.post("/items/{item_id}")
async def get_item(
    item_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_database),
):
    item = await db.get(MyModel, item_id)
    if not item:
        raise not_found_error("Item")
    return item
```

**Error code namespaces:** `AUTH_1xxx` · `VAL_2xxx` · `RES_3xxx` · `RATE_4xxx` · `EXT_5xxx` · `CFG_6xxx` · `INT_9xxx`

#### JSONB mutations — always call `flag_modified()`

SQLAlchemy does not auto-detect in-place mutations to JSONB columns:

```python
from sqlalchemy.orm.attributes import flag_modified

user.preferences["theme"] = "dark"
flag_modified(user, "preferences")   # required — silently lost without this
await db.commit()
```

#### Background tasks — use `get_session()`, not `get_database()`

`get_database()` is request-scoped. Background tasks run outside the request lifecycle:

```python
from utils.database import get_session

async def _background_task(user_id: str) -> None:
    async with get_session() as db:
        # ... query and mutate ...
        await db.commit()
```

#### Logging — always include `exc_info=True` inside except blocks

```python
from utils.logging_config import get_structured_logger, sanitize_log_value, mask_email
from utils.error_responses import internal_error

logger = get_structured_logger(__name__)

try:
    ...
except Exception as exc:
    logger.error("Operation failed: %s", sanitize_log_value(str(exc)), exc_info=True)
    raise internal_error()
```

**Log injection:** use `%s` placeholders + `sanitize_log_value()` for dynamic values — not f-strings. Use `mask_email()` for emails. Do not wrap `%d`/`%f` numeric args with `sanitize_log_value()`. See [`.cursor/rules/codeql-security-scanning.mdc`](.cursor/rules/codeql-security-scanning.mdc).

#### Pydantic v2 validators

Use `@field_validator` with module-level functions — not `@validator("field") def validate(cls, v)`.

---

### JavaScript / Frontend

The frontend is **vanilla JavaScript with JSDoc** type-checked by TypeScript in strict mode (`jsconfig.json`). All files in `ui/static/js/` must compile with `checkJs: true`, `noImplicitAny: true`, and `strictNullChecks: true` — zero errors.

#### Required helpers in every page-level file

```javascript
/** @param {string} str @returns {string} */
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    // Decode &amp; FIRST (bleach double-encodes &), then other named entities, then re-encode.
    return String(str)
        .replace(/&amp;/g, '&')
        .replace(/&#x27;/g, "'").replace(/&#039;/g, "'")
        .replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

/** @returns {string|null} */
function getAuthToken() {
    // @ts-ignore
    return (window.app && typeof window.app.getAuthToken === 'function')
        ? window.app.getAuthToken()
        : (localStorage.getItem('access_token') || localStorage.getItem('authToken'));
}

/** @param {string} msg @param {'success'|'error'|'warning'|'info'} [type] */
function notify(msg, type = 'info') {
    // @ts-ignore
    if (window.app && window.app.showNotification) { window.app.showNotification(msg, type); return; }
    const c = document.getElementById('alertContainer');
    if (!c) return;
    const d = document.createElement('div');
    d.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
    d.innerHTML = `${escapeHtml(msg)}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    c.appendChild(d); setTimeout(() => d.remove(), 5000);
}
```

#### Key rules at a glance

| Rule | ✅ Correct | ❌ Wrong |
|------|-----------|---------|
| API calls | raw `fetch()` with `Authorization: Bearer ${token}` header | `window.app.apiCall()` (only exists on landing page) |
| FastAPI errors | `errData.message \|\| errData.detail` | `errData.message` only |
| Error casting | `const err = /** @type {Error} */ (error)` | `error.message` directly |
| Confirmations | `await window.showConfirm({...})` | `confirm('Are you sure?')` |
| Event handlers | `data-action` + event delegation | `onclick=` attributes |
| Style toggling | `.is-hidden` CSS class | `style="display:none"` attribute |
| Inline styles | Never — CSP blocks them | `<div style="...">` |
| New tab links | `rel="noopener noreferrer"` | missing `rel` |
| User messages | `notify(msg, 'error')` | `alert(msg)` |

#### Adding a new JS file

1. Annotate all functions with JSDoc `@param` / `@returns`
2. Null-check all `getElementById` / `querySelector` results before use
3. Cast `error` in catch blocks: `const err = /** @type {Error} */ (error)`
4. Use `// @ts-ignore` for `window.*` assignments and third-party globals
5. Register a `beforeunload` cleanup for any `setInterval` / `setTimeout`
6. Register the file in `ui/build.mjs`
7. Load it in the template with `{{ asset_url('js/filename.js') }}`

---

## Adding New Features

### New API endpoint

1. Add Pydantic request/response models in the relevant `api/` file
2. Write the route handler following the endpoint pattern above
3. **Existing router file** (e.g. `api/auth.py`): the route is picked up automatically
4. **New router file**: add `app.include_router(router, prefix="/api/v1/...", tags=["..."])` to `main.py`
5. Add tests in `tests/test_api/`

### New agent

1. Create the agent class in `agents/`
2. Implement an async `process()` or `generate()` method
3. **Workflow agent**: add it to `workflows/job_application_workflow.py`
4. **Standalone agent**: create an API endpoint in `api/`

> The workflow runs exactly **5 agents** in sequence (Job Analyzer → Profile Matcher → Company Research → Resume Advisor + Cover Letter Writer in parallel). Do not add new agents to the LangGraph graph without understanding the gate logic.

### New career tool

1. Create the agent in `agents/` following the existing 6-tool pattern (see `agents/salary_coach.py` as reference)
2. Add request/response models and endpoint in `api/tools.py`
3. Add the tab and form to `ui/dashboard/tools.html`
4. Add tests in `tests/test_agents/` and `tests/test_api/`

### New database column

1. Add the field to the model in `models/database.py`
2. Create a migration: `alembic revision --autogenerate -m "add <field> to <table>"`
3. Test locally: `alembic upgrade head`
4. Never edit an existing migration that has already been applied

---

## Pull Request Process

1. **Open an issue first** for anything beyond a small bug fix — discuss the approach before writing code
2. Fork the repo and create a branch: `feature/my-feature` or `fix/my-fix`
3. Make your changes and ensure all checks pass
4. Open a PR against `main` — GitHub pre-fills the [pull request template](.github/pull_request_template.md); complete every section
5. A maintainer will review; expect feedback within a few days

---

## Commit Messages

Use the imperative mood, present tense. Keep the subject line under 72 characters.

```
Add salary negotiation coach agent

- Add SalaryCoachAgent with market analysis and negotiation script
- Add POST /api/v1/tools/salary-coach endpoint
- Add salary coach tab to tools.html
- Add unit tests in tests/test_agents/test_salary_coach.py

Closes #42
```

**Prefixes:**
- `Add` — new feature or file
- `Fix` — bug fix
- `Update` — change to existing feature
- `Remove` — deletion of code or file
- `Refactor` — internal restructuring, no behavior change
- `Docs` — documentation only

---

## Questions

Open an issue — questions are welcome. Include your OS, how you're running the app, and what you've already tried.

---

## For maintainers

Issue and PR templates live under [`.github/`](.github/). Templates reference these labels — create them under **Issues → Labels** if they do not exist yet:

| Label | Used by |
|-------|---------|
| `bug` | Bug Report template |
| `enhancement` | Feature Request template |
| `dependencies` | Dependabot pull requests |

### Continuous integration (GitHub Actions)

Workflows under [`.github/workflows/`](.github/workflows/):

| Workflow | What it checks |
|----------|----------------|
| `ci.yml` | **Ruff lint** (`ruff check .`), agent unit tests, API integration tests (Postgres + Redis), frontend build, security grep, E2E smoke tests |
| `codeql.yml` | **CodeQL** static analysis for Python and JavaScript (`security-and-quality` pack; config [`.github/codeql/codeql-config.yml`](.github/codeql/codeql-config.yml)) |

**Repository security features** (Settings → Code security): Dependabot alerts + security updates, secret scanning + push protection, private vulnerability reporting, Code scanning.

**Before pushing Python changes:**

```bash
ruff check .
pytest tests/test_api/ tests/test_agents/ -q --override-ini="addopts="
```

**Test API keys:** never commit `AIzaSy…` dummy keys — import `DUMMY_GEMINI_API_KEY` from `tests/gemini_test_keys.py`.

Dependabot opens weekly dependency PRs ([`.github/dependabot.yml`](.github/dependabot.yml)). Sensitive paths use [`.github/CODEOWNERS`](.github/CODEOWNERS).

**After merging CI for the first time**, enable branch protection on `main`:

1. **Settings → Branches → Add rule** for `main`
2. Require pull request before merging (1 approval recommended)
3. Require status check **`CI success`** (the aggregate job in `ci.yml`)
4. Optionally require CodeQL checks to pass
5. Enable **Require approval for first-time contributors** under **Settings → Actions → General → Fork pull request workflows**

The dependency-audit job is **advisory** (`continue-on-error`) until the Dependabot backlog is cleared — it still surfaces CVEs in the Actions log.

---

By contributing, you agree your code will be licensed under the [MIT License](LICENSE).
