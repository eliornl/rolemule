# ApplyPilot CLI Reference

Command-line client for a running ApplyPilot server. Full API parity for auth, profile, workflows, applications, interview prep, CV optimization, career tools, extension autofill testing, and admin monitoring.

**Implementation plan:** [cli-implementation-plan.md](./cli-implementation-plan.md)

**Status:** Merged / complete — 96 leaf commands, **364** mocked CLI tests + **6** ASGI integration tests.

---

## Install

From the repo root, the CLI is installed automatically when you run **`make setup`**, **`make start-local`**, or **`just setup`** (same venv as the server).

```bash
make setup          # or make start-local on macOS
source venv/bin/activate
applypilot doctor
```

Without activating the venv: `venv/bin/applypilot` (Windows: `venv\Scripts\applypilot.exe`).

**Docker only (`make start`):** run `make setup` once on the host if you want the CLI locally — the container image does not install a host-side `applypilot` command.

Manual reinstall (optional): `pip install -e ".[cli]"` inside the project venv.

Entry point: `applypilot` → `cli.main:main`

---

## Configuration

| Path | Purpose |
|------|---------|
| `~/.applypilot/config.toml` | `base_url`, poll intervals, output defaults |
| `~/.applypilot/credentials.json` | JWT (`0600` permissions) |

Override server URL per invocation: `applypilot --base-url http://localhost:8000 …`

---

## Global flags

Place **before** the subcommand:

| Flag | Description |
|------|-------------|
| `--base-url URL` | Server origin (default from config) |
| `--format human\|json` | Output format |
| `--no-color` | Disable styled output |
| `-q` / `--quiet` | Minimal output |
| `-v` / `--verbose` | Verbose output |
| `--no-pager` | Disable pager for long human output |

Shell completion (run from an interactive terminal so Typer can detect your shell):

```bash
applypilot --install-completion
applypilot --show-completion
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success (`RES_3002` duplicate job → warning, still exit 0) |
| `1` | General API / validation error |
| `2` | Auth required or profile incomplete |
| `3` | Rate limited (`RATE_4001`) |
| `4` | Config error |

---

## `version`

| Command | Description |
|---------|-------------|
| `version` | Print package version (`0.0.0` until release tagging) |

---

## `doctor`

| Command | API / action |
|---------|--------------|
| `doctor` | `GET /health`, token check (JWT vs PAT), local config paths |

```bash
applypilot doctor
applypilot doctor --format json
```

---

## `config`

| Command | Action |
|---------|--------|
| `config` | Show `~/.applypilot/config.toml` (default when no subcommand) |
| `config set` | Patch config (`--base-url`, `--format`, `--poll-interval`, `--poll-timeout`, `--color` / `--no-color`) |

```bash
applypilot config
applypilot config set --base-url https://apply.example.com --format json
```

---

## `auth`

| Command | API |
|---------|-----|
| `auth login [--email] [--remember-me]` | `POST /api/v1/auth/login` |
| `auth logout` | `POST /api/v1/auth/logout` + clear local credentials |
| `auth whoami` | `GET /api/v1/auth/verify` |
| `auth refresh` | `POST /api/v1/auth/refresh` |
| `auth register` | `POST /api/v1/auth/register` (does **not** save JWT) |
| `auth verify-code --email EMAIL --code CODE` | `POST /api/v1/auth/verify-code` (saves JWT) |
| `auth change-password` | `PUT /api/v1/auth/change-password` |
| `auth token set [--token TOKEN] [--from-stdin]` | Local only (paste, getpass, or stdin) |
| `auth token show` | Local only (masked JWT) |
| `auth token create --name LABEL [--expires-days N] [--save]` | `POST /api/v1/auth/tokens` (PAT shown once; `--save` writes to credentials) |
| `auth token list` | `GET /api/v1/auth/tokens` (metadata only) |
| `auth token revoke TOKEN_ID` | `DELETE /api/v1/auth/tokens/{id}` |
| `auth email-status` | `GET /api/v1/auth/email-status` |
| `auth oauth-status` | `GET /api/v1/auth/oauth/status` |
| `auth resend-verification` | `POST /api/v1/auth/resend-verification` |
| `auth verification-status` | `GET /api/v1/auth/verification-status` |
| `auth extension-status` | `GET /api/v1/auth/extension-status` |

Google OAuth users: log in via the browser, then `applypilot auth token set`. For automation, prefer **`auth token create`** (personal access token) over pasting a short-lived JWT.

---

## `profile`

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
| `profile resume upload FILE` | `POST /api/v1/profile/parse-resume` (10 MB max) |
| `profile resume show` | `GET /api/v1/profile/resume` |
| `profile resume delete --confirm` | `DELETE /api/v1/profile/resume` |
| `profile api-key status` | `GET /api/v1/profile/api-key/status` |
| `profile api-key set [--provider gemini\|openai\|anthropic]` | `POST /api/v1/profile/api-key` |
| `profile api-key delete --confirm [--provider …]` | `DELETE /api/v1/profile/api-key?provider=` |
| `profile api-key validate [--provider …]` | `POST /api/v1/profile/api-key/validate` |
| `profile workflow-preferences show` | `GET /api/v1/profile/preferences` |
| `profile workflow-preferences set` | `PATCH /api/v1/profile/preferences` |

**Workflow preferences flags:** `--file`, `--gate-threshold`, `--auto-generate-documents` / `--no-auto-generate-documents`, `--cover-letter-tone`, `--resume-length`, `--preferred-model`, `--preferred-provider`
| `profile export [--out FILE]` | `GET /api/v1/profile/export` |
| `profile clear-data --confirm` | `DELETE /api/v1/profile/clear-data` |
| `profile delete-account --confirm` | `DELETE /api/v1/profile/delete-account` |

JSON sections accept `--file path.json` or `--file -` (stdin).

---

## `workflow`

| Command | API |
|---------|-----|
| `workflow analyze -` | `POST /api/v1/workflow/start` (`job_text` from stdin) |
| `workflow analyze job.txt` | same (file contents) |
| `workflow analyze --upload job.pdf` | multipart `job_file` (`.pdf`, `.txt`, `.docx`; 5 MB) |
| `workflow analyze --url URL` | optional posting URL metadata (not fetched) |
| `workflow analyze --source-url URL` | source page URL (extension parity) |
| `workflow analyze --title TITLE` | optional detected job title |
| `workflow analyze --company COMPANY` | optional detected company name |
| `workflow status SESSION` | `GET /api/v1/workflow/status/{id}` |
| `workflow results SESSION` | `GET /api/v1/workflow/results/{id}` |
| `workflow results SESSION --out FILE` | Write one section (or JSON) to a file |
| `workflow results SESSION --out-dir DIR` | Write per-section `.md` files (or `results.json` with `--format json`) |
| `workflow watch SESSION` | WebSocket `/api/v1/ws/workflow/{id}` (live progress; human lines by default, `--format json` for raw events) |
| `workflow history` | `GET /api/v1/workflow/history` |
| `workflow continue SESSION --confirm` | `POST /api/v1/workflow/continue/{id}` |
| `workflow generate-documents SESSION` | `POST /api/v1/workflow/generate-documents/{id}` |
| `workflow regenerate cover-letter SESSION` | `POST .../regenerate-cover-letter/{id}` |
| `workflow regenerate resume SESSION` | `POST .../regenerate-resume/{id}` |
| `workflow generate-interview-prep SESSION` | `POST .../generate-interview-prep/{id}` (legacy — prefer `interview generate`) |

**Analyze flags:** `--wait`, `--section cover-letter|resume|fit|company|all`, `--open`

**History filters:** `--page`, `--per-page`, `--status`, `--sort`

**Polling stops at:** `completed`, `failed`, `awaiting_confirmation`, `analysis_complete`

**Errors:** `409 RES_3002` → exit 0 warning; `422 CFG_6001` → add API key hint

```bash
applypilot workflow analyze posting.txt --wait --format json
applypilot workflow results SESSION_ID --section cover-letter --out cover-letter.md
applypilot workflow watch SESSION_ID
```

Long human output uses `$PAGER` / `$APPLYPILOT_PAGER` (disable with `--no-pager`).

---

## `apps`

| Command | API |
|---------|-----|
| `apps list` | `GET /api/v1/applications/` |
| `apps show APP_ID` | `GET /api/v1/applications/{id}` |
| `apps stats` | `GET /api/v1/applications/stats/overview` |
| `apps status APP_ID STATUS` | `PATCH .../status` |
| `apps notes APP_ID [--file\|TEXT]` | `PATCH .../notes` |
| `apps delete APP_ID --confirm` | `DELETE .../{id}` |
| `apps download APP_ID [--out FILE]` | `GET .../download` |

**List filters:** `--search`, `--status` → `status_filter`, `--company`, `--days`, `--sort`, `--page`, `--per-page`

---

## `interview`

| Command | API |
|---------|-----|
| `interview show SESSION` | `GET /api/v1/interview-prep/{id}` |
| `interview status SESSION` | `GET /api/v1/interview-prep/{id}/status` |
| `interview generate SESSION [--wait] [--regenerate]` | `POST .../generate` |
| `interview delete SESSION --confirm` | `DELETE .../{id}` |

---

## `cv`

| Command | API |
|---------|-----|
| `cv start SESSION [--max-iter N] [--threshold SCORE] [--wait]` | `POST /api/v1/cv-optimizer/{id}/start` |
| `cv show SESSION` | `GET /api/v1/cv-optimizer/{id}` |
| `cv status SESSION` | `GET /api/v1/cv-optimizer/{id}/status` |
| `cv download SESSION [--out FILE]` | `GET .../download-cv` |
| `cv clear SESSION --confirm` | `DELETE .../{id}` |

`--max-iter` 2–7 (default 5). `--threshold` 7.0–9.5 (default 8.5).

---

## `tools`

| Command | API |
|---------|-----|
| `tools followup-stages` | `GET /api/v1/tools/followup-stages` |
| `tools followup` | `POST /api/v1/tools/followup` |
| `tools thank-you` | `POST /api/v1/tools/thank-you` |
| `tools salary-coach` | `POST /api/v1/tools/salary-coach` |
| `tools rejection-analysis` | `POST /api/v1/tools/rejection-analysis` |
| `tools reference-request` | `POST /api/v1/tools/reference-request` |
| `tools job-comparison` | `POST /api/v1/tools/job-comparison` |
| `tools schema TOOL` | Print example JSON (no API call) |

Most tools accept `--file REQUEST.json` or flag shortcuts. Example:

```bash
applypilot tools schema thank-you
applypilot tools thank-you --interviewer "Jane" --interview-type video \
  --company Acme --title "Engineer" --highlights "Led migration"
applypilot tools salary-coach --file offer.json --format json
```

---

## `extension` (advanced)

For extension development / autofill testing without the browser.

| Command | API |
|---------|-----|
| `extension autofill map --file FIELDS.json [--url URL]` | `POST /api/v1/extension/autofill/map` |

Requires complete profile. JSON must include `page_url` (http(s)) and `fields` array.

---

## `admin` (power users)

Hidden from `applypilot --help` unless `APPLYPILOT_ADMIN=1` is set **before** launching the CLI. Commands still work without the env var.

| Command | API |
|---------|-----|
| `admin maintenance show` | `GET /api/v1/admin/maintenance` |
| `admin maintenance on --confirm` | `POST /api/v1/admin/maintenance` |
| `admin maintenance off --confirm` | `DELETE /api/v1/admin/maintenance` |
| `admin metrics` | `GET /api/v1/admin/metrics` |
| `admin cache-stats` | `GET /api/v1/cache/stats` |

Requires `is_admin` on your account.

---

## AI assistant usage

Prefer `--format json` when an agent parses output:

```bash
applypilot doctor && applypilot profile status
applypilot workflow analyze jobs/acme.txt --wait --format json
applypilot apps list --status applied --format json
applypilot interview generate SESSION --wait --format json > prep.json
applypilot tools salary-coach --file offer.json --format json
```

**Rules for agents:**

- Server must be running (`make start-local` or Docker)
- Login once: `applypilot auth login` or `auth token set`
- Global flags go **before** subcommands
- Destructive commands need `--confirm` (account/data/application/resume/api-key deletes, maintenance toggles, etc.)
- `422 CFG_6001` → configure AI (`profile api-key set --provider …`, `preferred_provider=ollama`, or Vertex)

---

## Shell aliases (optional)

Copy into `~/.bashrc` or `~/.zshrc` for shorter commands. Adjust paths to your ApplyPilot install.

```bash
# Server + auth
alias ap='applypilot'
alias apdoc='applypilot doctor'
alias aplogin='applypilot auth login'
alias aptoken='applypilot auth token create --save --name'

# Analyze and watch
alias apanalyze='applypilot workflow analyze --wait'
alias apwatch='applypilot workflow watch'

# Applications
alias aplist='applypilot apps list'
alias apshow='applypilot apps show'

# Export cover letter after a completed workflow
apcover() {
  applypilot workflow results "$1" --section cover-letter --out "${2:-cover-letter.md}"
}

# JSON-friendly scripting
alias apjson='applypilot --format json --no-pager'
```

Example session:

```bash
aplogin
aptoken "my-laptop"
apanalyze ~/jobs/acme-backend.txt
apwatch SESSION_ID_FROM_OUTPUT
apcover SESSION_ID_FROM_OUTPUT ~/cover-letters/acme.md
```

---

## Testing

```bash
make cli-test                              # pytest tests/test_cli/ (364 tests)
pytest tests/test_cli_integration/ -v      # ASGI integration (6 tests; needs Postgres)
./scripts/cli_smoke.sh                     # optional live server smoke
```

CI: `cli-tests` job runs mocked suite; `python-tests` job also runs `tests/test_cli_integration/`.
