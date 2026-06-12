# Changelog

All notable changes to ApplyPilot are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2026-05-29

### Added

#### Chrome Extension v2.0.0 — Hybrid form autofill ("Match Form To Profile")

**`POST /api/v1/extension/autofill/map`** maps visible application fields to profile data using an LLM, then merges **`api/extension_autofill_rules.py`** deterministic assignments that override the model on known labels (name, email, phone, country, location, work authorization, visa sponsorship, screening Yes/No, work-location acknowledgements, education blocks, consent checkboxes, and more). Cached responses are re-merged on replay so rules stay authoritative.

**`extension/lib/form-autofill.js`** deep-scrolls long application pages, serializes combobox options, re-scans and rematches by label before apply, and uses dedicated paths for Yes/No comboboxes, acknowledgement dropdowns, and applicant location fields. The popup can attach a stored resume file after text fields are filled. Integration tests in **`tests/test_api/test_extension_autofill.py`**.

#### Profile — work authorization, visa sponsorship, stored resume

Profile setup adds **work authorization** (radio), **visa sponsorship** (checkbox), contact fields, and resume upload persisted for extension autofill (**`utils/user_resume_storage.py`**). Migrations **`021`** / **`022`**. Degree alias helper for education combobox matching (**`utils/degree_aliases.py`**).

### Changed

- Chrome extension **manifest**, popup footer, and landing mockup version → **2.0.0**.

---

## [Unreleased]

### Added

#### Profile — Education step (JSONB)

Profile setup adds an **Education** step (institution, degree, field of study, dates, **Currently enrolled**). Users with no formal education check **“I don't have formal education to add”** — that persists `education: []` so the step counts complete. Agents and extension autofill read `profile.education`; degree dropdown matching uses **`utils/degree_aliases.py`**.

#### Application detail — View posting link and multi-location display

When **`job_url`** is stored (extension **`source_url`**, optional manual URL metadata — not fetch-from-URL), the application detail header shows **View posting** (http(s) only). Job Analyzer **`additional_locations`** render in the header and Job Details tab as `Primary | Office 2 | …`.

### Changed

#### Workflow — posting URL on Form path and scheme guard

`POST /api/v1/workflow/start` accepts **`source_url`** and related fields on the **Form** path (multipart clients could never populate the JSON body). Non-http(s) schemes are discarded before persisting **`job_url`**.

### Fixed

#### Job Analyzer — all posting locations preserved

Extracts **`additional_locations`** for every office listed in the posting, not just the first primary city. Profile Matcher uses all offered locations for location-fit scoring.

#### Chrome Extension — Shared page content extraction

Injectable **`extension/lib/extract-page-content.js`**: selection, JSON-LD, site connectors, split-view heuristics. Large **jobs listing** pages (e.g. **`/jobs`** UIs): skip feed JSON-LD, prefer the detail pane, two-pass async extract. **Ashby** marketing embeds (query params such as **`ashby_jid`** on third-party career pages): resolve posting text via Ashby's public posting API when the slug is known. Popup and context menu use the async extractor; **`extension/lib/`** is tracked in git (`.gitignore` exception); manifest adds Ashby API host permission. README and **`.cursor`/`.claude`** chrome-extension rules updated.

#### New Application — Word (.docx) job file upload

The **Upload File** tab on `/dashboard/new-application` accepts **`.docx`** in addition to **`.pdf`** and **`.txt`** (still **5 MB** max). The API (`POST /api/v1/workflow/start`, `job_file`) validates ZIP magic bytes for DOCX and extracts text with `extract_text_from_docx()` (`docx2txt`), same approach as resume uploads. Legacy binary **`.doc`** (Word 97–2003) is not supported.

#### CV Optimizer — iterative CV optimization loop

On-demand **Optimize CV** tab on the application detail page (after workflow **`completed`**). **`CVOptimizationOrchestrator`** runs a hiring-manager evaluate → applicant revise loop until score threshold, max iterations, score decrease, or plateau; then generates a tailored cover letter. Agents: **`agents/hiring_manager.py`**, **`agents/cv_optimizer_loop.py`**. API: **`api/cv_optimizer.py`** (`POST /start`, `GET`, `GET /status`, `GET /download-cv`, `DELETE`). Persists to **`workflow_sessions.cv_optimization`** (migration **`20260609_023`**) with Redis cache (**24 h** result, **30 min** running lock). WebSocket events: `cv_optimization_started`, `cv_optimization_iteration`, `cv_optimization_complete`, `cv_optimization_error`. Rate limits: **5 starts/hour**, **10 ODT downloads/hour**. Ownership verified before cache on GET/DELETE/download. Frontend: **`ui/static/js/cv-optimizer.js`**. Tests: **`tests/test_api/test_cv_optimizer.py`**, **`tests/test_agents/test_cv_optimizer_loop.py`**. Docs: **USER_GUIDE**, **Help**, **README**, **`.cursor`/`.claude`** rules.

### Changed

#### LLM — Gemini model lineup refresh (Gemini 3.5 Flash default)

Refreshed the selectable Gemini models to match Google's current lineup (verified against the [Gemini API changelog](https://ai.google.dev/gemini-api/docs/changelog)):

- **Added** `gemini-3.5-flash` (stable GA 2026-05-19) and `gemini-3.1-flash-lite` (stable GA 2026-05-07).
- **New default** `gemini-3.5-flash` replaces the preview `gemini-3-flash-preview` (`config/settings.py`, `.env.local.example`, README). This is the server default **and** the BYOK fallback when a user has not picked a model in **Settings → AI Setup** (`preferred_model = null`); `utils/llm_client.py` resolves `model or settings.gemini_model`.
- **Removed** shut-down / deprecated options: `gemini-3.1-flash-lite-preview` (shut down 2026-05-25), `gemini-2.0-flash` / `gemini-2.0-flash-lite` (shut down 2026-06-01), plus the stale `gemini-1.5-*` and `gemini-2.5-*-preview` names. The `gemini-2.5-flash` / `gemini-2.5-pro` GA pair is **kept** as a stable, lower-cost tier and the only models that run on a region-pinned Vertex deployment (every `gemini-3.*` model requires `VERTEX_AI_LOCATION=global`).
- **Fixed** a validation/UI mismatch: `_VALID_MODELS` in `api/profile.py` no longer disagrees with the Settings dropdown, so saving the recommended default via `PATCH /api/v1/profile/preferences` no longer returns `422`. Dropdown (`ui/dashboard/settings.html`) and backend allow-list are now identical. Rule docs (`llm-integration.mdc`, `settings-page.mdc`, `settings-and-env.mdc`) and `USER_GUIDE.md` updated.

#### Dashboard — funnel statistics (Applied card and response rate)

- **Applied** stats card counts **Applied**, **Interview**, **Offer** (accepted), and **Rejected** so the card reflects submissions and funnel progress (not Applied-only).
- **Response rate** uses only user-tracked funnel rows: **(Interview + Offer + Rejected) / (Applied + Interview + Offer + Rejected)** — analysis-only rows no longer dilute the denominator. The numerator counts employer-side outcomes (**Interview**, **Offer**, **Rejected**) only; **Applied** is excluded from the rate and remains its own stat. API field descriptions and stats logging updated.

#### Workflow — `POST /api/v1/workflow/start` rate limit

Raised to **30 requests per hour** per user with a reset counter key for the limiter.

#### Documentation — extension copy alignment (landing, Help, README)

Landing extension headline/subtitle/bullets and hero typography parity; Help Chrome quick link and Match Form FAQ as numbered steps; README Chrome blurb aligned with landing; extension README, manifest, and popup label casing; **`.claude`** chrome-extension and landing-page rule notes. **USER_GUIDE**, **Terms**, **Privacy**, **New Application** tip, and Help FAQ updated for **Analyze This Job** + **Match Form To Profile**.

#### Dev — Justfile on Windows (no cygpath / Git Bash requirement)

Shebang-based recipes that broke on Windows without **cygpath** were replaced: **`docker info`** instead of a shell helper for Docker checks; **`_create-env`** split (Unix uses a Python script, Windows uses PowerShell); **`run_alembic.py`** for **`just migrate`** / **`just migrate-status`** (fixes temp cwd shadowing); **`make_just_test_sandbox.py`** and **`just sandbox-for-testing`**; README clarifies Docker path setup; **`sandbox-just-test/`** gitignored.

#### BYOK / `GEMINI_API_KEY` — relaxed format validation

Google rotates Gemini API key shapes (not only the legacy `AIza…` prefix). The app uses `utils/gemini_api_key_format.validate_gemini_api_key()` for optional server `GEMINI_API_KEY`, user keys in Settings, and profile setup no longer enforces an `AIza` prefix in the browser. Documentation: `.claude/rules/settings-and-env.mdc`.

#### Dashboard & application detail — unknown employer display

When the job analyzer omits an employer or returns placeholder text (for example `—`, `-`, `N/A`, or `unknown`), **`dashboard-home.js`** and **`application-detail.js`** treat those values as missing via **`isPlaceholderCompanyName()`** and show the label **Unknown** on cards and in the application header. Completion toasts and polling metadata use **`displayCompanyNameOrUnknown()`** so the same rules apply. The Company tab uses **About this opportunity** when there is no real employer name. **`agents/company_research.py`** — **`_has_usable_company_name()`** — rejects dash-only strings so backend “unnamed posting” research aligns with the UI.

### Fixed

#### Dashboard — duplicate application rows on "Load more"

Applications list API uses **`EXISTS`** for workflow-session visibility instead of **`LEFT JOIN`**, so **OFFSET** pagination cannot return duplicate **`job_applications`** rows. Stable **`ORDER BY`** with an **`id`** tie-breaker. **`dashboard-home.js`** dedupes merged pages by **`id`** as a client-side safeguard.

#### Chrome Extension — JSON-LD `JobPosting` salary fields

Schema.org **`MonetaryAmount.value`** is often a **`QuantitativeValue`** object (**`minValue`** / **`maxValue`** / **`unitText`**). Stringifying it produced **`[object Object]`** in extracted text on Ashby and similar ATS pages. **`formatJsonLdSalaryField`** formats **`baseSalary`** and **`estimatedSalary`**; extractor build version bumped.

#### Chrome Extension — jobs listing extraction reliability

Extraction is anchored to the **current job id** and **`jobPosting` URN** (prefer detail HTML that references **`urn:li:jobPosting:{id}`** before geometry heuristics; resolve **`data-job-id`** / **`data-entity-urn`**; filter side-rail candidates by URL job id when present). **Guest** listing HTML: parse JSON-LD + DOM when the API returns HTML instead of JSON; MAIN-world prefetch and service-worker/popup orchestration; higher confidence when extracted text is long; backend **Job Analyzer** **`MAX_CONTENT_LENGTH_FOR_AI`** aligned with the extension extract cap. Header merge path and resilient list fields: normalize LLM string vs list shapes for responsibilities (and related fields), **application-detail** filtering, unit tests for **`_normalize_string_list`**.

#### Profile setup — Years of Experience can be zero

`profile-setup.js` no longer treats **`0`** years of experience as a missing required field (JavaScript falsy bug on `parseInt` results) and correctly pre-fills the field when the saved profile has **0**. Backend validation already allowed `ge=0`; only the client-side checks needed fixing.

### Changed

#### LLM — unified max output tokens (16,000)

All workflow agents, career-tool agents, interview prep, `utils/resume_parser.py`, and `gemini_client.generate()` defaults use **`DEFAULT_MAX_TOKENS = 16000`** in `utils/llm_client.py` so long structured outputs are not capped by mixed per-agent limits.

#### Caching — job analysis Redis key

Job analysis cache keys (`_get_job_cache_key` in `utils/cache.py`) hash normalized URL plus up to **50,000** characters of job text (`_MAX_JOB_CONTENT_FOR_CACHE_KEY`), reducing false cache hits when different roles share the same long page or URL chrome.

#### Dashboard — application list refresh races

`loadApplications` in `dashboard-home.js` uses a **single-flight** pattern (`_pendingLoadApplicationsReset`, `_loadApplicationsInFlight`, `_loadApplicationsSinglePass`) so overlapping WebSocket-driven refreshes do not drop a full reload while a fetch is already in progress.

### Added

#### Chrome Extension — Instant Job Title & Company on Dashboard

When a job is submitted via the extension the dashboard card now shows a real job title and company name immediately, instead of generic placeholders:

- **Extension (`popup.js`)**: `parseJobTitleAndCompany(pageTitle)` extracts a clean title and company from the browser's page title before submission. Handles all common job-board formats (`"Title - Company | Site"`, `"Title | Company | Site"`, `"Title at Company | Site"`, `"Title | Dept - Company"`). An `extractCompany` helper resolves `"Dept - Company"` substrings by greedily matching to the **last** spaced dash, so `"Data Ingestion, NG-SIEM (Hybrid) - CrowdStrike"` → `"CrowdStrike"` (note: `"NG-SIEM"` hyphen has no spaces so it is not treated as a separator). Known site-name suffixes are stripped.
- **Backend (`api/workflow.py`)**: `start_workflow` now accepts `detected_title` and `detected_company` as optional `Form` fields. These are written to `job_title` / `company_name` on the `JobApplication` record at creation time so the dashboard card is populated immediately.
- **Backend (`workflows/job_application_workflow.py`)**: `_save_workflow_state` performs an early `UPDATE` on the `job_applications` table the moment the Job Analyzer agent writes `job_analysis` (~4 s into the workflow). This overwrites the heuristic seed with the AI-extracted authoritative title and company name.
- **Dashboard (`dashboard-home.js`)**: `renderCard` now shows animated skeleton shimmer lines (`.skeleton-line.skeleton-title` / `.skeleton-line.skeleton-subtitle`) in place of a job title or company name while an application is still `processing` and those fields are not yet populated.

#### Chrome Extension — Inline Notification Bar

Replaced the old `position: fixed` floating toast in the extension popup with a permanent inline notification bar (`#popupNotification`) that slides in just below the header:

- Always visible within the popup frame — not affected by popup height changes during view transitions
- Proper contrast: `rgba(16,185,129,0.18)` background + `#34d399` text + Font Awesome icon for success; matching variants for error and info
- Animates in/out via `max-height` + `opacity` transition; auto-dismisses after 3 s

#### Dashboard — Real-Time Updates from Extension

`handleUserWsMessage` now processes `agent_update` WebSocket events. When an `agent_update` is received for a session ID that is not yet in `_loadedApps` (i.e. submitted from the extension in another tab), `loadApplications(true)` is triggered immediately so the card appears in `processing` state within seconds — without requiring a manual refresh.

#### Dashboard — Application Card Redesign

The application card UI was completely redesigned to separate two distinct concepts that were previously conflated in a single dropdown:

- **AI analysis badge** (read-only, top-right): shows `Analyzing…` (blue spinner) while the workflow runs, `✓ Ready` (cyan) when complete, or `Failed` (red) on error. Users cannot change this.
- **Tracking stage buttons** (user-editable, bottom-right): `Applied` / `Interview` / `Offer` / `Rejected` — appear only after analysis completes; the active stage is highlighted. Clicking the active button again **toggles it off** (undo), resetting to untracked. Toast messages read "Marked as Applied." or "Stage cleared." — never "Status updated to Completed."

Card layout is now a 2-column design: left column (title, company, date/match) and right column (AI badge top, tracking buttons + always-visible trash bottom).

#### Dashboard — Status Filter

The `All Status` filter dropdown was simplified to only show the four user-trackable stages: **Applied**, **Interview**, **Offer**, **Rejected**. The `Processing` and `Completed` options are removed — those are AI-internal states that users don't track manually.

#### Cross-Page Analysis Completion Badge (`navbar-notifications.js`)

A new shared script (`ui/static/js/navbar-notifications.js`) loaded globally in `base.html` notifies users when an analysis completes while they are on a subpage (Career Tools, New Application, Settings, etc.).

- A small **pulsing cyan dot** appears on the "← Back to Dashboard" button in `navbar_subpage.html`
- Uses the existing **user-scoped WebSocket** (`/api/v1/ws/user`) for real-time detection — no polling
- A **one-shot status check** on page load catches analyses that finished while the browser was closed
- The dot is cleared the moment the user lands on `/dashboard` (which shows the full "Analysis ready!" toast)
- Session IDs are stored in `localStorage.applypilot_tracked_sessions` by `dashboard-new-application.js` immediately after a successful submit

#### Landing Page — Inter-Section Scroll Hints

Pulsing chevron arrows now appear between every pair of adjacent landing page sections, matching the existing hero scroll hint in style (42 px circle, cyan border, `scroll-bounce` + `scroll-pulse` animations). This addresses discoverability for the sections hidden below the fold.

#### Landing Page — "See It In Action" Interaction Hints

Two small pill badges above the screenshot showcase tabs — `Click a tab to explore` and `Scroll to read` — inform first-time visitors that the section is interactive and the content is scrollable.

#### Landing Page — Real Screenshot Showcase ("See It In Action")
The "See It In Action" section on the landing page (`ui/index.html`) now shows real screenshots of the live application instead of the previous text-based mockup. A 7-tab showcase (Job Details, Your Fit, Strategy, Company, Cover Letter, Resume, Interview) lets visitors browse actual AI-generated output from a real job analysis.

- **7 merged screenshots** stored in `ui/static/img/screenshots/` — each is a single tall PNG combining the full scrollable content of that tab, served as static assets
- **Fake browser chrome** at the top (traffic-light dots + URL bar) frames the screenshots as an in-app window
- **Tab bar** with `flex: 1` so all 7 tabs share equal width across the full container
- **Scrollable panel** (`max-height: 580px; overflow-y: auto`) with a styled thin scrollbar — clicking a tab resets the scroll to the top
- **Fade-in animation** (`ss-fade-in`) when switching tabs
- **Full container width** — matches the width of the "Career Tools for Every Stage" grid
- **Mobile responsive**: tab labels hide below 768px (icons only); panel height reduced to 340px

CSS classes: `.screenshot-showcase`, `.ss-tabs`, `.ss-tab`, `.ss-frame`, `.ss-browser-chrome`, `.ss-dots`, `.ss-url-bar`, `.ss-panels`, `.ss-panel`, `.ss-panel.active`
JS: `ssActivateTab(tabId)` in `ui/static/js/landing.js`
Screenshot files: `ui/static/img/screenshots/tab-{job-details,your-fit,strategy,company,cover-letter,resume,interview}.png`

#### Consistent Subpage Navbar (Help, Terms, Privacy)
All secondary pages (Help, Terms of Use, Privacy Policy) now use `navbar_subpage.html` — the same grey card navbar with the `← Back to …` button as Settings and the application detail page. Previously they used a floating fixed-position "Back to Home" link that was visually inconsistent.

- Help page: `?from=dashboard` query param detected via JS; button reads "Back to Dashboard" or "Back to Home" accordingly
- Terms of Use and Privacy: always link back to Home
- All three pages now define the same `.navbar`, `.brand-icon`, `.brand-text` CSS block as the dashboard/settings pages so the navbar height, icon size, and padding are pixel-identical

#### Help Page — Gradient Header Card
The Help page header (`"How can we help?"`) is now styled as a dark card with a 3 px cyan→purple gradient accent line at the top, matching the Settings header card design.

#### Dashboard Help Link — Context-Aware Return
The Help button in the dashboard navbar now links to `/help?from=dashboard`. When the Help page is opened with this parameter, the back button dynamically changes to "← Back to Dashboard".

#### Individual Document Generation Buttons (Cover Letter & Resume Tips)
The Cover Letter and Resume tabs now have **separate** generate buttons. Previously, clicking "Generate" in either tab triggered generation of both documents together. Now each tab generates only its own document, using the existing `regenerate-cover-letter` and `regenerate-resume` endpoints directly. This supports the scenario where a user wants only one document after a completed analysis.

The four generation scenarios are now fully handled:
- Auto-generate ON + above gate → both created automatically
- Auto-generate ON + below gate → workflow pauses; user can trigger each tab independently
- Auto-generate OFF → workflow ends at `analysis_complete`; user triggers each doc individually
- Any status → user can always re-generate a single doc from its tab

#### Company Tab — "Run Full Analysis Anyway" Button
When an application's match score was below the configured gate threshold (workflow stopped at `awaiting_confirmation`), the Company tab previously showed a blank or confusing empty state. It now shows a structured message explaining that company research was skipped due to a low match score, with a **"Run Full Analysis Anyway"** button. Clicking it calls `POST /api/v1/workflow/continue/{session_id}` which resumes the workflow and generates company research, cover letter, and resume tips.

#### Application Detail Tab Reorder
Tab order changed to: **Job Details → Your Fit → Strategy → Company → Cover Letter → Resume → Interview**. Job Details is now the default active tab (was Company). This matches the natural reading flow: understand the job → see your fit → read strategy → explore company → view generated docs → prepare for interview.

#### Consistent Empty State Design Across All Content Tabs
All four content tabs (Company, Cover Letter, Resume, Interview) now use a unified empty state layout: icon (`fa-*` at 2.5rem accent color) → title → description paragraph → action button using the subtle `regen-btn` style (dark background, no gradient). New CSS classes: `.empty-state-icon`, `.empty-state-title`, `.empty-state-desc`.

#### Interview Tab — Basic Data Notice
When the Interview tab has basic job-description data but no AI-generated prep, a notice banner (`.iv-basic-notice`) now appears at the top of the content explaining what is shown and why full prep was not generated. The "Generate Full Prep" button lives inside the banner, not buried below the content.

#### Cross-Platform Dev Setup — `make start-local` and `Justfile`

**`make start-local` (macOS)** — new one-command no-Docker setup. Installs PostgreSQL 17 and Redis via Homebrew if missing, creates the database and user, runs migrations, and starts the app. Mirrors the simplicity of `make start` without requiring Docker.

```bash
make start-local    # first run: ~3 min (installs services); subsequent: ~5 sec
make stop-local     # stop PostgreSQL and Redis Homebrew services
```

**`Justfile`** — new cross-platform task runner file for Windows users. Covers Option A (Docker) and Option C (manual setup) without requiring WSL2. Install with `winget install Casey.Just`.

```powershell
just start          # Docker — identical to make start, works in PowerShell/cmd
just setup          # create venv, install deps, build frontend, generate .env
just migrate        # run Alembic migrations (handles Windows paths correctly)
just dev            # start FastAPI dev server
just test           # run test suite
just lint           # run ruff linter
just build-frontend # compile and content-hash JS/CSS assets
```

**README restructured** — Quick Start now shows three options clearly: Docker (Option A), macOS no-Docker (Option B), and manual (Option C). Docker stays first for broad compatibility; macOS no-Docker and manual paths are promoted to first-class options rather than a buried developer note.

**CONTRIBUTING.md updated** — development setup section reflects all three options with `just` alternatives for Windows contributors throughout.

#### Open-Source / Self-Hosted Support
- **`make start`** — single command to start the entire app. Auto-creates `.env` from `.env.local.example` and fills in strong random secrets on the first run, then starts all Docker services. No manual key generation or `.env` editing required.
- **`make start-d`** — same as `make start` but runs in the background (detached mode)
- **Gemini API key via UI** — `GEMINI_API_KEY` is now optional in `.env`. For personal use, add the key through **Settings → AI Setup** after registering. The `.env` server key is only needed for multi-user shared deployments.
- **Docker Compose** setup — single `docker compose up` starts PostgreSQL, Redis, and the app together
- **`DISABLE_EMAIL_VERIFICATION` flag** — when set to `true`, new users are auto-verified on registration and can log in immediately without configuring SMTP. Default is `true` in `.env.local.example` for local use
- **`.env.local.example`** — dedicated environment template with local-friendly defaults (replaces the cloud-oriented `.env.example` for self-hosted users)

#### E2E Test Suite — Complete Overhaul (Phases 1–4)

The Playwright E2E suite grew from **315 tests / 18 files** to **~1,450 tests / 24 spec files** with full TypeScript strict-mode compliance.

| Phase | What changed |
|-------|-------------|
| Phase 1 | Fixed existing TypeScript issues, confirmed clean compile under `strict: true` |
| Phase 2 | +480 tests across 15 spec files — auth flows, dashboard elements, career tools, history, responsive layout |
| Phase 3 | +72 tests — new `onboarding.spec.ts` (45 tests) and `journey.spec.ts` (27 multi-step user journeys) |
| Phase 4 | +3 new spec files — API validation, keyboard navigation, rate-limit handling; deepened websocket and file-upload coverage |

New shared utilities in `e2e/utils/api-mocks.ts` — `MOCK_JWT`, `setupAuth()`, `setupCookieConsent()`, `setupAllMocks()` used by every mocked spec.

#### Security Hardening
- **Content Security Policy** header with nonce-gated `script-src` and `style-src` directives
- **In-memory rate-limiter fallback** — rate limits continue working if Redis is briefly unavailable
- **File upload MIME validation** — magic-bytes check for PDF/DOCX/TXT, 10 MB size cap
- **Three new auth endpoints** now rate-limited: reset-password, verify-code, resend-verification

#### Performance — Frontend Build Pipeline
- **esbuild-based asset pipeline** — minifies all JS/CSS, generates 8-char content hashes, outputs `manifest.json`
- `asset_url()` Jinja2 global resolves hashed paths at runtime; falls back to `/static/<path>` in development
- All 15 templates updated to use `{{ asset_url('js/...') }}` / `{{ asset_url('css/...') }}`

#### Cache Hardening
- **Cache schema versioning** — bumping `CACHE_VERSION` triggers a clean flush on deploy
- **Stampede protection** — Redis `SET NX` lock prevents concurrent cache-miss LLM calls for the same key
- **Per-user LLM cache scoping** — cache keys include `user_id` for prompts that contain personal content
- **Cache schema validation on read** — malformed cache entries are evicted immediately rather than returned
- **Cache observability** — `GET /api/v1/cache/stats` includes per-type hit/miss rates, Redis eviction counts, and fallback limiter status

#### Frontend Architecture
- **API call pattern** — all page-level JS files use raw `fetch()` with a `Bearer` token header; `getAuthToken()` provides a consistent fallback across landing and dashboard pages
- **Shared utility methods** on `window.app`: `getAuthToken()`, `escapeHtml()`, `formatStatus()`, `copyToClipboard()`
- **Notification standardization** — unified `notify()` helper across all pages; removed ad-hoc `alert()` usage
- **Input debouncing** — 300 ms debounce on search, password, email, and name validators
- **In-flight guards** — prevents duplicate concurrent API calls on buttons across all async handlers
- **Memory leak fixes** — timer IDs tracked and cleared on `beforeunload` in `application-detail.js`

#### Application Details Page — 7-Tab Redesign
The Overview tab and its 4 sub-tabs were promoted to independent top-level tabs: **Company**, **Your Fit**, **Strategy**, **Job Details**, **Cover Letter**, **Resume**, **Interview**.

- Resume Advisor sub-tabs merged into a single flat scrollable view
- Per-tab Copy and Export PDF buttons
- Profile Match score widget fixed to the top-right corner across all tabs
- Tab bar is horizontally scrollable on mobile (no wrapping)

#### On-Demand Content Regeneration
Three new endpoints allow regenerating AI content for completed workflows (rate-limited to 5/hour):
- `POST /api/v1/workflow/regenerate-cover-letter/{session_id}`
- `POST /api/v1/workflow/regenerate-resume/{session_id}`
- `POST /api/v1/workflow/generate-interview-prep/{session_id}`

### Changed

#### Infrastructure & Runtime Versions
- **Python 3.11 → 3.13** — Dockerfile base image updated to `python:3.13-slim` (latest stable, Oct 2024)
- **Node.js 20 → 22** — Dockerfile frontend builder updated to `node:22-slim` (Active LTS)
- **PostgreSQL 15 → 17** — `docker-compose.yml` image updated to `postgres:17-alpine` (current stable)
- **Redis 7 → 7.4** — `docker-compose.yml` image updated to `redis:7.4-alpine` (pinned to stable minor)

#### Dependency Cleanup — Removed GCP Infrastructure Packages
The following packages were removed from `requirements.txt`. They were only needed for GCP-hosted deployments. The code that uses them remains in the repo with graceful `ImportError` guards — local and Docker users are unaffected:
- `google-cloud-tasks` — Cloud Tasks workflow dispatch (code in `utils/cloud_tasks.py`)
- `google-cloud-trace` — Cloud Trace distributed tracing exporter
- `opentelemetry-api`, `opentelemetry-sdk` and all `opentelemetry-instrumentation-*` packages
- `opentelemetry-exporter-gcp-trace`, `opentelemetry-resourcedetector-gcp`
- `google-generativeai` — legacy Gemini SDK (replaced by `google-genai` throughout)

To re-enable Cloud Tasks: `pip install google-cloud-tasks` then set `CLOUD_TASKS_SERVICE_URL`, `CLOUD_TASKS_SERVICE_ACCOUNT`, and `CLOUD_TASKS_SECRET` in `.env`.

#### `utils/cloud_tasks.py` — Graceful Startup Without `google-cloud-tasks`
The `from google.cloud import tasks_v2` import is now wrapped in `try/except ImportError`. The app no longer crashes at startup when `google-cloud-tasks` is not installed. When the package is absent and `use_cloud_tasks` is `False` (the default), all workflow dispatch falls back to FastAPI `BackgroundTasks` automatically.

### Removed

- **URL job input method** — the ability to paste a job posting URL and have the app **fetch** the description has been removed. Job descriptions must now be provided via the Chrome Extension, pasted text, or file upload. The app still **stores** an optional http(s) **posting URL** as metadata (extension `source_url`, dedupe, and **View posting** on the detail page) — it does not download the page content from that URL.
- **`beautifulsoup4` / `bs4`** removed from `requirements.txt` — no longer used following the URL input removal.

### Fixed

#### Chrome Extension — Popup Non-Responsive on Click

`showExtracting()` in `popup.js` referenced `elements.copyBtn` which was no longer present in `popup.html`. This caused a silent `TypeError` that aborted the entire extraction flow before any visible error. Fixed with null checks (`if (elements.copyBtn)`) around all references to that element.

#### Dashboard — Duplicate "Analysis Ready!" Toasts

`notifyReady` is now guarded at its entry point: if `_isAnalysisNotified(detailId)` is already true the function returns immediately, before creating any DOM element. Additionally, `_markAnalysisNotified` is called at the **top** of `notifyReady` (before DOM creation) so any concurrent call — e.g. the WebSocket handler and the polling fallback firing in the same event-loop turn — sees the session as handled and bails out. Previously the mark only happened after DOM creation, allowing a race between the WS path and the poll path to produce two toasts for the same analysis.

#### Dashboard — "Analysis Ready" Toast Improvements

- The "Application submitted!" toast is automatically dismissed when the "Analysis ready!" toast appears, preventing duplicate notifications
- The close (×) button no longer overlaps the "View Results" button — fixed by removing Bootstrap's `alert-dismissible` class and placing the button explicitly inside the flex layout
- If a user navigates away from the dashboard while an analysis is running and returns later, the "Analysis ready!" toast still appears (persisted via `localStorage.applypilot_notified_analyses`)

#### Dashboard Status Incorrect for Gate-Stopped Applications
Applications where the workflow paused at `awaiting_confirmation` (low match score below the configured gate) were showing **PROCESSING** status on the dashboard card. Since the Job Analyzer and Profile Matcher have both completed successfully at this point, the correct status is **COMPLETED**. Fixed in `api/workflow.py` by mapping `WorkflowStatus.AWAITING_CONFIRMATION` → `ApplicationStatus.COMPLETED`.

#### Cover Letter — Candidate Name in Sign-Off

The AI-generated cover letter now signs off with the user's actual full name (from their profile) instead of the placeholder `"Candidate"`. The `cover_letter_writer.py` prompt explicitly injects `candidate_name` and instructs the LLM to use it verbatim.

#### Cover Letter Showing Literal `&amp;` Instead of `&`
Cover letter text was displaying `&amp;` literally (e.g. "AI &amp; ML" instead of "AI & ML"). The backend's `html.escape()` + `bleach.clean()` pipeline was double-encoding ampersands (`&` → `&amp;` → `&amp;amp;`). Fixed by:
- Adding `&amp;amp;` → `&` as the first decode step in both `escapeHtml()` and `decodeEntities()` in `application-detail.js`
- Switching the cover letter body from `innerHTML = escapeHtml(letter)` to `el.textContent = decodeEntities(letter)` — the letter is plain text, so `textContent` is the correct assignment and bypasses all entity parsing

#### Onboarding Tour — Repeated Appearance After Login

The onboarding tour was incorrectly shown every time a user signed in with an email/password account. Root cause: `auth-verify-email.js` was unconditionally clearing `localStorage.onboarding_completed` on every successful verification, including for returning users re-verifying after a lockout. Fixed by only clearing the flag when `profile_completed` is `false` (i.e., genuinely new users).

#### Application Detail — "Posted" Date Hidden When Unknown

The "Posted" meta item in the application detail header no longer displays when no date is available. Fixed a CSS specificity conflict where `.job-meta-item { display: inline-flex }` in the page `<style>` was overriding `.is-hidden { display: none }`. Added a higher-specificity companion rule `.job-meta-item.is-hidden { display: none }`.

#### Salary Badge Showing Without Salary Data
The salary badge in the application detail header was appearing with only the dollar-sign icon and no text in two cases:

1. **CSS specificity bug** — `.job-badge { display: inline-flex }` in the page-level `<style>` block has equal specificity to `.is-hidden { display: none }` in `app.css`. Because the page style loads after the linked stylesheet, it silently overrode `.is-hidden`, making all job badges (salary, type, work arrangement) permanently visible regardless of the hidden class. Fixed by adding `.job-badge.is-hidden { display: none }` (two-class selector, higher specificity) to the page `<style>`.

2. **No digit check on string salary** — When the LLM returns `salary_range` as a bare currency symbol string (e.g. `"$"`), the old code set it as the display value (truthy string), causing the badge to show with only the `$` icon and an empty text span. The string path now requires `/\d/.test(trimmed)` — a digit must be present — before the badge is shown.

#### Job Badge Casing — "full-time" → "Full-Time", "onsite" → "Onsite"
The employment type and work arrangement badges in the application header were rendered in raw lowercase (as returned by the LLM). A module-level `toTitleCase()` helper was added to `application-detail.js` and is now applied to both badges via `toTitleCase(decodeEntities(value))`. The "At a Glance" grid in the Job Details tab was already correctly title-casing these values.

#### Application Detail Navbar Size — Matches Dashboard
The application detail page navbar was using smaller values than the dashboard:
- Padding: `0.75rem` → `1rem`
- Brand icon: `32×32 px / 0.9rem` → `36×36 px / 1rem`
- Brand text: `1.1rem` → `1.2rem`

#### Landing Page Logo — Matches Dashboard Size
The landing page logo icon was `40×40 px / 1.2rem / 1.4rem` (larger than the dashboard). Reduced to `36×36 px / 1rem / 1.2rem` in `landing.css` for visual consistency across all pages.

#### Percentile Marker Position
The "Your Competitive Position" percentile bar marker dot was stuck at position 0 instead of the correct percentile position. The `style="left: X%"` attribute set inside a JavaScript `innerHTML` string was not being applied reliably. Fixed by using a `data-pct` attribute in the HTML string and setting `marker.style.left` via JavaScript after the `innerHTML` assignment.

#### "Unknown" Website Link Causing Application Not Found Error
When the Company Research agent cannot find a website, it sometimes returns the string `"Unknown"` instead of a real URL. This was being rendered as a relative hyperlink, causing navigation to `/Unknown` which showed the "Application not found" error. Fixed by validating that the website value starts with `http://` or `https://` before rendering the link — invalid values are silently hidden.

#### Trajectory Badge Removed from Experience Row
The `↑ ASCENDING` / `→ LATERAL` / `↓ DESCENDING` career trajectory badge was appearing inline with the "Experience" label in the Qualification Breakdown. Users found it confusing. The badge has been removed; the experience score and description bar already communicate fit quality clearly.

#### "Potential Employer Concerns" — Clearer Section Header
The "What the Employer Might Worry About" section in the Your Fit tab was renamed to **"Potential Employer Concerns"** with a simplified description: *"The hiring manager might raise these objections. Be ready to address them in your cover letter or interview."*

#### Quick Win Cards — Time Estimate Removed
The `time_to_implement` field (e.g. "5 min", "15 min") was removed from Quick Win cards in the Resume tab Overview sub-pane. The priority badge (HIGH / MEDIUM / LOW) is retained.

#### Generate Button Icons Removed
Icons were removed from four action buttons to reduce visual clutter: "Generate Cover Letter", "Generate Resume Tips", "Generate Interview Prep", "Run Full Analysis Anyway".

#### Agent Year Claims — Domain-Specific Not Total Career Years
All six content-generating agents were using the profile's `years_experience` (total career years) to make domain-specific claims like "7 years of Backend expertise" even when only a subset of those years were in the relevant domain. A `YEARS OF EXPERIENCE RULE` was added to the `SYSTEM_CONTEXT` of all six agents:

> *"The `Years of Experience` field is TOTAL career years — NEVER use it as domain-specific experience. When claiming 'X years of [skill/domain]', derive that number only from the relevant work history entries where that skill was actually used. If you cannot calculate it, say 'experience with [skill]' without stating a specific year count."*

Affected agents: `profile_matching`, `interview_prep`, `resume_advisor`, `cover_letter_writer`, `job_comparison`, `salary_coach`.

#### HTML Entity Double-Encoding in Dashboard Cards and Application Detail
Application titles and company content containing special characters (e.g. `&`, `'`) were being double-encoded by the backend's `html.escape()` + `bleach.clean()` combination (`'` → `&#x27;` → `&amp;#x27;`), causing `&amp;` and `&#x27;` to display literally as text rather than rendered characters.

Two fixes applied:
- **`dashboard-home.js`** — `escapeHtml()` now decodes `&amp;` first before decoding named entities, then re-encodes. This prevents `&amp;` rendering literally in card titles (e.g. "New Markets &amp; Models" now shows "New Markets & Models").
- **`application-detail.js`** — Same decode-order fix in `escapeHtml()`. Also added a `decodeEntities()` helper used for `.textContent` assignments (job title, company name in the page header), where HTML entities would display literally because `.textContent` does not interpret them.

#### `analysis_complete` Applications Rejected by Regeneration Endpoints
When a user tried to generate a cover letter, resume tips, or interview prep for an application with `analysis_complete` status (auto-generate was off), the backend returned a `VAL_2001` validation error ("Can only generate for completed workflows"). Fixed by adding `WorkflowStatus.ANALYSIS_COMPLETE` to the allowed statuses list in all three endpoints (`regenerate_cover_letter`, `regenerate_resume`, `generate_interview_prep`).

#### Sort Filter Button Text Clipping
The sort `<select>` in the dashboard filter bar was set to `min-width: 0; flex-shrink: 1`, which allowed it to shrink below its content width when the selected option text was long. "Company A–Z" and "Recently updated" were both clipped in the button. Changed `.filter-select-auto` to `min-width: max-content; flex-shrink: 0` so the button is always wide enough for its selected option.

#### XSS — All `innerHTML` Notification Paths
All `innerHTML` paths that accepted API data, LLM output, or user input without escaping have been corrected across `app.js`, `dashboard-*.js`, `auth-*.js`, and `profile.js`.

---

## [1.2.0] — Interview Prep & Career Tools

### Added

#### Interview Preparation
Standalone interview prep agent accessible from any completed application.
- Predicted interview questions based on job requirements and company culture
- STAR method answer frameworks using the candidate's real experience
- Strategies to address profile gaps
- Questions to ask interviewers
- Cached for 24 hours; regeneratable on demand

**API endpoints:**
- `GET /api/v1/interview-prep/{session_id}`
- `POST /api/v1/interview-prep/{session_id}/generate`
- `GET /api/v1/interview-prep/{session_id}/status`
- `DELETE /api/v1/interview-prep/{session_id}`

#### Career Tools Suite (6 Tools)
AI-powered communication tools at `/dashboard/tools`:

| Tool | What it generates |
|------|------------------|
| Thank You Note | Post-interview thank you emails |
| Rejection Analysis | Insight + re-engagement strategy from rejection emails |
| Reference Request | Professional reference request emails |
| Job Comparison | Side-by-side comparison of 2–3 jobs |
| Follow-up Generator | Follow-up emails for any stage |
| Salary Coach | Negotiation strategy and talking points |

Rate limited to 10/hour (Salary Coach: 5/hour).

#### Chrome Extension
Manifest V3 Chrome extension for one-click job extraction from any website.
- Popup UI matching the main app's design system
- Seamless JWT authentication with the web app
- Context menu integration
- Auto token refresh every 55 minutes
- `IS_DEV` flag for toggling local vs production URL

---

## [1.1.0] — Auth, Profile & BYOK

### Added

#### BYOK — Bring Your Own Key
Each user can add their own Gemini API key in **Settings → AI Setup**:
- Keys encrypted with Fernet before storage
- Keys never logged or exposed in API responses
- Server key optional — works as a fallback when set

**Deployment modes:**

| Mode | Server key | User key | Use case |
|------|-----------|---------|---------|
| BYOK Only | Not set | Required | Community / open-source |
| Server Key | Set | Optional | Single-user self-hosted |
| Hybrid | Set | Optional (overrides) | Mixed |

#### Google OAuth — "Continue with Google"
- One-click sign up / sign in
- Link or unlink Google from an existing email/password account
- CSRF-protected via Redis state token

#### Email Verification System
- 6-digit code sent on registration
- Rate-limited resend endpoint
- Bypass available via `DISABLE_EMAIL_VERIFICATION=true` for self-hosted setups

#### Password Reset
- Secure time-limited token via email
- Change password (authenticated)
- Fixes `auth_method` for Google users who add a password via reset

#### Cookie Consent & Data Privacy
GDPR-friendly banner with essential / functional / analytics categories.
- `GET /api/v1/profile/export` — export all user data
- `DELETE /api/v1/profile/delete-account` — delete account and data
- `DELETE /api/v1/profile/clear-data` — clear data, keep account

#### Onboarding Tour
5-step interactive tour on first dashboard visit, restartable from Settings.

#### Help & FAQ Page
Searchable FAQ at `/help` covering setup, API keys, workflow, career tools, and the Chrome extension.

---

## [1.0.0] — Initial Release

### Added
- Multi-agent workflow with 5 specialized agents:
  - **Job Analyzer** — extracts requirements, skills, and keywords
  - **Profile Matcher** — evaluates fit, produces match score and gate decision
  - **Company Research** — culture, leadership, interview style
  - **Resume Advisor** — per-bullet rewrites, ATS score, checklist
  - **Cover Letter Writer** — personalized letter with regeneration
- LangGraph workflow orchestration with gate decision (stops early on poor match)
- PostgreSQL database with SQLAlchemy async ORM (UUID primary keys, JSONB columns)
- Redis caching and rate limiting
- JWT-based authentication with account lockout protection
- WebSocket real-time workflow status updates
- Resume parser (PDF, DOCX, TXT) with AI-assisted field extraction
- Profile setup wizard (4 steps)
- Application tracking dashboard with search, filter, and sort
- Modern dark theme UI with Bootstrap 5 and custom CSS variables
- Structured JSON/text logging with request context propagation
