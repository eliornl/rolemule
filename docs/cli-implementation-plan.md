# RoleMule CLI — Implementation Plan

**Status:** Implemented (Phases 0–9 complete on `feature/cli`, 2026-07-08)  
**Last updated:** 2026-07-08  
**Audience:** Engineers implementing the CLI and reviewers signing off each phase  

**Review notes:** Final pass verified every `@router` in `api/*.py`, `ApplicationStatus` / `WorkflowStatus` enums, `ErrorResponse` schema in `utils/error_responses.py`, profile-gate dependencies, upload size limits, and admin/monitoring routes in `main.py`.

---

## 1. Executive summary

Build a **full-parity CLI** for RoleMule that talks to the existing FastAPI server over `/api/v1/*`. The CLI is a thin client — no agents, no database, no duplicate business logic. Same architecture as the Chrome extension.

**Primary users:**
- Developers using **AI coding assistants** (Claude Code, Cursor, Codex, Gemini CLI, etc.) — any tool that can run shell commands and read stdout
- Shell scripts and automation
- Power users who prefer terminal over browser

**Non-goals:**
- Replacing the web UI for rich visual review (tabs, charts, long-form reading)
- Running workflows offline without the server
- MCP server (future optional layer; out of scope for this plan)

**Success criteria:**
- Every user-facing API capability has a CLI equivalent (except browser-only OAuth redirect flows)
- `--format json` output is stable enough for Claude Code to parse
- Each phase ships with tests + documented code review sign-off before the next phase starts

---

## 2. Design principles

| Principle | Rule |
|-----------|------|
| Thin client | CLI → HTTP only. Never import `agents/`, `workflows/`, or SQLAlchemy from CLI code. |
| API v1 only | Always call `/api/v1/...`. Never legacy `/api/...`. |
| Same errors as UI | Map `error_code` (`CFG_6001`, `RES_3002`, `RATE_4001`, etc.) to actionable CLI messages. |
| Safe defaults | Destructive commands require `--confirm` or an interactive Typer/Click confirmation prompt. |
| Two output modes | `--format human` (default) and `--format json` (machine-readable for AI agents). |
| Long jobs poll | `--wait` blocks with progress until a **stop state** (see §5.5 workflow statuses). |
| Config on disk | `~/.rolemule/config.toml` + `~/.rolemule/credentials.json` (mode `0600`). |
| No secrets in logs | Never print JWT, BYOK keys, or passwords except masked. |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  rolemule (Typer CLI entry point)                         │
│    commands/auth.py, workflow.py, apps.py, tools.py, ...    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  rolemule_client/ (shared HTTP library)                   │
│    client.py      — httpx sync wrapper, auth header         │
│    errors.py      — APIError parsing, exit codes            │
│    polling.py     — wait_for_workflow, wait_for_cv, etc.    │
│    output.py      — human/json formatters                   │
│    resources/     — one module per API domain               │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP or HTTPS
┌──────────────────────────▼──────────────────────────────────┐
│  RoleMule server (existing FastAPI app)                     │
│    /api/v1/auth, profile, workflow, applications, ...         │
└───────────────────────────────────────────────────────────────┘
```

### 3.1 Proposed directory layout

```
rolemule/
├── cli/
│   ├── __init__.py
│   ├── __main__.py              # python -m cli
│   ├── main.py                  # Typer app root
│   ├── config.py                # load/save ~/.rolemule/*
│   ├── context.py               # global flags: --base-url, --format, --no-color
│   └── commands/
│       ├── auth.py
│       ├── profile.py
│       ├── workflow.py
│       ├── applications.py
│       ├── interview.py
│       ├── cv.py
│       ├── tools.py
│       ├── extension.py         # autofill map (power users)
│       └── doctor.py            # health + config diagnostics
├── rolemule_client/
│   ├── __init__.py
│   ├── client.py
│   ├── errors.py
│   ├── polling.py
│   ├── output.py
│   └── resources/
│       ├── auth.py
│       ├── profile.py
│       ├── workflow.py
│       ├── applications.py
│       ├── interview_prep.py
│       ├── cv_optimizer.py
│       ├── tools.py
│       └── extension.py
├── tests/
│   └── test_cli/
│       ├── conftest.py          # CliRunner, mock client fixtures
│       ├── test_client.py
│       ├── test_auth_commands.py
│       └── ...                  # one file per phase
├── pyproject.toml               # [project.scripts] rolemule = "cli.main:main"
└── docs/
    └── cli-implementation-plan.md   # this file
```

### 3.2 Dependencies (optional extra — do **not** add to server `requirements.in`)

Keep CLI deps out of the production server image. Use a `pyproject.toml` optional group:

```toml
[project]
dependencies = [
  "httpx>=0.28",   # shared with server; required by rolemule_client
]

[project.optional-dependencies]
cli = [
  "typer[all]>=0.12",
  "tomli-w>=1.0",   # write config.toml (read via stdlib tomllib on Python 3.11+)
]
```

**Reuse existing:** `httpx` is already in `requirements.txt` for the server — also declare it in `pyproject.toml` `[project.dependencies]` so `pip install -e ".[cli]"` works in a clean venv without manually installing server reqs first.

**Python version:** Project targets **3.13** (see `Dockerfile`). Use stdlib `tomllib` for reading config; only `tomli-w` needed for writes.

### 3.3 Entry point

Typer root apps must expose a **callable entry function** (not the raw `Typer` object):

```python
# cli/main.py
app = typer.Typer(...)

def main() -> None:
    app()

if __name__ == "__main__":
    main()
```

```toml
# pyproject.toml
[project.scripts]
rolemule = "cli.main:main"
```

Install locally: `pip install -e ".[cli]"` from repo root.

---

## 4. Configuration and authentication

### 4.1 Config file — `~/.rolemule/config.toml`

```toml
[server]
base_url = "http://localhost:8000"

[output]
default_format = "human"   # human | json
color = true

[cli]
poll_interval_seconds = 3
poll_timeout_seconds = 600
```

Override per invocation: `rolemule --base-url https://... workflow analyze ...`

### 4.2 Credentials — `~/.rolemule/credentials.json`

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "email": "user@example.com",
  "saved_at": "2026-07-08T12:00:00Z"
}
```

- File permissions: `0600` on write
- `rolemule auth login` writes; `rolemule auth logout` deletes token key only
- `rolemule auth token set --from-stdin` for Google OAuth users (paste JWT from browser DevTools)

### 4.3 Auth flows

| Flow | CLI support | Notes |
|------|-------------|-------|
| Email + password login | ✅ Phase 1 | `POST /api/v1/auth/login` |
| Token refresh | ✅ Phase 1 | `POST /api/v1/auth/refresh` with current Bearer JWT (no separate refresh token) |
| Logout | ✅ Phase 1 | `POST /api/v1/auth/logout` + clear local file |
| Register + verify email | ⚠️ Partial | Register yes; **do not save JWT from register** — only save token from `verify-code` success (same rule as web UI) |
| Resend verification | ✅ Phase 1 | `POST /api/v1/auth/resend-verification` |
| Verification status | ✅ Phase 1 | `GET /api/v1/auth/verification-status` |
| Google OAuth | ⚠️ Document only | Browser required; CLI imports token via `auth token set` |
| Change password | ✅ Phase 1 | `PUT /api/v1/auth/change-password` |
| Forgot / reset password | ❌ Skip | Browser-only UX is fine |

### 4.4 Profile gate (`get_current_user_with_complete_profile`)

Only some endpoints require a **completed profile** (403 otherwise). The CLI must map 403 to exit code `2` with actionable copy.

| Requires complete profile (`403 AUTH_1006`) | Auth only (`get_current_user`) |
|---------------------------------------------|--------------------------------|
| `POST /workflow/start` | `GET /workflow/status`, `GET /workflow/results`, `GET /workflow/history` |
| `POST /workflow/regenerate-*` | `POST /workflow/continue`, `POST /workflow/generate-documents` |
| All `/applications/*` (list, stats, patch, delete, download) | All `/tools/*` endpoints |
| `POST /extension/autofill/map` | All `/interview-prep/*`, `/cv-optimizer/*` |
| | All `/profile/*` (read/update during setup — no complete profile required) |

CLI helpers:
- `rolemule profile status` — show completion breakdown
- Exit code `2` — link to `rolemule profile complete` or web `/profile/setup`

---

## 5. Complete command tree → API mapping

Legend: **Phase** = implementation phase number.

### 5.1 Global flags (all commands)

| Flag | Description |
|------|-------------|
| `--base-url URL` | Override config server URL |
| `--format human\|json` | Output format |
| `--no-color` | Disable Rich styling |
| `-q` / `-v` | Quiet / verbose |

### 5.2 `rolemule doctor` — Phase 0

| Command | API | Notes |
|---------|-----|-------|
| `doctor` | `GET /health` | Server reachable? PAT vs JWT, expiry hint |
| `doctor` | `GET /api/v1/auth/verify` | Token valid? (if logged in) |
| `doctor` | reads config files | Permissions, paths |

### 5.3 `rolemule auth` — Phase 1

| Command | API |
|---------|-----|
| `auth login [--email]` | `POST /api/v1/auth/login` |
| `auth logout` | `POST /api/v1/auth/logout` |
| `auth whoami` | `GET /api/v1/auth/verify` |
| `auth refresh` | `POST /api/v1/auth/refresh` |
| `auth register` | `POST /api/v1/auth/register` |
| `auth verify-code CODE` | `POST /api/v1/auth/verify-code` |
| `auth change-password` | `PUT /api/v1/auth/change-password` |
| `auth token set` | local only |
| `auth token show` | local only (masked) |
| `auth email-status` | `GET /api/v1/auth/email-status` |
| `auth resend-verification` | `POST /api/v1/auth/resend-verification` |
| `auth verification-status` | `GET /api/v1/auth/verification-status` |
| `auth extension-status` | `GET /api/v1/auth/extension-status` (parity with Chrome extension auth check) |

**Not in CLI:** OAuth browser redirects (`/auth/google`, callback, exchange-code), `google/link`, `google/unlink` — document token-import workaround via `auth token set`.

### 5.4 `rolemule profile` — Phase 2

| Command | API |
|---------|-----|
| `profile show` | `GET /api/v1/profile/` |
| `profile status` | `GET /api/v1/profile/status` |
| `profile complete` | `POST /api/v1/profile/complete` |
| `profile set basic-info` | `PUT /api/v1/profile/basic-info` |
| `profile set work-experience --file` | `PUT /api/v1/profile/work-experience` |
| `profile set education --file` | `PUT /api/v1/profile/education` |
| `profile set skills` | `PUT /api/v1/profile/skills-qualifications` |
| `profile set preferences` | `PUT /api/v1/profile/career-preferences` |
| `profile set notifications` | `PUT /api/v1/profile/notifications` |
| `profile resume upload FILE` | `POST /api/v1/profile/parse-resume` (multipart; **10 MB** max — larger than workflow job uploads at 5 MB) |
| `profile resume show` | `GET /api/v1/profile/resume` |
| `profile resume delete` | `DELETE /api/v1/profile/resume` |
| `profile api-key status` | `GET /api/v1/profile/api-key/status` |
| `profile api-key set` | `POST /api/v1/profile/api-key` |
| `profile api-key delete` | `DELETE /api/v1/profile/api-key` |
| `profile api-key validate` | `POST /api/v1/profile/api-key/validate` |
| `profile workflow-preferences show` | `GET /api/v1/profile/preferences` |
| `profile workflow-preferences set` | `PATCH /api/v1/profile/preferences` |
| `profile export [--out FILE]` | `GET /api/v1/profile/export` |
| `profile clear-data --confirm` | `DELETE /api/v1/profile/clear-data` — JSON body `{"confirm": true}` |
| `profile delete-account --confirm` | `DELETE /api/v1/profile/delete-account` — JSON body `{"password": "..."}` (empty string for Google-only accounts) |

JSON profile sections: accept `--file data.json` or stdin (`--file -`).

### 5.5 `rolemule workflow` — Phase 3

| Command | API |
|---------|-----|
| `workflow analyze -` | `POST /api/v1/workflow/start` — Form `job_text` from stdin |
| `workflow analyze job.txt` | same — Form `job_text` from file contents |
| `workflow analyze --upload job.pdf` | multipart field `job_file` (`.pdf`, `.txt`, `.docx`; max 5 MB) |
| `workflow analyze --url URL` | Form `job_url` (metadata only; server does **not** fetch URL) |
| `workflow analyze --source-url URL` | Form `source_url` (optional; stored as posting URL when http(s)) |
| `workflow analyze --title T --company C` | Form `detected_title` / `detected_company` (optional CLI metadata) |
| `workflow status SESSION` | `GET /api/v1/workflow/status/{id}` |
| `workflow results SESSION` | `GET /api/v1/workflow/results/{id}` |
| `workflow history` | `GET /api/v1/workflow/history` |
| `workflow continue SESSION [--confirm]` | `POST /api/v1/workflow/continue/{id}` |
| `workflow generate-documents SESSION` | `POST /api/v1/workflow/generate-documents/{id}` |
| `workflow regenerate cover-letter SESSION` | `POST .../regenerate-cover-letter/{id}` |
| `workflow regenerate resume SESSION` | `POST .../regenerate-resume/{id}` |
| `workflow generate-interview-prep SESSION` | `POST .../generate-interview-prep/{id}` (legacy path; prefer `rolemule interview generate`) |

**Workflow statuses** (from `WorkflowStatus` enum — use these exact strings when polling):

| Status | Meaning | `--wait` stops here? |
|--------|---------|------------------------|
| `initialized` | Just created | No — keep polling |
| `in_progress` | Agents running | No |
| `awaiting_confirmation` | Gate score below threshold — user must confirm | **Yes** — print match score + hint to run `workflow continue` |
| `analysis_complete` | Analysis done; cover letter/resume not generated yet | **Yes** — hint to run `workflow generate-documents` |
| `completed` | Full success | **Yes** |
| `failed` | Terminal error | **Yes** — print `error_messages` |

**Flags:**
- `--wait` — poll until a stop state in the table above (not only `completed`/`failed`)
- `--section cover-letter|resume|fit|company|all` — filter human output
- `--open` — print dashboard URL for session/application

**Error handling:**
- `409 RES_3002` → exit `0` with warning; parse `details[]` where `field` is `application_id` or `session_id` (not a top-level object)
- `422 CFG_6001` → “Add API key: rolemule profile api-key set” (or configure server `GEMINI_API_KEY` / Vertex)

### 5.6 `rolemule apps` — Phase 4

| Command | API |
|---------|-----|
| `apps list` | `GET /api/v1/applications/` |
| `apps stats` | `GET /api/v1/applications/stats/overview` |
| `apps status APP_ID STATUS` | `PATCH /api/v1/applications/{id}/status` |
| `apps notes APP_ID [--file\|TEXT]` | `PATCH /api/v1/applications/{id}/notes` |
| `apps delete APP_ID --confirm` | `DELETE /api/v1/applications/{id}` |
| `apps download APP_ID [--out FILE]` | `GET /api/v1/applications/{id}/download` |

**List filters** (CLI flags → API query params):

| CLI flag | API param | Notes |
|----------|-----------|-------|
| `--search` | `search` | Title + company |
| `--status` | `status_filter` | `draft`, `processing`, `completed`, `failed`, `applied`, `interview`, `rejected`, `accepted` |
| `--company` | `company` | Partial match |
| `--days` | `days` | 1–365 |
| `--sort` | `sort` | `created_desc` (default), `created_asc`, `updated_desc`, `company_asc`, `title_asc` |
| `--page` | `page` | |
| `--per-page` | `per_page` | |

Application detail view = combine `apps list` row + `workflow results` when `session_id` known.

### 5.7 `rolemule interview` — Phase 5

| Command | API |
|---------|-----|
| `interview show SESSION` | `GET /api/v1/interview-prep/{id}` |
| `interview status SESSION` | `GET /api/v1/interview-prep/{id}/status` |
| `interview generate SESSION [--wait] [--regenerate]` | `POST /api/v1/interview-prep/{id}/generate?regenerate=true` (preferred over `workflow generate-interview-prep`) |
| `interview delete SESSION --confirm` | `DELETE /api/v1/interview-prep/{id}` |

Human output: sections for questions, model answers, checklist (match UI fields).

### 5.8 `rolemule cv` — Phase 6

| Command | API |
|---------|-----|
| `cv start SESSION [--max-iter N] [--threshold SCORE] [--wait]` | `POST /api/v1/cv-optimizer/{id}/start` — body optional: `max_iterations` **2–7** (default 5), `score_threshold` **7.0–9.5** (default 8.5) |
| `cv show SESSION` | `GET /api/v1/cv-optimizer/{id}` |
| `cv status SESSION` | `GET /api/v1/cv-optimizer/{id}/status` |
| `cv download SESSION [--out FILE]` | `GET /api/v1/cv-optimizer/{id}/download-cv` |
| `cv clear SESSION --confirm` | `DELETE /api/v1/cv-optimizer/{id}` |

Download: respect `Content-Disposition` filename; fallback `optimized-cv.odt` / `.docx`.

### 5.9 `rolemule tools` — Phase 7

| Command | API |
|---------|-----|
| `tools followup-stages` | `GET /api/v1/tools/followup-stages` |
| `tools followup --file REQUEST.json` | `POST /api/v1/tools/followup` |
| `tools thank-you --file REQUEST.json` | `POST /api/v1/tools/thank-you` |
| `tools salary-coach --file REQUEST.json` | `POST /api/v1/tools/salary-coach` |
| `tools rejection-analysis --file REQUEST.json` | `POST /api/v1/tools/rejection-analysis` |
| `tools reference-request --file REQUEST.json` | `POST /api/v1/tools/reference-request` |
| `tools job-comparison --file REQUEST.json` | `POST /api/v1/tools/job-comparison` |

**Ergonomic shortcuts** (optional sugar, same endpoints):

```bash
rolemule tools thank-you \
  --application-id UUID \
  --interviewer "Jane Smith" \
  --highlights "Led migration project"
```

Provide `rolemule tools schema thank-you` — print example JSON request.

### 5.10 `rolemule extension` — Phase 8 (power users)

| Command | API |
|---------|-----|
| `extension autofill map --file FIELDS.json [--url URL]` | `POST /api/v1/extension/autofill/map` |

For testing autofill rules without the browser. Requires **complete profile** (including `work_authorization` for screening fields). Not needed for most AI assistant users.

### 5.11 Admin — Phase 8 (optional, gated)

| Command | API | Requirement |
|---------|-----|-------------|
| `admin maintenance show` | `GET /api/v1/admin/maintenance` | `is_admin` |
| `admin maintenance on\|off` | `POST/DELETE .../maintenance` | admin |
| `admin metrics` | `GET /api/v1/admin/metrics` | admin |
| `admin cache-stats` | `GET /api/v1/cache/stats` | admin (monitoring) |

**Not in CLI:** `POST /api/v1/admin/internal/cleanup/orphaned-sessions` — requires `X-Scheduler-Secret`; Cloud Scheduler only.

Hidden behind `rolemule admin` — not in top-level help unless `ROLEMULE_ADMIN=1`.

### 5.12 Explicitly out of scope

| Surface | Reason |
|---------|--------|
| `POST /api/v1/workflow/internal/workflow/execute` | Cloud Tasks only (`X-CloudTasks-Secret`) |
| `POST /api/v1/admin/internal/cleanup/orphaned-sessions` | Cloud Scheduler only (`X-Scheduler-Secret`) |
| WebSocket live stream | CLI uses polling (`--wait`); optional `--watch` later |
| `GET /api/v1/ws/stats` | Optional debug (`auth whoami` + any user); low priority |
| HTML page routes (`/dashboard`, etc.) | Browser only; CLI prints URLs |
| Cookie consent / PostHog | Browser only |

---

## 6. Output formats

### 6.1 JSON mode (`--format json`)

- Single JSON object on stdout for success (API response body as-is)
- Errors: mirror server `ErrorResponse` schema exactly:

```json
{
  "success": false,
  "error_code": "CFG_6001",
  "message": "Human-readable message",
  "details": [{"field": "application_id", "message": "uuid", "code": "DUPLICATE_APPLICATION"}],
  "request_id": "abc123",
  "timestamp": "2026-07-08T16:00:00Z"
}
```

- CLI may wrap this with exit code; do **not** invent a parallel `{ "error": true }` shape
- Stable success keys documented in `docs/cli-reference.md` (Phase 9)

### 6.2 Human mode (default)

| Data type | Renderer |
|-----------|----------|
| Lists | Rich table |
| Long text (cover letter, CV) | Pager (`--no-pager` to disable) |
| Progress | Spinner + step label during `--wait` |
| Errors | Red stderr, non-zero exit |

### 6.3 Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success (includes `RES_3002` warning if `--treat-duplicate-as-success`, default on) |
| `1` | General error / API failure |
| `2` | Auth required or profile incomplete |
| `3` | Rate limited (`RATE_4001`) |
| `4` | Config error (no base URL, bad credentials file) |

---

## 7. Phased implementation

Each phase follows the same **delivery loop:**

```
Implement → Unit/CLI tests → Code review checklist → Sign-off → Next phase
```

**Estimated total:** Phases 0–9 (10 phases: foundation + 8 feature groups + polish) (~4–6 weeks part-time).

---

### Phase 0 — Foundation (scaffolding + HTTP client)

**Goal:** Empty CLI runs, talks to server, handles errors.

**Deliverables:**
- [ ] `pyproject.toml` with `rolemule` entry point
- [ ] `cli/main.py` Typer root + global options
- [ ] `cli/config.py` — load/save TOML + credentials
- [ ] `rolemule_client/client.py` — sync `httpx.Client`, Bearer auth, timeout 30s
- [ ] `rolemule_client/errors.py` — parse API error JSON, map to `CliError`
- [ ] `cli/commands/doctor.py`
- [ ] `Makefile` target: `make cli-test`

**Tests (`tests/test_cli/`):**

| Test file | Cases |
|-----------|-------|
| `test_config.py` | Missing config creates defaults; credentials `0600`; base URL override |
| `test_client.py` | Auth header injection; 401/404/422 parsing; connection refused message |
| `test_doctor.py` | Mock health OK/fail; mock verify token valid/expired |

```bash
pytest tests/test_cli/test_config.py tests/test_cli/test_client.py tests/test_cli/test_doctor.py -v
```

**Code review checklist:**
- [ ] No imports from `agents/`, `workflows/`, `models/`
- [ ] Secrets never logged (grep for `access_token`, `password`, `api_key`)
- [ ] Uses `%s` + sanitize pattern if any server-side code touched (unlikely this phase)
- [ ] httpx calls have explicit timeout
- [ ] File permissions on credentials write

**Exit criteria:** `rolemule doctor` works against local `make start-local`.

---

### Phase 1 — Authentication

**Goal:** Login, logout, token management.

**Deliverables:**
- [ ] `rolemule_client/resources/auth.py`
- [ ] `cli/commands/auth.py` — login, logout, whoami, refresh, register, verify-code, change-password, resend-verification, verification-status, extension-status, token set/show
- [ ] Password prompt via `getpass` (never argv)
- [ ] `auth token set --from-stdin` for OAuth users
- [ ] Auto-refresh: on 401, call `POST /auth/refresh` with current JWT, retry request once, save new token
- [ ] **Register flow:** save credentials only after `verify-code` succeeds — never persist register response token

**Tests:**

| Test file | Cases |
|-----------|-------|
| `test_auth_commands.py` | login success saves credentials; register does **not** save token; verify-code saves token; wrong password exit 1; logout clears token; whoami without token exit 2; token set/read masked |
| `test_auth_client.py` | Mock httpx: login, refresh, verify paths |

**Code review checklist:**
- [ ] Password never in shell history (no CLI arg)
- [ ] JWT never printed in full (only `auth token show` masked)
- [ ] Logout calls server before deleting local token
- [ ] Google OAuth documented in command help, not half-implemented

**Exit criteria:** `rolemule auth login && rolemule auth whoami` succeeds against dev server.

---

### Phase 2 — Profile and settings

**Goal:** Full profile CRUD, resume, API key, workflow preferences.

**Deliverables:**
- [ ] `rolemule_client/resources/profile.py`
- [ ] `cli/commands/profile.py`
- [ ] JSON file helpers for work-experience / education arrays
- [ ] Multipart upload for resume
- [ ] Destructive commands require `--confirm`; map to API bodies (`clear-data` → `{"confirm": true}`; `delete-account` → password via getpass)

**Tests:**

| Test file | Cases |
|-----------|-------|
| `test_profile_commands.py` | show/status; set basic-info from flags; upload resume mock multipart; api-key set; clear-data without confirm fails; delete-account prompts password |
| `test_profile_client.py` | Each resource method with mocked responses |

**Code review checklist:**
- [ ] `--confirm` on delete-account, clear-data
- [ ] BYOK key read via getpass, never echoed
- [ ] `CFG_6001` not applicable here but api-key status message is clear
- [ ] JSON `--file -` reads stdin safely

**Exit criteria:** User with complete profile can view and update basic info from CLI alone.

---

### Phase 3 — Workflow (core value)

**Goal:** Analyze jobs end-to-end from terminal — the main Claude Code workflow.

**Deliverables:**
- [ ] `rolemule_client/resources/workflow.py`
- [ ] `rolemule_client/polling.py` — `wait_for_terminal_status()`
- [ ] `cli/commands/workflow.py`
- [ ] `workflow analyze` from stdin, `.txt`, `.pdf`, `.docx`
- [ ] `--wait` progress UI
- [ ] Human formatters for fit score, cover letter, resume tips
- [ ] `RES_3002` + `CFG_6001` handling

**Tests:**

| Test file | Cases |
|-----------|-------|
| `test_workflow_commands.py` | analyze from file; --wait polls until completed; duplicate 409 returns app id; no API key 422 message; continue gate |
| `test_polling.py` | Timeout; failed workflow; `awaiting_confirmation` and `analysis_complete` stop `--wait`; user runs `continue` / `generate-documents` separately |
| `test_workflow_formatters.py` | Markdown sections render expected headings |

**Code review checklist:**
- [ ] Multipart matches extension: magic bytes delegated to server
- [ ] `job_url` only sent if http(s)
- [ ] Polling interval from config
- [ ] No busy-loop without sleep
- [ ] Large job text from stdin works (pipe-friendly)

**Exit criteria:**

```bash
cat job.txt | rolemule workflow analyze --wait --format json
```

returns full results JSON on a complete profile with API key configured.

---

### Phase 4 — Applications (dashboard parity)

**Goal:** List, filter, update, delete, download applications.

**Deliverables:**
- [ ] `rolemule_client/resources/applications.py`
- [ ] `cli/commands/applications.py`
- [ ] Table output for `apps list`
- [ ] Binary download for `apps download`

**Tests:**

| Test file | Cases |
|-----------|-------|
| `test_apps_commands.py` | list with filters; stats; patch status; delete needs confirm; download writes file |
| `test_apps_client.py` | Query string building for pagination/filters |

**Code review checklist:**
- [ ] Filter param names match API (`status_filter`, not `status` if that's what API expects)
- [ ] Download uses streaming for large files
- [ ] Soft-deleted apps not shown (server handles; CLI documents)

**Exit criteria:** `rolemule apps list --search python` matches dashboard search.

---

### Phase 5 — Interview prep

**Goal:** Generate and display interview prep from CLI.

**Deliverables:**
- [ ] `rolemule_client/resources/interview_prep.py`
- [ ] `cli/commands/interview.py`
- [ ] `--wait` on generate (poll status endpoint)

**Tests:**

| Test file | Cases |
|-----------|-------|
| `test_interview_commands.py` | generate --wait; show formats questions array; 404 session |
| `test_interview_client.py` | Mock generate 202 → status running → complete |

**Code review checklist:**
- [ ] Arrays handled when LLM returns lists (no `.map is not a function` equivalent in Python)
- [ ] Rate limit 429 → exit 3

**Exit criteria:** Generate + show works for a completed workflow session.

---

### Phase 6 — CV optimizer

**Goal:** Start optimization loop, monitor, download CV file.

**Deliverables:**
- [ ] `rolemule_client/resources/cv_optimizer.py`
- [ ] `cli/commands/cv.py`
- [ ] Long `--wait` (up to 10+ min) with iteration progress
- [ ] Download binary with correct extension

**Tests:**

| Test file | Cases |
|-----------|-------|
| `test_cv_commands.py` | start --wait through iterations; download saves .odt/.docx; clear confirm; 409 already running |
| `test_cv_client.py` | Status polling; partial result on quota |

**Code review checklist:**
- [ ] Session must be `completed` — friendly error if not
- [ ] Download rate limit surfaced clearly
- [ ] Partial/quota result shows notice in human mode

**Exit criteria:** `rolemule cv start SESSION --wait && rolemule cv download SESSION -o cv.odt`

---

### Phase 7 — Career tools (6 tools)

**Goal:** All standalone tools invocable with JSON or flags.

**Deliverables:**
- [ ] `rolemule_client/resources/tools.py`
- [ ] `cli/commands/tools.py`
- [ ] `tools schema <tool>` example JSON generator
- [ ] Flag-based shortcuts for common fields

**Tests:**

| Test file | Cases |
|-----------|-------|
| `test_tools_commands.py` | Each tool POST with minimal valid payload; followup-stages GET; 429 handling |
| `test_tools_client.py` | Request body serialization |

Reuse patterns from `tests/test_api/test_career_tools.py` for fixture payloads.

**Code review checklist:**
- [ ] Request JSON validated locally where API validates (required fields)
- [ ] Output subject/body split for email tools in human mode
- [ ] No bracket placeholders in output (server responsibility; CLI doesn't corrupt)

**Exit criteria:** All six tools runnable from CLI with `--format json`.

---

### Phase 8 — Extension autofill + admin (optional power features)

**Goal:** Remaining API surfaces for 100% coverage.

**Deliverables:**
- [ ] `cli/commands/extension.py`
- [ ] `cli/commands/admin.py` (env-gated)
- [ ] Document autofill as advanced/testing command

**Tests:**

| Test file | Cases |
|-----------|-------|
| `test_extension_commands.py` | autofill map with sample fields JSON |
| `test_admin_commands.py` | non-admin gets 403; admin maintenance toggle mocked |

**Code review checklist:**
- [ ] Admin commands hidden from default `--help`
- [ ] Autofill docs say "for extension testing"

**Exit criteria:** `rolemule extension autofill map --file fields.json` returns assignments JSON.

---

### Phase 9 — Polish, packaging, documentation

**Goal:** Ship-ready CLI for contributors and Claude Code users.

**Deliverables:**
- [x] `docs/cli-reference.md` — full command reference
- [x] `USER_GUIDE.md` — new "CLI" section
- [x] `README.md` — Quick Start CLI block
- [x] Shell completion: `rolemule --install-completion`
- [x] CI job: `pytest tests/test_cli/ -v`
- [x] `CHANGELOG.md` entry
- [x] `.cursor/rules/cli.mdc` — conventions for future CLI changes
- [x] Expanded test suite: 364 mocked CLI tests + 6 ASGI integration tests (`tests/test_cli_integration/`)

**Tests:**

| Test file | Cases |
|-----------|-------|
| `test_smoke.py` | CliRunner `--help` for every command group (no import errors) |
| `test_completion.py` | Completion script generates |

Optional live smoke (manual / nightly):

```bash
# Requires running server + test user
./scripts/cli_smoke.sh
```

**Code review checklist (final):**
- [x] Full command tree matches Section 5
- [x] All test_cli files pass in CI
- [x] No duplicate HTTP logic between commands (everything through client)
- [x] Security review: credentials, confirm flags, no shell injection in `--file` paths

**Exit criteria:** New user can follow README CLI section end-to-end.

---

## 8. Testing strategy (cross-cutting)

### 8.1 Test pyramid for CLI

```
        ┌─────────────────┐
        │  Smoke (manual) │  optional live server
        ├─────────────────┤
        │  CLI (CliRunner)│  mock client or respx
        ├─────────────────┤
        │  Client unit    │  httpx.MockTransport
        └─────────────────┘
```

### 8.2 Conventions

- All CLI tests in `tests/test_cli/` — never mix with `tests/test_api/`
- Use `typer.testing.CliRunner` with `mix_stderr=False`
- Mock HTTP via `httpx.MockTransport` — **no live server in CI**
- Fixture payloads: copy shapes from existing `tests/test_api/` mocks
- Name pattern: `test_<command>_<scenario>`

### 8.3 Shared fixtures (`tests/test_cli/conftest.py`)

```python
@pytest.fixture
def cli_runner():
    return CliRunner()

@pytest.fixture
def mock_config(tmp_path, monkeypatch):
    # Redirect ~/.rolemule to tmp_path
    ...

@pytest.fixture
def authed_client_transport():
    # httpx.MockTransport with canned API responses
    ...
```

### 8.4 Coverage target

- `rolemule_client/`: **≥ 90%** line coverage
- `cli/commands/`: every command at least one happy-path + one error-path test
- No coverage requirement on formatters if tested via snapshot strings

---

## 9. Code review process (every phase)

### 9.1 Reviewers

- **Author** implements phase
- **Reviewer** (self or teammate) runs checklist before merge
- Optional: run `@bugbot` on CLI diff before sign-off

### 9.2 Standard checklist (all phases)

- [ ] Scope limited to phase deliverables — no drive-by refactors
- [ ] `pytest tests/test_cli/ -v` passes
- [ ] No new bare `HTTPException` in any touched server code (CLI shouldn't touch server)
- [ ] `--format json` output is valid JSON on stdout (stderr separate)
- [ ] Help text exists for every command (`rolemule <cmd> --help`)
- [ ] Destructive ops need `--confirm`
- [ ] Claude Code example in PR description (one copy-paste command)

### 9.3 Security checklist (Phases 1–2 especially)

- [ ] Credentials file mode `0600`
- [ ] No tokens in exception messages
- [ ] `--file` paths read-only, not executed
- [ ] Login password via getpass only

### 9.4 Sign-off template (PR description)

```markdown
## Phase N — [Name]

### Deliverables
- [x] ...

### Tests
- [x] `pytest tests/test_cli/test_....py -v` (N passed)

### Code review
- [x] Section 9.2 checklist
- [x] Section 9.3 if applicable

### Demo
\`\`\`bash
rolemule ...
\`\`\`
```

---

## 10. CI integration

Add to `.github/workflows/` (or existing test workflow):

```yaml
- name: CLI tests
  run: pytest tests/test_cli/ -v --override-ini="addopts="
```

Phase 9 adds:

```yaml
- name: Install CLI editable
  run: pip install -e ".[cli]"
- name: CLI help smoke
  run: rolemule --help && rolemule workflow --help
```

---

## 11. AI assistant usage examples (Claude Code, Cursor, Codex, Gemini CLI, …)

Any agent with shell access can run the CLI. Document these in `docs/cli-reference.md`:

```bash
# Analyze a job file and get JSON for the agent to read
rolemule workflow analyze jobs/acme.txt --wait --format json

# List applications needing follow-up (--status is CLI flag → API status_filter)
rolemule apps list --status applied --format json

# Generate interview prep and save to file
rolemule interview generate SESSION --wait --format json > prep.json

# Salary negotiation script
rolemule tools salary-coach --file offer.json --format json

# Check setup before a session
rolemule doctor && rolemule profile status
```

**`CLAUDE.md` / project rules snippet** (Phase 9):

```markdown
## RoleMule CLI
- Server must be running (`make start-local`)
- Login once: `rolemule auth login` (or `auth token set` for Google OAuth users)
- Prefer `--format json` when parsing output in an AI session
- Job analysis: `rolemule workflow analyze FILE --wait --format json`
- Works from any AI tool that can run terminal commands — not Claude-specific
```

---

## 12. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| OAuth users can't login via CLI | `auth token set` for JWT paste; **`auth token create`** for long-lived PAT |
| Long workflows timeout | Configurable `poll_timeout_seconds`; `--no-wait` + manual status |
| Output too large for terminal | `--section` filters; `--format json` to file |
| API changes break CLI | Client resource layer isolates paths; contract tests from OpenAPI |
| Feature creep | Strict phase gates; admin/autofill last |
| Duplicate maintenance (extension + CLI) | Shared API client patterns documented; extension stays separate |

---

## 13. Future enhancements (post v1)

**Implemented (2026-07-08):**

- ✅ Personal access tokens — `POST/GET/DELETE /api/v1/auth/tokens`; CLI `auth token create|list|revoke`
- ✅ `rolemule apps show APP_ID` — `GET /api/v1/applications/{id}`
- ✅ `workflow results --out` / `--out-dir` — write cover letter, resume tips, etc. to files
- ✅ `rolemule workflow watch SESSION` — WebSocket streaming progress (`websocket-client` extra)
- ✅ Pager for long human output — `--no-pager` global flag; `$PAGER` / `$ROLEMULE_PAGER`
- ✅ `config` / `config set` — view and patch `~/.rolemule/config.toml`
- ✅ `--confirm` on `profile resume delete` and `profile api-key delete`
- ✅ `auth token create --save` — write PAT to `credentials.json` for scripts

**Nice-to-have (not blocking merge):**

| Item | Effort | Status |
|------|--------|--------|
| `auth oauth status` (`GET /auth/oauth/status`) | ~1 h | ✅ `auth oauth-status` |
| `doctor` PAT awareness | ~2 h | ✅ token type, expiry hint, refresh guidance |
| `workflow watch` human mode | ~3 h | ✅ human lines; `--format json` for raw events |
| Shell alias recipes in docs | ~1 h | ✅ `cli-reference.md` § Shell aliases |
| MCP server over `rolemule_client` | ~2–3 days | Open — optional; CLI + shell is enough for self-hosted |
| pipx / Homebrew publish | ~1 day | **Not planned** — self-hosted users get CLI via `make setup` |

**Deploy note:** run `make migrate` (revision `20260708_024`) on any environment before using PAT endpoints.

### Why MCP? (optional, not required)

The CLI already works from any terminal (Cursor, Claude Code, scripts). **MCP** (Model Context Protocol) would wrap `rolemule_client` as a structured tool server so AI apps could call “analyze job” / “list applications” without shelling out. Useful for tighter IDE integration; **not** needed for correctness or parity.

### What is pipx / Homebrew publish?

- **pipx** — installs Python CLI tools in isolated global venvs (`pipx install rolemule` → `rolemule` on PATH without cloning the repo).
- **Homebrew** — macOS/Linux package manager (`brew install rolemule` from a tap). Same goal: one-command install for end users who are not developers.

---

## 14. Phase summary table

| Phase | Name | Key commands | Tests dir | Depends on |
|-------|------|--------------|-----------|------------|
| 0 | Foundation | `doctor` | `test_config`, `test_client`, `test_doctor` | — |
| 1 | Auth | `auth *` | `test_auth_*` | 0 |
| 2 | Profile | `profile *` | `test_profile_*` | 1 |
| 3 | Workflow | `workflow *` | `test_workflow_*`, `test_polling` | 2 |
| 4 | Applications | `apps *` | `test_apps_*` | 1 |
| 5 | Interview | `interview *` | `test_interview_*` | 3 |
| 6 | CV optimizer | `cv *` | `test_cv_*` | 3 |
| 7 | Career tools | `tools *` | `test_tools_*` | 1 |
| 8 | Extension + admin | `extension *`, `admin *` | `test_extension_*`, `test_admin_*` | 1 |
| 9 | Polish | docs, CI, completion | `test_smoke` | all |

Phases 4–7 can be parallelized after Phase 3 if multiple contributors.

---

## 15. Getting started (Phase 0 kickoff)

```bash
# 1. Add pyproject.toml + cli/ skeleton
# 2. pip install -e ".[cli]"   # or editable install
# 3. rolemule doctor
# 4. Open PR: "Phase 0: CLI foundation"
```

**First PR scope:** ≤ 800 lines. No commands beyond `doctor` and `--version`.

---

## 16. API coverage checklist (full parity audit)

Use this table during Phase 9 sign-off. ✅ = CLI command planned above.

### User-facing API (`/api/v1`)

| Endpoint | CLI coverage |
|----------|--------------|
| **Auth** | |
| `POST /auth/register` | ✅ `auth register` |
| `POST /auth/login` | ✅ |
| `POST /auth/logout` | ✅ |
| `POST /auth/refresh` | ✅ |
| `GET /auth/verify` | ✅ `auth whoami` / `doctor` |
| `GET /auth/extension-status` | ✅ |
| `POST /auth/verify-code` | ✅ |
| `POST /auth/resend-verification` | ✅ |
| `GET /auth/verification-status` | ✅ |
| `GET /auth/email-status` | ✅ |
| `PUT /auth/change-password` | ✅ |
| `POST /auth/tokens` | ✅ `auth token create` |
| `GET /auth/tokens` | ✅ `auth token list` |
| `DELETE /auth/tokens/{id}` | ✅ `auth token revoke` |
| `POST /auth/forgot-password` | ❌ browser (intentional) |
| `POST /auth/reset-password` | ❌ browser (intentional) |
| `GET /auth/oauth/status` | ✅ `auth oauth-status` |
| `GET /auth/verify-email` | ❌ browser token link (intentional) |
| `POST /auth/oauth/exchange-code` | ❌ browser OAuth step 3 (intentional) |
| Google OAuth + link/unlink | ❌ token import workaround |
| **Profile** | |
| All profile routes (21 endpoints) | ✅ Section 5.4 |
| **Workflow** | |
| All 9 public workflow routes | ✅ Section 5.5 |
| **Applications** | |
| All 7 application routes | ✅ Section 5.6 + `apps show` (`GET /{id}`) |
| **Interview prep** | |
| All 4 routes | ✅ Section 5.7 |
| **CV optimizer** | |
| All 5 routes | ✅ Section 5.8 |
| **Career tools** | |
| All 7 routes | ✅ Section 5.9 |
| **Extension** | |
| `POST /extension/autofill/map` | ✅ Phase 8 |
| **Admin** | |
| Maintenance + metrics + cache stats | ✅ Phase 8 |
| Internal cleanup | ❌ scheduler secret (intentional) |
| **Monitoring** | |
| `GET /health` | ✅ `doctor` |
| **WebSocket** | |
| `/ws/workflow/*` | ✅ `workflow watch` (optional; polling still default) |
| `/ws/user` | ❌ polling instead (intentional) |
| `GET /ws/stats` | ❌ optional debug (any authed user; low priority) |
| **HTML pages** | |
| `/dashboard`, `/profile/setup`, etc. | ❌ CLI prints URLs only |

### Coverage score

- **User API endpoints:** ~95% (all except intentional browser/OAuth/internal/scheduler paths)
- **Platform capabilities:** 100% for programmatic use cases

---

## 17. Final audit log (2026-07-08)

Issues found in prior draft and corrected in this version:

| Issue | Fix |
|-------|-----|
| Wrong workflow stop label `gate_pending` | → `awaiting_confirmation` + full status table |
| Error JSON shape invented by CLI doc | → matches `ErrorResponse` in `utils/error_responses.py` |
| `RES_3002` ids as top-level field | → parse `details[]` with `field: application_id \| session_id` |
| Profile gate missing extension autofill | → added; requires complete profile |
| Application status example `interviewing` | → `interview` (per `ApplicationStatus` enum) |
| Resume upload size unspecified | → 10 MB (profile) vs 5 MB (workflow job file) |
| `delete-account` only had `--confirm` | → password via getpass; `""` for Google-only |
| `clear-data` only had `--confirm` | → API requires JSON `{"confirm": true}` |
| Typer entry point `cli.main:app` | → `cli.main:main` |
| CLI deps in server `requirements.in` | → optional `[cli]` + `httpx` in pyproject |
| CI `pip install -e .` | → `pip install -e ".[cli]"` |
| Internal workflow path abbreviated | → full path + secret header names |
| Missing auth exclusions | → `verify-email`, `oauth/exchange-code` |
| Interview `--regenerate` not documented | → added |
| CV optimizer param ranges | → 2–7 iterations, 7.0–9.5 threshold |

**Endpoint counts verified:** auth 23 routes (15 CLI / 8 excluded), profile 21, workflow 9 public + 1 internal, applications 7, interview 4, cv 5, tools 7, extension 1, admin 4 + 1 internal, cache stats 1 (admin).

---

*End of plan.*
