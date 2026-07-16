<p align="center">
  <img src="docs/logo.svg" width="280" height="64" alt="ApplyPilot">
</p>

[![Python](https://img.shields.io/badge/Python-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D.svg)](https://redis.io/)
[![Node.js](https://img.shields.io/badge/Node.js-339933.svg)](https://nodejs.org/)
[![Chrome Extension](https://img.shields.io/badge/Chrome-Extension-4285F4.svg)](https://developer.chrome.com/docs/extensions/)
[![Gemini API](https://img.shields.io/badge/Gemini-API-4285F4.svg)](https://ai.google.dev/gemini-api)
[![OpenAI](https://img.shields.io/badge/OpenAI-API-412991.svg)](https://platform.openai.com/)
[![Anthropic](https://img.shields.io/badge/Anthropic-API-D4A27F.svg)](https://www.anthropic.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local-000000.svg)](https://ollama.com/)
[![Claude Code](https://img.shields.io/badge/Claude-Code-D97757.svg)](https://claude.ai/code)
[![Cursor](https://img.shields.io/badge/Cursor-IDE-000000.svg)](https://cursor.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

150 applications. One offer. Each application took 5+ manual steps.

Separate tools, separate tabs, separate sites — none of them talking to each other. Generic output. Over an hour per application.

Paste a job description — or pull it from any job site with the Chrome extension — and five AI agents run an orchestrated pipeline in under 30 seconds: analyzing the role, scoring your fit, researching the company, writing a targeted cover letter, and tailoring your resume to the role. Sequential where it needs to be, parallel where it can be, each agent's output feeding the next.

Also includes a dashboard to track every application. And tools for everything around it: interview prep with mock sessions, salary negotiation, job comparison, follow-ups, thank you notes, and references.

Runs on your machine. No subscriptions — each user picks Gemini, OpenAI, Anthropic, or local Ollama in **Settings → AI Setup** and brings their own key (Ollama needs none).

*Here's what a completed application looks like:*

![ApplyPilot demo](docs/demo.gif)

---

[Six AI Agents](#six-ai-agents) · [Career Tools](#six-career-tools) · [Quick Start](#quick-start) · [CLI](#cli) · [AI Provider / API Key](#ai-provider--api-key) · [Chrome Extension](#chrome-extension) · [Highlights](#highlights) · [Optional Features](#optional-features) · [Developer Setup](#developer-setup) · [Environment Variables](#environment-variables) · [How It Works](#how-it-works) · [Project Structure](#project-structure) · [Contributing](#contributing) · [License](#license)

---

## AI agents

Paste a job description and five agents run automatically:

| Agent | What it produces |
|-------|-----------------|
| **Job Analyzer** | Structured breakdown of requirements, skills, and ATS keywords |
| **Profile Matcher** | Fit score, strengths to highlight, gaps to address, application strategy |
| **Company Research** | Culture, leadership style, interview approach, watch-out notes |
| **Resume Advisor** | Per-bullet rewrites, ATS alignment score, before-you-submit checklist |
| **Cover Letter Writer** | Personalized cover letter, regenerate with one click |

Three more agents run **on demand** from the application detail page (after the workflow completes):

| Agent | What it produces |
|-------|-----------------|
| **Interview Prep** | Role-specific questions, model answers, STAR frameworks, and process tips (static guide on the Interview tab) |
| **CV Optimizer** | Iterative evaluate→revise loop: AI hiring manager scores your CV, AI applicant rewrites it, repeats until score threshold or max iterations. Outputs an optimized CV, cover letter, and **Download CV** (`.odt` via LibreOffice + HTML normalizer on server when available, else `.docx`; see [USER_GUIDE.md](USER_GUIDE.md#cv-optimization)). |
| **Mock Session** | Timed conversational mock session (HR / Pro / Manager; 10/15/20 min) with browser voice or typed answers and a scored debrief — see [USER_GUIDE.md](USER_GUIDE.md#practice-interview) |
| **Hiring Outreach** | Public web contact suggestions and copy-ready outreach drafts on the Outreach tab — see [USER_GUIDE.md](USER_GUIDE.md#hiring-outreach) |

## Six career tools

Standalone tools you can use any time — no job description needed:

| Tool | What it does |
|------|-------------|
| **Follow-up Email** | Post-application and post-interview follow-ups |
| **Thank You Note** | Interviewer thank you note, ready to send |
| **Salary Coach** | Negotiation script based on your offer and market data |
| **Rejection Analyzer** | Lessons learned and re-application strategy from a rejection email |
| **Reference Request** | Professional reference request for a specific contact |
| **Job Comparison** | Side-by-side comparison of 2–3 open roles |

## Quick Start

Three ways to run it — pick the one that suits you:

| | Docker (all platforms) | No Docker (macOS) | Manual |
|--|------------------------|-------------------|--------|
| **Command** | `make start` | `make start-local` | `make dev` |
| **Requires** | [Docker Desktop](https://www.docker.com/products/docker-desktop/) | macOS only | PostgreSQL + Redis running yourself |
| **First run** | ~2 min (builds Docker image) | ~3 min (installs Postgres + Redis) | Depends on your setup |
| **Subsequent runs** | ~5 sec | ~5 sec | ~5 sec |

### Option A — Docker (macOS, Linux, Windows)

**What you need:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running (installs WSL2 automatically on Windows). `make start` will tell you if it isn't running.

**macOS / Linux** — `make` is pre-installed:

```bash
git clone https://github.com/eliornl/applypilot.git
cd applypilot
make start
```

**Windows** — install [just](https://just.systems) (`winget install Casey.Just`) instead of `make`. It works natively in PowerShell and cmd — no WSL2 needed, and **no Git for Windows / `cygpath` required** for `just start` (only Docker Desktop + `just`).

```powershell
git clone https://github.com/eliornl/applypilot.git
cd applypilot
just start
```

Both commands do the same thing on first run:
- Copies `.env.local.example` → `.env` and fills in strong random secrets automatically
- Builds the Docker image (takes ~2 min, only on the first run)
- Starts PostgreSQL, Redis, and the app at **http://localhost:8000**
- Applies database migrations automatically when the app container starts (then starts the web server)

**After `git pull`:** Run **`make start`** / **`just start`** again — it rebuilds the app Docker image when needed (including the frontend bundle inside the image), then migrations run automatically when the app container starts.

```bash
make start-d      / just start-d       # run in background
make docker-logs  / just docker-logs   # watch the log
make docker-down  / just docker-down   # stop everything (data preserved)
make docker-reset / just docker-reset  # stop and wipe all data
```

---

### Option B — No Docker (macOS)

**What you need:** macOS. No Docker, no manual installs — `make start-local` installs everything it needs (Homebrew, Python 3, Node.js, PostgreSQL, Redis) automatically on the first run. If Homebrew isn't installed yet, you'll be prompted for your **sudo password** once in the terminal — this is normal and required to install Homebrew.

```bash
git clone https://github.com/eliornl/applypilot.git
cd applypilot
make start-local
```

`make start-local` handles everything on the first run:
- Installs Homebrew, Python 3, and Node.js if not already present
- Creates venv, installs Python and Node dependencies, **installs the `applypilot` CLI**, builds the frontend
- Copies `.env.local.example` → `.env` and fills in strong random secrets automatically
- Installs PostgreSQL 17 and Redis via Homebrew (first run only)
- Creates the database and user, runs migrations
- Starts the app at **http://localhost:8000**

**After `git pull`:** Run **`make start-local`** again — it rebuilds the frontend, applies migrations, and starts the app.

```bash
make start-local    # start everything
make stop-local     # stop PostgreSQL and Redis when done
make dev            # restart just the app (when services are already running)
```

---

### Option C — Manual (you run PostgreSQL and Redis yourself)

Use this if you already have PostgreSQL and Redis running (any platform, any setup). If you're on macOS and don't have them, use **Option B** instead — it installs everything for you.

**Step 1 — Clone and set up the project**

macOS / Linux:

```bash
git clone https://github.com/eliornl/applypilot.git
cd applypilot
make setup          # creates venv, installs deps + CLI, builds frontend, generates .env
```

Windows — install [just](https://just.systems) (`winget install Casey.Just`) first:

```powershell
git clone https://github.com/eliornl/applypilot.git
cd applypilot
just setup
```

**Step 2 — Create the database user and database**

Connect to PostgreSQL as a superuser (usually `postgres`) and run:

```sql
CREATE USER applypilot WITH PASSWORD 'applypilot';
CREATE DATABASE applypilot OWNER applypilot;
```

You can run these with `psql -U postgres` or any PostgreSQL client (pgAdmin, TablePlus, etc.).

> **Tip:** Using `applypilot` as the password matches the default in `.env` — you can skip Step 3 entirely. If you choose a different password, update `DATABASE_URL` in Step 3.

**Step 3 — Edit `.env` with your connection strings** _(skip if you used the default password above)_

Open `.env` and update `DATABASE_URL` to match the password you chose:

```bash
DATABASE_URL=postgresql+asyncpg://applypilot:yourpassword@localhost:5432/applypilot
REDIS_URL=redis://localhost:6379/0
```

**Step 4 — Run migrations and start the app**

```bash
make migrate  / just migrate   # creates all database tables
make dev      / just dev       # start the app at http://localhost:8000
```

**After `git pull`:** Run **`make migrate`** / **`just migrate`**, then **`make dev`** / **`just dev`** (`make dev` rebuilds the frontend before starting uvicorn). If **`requirements.txt`** or **`ui/package.json`** changed, run **`make setup`** / **`just setup`** first, then migrate and dev again.

From then on, as long as PostgreSQL and Redis are running and you are not pulling new upstream changes, `make dev` / `just dev` is all you need.

---

### You're running when you see:

```
INFO:     Application startup complete.
```

Open **http://localhost:8000** in your browser and create your account.
During profile setup you can add a Gemini API key, or configure any provider later in **Settings → AI Setup** (Gemini / OpenAI / Anthropic / Ollama).

---

## CLI

Terminal client for the same API — useful for scripting, AI assistants (Cursor, Claude Code, Codex), and automation.

**Installed automatically** by `make setup`, `make start-local`, and `just setup`. The command lives in the venv:

```bash
source venv/bin/activate    # macOS/Linux
applypilot doctor
```

Or without activating: `venv/bin/applypilot doctor` (Windows: `venv\Scripts\applypilot.exe`).

**Docker only (`make start`):** the app runs in containers; run **`make setup` once on the host** if you also want the CLI on your machine (same venv + `applypilot` command).

**First session** (server must be running):

```bash
applypilot auth login              # or: applypilot auth token set  (OAuth users)
applypilot profile status          # complete profile if needed
applypilot workflow analyze job.txt --wait --format json
applypilot apps list
applypilot apps show APP_ID        # summary + workflow session link
```

**Automation / scripts:** create a personal access token (shown once) and save it locally:

```bash
applypilot auth token create --name "CI" --save
applypilot workflow results SESSION_ID --section cover-letter --out letter.md
applypilot workflow watch SESSION_ID   # live WebSocket progress
applypilot config set --base-url https://your-server.example.com
```

Use `--no-pager` when piping long human output. Destructive commands require `--confirm` (e.g. `profile resume delete --confirm`).

**Shell completion:** run `applypilot --install-completion` from your terminal (auto-detects bash/zsh/fish).

Full command reference: **[docs/cli-reference.md](docs/cli-reference.md)** (shell aliases included) · Tests: `make cli-test`

---

## AI Provider / API Key

Each user **must** pick an AI provider in **Settings → AI Setup** (`gemini`, `openai`, `anthropic`, or `ollama`) and add a BYOK API key for cloud providers. Ollama needs no key. Model is optional (system default or pick from the provider list).

1. Open **Settings → AI Setup**
2. Select a provider
3. Paste your API key (Gemini / OpenAI / Anthropic) — or choose Ollama for local inference
4. Optionally pick a preferred model

**Vertex AI (self-hosted admins):** set `USE_VERTEX_AI=true` so users do not need a personal key (Gemini path).

**`LLM_PROVIDER` / server API keys** are for health checks and admin fallback only — they are **not** used as a substitute for user BYOK on generate paths (except Vertex).

See [`.env.local.example`](.env.local.example) and `.cursor/rules/llm-integration.mdc`.

---

## Chrome Extension

**Analyze This Job** and **Match Form To Profile** in one click, one Chrome extension—any job site.

1. Open **chrome://extensions** in Chrome
2. Enable **Developer Mode** (toggle, top-right corner)
3. Click **Load unpacked**
4. Select the `extension/` folder from this repo

The extension appears in your Chrome toolbar. Browse jobs naturally. When you find one you like, use **Analyze This Job** to send the posting to your dashboard for the full AI workflow, or use **Match Form To Profile** to fill application forms from your profile (AI mapping plus deterministic rules for screening and contact fields — always review before submit).

---

## Highlights

- **Local-first** — PostgreSQL, Redis, and the app all run on your machine. One command to start, no external services required.
- **Full profile system** — work experience, skills, career preferences; agents use your profile in every output.
- **BYOK AI keys** — each user picks a provider and adds their own key via Settings (or uses Ollama / Vertex admin mode).
- **Google OAuth** — optional "Continue with Google" alongside standard email/password.
- **Multi-user ready** — JWT auth, encrypted key storage, rate limiting per user, soft delete.
- **No analytics by default** — PostHog is disabled unless you explicitly enable it in `.env`.
- **Data ownership** — everything lives in your local PostgreSQL database. Delete the volume and it's gone.

---

## Optional Features

### Password reset emails (SMTP)

For a personal single-user setup this is usually not needed. To enable:

```bash
# Add to .env:
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-gmail@gmail.com
SMTP_PASSWORD=your-app-password        # myaccount.google.com/apppasswords
SMTP_FROM_EMAIL=your-gmail@gmail.com
SMTP_FROM_NAME=ApplyPilot
DISABLE_EMAIL_VERIFICATION=false       # require email verification on sign-up
```

### Continue with Google (OAuth)

1. [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Web application)
3. Set authorized redirect URI: `http://localhost:8000/api/v1/auth/google/callback`
4. Add to `.env`:

```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
```

### Analytics (PostHog)

Disabled by default. To enable:

1. Create a free project at [posthog.com](https://posthog.com)
2. Add to `.env`:

```bash
POSTHOG_ENABLED=true
POSTHOG_API_KEY=phc_your-api-key
POSTHOG_HOST=https://us.i.posthog.com   # or your self-hosted instance
```

### Vertex AI (server admins)

Use this if you have a Google Cloud project and want to use Vertex AI instead of per-user BYOK. End users skip personal keys when Vertex is enabled — otherwise they pick a provider and add their own key in **Settings → AI Setup**.

```bash
USE_VERTEX_AI=true
VERTEX_AI_PROJECT=your-gcp-project-id
VERTEX_AI_LOCATION=global   # required for gemini-3-* models
```

Requires [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials) (`gcloud auth application-default login`) or a service account in the environment.

---

## Developer Setup

**macOS (no Docker)** — see [Option B](#option-b--no-docker-macos) in Quick Start. After the first run, restarting the app is just:

```bash
make dev            # restart the FastAPI server (Postgres + Redis already running)
```

**Frontend changes** — after editing any JS or CSS file, rebuild assets and hard-refresh:

```bash
make build-frontend    # rebuilds dist/ and updates manifest.json
# Then Cmd+Shift+R in the browser (no server restart needed in dev mode)
```

**Linux / custom setup** — see [Option C](#option-c--manual-you-run-postgresql-and-redis-yourself) in Quick Start.

### All make commands

| Command | What it does |
|---------|-------------|
| `make start-local` | No Docker: install services + setup + migrate + start app (macOS) |
| `make stop-local` | Stop PostgreSQL and Redis Homebrew services |
| `make start` / `just start` | Docker: generate `.env` + start all services (foreground) |
| `make start-d` / `just start-d` | Docker: generate `.env` + start all services (background) |
| `make docker-down` / `just docker-down` | Stop Docker services, keep data |
| `make docker-reset` / `just docker-reset` | Stop Docker services, wipe data volumes |
| `make docker-logs` / `just docker-logs` | Tail the Docker app log |
| `make setup` / `just setup` | Dev setup: venv + Python/Node deps + **CLI** + frontend build |
| `make dev` / `just dev` | Start FastAPI dev server with auto-reload (services must be running) |
| `make migrate` / `just migrate` | Run Alembic database migrations |
| `make build-frontend` / `just build-frontend` | Compile and content-hash JS/CSS assets |
| `make test` / `just test` | Run the test suite |
| `make cli-test` / `just cli-test` | Run CLI tests (`tests/test_cli/`) |
| `make lint` / `just lint` | Run ruff linter |
| `make clean` | Remove venv and compiled artefacts |

---

## Environment Variables

`.env` is created and populated automatically by `make start`, `make start-local`, or `make setup`. You normally don't need to touch it.

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | Auto-generated | Signs auth tokens |
| `ENCRYPTION_KEY` | Auto-generated | Encrypts stored API keys |
| `DATABASE_URL` | Set automatically | PostgreSQL connection |
| `REDIS_URL` | Set automatically | Redis connection |
| `LLM_PROVIDER` | `gemini` | Health/admin fallback provider only (`gemini` \| `openai` \| `anthropic` \| `ollama`) — users pick via **Settings → AI Setup** |
| `GEMINI_API_KEY` | _(empty)_ | Server Gemini key for health/admin; users add BYOK in Settings |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Default Gemini model (overridable per user when BYOK) |
| `OPENAI_API_KEY` | _(empty)_ | Server OpenAI key for health/admin; users add BYOK in Settings |
| `OPENAI_MODEL` | `gpt-5.6-luna` | Default OpenAI model |
| `ANTHROPIC_API_KEY` | _(empty)_ | Server Anthropic key for health/admin; users add BYOK in Settings |
| `ANTHROPIC_MODEL` | `claude-sonnet-5` | Default Anthropic model |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama host when user selects Ollama |
| `OLLAMA_MODEL` | `qwen3` | Default Ollama model |
| `BASE_URL` | `http://localhost:8000` | Used in password-reset and verification email links |
| `DISABLE_EMAIL_VERIFICATION` | `true` | Set `false` when SMTP is configured |
| `GOOGLE_CLIENT_ID` | _(empty)_ | Enables "Continue with Google" |
| `SMTP_HOST` | _(empty)_ | Enables password-reset emails |
| `DEBUG` | `true` | Set `false` in any shared or public environment |
| `USE_VERTEX_AI` | `false` | Server-admin: use Google Cloud Vertex AI instead of a direct API key |

Full reference with comments: [`.env.local.example`](.env.local.example)

---

## How it works

```
Browser / Chrome Extension
         │
         ▼
┌──────────────────────────────┐
│         FastAPI app          │  Python 3.13, async
│    uvicorn · port 8000       │
└──────────┬───────────────────┘
           │
           ├── PostgreSQL   users, profiles, job applications, workflow sessions, agent outputs
           ├── Redis         caching, rate limiting, auth state, background task locks
           │
           └── Five-Agent Pipeline (`get_llm_client()` + LangGraph)
                  Job Analyzer
                       ↓
                 Profile Matcher  ← gates on low fit score
                       ↓
               Company Research
                       ↓
        Resume Advisor + Cover Letter Writer  (parallel)

        Interview Prep  ← standalone, runs on demand (static guide)

        CV Optimizer  ← standalone, runs on demand after workflow completes
               Hiring Manager (evaluator) ←──────────────┐
                       ↓                                  │
               CV Optimizer (reviser)                     │
                       ↓                                  │
               Convergence check ─── continue ───────────┘
                       │ stop
               Cover Letter Finalizer → optimized CV + cover letter

        Mock Session       ← standalone timed conversational mock (HR/Pro/Manager)

        Hiring Outreach  ← standalone public-web contacts + copy-only draft messages
        Six career tools (Follow-up Email, Thank You Note, Salary Coach,
        Rejection Analyzer, Reference Request, Job Comparison)
                        ← standalone, no job description needed
```

Frontend: server-rendered HTML + **TypeScript** (Vite-bundled per page), no React/Vue. CSS is esbuild-minified; JS is built from `ui/src/` into content-hashed bundles. The Chrome extension uses Manifest V3 and posts directly to your server.

---

## Project Structure

```
applypilot/
├── main.py               # FastAPI app entry point
├── cli/                  # ApplyPilot CLI (Typer commands)
├── applypilot_client/    # Sync HTTP client for CLI
├── agents/               # 5 workflow agents + interview prep + hiring outreach + CV optimizer loop + 6 career tool agents
├── workflows/            # LangGraph pipeline orchestration and state schema
├── api/                  # FastAPI route handlers
├── config/               # Settings (Pydantic BaseSettings + .env)
├── models/               # SQLAlchemy ORM models and database setup
├── utils/                # Auth, email, Redis, encryption, multi-provider LLM (`utils/llm/`)
├── alembic/              # Database migrations
├── extension/            # Chrome Extension (Manifest V3)
├── ui/                   # HTML templates + TypeScript frontend + CSS
│   ├── src/              # TypeScript page entries + shared modules (Vite)
│   ├── index.html        # Landing page
│   ├── dashboard/        # All dashboard pages
│   ├── auth/             # Login, register, verify
│   ├── profile/          # Profile setup
│   ├── partials/         # Shared template fragments
│   └── static/           # CSS source + dist/ build output (gitignored)
├── tests/                # Unit + integration tests (pytest)
│   ├── test_agents/      # Agent unit tests
│   ├── test_api/         # API integration tests (no live server needed)
│   └── test_cli/         # CLI tests (CliRunner, mocked HTTP)
├── e2e/                  # Playwright end-to-end tests
├── docs/                 # Demo GIF, logo, CLI reference
├── docker-compose.yml    # Local: postgres + redis + app
├── Dockerfile            # Multi-stage build: Node (frontend) → Python
├── Makefile              # Dev workflow shortcuts (macOS / Linux)
├── Justfile              # Same shortcuts for Windows (just)
├── requirements.txt      # Python dependencies
├── CHANGELOG.md          # Version history
├── CONTRIBUTING.md       # Contribution guide
├── CODE_OF_CONDUCT.md    # Contributor Covenant
├── SECURITY.md           # Private vulnerability reporting
├── .github/              # Issue & PR templates
├── USER_GUIDE.md         # End-user documentation
└── .env.local.example    # Config template (make start copies this to .env)
```

---

## Contributing

Contributions are welcome. Open an issue first to discuss what you'd like to change.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and run the tests: `make test`
4. Open a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code style, and the PR checklist. Security issues: [SECURITY.md](SECURITY.md). Community standards: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

## License

[MIT](LICENSE) — use it, fork it, modify it, self-host it.
