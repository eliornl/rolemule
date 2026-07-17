# RoleMule Rebrand Plan — RoleMule → RoleMule

**Status:** In progress (in-repo rebrand); GitHub rename deferred pending approval  
**Owner:** Product / Engineering  
**Last updated:** 2026-07-16 (implementation started — pass 4)  

**Brand lock**

| Item | Value |
|------|--------|
| Product name | **RoleMule** |
| Wordmark split | `Role` + `Mule` → `Role<span class="brand-accent">Mule</span>` |
| Tagline | **One mule for every role.** |
| Icon | **Locked** — line-profile mule carrying a document pack (cyan eye). Source: `docs/rolemule-icon.png` |
| GitHub repo | Rename `eliornl/rolemule` → `eliornl/rolemule` (core goal) |
| CLI command | `rolemule` (CLI is new — rename in this rebrand) |
| PAT prefix | `rm_pat_` (was `rm_pat_`) |
| localStorage / WS | `rolemule_*` / `rolemule:ws` |

This document is the **complete** execution checklist.

**Inventory basis (audit pass 2):** Source tree brand hits across HTML/TS/PY/MD/MDC/extension/docs/rules. A naïve `rg RoleMule` **misses** split wordmarks `Role<span class="brand-accent">Mule</span>` — listed explicitly below.

---

## Locked product decisions (pass 3)

### We **do** change
- Visible brand → RoleMule + tagline  
- GitHub repo rename  
- CLI binary, client package/class, `~/.rolemule`, `ROLEMULE_*` env  
- localStorage keys + `rolemule:ws`  
- PAT prefix → `rm_pat_`  
- Docs, rules, extension, emails, tests  
- Icon when chosen  

### We **do not** change
- **Postgres DB name / user `rolemule`** (and `DATABASE_URL` host path using that name)  
- Redis functional key patterns (`v1:job_analysis:…`, `jwt_blocklist:`, …)  
- Extension storage `jaa_*` (historical, not the product word)  
- PyPI publish (not in use — ignore)  

### Existing users (verified against code)

| Step | Correct? | Detail |
|------|----------|--------|
| `git pull` after rebrand PR merges | **Yes** | Gets RoleMule UI/code; no re-clone required. Local folder may still be named `rolemule/` (cosmetic). |
| After GitHub rename: update remote | **Yes (recommended)** | `git remote set-url origin git@github.com:eliornl/rolemule.git`. GitHub redirects often keep old remotes working for a while; set-url is the reliable step. |
| Restart app (+ rebuild frontend if needed) | **Yes** | See RoleMule in the browser. |
| CLI: use new command | **Yes** | After pull, reinstall entry point (`pip install -e .` or project setup). Command becomes `rolemule …`. Old `rolemule` command gone unless you add a temporary alias. |
| Old PATs | **Yes** | `utils/personal_access_tokens.py` rejects tokens that don’t start with `PAT_PREFIX`. Changing to `rm_pat_` invalidates old tokens → create a new token once. |
| Database | **Unchanged** | Same `DATABASE_URL`; no dump/restore. |
| Extension | Reload / republish | New manifest name. |

---

## 0. Agent / engineer instructions (read first)

### 0.1 Goal

Rebrand RoleMule → RoleMule in the product **and** on GitHub, including CLI/client/PAT/localStorage renames (CLI is new). **Keep** the Postgres database name/user as `rolemule` so existing `.env` files keep working.

### 0.2 Non-negotiables

1. **Do not rename** Postgres DB/user `rolemule` or force `DATABASE_URL` migrations for self-hosters.
2. **Do** rename display brand, GitHub repo, CLI, client package, PAT prefix, localStorage, WS event (per locked decisions above).
3. **Never raise bare `HTTPException`** — rebrand does not touch error system.
4. **Navbar rule** → Role + Mule; icon may leave `fa-rocket` until Phase D.
5. **Legal / help** stay accurate (self-hosted, no job-board name drops).
6. After bulk replace, **`ast.parse()`** Python + e2e brand asserts.
7. **Do not rewrite CHANGELOG history** — add a dated rebrand entry.
8. **Grep trap:** also search `brand-accent">Pilot` and `Apply<span`. Split-only: `navbar_dashboard.html`, `navbar_subpage.html`, `navbar_public.html`.
9. **Tracing:** either hardcode `service_name="rolemule"` deliberately or keep `"rolemule"` for ops — pick one; do not accidentally diverge logging vs tracing.
10. **Do not hand-edit** `sandbox-just-test/`, egg-info, `ui/static/dist/`, coverage, `.ruff_cache/`.
11. **`_private/`** — Phase K if that tree ships.

### 0.3 Existing clients after rebrand (canonical)

```text
1. git remote set-url origin git@github.com:eliornl/rolemule.git   # after GitHub rename
2. git pull
3. Restart the server (make/just as usual; rebuild frontend if JS brand strings changed)
4. Optional: reload Chrome extension
5. CLI users: pip install -e .   # or make setup — then use `rolemule` not `rolemule`
6. If you had a PAT: create a new token (old rm_pat_ tokens stop working)
```

DB / `.env` `DATABASE_URL` with user/db `rolemule` — **no change**.

### 0.4 Rules to read before coding

| Area | File |
|------|------|
| Core | `.cursor/rules/rolemule-core.mdc` |
| Settings / env | `.cursor/rules/settings-and-env.mdc` |
| Landing | `.cursor/rules/landing-page.mdc` |
| Extension | `.cursor/rules/chrome-extension.mdc` |
| Dashboard / detail | `.cursor/rules/dashboard-home.mdc`, `ui-application-detail.mdc` |
| Frontend | `.cursor/rules/frontend-js-strict.mdc`, `frontend-build-pipeline.mdc` |
| E2E | `.cursor/rules/e2e-testing.mdc` |
| CLI | `.cursor/rules/cli.mdc` |
| Indexes | `CLAUDE.md`, `.cursorrules` |

---

## 1. Compatibility matrix (decide once, never mix)

### 1.1 CHANGE in this rebrand

| Item | From | To |
|------|------|-----|
| Product name | RoleMule | RoleMule |
| Wordmark | `Apply` + `Pilot` | `Role` + `Mule` |
| Tagline | Co-Pilot / companion variants | **One mule for every role.** |
| `settings.app_name` / description / `smtp_from_name` | RoleMule / Co-Pilot | RoleMule / new description |
| Emails, extension, docs, rules, e2e brand asserts | RoleMule | RoleMule |
| GitHub repo | `eliornl/rolemule` | `eliornl/rolemule` |
| CLI entry / Typer name | `rolemule` | `rolemule` |
| Package dir / imports | `rolemule_client` | `rolemule_client` |
| Client class | `RoleMuleClient` | `RoleMuleClient` |
| `pyproject.toml` package `name` | `rolemule` | `rolemule` |
| Config dir / env | `~/.rolemule`, `ROLEMULE_*` | `~/.rolemule`, `ROLEMULE_*` |
| PAT prefix | `rm_pat_` | `rm_pat_` |
| localStorage | `rolemule_tracked_sessions`, `rolemule_badge`, `rolemule_notified_analyses` | `rolemule_*` equivalents |
| WS event | `rolemule:ws` | `rolemule:ws` |
| Export filenames | `rolemule-export-*.json` | `rolemule-export-*.json` |
| Logging/tracing service (pick) | `rolemule` | Prefer `rolemule` for consistency |

### 1.2 KEEP unchanged

| Identifier | Why |
|------------|-----|
| Postgres user & DB name `rolemule` | Existing `.env` / Docker / CI — users never see this |
| `DATABASE_URL=...rolemule:rolemule@.../rolemule` | Same |
| Redis functional prefixes | Not product brand |
| Extension `jaa_*` storage | Historical keys; renaming is optional busywork |
| CSS class `.brand-accent` | Structural |
| Local disk folder name `rolemule/` | Cosmetic; optional rename by user |

### 1.3 Out of scope / ignore

- Publishing to PyPI (not used today)  
- Forcing DB rename / dump-restore  
- Dual-read localStorage (not needed — empty new keys are fine)  

---

## 2. Phased execution plan

### Phase A — Config source of truth

**Goal:** One place drives titles / OpenAPI / emails.

| # | Task | Files |
|---|------|-------|
| A1 | Set `app_name = "RoleMule"` | `config/settings.py` |
| A2 | Update `app_description` | `config/settings.py` |
| A3 | Set `smtp_from_name = "RoleMule"` | `config/settings.py` |
| A4 | Update module docstring | `config/settings.py`, `config/__init__.py` |
| A5 | Update `.env.local.example`: `APP_NAME`, `SMTP_FROM_NAME`, header comments; **leave** `DATABASE_URL` user/db as `rolemule` | `.env.local.example` |
| A6 | Update settings rule examples | `.cursor/rules/settings-and-env.mdc`, `.claude/rules/settings-and-env.mdc` |

**Verify:** App starts; `/docs` OpenAPI title shows RoleMule; `settings.app_name` in templates.

---

### Phase B — UI chrome (nav, titles, landing, footers)

**Goal:** Every page shows RoleMule wordmark + tagline where appropriate.

| # | Task | Files |
|---|------|-------|
| B1 | Navbar wordmark → `Role<span class="brand-accent">Mule</span>` | `ui/partials/navbar_landing.html`, `navbar_dashboard.html`, `navbar_subpage.html`, `navbar_public.html` |
| B2 | Landing: “Why RoleMule” → “Why RoleMule”; footer brand + © | `ui/index.html`, `navbar_landing.html` |
| B3 | Landing extension mockup brand text | `ui/index.html` |
| B4 | Page titles / meta fallbacks `"RoleMule"` → `"RoleMule"` | `ui/base.html`, all `ui/**/*.html` with `{% block title %}` |
| B5 | Auth pages copy (login/register/verify/reset) | `ui/auth/*.html` |
| B6 | Profile setup brand | `ui/profile/setup.html` |
| B7 | Dashboard pages titles (index, new-application, application, settings, tools, interview-prep) | `ui/dashboard/*.html` |
| B8 | Help FAQ — replace product name throughout (~20+) | `ui/help.html` |
| B9 | Legal: privacy + terms product name; keep GitHub URL path until repo rename | `ui/legal/privacy.html`, `ui/legal/terms.html` |
| B10 | Errors + maintenance + **hardcoded fallback HTML** in `main.py` (`<h1>RoleMule</h1>` initializing / unavailable — lines ~794, ~811) | `ui/errors/404.html`, `500.html`, `ui/maintenance.html`, `main.py` |
| B11 | Onboarding strings | `ui/src/onboarding/steps.ts` |
| B12 | Optional: export download filename | `ui/src/dashboard-settings/privacy.ts`, `api/profile.py`, `cli/commands/profile.py` |
| B13 | Landing hero / subtitle alignment with tagline **One mule for every role.** | `ui/index.html` (and landing rules) |
| B14 | **Split-only navbars** (no `RoleMule` string — grep misses these) | `ui/partials/navbar_dashboard.html`, `navbar_subpage.html`, `navbar_public.html` |

**Icon note:** Keep `fa-rocket` until Phase D. Do not half-migrate icons.

**Grep reminder:** After B1/B14, search `brand-accent">Pilot` and `Apply<span` — expect **zero** hits in `ui/`.

**Verify:** Click through landing, auth, dashboard, help, legal; hard-refresh after `make build-frontend` if TS changed.

---

### Phase C — Backend user-facing strings

| # | Task | Files |
|---|------|-------|
| C1 | All email HTML/text subjects, headers, footers | `utils/email_service.py` |
| C2 | Auth welcome / verify messages | `api/auth.py` |
| C3 | Startup/shutdown log messages; set logging + tracing `service_name="rolemule"` consistently (or document keeping rolemule) | `main.py` |
| C4 | Agent module docs / mock interview persona “for RoleMule” | `agents/*.py` (esp. `mock_interview.py` `SYSTEM_CONTEXT`) |
| C5 | Misc module one-liners “for RoleMule” | `agents/__init__.py`, `api/__init__.py`, `models/__init__.py`, `models/database.py`, `workflows/__init__.py`, `workflows/job_application_workflow.py`, `utils/__init__.py`, `utils/auth.py`, `utils/cache.py`, `utils/cv_odt_export.py`, `utils/database.py`, `utils/error_responses.py`, `utils/logging_config.py`, `utils/redis_client.py`, `utils/request_middleware.py`, `utils/security.py`, `utils/text_processing.py`, `utils/tracing.py` (docstrings / comments only — do not change default `service=` technical ids) |

**Keep:** Postgres credentials named `rolemule`. Prefer logging/tracing `service_name="rolemule"`.

---

### Phase D — Assets & icon (**icon locked**)

**Chosen mark:** white line-art mule in profile on black, document/role pack on its back, cyan eye. File: `docs/rolemule-icon.png`.

| # | Task | Files |
|---|------|-------|
| D1 | Icon locked — use `docs/rolemule-icon.png` as master | `docs/rolemule-icon.png` |
| D2 | Derive favicon (SVG preferred + PNG fallbacks) | `ui/static/img/favicon.svg` (+ PNG/ICO if used) |
| D3 | Regenerate `docs/logo.svg` (Role + Mule wordmark and/or mule mark) | `docs/logo.svg` |
| D4 | Extension icons 16 / 48 / 128 from master (update `generate_icons.py`) | `extension/icons/*` |
| D5 | Swap `fa-rocket` → mule icon in navbars / popup / landing mockup | Partials + `extension/popup/popup.html` + landing |
| D6 | Re-capture landing screenshots if chrome changed | `ui/static/img/screenshots/tab-*.png` |
| D7 | Re-record or accept stale `docs/demo.gif` | `docs/demo.gif` |
| D8 | Update landing / chrome-extension / `.cursorrules` icon requirement (no longer `fa-rocket`-only) | rules |

---

### Phase E — Chrome extension

| # | Task | Files |
|---|------|-------|
| E1 | `name`, `short_name`, `description`, `default_title` | `extension/manifest.json` |
| E2 | Popup title, wordmark, credential copy | `extension/popup/popup.html`, `popup.css` |
| E3 | Console / file header `[RoleMule]` → `[RoleMule]` (optional polish) | `extension/popup/popup.js`, content/background/lib headers |
| E4 | README + **PUBLISHING.md** | `extension/README.md`, `extension/PUBLISHING.md` |
| E5 | Optional rename `installRoleMuleLiNetworkHook` → `installRoleMuleLiNetworkHook` | `extension/lib/linkedin-voyager-hook.js` — **only if** no external refs; else leave |
| E5b | Header / IIFE name in guest prefetch (`applyPilotLinkedInGuestPrefetch`) | `extension/lib/linkedin-guest-prefetch.js` — D comment; rename function optional (same caution as E5) |
| E6 | **Keep** `jaa_*` storage keys | — |
| E7 | Chrome Web Store listing (outside repo) | Manual |

**Verify:** Load unpacked extension; popup shows RoleMule; submit still works.

---

### Phase F — Docs (human)

| # | Task | Files |
|---|------|-------|
| F1 | README product name, badges alt text, prose; keep clone URL / DB user as technical | `README.md` |
| F2 | USER_GUIDE | `USER_GUIDE.md` |
| F3 | CONTRIBUTING, SECURITY | `CONTRIBUTING.md`, `SECURITY.md` |
| F4 | Add CHANGELOG rebrand entry (do not rewrite old history) | `CHANGELOG.md` |
| F5 | `docs/cli-reference.md` — display name in prose; keep `rolemule` command examples | `docs/cli-reference.md` |
| F6 | Other `docs/*-plan.md` — update product name in intro only if they say RoleMule as current product | `docs/*.md` |
| F7 | `ui/static/README.md`, `e2e/README.md` | as needed |
| F8 | `pyproject.toml` description string | `pyproject.toml` |
| F9 | CLI help + all docs examples: `` `rolemule …` `` | `cli/main.py`, `docs/cli-reference.md`, README, USER_GUIDE |

---

### Phase L — CLI / client / PAT / browser keys (in scope — CLI is new)

| # | Task | Files |
|---|------|-------|
| L1 | `pyproject.toml`: `name = "rolemule"`, script `rolemule = "cli.main:main"` | `pyproject.toml` |
| L2 | Rename package dir `rolemule_client/` → `rolemule_client/`; class `RoleMuleClient` | whole client tree + all imports |
| L3 | Typer `name="rolemule"`; config dir `~/.rolemule`; env `ROLEMULE_*` | `cli/**` |
| L4 | PAT prefix `rm_pat_` + tests | `utils/personal_access_tokens.py`, `tests/test_api/test_auth_tokens.py`, CLI PAT tests |
| L5 | localStorage keys → `rolemule_*` | `ui/src/shared/workflow-tracking.ts`, `dashboard-home.ts`, rules mentioning keys |
| L6 | WS event → `rolemule:ws` | `navbar-notifications.ts`, application-detail, cv/mock/hiring websockets |
| L7 | CI/Make/Just/scripts that invoke `rolemule` CLI → `rolemule` | `.github/workflows/ci.yml`, `Makefile`, `Justfile`, `scripts/cli_smoke.sh` |
| L8 | Update unit-testing / cli / dashboard-home rules for new keys & command | `.cursor/rules`, `.claude/rules` |

**Verify:** `rolemule --help`; create PAT starts with `rm_pat_`; old `rm_pat_` rejected; UI uses new localStorage keys after hard refresh.

---

### Phase G — Agent rules & indexes (must not drift)

| # | Task | Files |
|---|------|-------|
| G1 | Product name + navbar markup rule (Role + Mule) | `.cursorrules`, `CLAUDE.md` |
| G2 | Core / landing / dashboard / extension / settings / cli rules | `.cursor/rules/*.mdc`, `.claude/rules/*.mdc` |
| G3 | Especially: `rolemule-core.mdc`, `landing-page.mdc`, `chrome-extension.mdc`, `dashboard-home.mdc`, `settings-and-env.mdc`, `cli.mdc`, `e2e-testing.mdc` | both rule trees |
| G4 | Optional later: rename file `rolemule-core.mdc` → `rolemule-core.mdc` + update all indexes | Separate PR |

---

### Phase H — Tests

| # | Task | Files |
|---|------|-------|
| H1 | Landing brand suite | `e2e/tests/landing.spec.ts` (title, brand text, Why link, footer, extension mock, auth titles) |
| H2 | Other title / brand asserts | `e2e/tests/application-detail.spec.ts`, `interview-prep.spec.ts`, `dashboard-pages.spec.ts` |
| H2b | E2E package metadata / config comments | `e2e/package.json`, `e2e/README.md`, `e2e/playwright.config.ts` |
| H2c | Auth e2e — only hit is fixture email `admin@rolemule.io` | `e2e/tests/auth-pages.spec.ts` — **K** unless new fixture domain |
| H3 | Email tests default `smtp_from_name` | `tests/test_utils/test_email_service.py` |
| H4 | Logging / settings tests with `app_name="RoleMule"` | `tests/test_utils/test_logging_config.py`, `test_logging_config_extended.py`, `test_settings.py` |
| H4b | Misc test docstrings / locust description | `tests/test_security.py`, `tests/load/locustfile.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/security/pentest.py` |
| H5 | Update CLI/client tests for `rolemule` / `RoleMuleClient` / `rm_pat_` / `ROLEMULE_*` | `tests/test_cli/**`, client imports everywhere |
| H5b | **Keep** Postgres fixtures using DB name `rolemule` | CI / docker / conftest DB URLs |

**Verify:**

```bash
# targeted
npx playwright test e2e/tests/landing.spec.ts
pytest tests/test_utils/test_email_service.py tests/test_utils/test_logging_config_extended.py -q
# smoke CLI still named rolemule
rolemule --help
```

---

### Phase I — GitHub / ops surface

| # | Task | Files |
|---|------|-------|
| I1 | Issue templates user-facing wording | `.github/ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml` |
| I2 | CodeQL config display name | `.github/codeql/codeql-config.yml` |
| I3 | Leave `config.yml` repo URLs until GitHub rename | `.github/ISSUE_TEMPLATE/config.yml` |
| I4 | CI: keep Postgres user/db `rolemule`; change CLI smoke to `rolemule --help` | `.github/workflows/ci.yml` |
| I5 | Makefile / Justfile user-facing echo strings | `Makefile`, `Justfile` |
| I6 | Docker comments only (credentials stay) | `Dockerfile`, `docker-compose.yml` |
| I7 | Script comments | `scripts/*.sh`, `scripts/make_just_test_sandbox.py` |
| I8 | After sandbox script changes, regenerate or ignore `sandbox-just-test/` (do not hand-edit the mirror tree) | `sandbox-just-test/**` |

---

### Phase J — Outside the repo (manual checklist)

| # | Task |
|---|------|
| J1 | Register `rolemule.com` / `.io` (DNS) |
| J2 | **Rename GitHub repo** to `rolemule`; set description + website |
| J3 | Announce: `git remote set-url` + pull + restart; CLI → `rolemule`; new PAT if needed |
| J4 | Chrome Web Store name/description/screenshots |
| J5 | PostHog project display name (optional) |
| J6 | Social / Discord / docs site |
| J7 | Quick trademark search for RoleMule |
| J8 | Announce to self-hosters: pull + restart; CLI command unchanged |
| J9 | Update CORS example domains in docs/rules (`rolemule.yourdomain.com` → `rolemule.yourdomain.com`) | settings-and-env examples |

---

### Phase K — `_private/` tree (if present in deploy)

Cloud/LinkedIn/terraform materials under `_private/` (~22 brand hits). Treat as a **separate PR** if this tree is used for launches:

| Area | Examples |
|------|----------|
| Cloud docs | `_private/README.cloud.md`, `DEPLOYMENT.cloud.md`, `CHANGELOG.cloud.md`, `CONTRIBUTING.cloud.md` |
| LinkedIn launch copy | `_private/LINKEDIN_*.md`, `linkedin-card*.html` |
| Infra | `_private/terraform/*`, `_private/cloudbuild.yaml`, `_private/.env.example` |
| Private rules copies | `_private/cursor-rules/*.mdc` |
| Runbooks | `_private/docs/runbooks/DISASTER_RECOVERY.md` |

Same D vs K rules: display brand → RoleMule; keep technical DB/service ids unless infra is renamed deliberately.

---

## 3. Complete file inventory by area

Use this as the “did we miss anything?” list. Status: **D** = display change, **K** = keep technical, **A** = asset, **O** = outside/manual, **?** = optional polish.

### 3.1 Config / env / compose

| File | Action |
|------|--------|
| `config/settings.py` | D |
| `config/__init__.py` | D |
| `.env.local.example` | D (+ K DATABASE_URL) |
| `docker-compose.yml` | D comments / K credentials |
| `main.py` | D user strings / K logging service_name |
| `alembic.ini` | D comment |

### 3.2 UI templates & partials

| File | Action |
|------|--------|
| `ui/partials/navbar_landing.html` | D (full + split) |
| `ui/partials/navbar_dashboard.html` | D (**split-only** — grep trap) |
| `ui/partials/navbar_subpage.html` | D (**split-only** — grep trap) |
| `ui/partials/navbar_public.html` | D (**split-only** — grep trap) |
| `ui/base.html` | D |
| `ui/index.html` | D |
| `ui/auth/login.html` | D |
| `ui/auth/register.html` | D |
| `ui/auth/reset-password.html` | D |
| `ui/auth/verify-email.html` | D |
| `ui/profile/setup.html` | D |
| `ui/dashboard/index.html` | D |
| `ui/dashboard/new-application.html` | D |
| `ui/dashboard/application.html` | D |
| `ui/dashboard/settings.html` | D |
| `ui/dashboard/tools.html` | D |
| `ui/dashboard/interview-prep.html` | D |
| `ui/help.html` | D |
| `ui/legal/privacy.html` | D |
| `ui/legal/terms.html` | D |
| `ui/errors/404.html` | D |
| `ui/errors/500.html` | D |
| `ui/maintenance.html` | D |

### 3.3 Frontend TS / CSS

| File | Action |
|------|--------|
| `ui/src/onboarding/steps.ts` | D |
| `ui/src/dashboard-settings/privacy.ts` | D filename optional |
| `ui/src/shared/workflow-tracking.ts` | K localStorage keys |
| `ui/src/pages/dashboard-home.ts` | K |
| `ui/src/pages/navbar-notifications.ts` | K event name |
| `ui/src/pages/application-detail.ts` | K (WS event) |
| `ui/src/cv-optimizer/websocket.ts` | K |
| `ui/src/mock-interview/websocket.ts` | K |
| `ui/src/hiring-outreach/websocket.ts` | K |
| `ui/static/css/style.css` | D comment |
| `ui/static/css/base/variables.css` | D comment |
| `ui/static/css/landing.css` | K class names |
| `ui/package.json` | K name |
| `ui/build.mjs` | ? comment |
| `ui/scripts/build-vite.mjs` | K IIFE name |
| `ui/static/README.md` | D |

### 3.4 Extension

| File | Action |
|------|--------|
| `extension/manifest.json` | D |
| `extension/popup/popup.html` | D |
| `extension/popup/popup.css` | D |
| `extension/popup/popup.js` | D/? |
| `extension/background/service-worker.js` | D comment / K `jaa_*` |
| `extension/content/content.js` | D comment |
| `extension/content/content.css` | D comment |
| `extension/lib/form-autofill.js` | D comment |
| `extension/lib/extract-page-content.js` | D comment |
| `extension/lib/linkedin-voyager-hook.js` | ? rename function |
| `extension/lib/linkedin-guest-prefetch.js` | D comment |
| `extension/icons/*` | A |
| `extension/README.md` | D |
| `extension/PUBLISHING.md` | D |

### 3.5 Emails / API messages

| File | Action |
|------|--------|
| `utils/email_service.py` | D |
| `api/auth.py` | D |
| `api/profile.py` | D export name optional |

### 3.6 CLI / client / packaging

| File | Action |
|------|--------|
| `pyproject.toml` | D name + script → `rolemule` |
| `cli/main.py` | D Typer name + help |
| `cli/config.py` | D `~/.rolemule` / `ROLEMULE_*` |
| `cli/admin_visibility.py`, `cli/pager.py` | D env names |
| `cli/commands/*.py` | D help + imports |
| `rolemule_client/**` → `rolemule_client/**` | D rename package + `RoleMuleClient` |
| `.coveragerc` | D omit paths |

### 3.13 Misc

| Item | Action |
|------|--------|
| `PAT_PREFIX` | D → `rm_pat_` |
| Logging/tracing service | D prefer `rolemule` |
| Redis auth/cache keys | K |
| Extension `jaa_*` | K |
| Postgres `rolemule` | K |

### 3.7 Root + docs markdown

| File | Action |
|------|--------|
| `README.md` | D |
| `USER_GUIDE.md` | D |
| `CONTRIBUTING.md` | D |
| `SECURITY.md` | D |
| `CHANGELOG.md` | D add entry |
| `CODE_OF_CONDUCT.md` | — (no hits) |
| `docs/cli-reference.md` | D/K mix |
| `docs/cli-implementation-plan.md` | D prose / K commands |
| `docs/frontend-vite-typescript-migration-plan.md` | D if needed |
| `docs/hiring-outreach-web-plan.md` | D if needed |
| `docs/llm-provider-abstraction-plan.md` | D if needed |
| `docs/company-research-improvement-plan.md` | D if needed |
| `docs/logo.svg` | A |
| `docs/demo.gif` | A |
| `docs/rolemule-rebrand-plan.md` | this file |

### 3.8 Rules

| File | Action |
|------|--------|
| `CLAUDE.md` | D |
| `.cursorrules` | D (navbar + product name) |
| `.cursor/rules/*.mdc` (all with RoleMule) | D |
| `.claude/rules/*.mdc` (all with RoleMule) | D |
| `rolemule-core.mdc` filename | ? later |

### 3.9 Tests

| File | Action |
|------|--------|
| `e2e/tests/landing.spec.ts` | D asserts |
| `e2e/tests/application-detail.spec.ts` | D |
| `e2e/tests/interview-prep.spec.ts` | D |
| `e2e/tests/dashboard-pages.spec.ts` | D |
| `e2e/tests/auth-pages.spec.ts` | K (`admin@rolemule.io` fixture) |
| `e2e/README.md`, `e2e/package.json`, `e2e/playwright.config.ts` | D |
| `tests/test_utils/test_email_service.py` | D |
| `tests/test_utils/test_logging_config.py` | D |
| `tests/test_utils/test_logging_config_extended.py` | D |
| `tests/test_utils/test_settings.py` | D |
| `tests/test_security.py`, `tests/load/locustfile.py` | D/? docstring |
| `tests/test_cli/**`, `tests/test_api/**` client imports | K |
| `tests/test_api/test_auth_tokens.py` PAT | K |
| Other module docstring “RoleMule” | D optional |

### 3.10 GitHub / Make / Docker / scripts

| File | Action |
|------|--------|
| `.github/ISSUE_TEMPLATE/bug_report.yml` | D |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | D |
| `.github/ISSUE_TEMPLATE/config.yml` | K URLs until rename |
| `.github/codeql/codeql-config.yml` | D |
| `.github/workflows/ci.yml` | K DB + CLI binary |
| `.github/pull_request_template.md` | — |
| `Makefile` | D message / K DB create |
| `Justfile` | D/? / K sandbox name |
| `Dockerfile` | K comments/tags |
| `scripts/cli_smoke.sh` | K `rolemule` invoke |
| `scripts/ci-security-grep.sh` | ? |
| `scripts/make_just_test_sandbox.py` | ? |
| `sandbox-just-test/**` | Regenerate — do not hand-edit |

### 3.11 Assets

| File | Action |
|------|--------|
| `ui/static/img/favicon.svg` | A |
| `ui/static/img/pattern.svg` | ? |
| `ui/static/img/screenshots/tab-*.png` | A recapture |
| `extension/icons/icon.svg` + PNGs | A |
| `docs/logo.svg`, `docs/demo.gif` | A |

### 3.12 Analytics / consent

| Item | Action |
|------|--------|
| PostHog / cookie consent code | — no brand strings |
| `cookie_consent` localStorage | K |

### 3.13 Misc

| Item | Location | Action |
|------|----------|--------|
| `PAT_PREFIX` | `utils/personal_access_tokens.py` | D → `rm_pat_` |
| Logging/tracing `service_name` | `main.py` | D prefer `rolemule` |
| Redis auth/cache keys | various | K |
| Extension `jaa_*` | popup / service-worker | K |
| Postgres user/db `rolemule` | docker/CI/env | K |

### 3.14 `_private/` (Phase K)

| File | Action |
|------|--------|
| `_private/*.md` LinkedIn / cloud docs | D |
| `_private/terraform/*`, `cloudbuild.yaml`, `.env.example` | D/K mix |
| `_private/cursor-rules/*.mdc` | D |
| `_private/linkedin-card*.html` | D |
| `_private/docs/runbooks/*` | D |

---

## 3.15 Final greps before merge (must all be clean for display)

```bash
# Display leftovers
rg -n 'RoleMule' --glob '!sandbox-just-test/**' --glob '!.git/**' --glob '!node_modules/**' --glob '!**/dist/**' --glob '!docs/rolemule-rebrand-plan.md' --glob '!CHANGELOG.md'

# Split wordmark leftovers
rg -n 'Apply<span|brand-accent">Pilot|brand-accent'\''>Pilot' ui/ extension/

# Old CLI / PAT / keys should be gone
rg -n 'rm_pat_|rolemule_notified_analyses|rolemule:ws|rolemule_client|RoleMuleClient|\[project.scripts\].*rolemule|name="rolemule"' --glob '!docs/rolemule-rebrand-plan.md' --glob '!CHANGELOG.md' --glob '!sandbox-just-test/**'

# DB name must STILL be rolemule
rg -n 'POSTGRES_USER=applypilot|POSTGRES_DB=applypilot|/applypilot"' docker-compose.yml .env.local.example .github/workflows/ci.yml Makefile
```

Expected: zero display RoleMule; zero old CLI/PAT/localStorage/WS; DB credentials still `rolemule`.

---

## 4. Copy guidelines (while editing)

| Do | Don’t |
|----|--------|
| Use **RoleMule** (one word, camel M) in prose | `Role Mule`, `Rolemule`, `ROLE MULE` inconsistently |
| Tagline: **One mule for every role.** | LOTR jokes as primary subtitle |
| Wordmark HTML: `Role<span class="brand-accent">Mule</span>` | Reintroduce Apply/Pilot split |
| Keep CLI examples as `` `rolemule auth login` `` | Leave `` `rolemule` `` in new docs |
| Say “self-hosted” / “companion” accurately | Imply a hosted SaaS unless true |
| Never name specific job boards in user copy | — |

Suggested `app_description` options (pick one in Phase A):

1. `One mule for every role — AI job search companion`
2. `AI job search companion: prep, tools, and apply help`
3. `Paste a role. Your mule brings the packet.`

---

## 5. PR strategy (recommended)

| PR | Contents | Risk |
|----|----------|------|
| **PR1** | Phases A–C + L (CLI/PAT/keys) + H + F + G — no icon yet | Higher; mechanical renames |
| **PR2** | Phase E extension + store prep | Medium |
| **PR3** | Phase D icon/assets | Low/med |
| **PR4** | Phase I + J (GitHub rename + announce) + K | Ops / outside |

---

## 6. Definition of done

- [ ] No user-visible “RoleMule” in UI, emails, extension, help, legal, onboarding
- [ ] Zero `Apply<span` / `brand-accent">Pilot` under `ui/` + extension popup
- [ ] Tagline **One mule for every role.**
- [ ] `settings.app_name == "RoleMule"`
- [ ] CLI: `rolemule --help`; package/imports `rolemule_client` / `RoleMuleClient`
- [ ] PAT: new tokens `rm_pat_…`; `rm_pat_` rejected
- [ ] localStorage / WS use `rolemule_*` / `rolemule:ws`
- [ ] Postgres still `rolemule` in Docker/CI/`.env.local.example`
- [ ] E2E brand suite green
- [ ] GitHub repo renamed (or scheduled in PR4) + remote URL in README
- [ ] Self-hoster note matches §0.3
- [ ] CHANGELOG rebrand entry
- [ ] §3.15 greps pass

---

## 7. Rollback

Mostly string/path renames: revert PR(s). DB unchanged.  
If GitHub already renamed, rename back or rely on redirect.  
PATs issued as `rm_pat_` would need re-issue after rollback to `rm_pat_`.

---

## 8. Post-v1 (optional)

1. Rename rule file `rolemule-core.mdc` → `rolemule-core.mdc`
2. Temporary `rolemule` CLI alias pointing at `rolemule`
3. Fixture emails `*@rolemule.io` → new domain
4. PyPI publish as `rolemule` (only if you start publishing)
5. Optional: rename extension `jaa_*` keys (low value)

---

## 9. Audit log

### Pass 2 gaps (still valid)
Split-only navbars, `main.py` `<h1>` fallbacks, PUBLISHING.md, `_private/`, sandbox mirror, final greps — see earlier table.

### Pass 3 decision changes
| Old plan assumption | New locked decision |
|---------------------|---------------------|
| Keep CLI / client / PAT / localStorage | **Rename** (CLI is new) |
| GitHub rename later | **In scope** (main goal) |
| PyPI caution | **Ignore** (not publishing) |
| Keep DB name | **Still keep** |
| Existing users: CLI unchanged | **Reinstall + `rolemule`; new PAT once** |

---

## 10. Quick start for the implementing agent

```text
1. Read locked decisions + §0.3 existing-user flow (verified).
2. Phase A → B (incl. B14) → C → L (CLI/client/PAT/keys) → H tests.
3. Sync rules (.cursor + .claude) and docs/examples to `rolemule`.
4. Do NOT rename Postgres rolemule user/db.
5. Phase D: use `docs/rolemule-icon.png` for favicon / extension / navbar (replace `fa-rocket`).
6. Run landing e2e + CLI/PAT tests; run §3.15 greps.
7. PR4: GitHub rename + announce §0.3 steps.
```

**Brand lock reminder:** RoleMule — One mule for every role.
