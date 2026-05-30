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
[![Claude Code](https://img.shields.io/badge/Claude-Code-D97757.svg)](https://claude.ai/code)
[![Cursor](https://img.shields.io/badge/Cursor-IDE-000000.svg)](https://cursor.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

150 applications. One offer. Each application took 5+ manual steps.

Separate tools, separate tabs, separate sites — none of them talking to each other. Generic output. Over an hour per application.

Paste a job description — or pull it from any job site with the Chrome extension — and five AI agents run an orchestrated pipeline in under 30 seconds: analyzing the role, scoring your fit, researching the company, writing a targeted cover letter, and tailoring your resume to the role. Sequential where it needs to be, parallel where it can be, each agent's output feeding the next.

Also includes a dashboard to track every application. And tools for everything around it: interview prep with mock sessions, salary negotiation, job comparison, follow-ups, thank you notes, and references.

Runs on your machine. No subscriptions, no data stored on our servers — just your own Gemini API key connecting directly to Google.

*Here's what a completed application looks like:*

![ApplyPilot demo](docs/demo.gif)

---

[Six AI Agents](#six-ai-agents) · [Career Tools](#six-career-tools) · [Quick Start](#quick-start) · [Gemini API Key](#gemini-api-key) · [Chrome Extension](#chrome-extension) · [Highlights](#highlights) · [Optional Features](#optional-features) · [Developer Setup](#developer-setup) · [Environment Variables](#environment-variables) · [How It Works](#how-it-works) · [Project Structure](#project-structure) · [Contributing](#contributing) · [License](#license)

---

## Six AI agents

Paste a job description and the pipeline runs automatically:

| Agent | What it produces |
|-------|-----------------|
| **Job Analyzer** | Structured breakdown of requirements, skills, and ATS keywords |
| **Profile Matcher** | Fit score, strengths to highlight, gaps to address, application strategy |
| **Company Research** | Culture, leadership style, interview approach, watch-out notes |
| **Resume Advisor** | Per-bullet rewrites, ATS alignment score, before-you-submit checklist |
| **Cover Letter Writer** | Personalized cover letter, regenerate with one click |
| **Interview Prep** _(standalone)_ | Role-specific questions, model answers, full mock interview session |

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
- Creates venv, installs Python and Node dependencies, builds the frontend
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
make setup          # creates venv, installs deps, builds frontend, generates .env
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
During profile setup you'll be prompted to add your Gemini API key — or you can add it later in **Settings → AI Setup**.

---

## Gemini API Key

AI features require a key from Google AI Studio.

1. Go to [aistudio.google.com/api-keys](https://aistudio.google.com/api-keys)
2. Sign in with your Google account
3. Click **Create API key** — copy the entire key string (Google may show different formats over time).
4. Paste it in ApplyPilot — you'll be prompted during **profile setup**, or add it later via **Settings → AI Setup**

**For personal use** that's all — no `.env` editing needed. Each user stores their own key, encrypted in the database.

**For multi-user hosting:** add `GEMINI_API_KEY=<your key>` to `.env` to set a shared server-side key so users don't need to provide their own.

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
- **BYOK AI keys** — each user adds their own Gemini key via Settings, or the admin sets one server-wide key.
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

Use this if you have a Google Cloud project and want to use Vertex AI instead of a direct Gemini API key. End users are not affected — they still add their own Google AI Studio key via Settings.

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
| `make setup` / `just setup` | Dev setup: venv + Python/Node deps + frontend build |
| `make dev` / `just dev` | Start FastAPI dev server with auto-reload (services must be running) |
| `make migrate` / `just migrate` | Run Alembic database migrations |
| `make build-frontend` / `just build-frontend` | Compile and content-hash JS/CSS assets |
| `make test` / `just test` | Run the test suite |
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
| `GEMINI_API_KEY` | _(empty)_ | Server-wide AI key — users can add their own during profile setup or via **Settings → AI Setup** |
| `GEMINI_MODEL` | `gemini-3.5-flash` | AI model to use — users can change this in **Settings → AI Setup** |
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
           └── Five-Agent Pipeline (Google Gemini + LangGraph)
                  Job Analyzer
                       ↓
                 Profile Matcher  ← gates on low fit score
                       ↓
               Company Research
                       ↓
        Resume Advisor + Cover Letter Writer  (parallel)

        Interview Prep  ← standalone, runs on demand

        Six career tools (Follow-up Email, Thank You Note, Salary Coach,
        Rejection Analyzer, Reference Request, Job Comparison)
                        ← standalone, no job description needed
```

Frontend: server-rendered HTML + vanilla JS, no framework. Assets are compiled and content-hashed with esbuild. The Chrome extension uses Manifest V3 and posts directly to your local server.

---

## Project Structure

```
applypilot/
├── main.py               # FastAPI app entry point
├── agents/               # 5 workflow agents + interview prep + 6 career tool agents
├── workflows/            # LangGraph pipeline orchestration and state schema
├── api/                  # FastAPI route handlers
├── config/               # Settings (Pydantic BaseSettings + .env)
├── models/               # SQLAlchemy ORM models and database setup
├── utils/                # Auth, email, Redis, encryption, LLM client helpers
├── alembic/              # Database migrations
├── extension/            # Chrome Extension (Manifest V3)
├── ui/                   # HTML templates + JS + CSS
│   ├── index.html        # Landing page
│   ├── dashboard/        # All dashboard pages
│   ├── auth/             # Login, register, verify
│   ├── profile/          # Profile setup
│   ├── partials/         # Shared template fragments
│   └── static/           # Compiled assets (esbuild output)
├── tests/                # Unit + integration tests (pytest)
│   ├── test_agents/      # Agent unit tests
│   └── test_api/         # API integration tests (no live server needed)
├── e2e/                  # Playwright end-to-end tests
├── docs/                 # Demo GIF and logo assets
├── docker-compose.yml    # Local: postgres + redis + app
├── Dockerfile            # Multi-stage build: Node (frontend) → Python
├── Makefile              # Dev workflow shortcuts (macOS / Linux)
├── Justfile              # Same shortcuts for Windows (just)
├── requirements.txt      # Python dependencies
├── CHANGELOG.md          # Version history
├── CONTRIBUTING.md       # Contribution guide
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

---

## License

[MIT](LICENSE) — use it, fork it, modify it, self-host it.
