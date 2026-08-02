# Job Finder (Chat) — Plan & Execution Spec

**Status:** Implemented (phases 0–9)  
**Feature name (product):** Job Finder  
**Internal codename:** `job_finder`  
**Owner:** Engineering  
**Last updated:** 2026-07-20  
**Doc reviews:** 3 passes completed against RoleMule repo + OSS references (see §21)

Discover open roles on **company careers pages** via a chat UI, let the user pick roles, then run RoleMule’s **existing** application analysis pipeline.  
**Does not apply for the user. Does not use job boards / aggregators.**

---

## 0. Agent instructions (read first)

### 0.1 Goal

After login, RoleMule keeps **Applications** as the home experience. Users can open **Find jobs** (chat) to:

1. Confirm search filters (seeded from profile title + career preferences).
2. Name **one company at a time**.
3. Have an agent locate that company’s **careers / ATS board** (not a job board).
4. Fetch and filter open roles.
5. Pick roles from an in-chat list/cards UI.
6. **Add to applications** → existing `POST /api/v1/workflow/start` → normal 5-agent pipeline.

This feature is designed to be a **star surface** of the app from day one: polished chat UX, same design system, fast perceived performance, honest failure modes.

### 0.2 Product decisions (locked)

| Decision | Choice |
|----------|--------|
| Home tab | **Applications** is always the main/default tab (new and returning users) |
| Find jobs | Optional secondary surface; user navigates when they want to hunt |
| Input model | One company per turn; company name + filters |
| Filter seeding | Use `professional_title` + career prefs from `UserProfile`; **always confirm in chat**; ask for anything missing |
| Sources | **Company careers pages / ATS boards only** — Greenhouse, Ashby, Lever, Workday, SmartRecruiters, Teamtailor, Recruitee, BambooHR, Phenom, iCIMS, Rippling, Workable, Pinpoint, Breezy, custom `careers.*` when fetchable |
| Explicitly out | Job boards / aggregators (Indeed-style and peers). Never name specific job-board brands in user-facing copy (existing RoleMule rule) |
| Apply behavior | **Discover + analyze only** — RoleMule never submits applications to employers. User applies themselves |
| Rate limit (analyze) | Existing `workflow_start` limit: **30 / hour / user** — no extra “max N picks” cap |
| Rate limit (chat/search) | Separate limiter for finder turns (see §6.4) so search abuse ≠ burn analyze quota |
| LLM gate | `require_user_llm_context` → `CFG_6001` when not ready |
| Profile gate | `get_current_user_with_complete_profile` (same as workflow start) |
| Design | Same UX/UI: CSS variables, Outfit, accent gradient, cards, toasts, confirm-modal, mobile scrollable patterns — **not** a foreign chatbot skin |
| Manual paths | Keep New Application (paste/upload) + Chrome extension as parallel ingest |
| Landing / marketing | Job Finder is a hero capability; update landing showcase + README after UI ships |

### 0.3 “Discover + analyze only” (canonical wording)

| RoleMule does | RoleMule does **not** |
|---------------|------------------------|
| Find careers pages and list open roles | Click Apply / Submit on employer sites |
| Let user pick roles and start analysis | Auto-fill + auto-submit ATS forms |
| Run Job Analyzer → Match → Research → docs | Send applications, emails, or outreach for the user |
| Provide materials so the user can apply | Impersonate the user on third-party sites |

UI copy must say: **Add to applications** / **Analyze** — never “Apply” / “Auto-apply” / “Submit application”.

### 0.4 Non-negotiables (from `.cursorrules`)

- Never raise bare `HTTPException` — `APIError` / helpers from `utils/error_responses.py`
- Background tasks use `get_session()`, not request-scoped `get_database()`
- All `run_in_executor` LLM calls wrapped in `asyncio.wait_for()`
- `thinking_budget=0` in every Gemini `GenerateContentConfig`
- Top-level background `except`: `await report_exception(exc, user_id=...)` + `logger.error(..., exc_info=True)`
- SSRF: never fetch arbitrary user URLs; allowlist ATS hosts; `redirect="error"`; block private IPs
- Never name specific job-board brands in user-facing copy
- No `style=` HTML attributes; nonce on every `<style>` block
- No native `confirm()` / `alert()` / `prompt()` — `window.showConfirm()`
- No dynamically injected `<style>` from JS
- Integration tests in `tests/test_api/`; agent/unit in `tests/test_agents/` and `tests/test_utils/`
- Dynamic logs: `%s` + `sanitize_log_value()`; never wrap `%d`/`%f` args
- `escapeHtml` / `decodeEntities` rules for any LLM or job-title strings in DOM
- Reuse `RES_3002` for duplicates when starting workflows from finder picks
- Do not invent a second workflow-start path — call existing `start_workflow` internals or HTTP-equivalent shared service

### 0.5 Rules to read before coding

| Area | File |
|------|------|
| Core / CFG_6001 / RES_3002 / workflow failure | `.cursor/rules/rolemule-core.mdc` |
| Agents / standalone / grounding | `.cursor/rules/agent-patterns.mdc` |
| LLM / streaming / BYOK | `.cursor/rules/llm-integration.mdc` |
| WebSocket / speak_delta pattern | `.cursor/rules/websocket-patterns.mdc` |
| Cache / rate limits | `.cursor/rules/caching-redis.mdc` |
| Dashboard home | `.cursor/rules/dashboard-home.mdc` |
| Frontend TS / CSP | `.cursor/rules/frontend-js-strict.mdc` |
| Mobile | `.cursor/rules/mobile-responsive.mdc` |
| New feature checklist | `.cursor/rules/adding-new-features.mdc` |
| DB / JSONB / migrations | `.cursor/rules/database-patterns.mdc` |
| Security / uploads | `.cursor/rules/security-python.mdc` |
| Landing | `.cursor/rules/landing-page.mdc` |
| Unit / API / e2e tests | `.cursor/rules/unit-testing.mdc`, `.cursor/rules/e2e-testing.mdc` |
| Parallel plan style | `docs/hiring-outreach-web-plan.md` |

### 0.6 Learn from OSS (do not copy illegally — learn patterns)

| Repo | Stars (approx) | Steal pattern (not code wholesale) |
|------|----------------|-------------------------------------|
| [santifer/career-ops](https://github.com/santifer/career-ops) | ~60k | Provider modules per ATS; registry; SSRF host allowlists; `redirect:'error'`; normalize job → `{title,url,company,location,postedAt}`; trust flags; zero-token fetch before LLM |
| [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) | ~24k | Human-in-the-loop; structured evaluate-then-act; honest gaps |
| [Pickle-Pixel/ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot) | ~1.3k | Multi-stage discover→score→tailor; **we stop before auto-submit** |
| [Liam-Frost/AutoApply](https://github.com/Liam-Frost/AutoApply) | ~100 | Human-gated submission philosophy |
| [noble-ronin/ats-job-apis](https://github.com/noble-ronin/ats-job-apis) | — | Endpoint cheat-sheet for public ATS JSON feeds |
| RoleMule Practice Interview | (internal) | WS `speak_delta` streaming + poll fallback |
| RoleMule Hiring Outreach | (internal) | Standalone agent + Redis lock + CFG_6001 + docs/rule pattern |

**Architecture lesson from career-ops:** LLM finds/resolves the board; **HTTP adapters fetch jobs** (cheap, deterministic). Never ask the LLM to invent the job list.

### 0.7 Implementation map

| ID | Item | Phase |
|----|------|-------|
| **#1** | Locked product + threat model + schemas | 0 |
| **#2** | DB: finder sessions / messages JSONB + migration | 1 |
| **#3** | SSRF-safe HTTP client + host allow/block lists | 1 |
| **#4** | Provider interface + registry + job normalizer | 1 |
| **#5** | Tier-1 ATS providers (Greenhouse, Ashby, Lever, Workday, SmartRecruiters) | 2 |
| **#6** | Tier-2 ATS providers + careers HTML/JSON detectors | 3 |
| **#7** | Careers resolver agent (company → verified board) | 4 |
| **#8** | Chat orchestrator (`utils/job_finder/orchestrator.py`) | 5 |
| **#9** | API + Redis locks/cache + WS events | 6 |
| **#10** | Star UI page (Find jobs) + Applications CTA | 7 |
| **#11** | Add-to-applications → workflow start bridge | 8 |
| **#12** | Docs, rules, landing, CHANGELOG, e2e smoke | 9 |

### 0.8 Execution order

```
Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9
```

**Do not skip phase exit criteria.** Each phase ends with **code review + tests** before the next.

Phases 2 and 3 can partially parallelize after Phase 1 exit (different providers), but Phase 4 must not start until at least Tier-1 providers pass tests.

### 0.9 Quality bar

- **Clean:** Thin API; providers are pure fetch/normalize; agent owns language; orchestrator owns state machine.
- **Maintainable:** One file per ATS provider; shared types; registry auto-discovers; no god-module.
- **Scalable:** Redis cache for board listings (TTL); NX lock per finder conversation turn; connection limits unchanged on `/ws/user`.
- **High performance:** Prefer zero-LLM listing once board URL is known; stream only chat text; parallel provider probes with tight timeouts; cache verified company→board mappings per user (and optionally global slug cache with short TTL).

### 0.10 Out of scope (this project)

- Auto-apply / form submission to employers
- Job-board / aggregator scraping
- Multi-company batch search in one turn
- Salary scraping products / paid job-data APIs (unless later decided)
- Replacing New Application or the Chrome extension
- Changing the 5-agent workflow graph
- CLI commands for Job Finder (future; web-first)
- Auto-adding onboarding tour steps (optional follow-up in Phase 9 if product wants)

---

## 1. User experience (star feature)

### 1.1 Information architecture

```
Login → /dashboard (Applications) ──CTA──► /dashboard/find-jobs (chat)
                │
                ├── New Application (paste/upload) — kept
                ├── Career Tools — kept
                └── Application detail — unchanged
```

- **Applications remains home.** Do not default new users to Find jobs.
- Prominent **Find jobs** action card on dashboard home (peer to New Application / Tools), visually elevated (icon, short benefit line) so the feature is discoverable without stealing the home list.
- Navbar: optional link “Find jobs” in dashboard nav **or** rely on action card only (prefer **action card + optional nav link** for discoverability; keep nav uncluttered — match existing Help/Settings pattern).

### 1.2 Chat flow (canonical)

1. **Open Find jobs**
2. Bot loads profile: `professional_title`, location (`city`/`state`/`country`), `job_types`, `work_arrangements`, salary/company-size prefs when present.
3. Bot **proposes filters** in plain language and asks for confirmation / edits.  
   Example: *“I’ll look for roles matching **Senior Backend Engineer**, preferring **remote / hybrid**, full-time. Change anything?”*
4. If critical fields missing (no title, no location preference when user cares about geo), bot **asks**.
5. After confirm: *“Which company first?”*
6. User: company name (+ optional extra filters for this turn).
7. System: resolve careers board → fetch → filter → render **picker cards** in the transcript.
8. User selects one or more roles → **Add to applications**.
9. Each selection triggers workflow start (respect 30/hr). Toast + Applications list update via existing WS/`notifyReady` patterns.
10. Bot: *“Want another company?”*

### 1.3 UI components (design system)

Use existing tokens from `ui/static/css/base/variables.css` and patterns from `app.css`:

| Component | Spec |
|-----------|------|
| Page shell | `.page-container`, dashboard navbar include |
| Chat column | Full-height flex column; transcript scroll; composer sticky bottom |
| Bubbles | Bot: `--bg-card` / subtle border; User: accent-tinted; max-width ~720px; radius `--radius-lg` |
| Composer | Textarea + send button `.btn.btn-primary`; Enter to send, Shift+Enter newline |
| Filter chips | Removable chips for confirmed filters (title, remote, location…) |
| Job picker | Card list: title, location, ATS badge (generic “Careers” / provider id for debug only), checkbox/select, primary CTA **Add to applications** |
| Empty / error | Friendly empty states (icon + title + helper), never raw exceptions |
| Loading | Typing indicator + skeleton cards while listing loads |
| Mobile | Composer safe-area; transcript `overflow-y: auto`; chips wrap; picker cards full width; follow `mobile-responsive.mdc` |
| A11y | `role="log"` / `aria-live="polite"` on transcript; focus management after bot reply; keyboard selectable cards |

**Do not:** Inter font, purple-on-white chatbot skin, floating promo badges, native dialogs, inline `style=`.

### 1.4 Copy guidelines

- Prefer: “Find jobs”, “Add to applications”, “Analyze this role”, “company careers page”
- Avoid: “Auto-apply”, “Apply for me”, naming Indeed/LinkedIn/etc.
- Errors: actionable (“We couldn’t open that careers page — paste the careers URL, or try another company.”)

### 1.5 States

| State | UX |
|-------|-----|
| No API key (`CFG_6001`) | Same `showApiKeyAlert()` / Settings AI Setup link pattern as New Application |
| Profile incomplete | Hard redirect `/profile/setup` |
| Rate limited (finder or workflow) | Toast with retry timing; stay on page |
| Duplicate (`RES_3002`) | Warning-style message; keep other selections |
| Board not found | Ask for careers URL paste OR next company |
| Zero jobs after filters | Show count + offer to relax filters |
| Partial provider failure | Show what we found; note if some sources failed |

---

## 2. System architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Find jobs UI (Vite page)                                   │
│  composer → POST /job-finder/chat  |  WS deltas on /ws/user │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│  api/job_finder.py                                          │
│  auth · rate limit · CFG_6001 · session CRUD                │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│  JobFinderOrchestrator (`utils/job_finder/orchestrator.py`) │
│  state machine: greet → confirm_filters → await_company →   │
│  resolve → list → await_pick → add_apps → await_company     │
└───────┬─────────────────────────────┬───────────────────────┘
        │                             │
        ▼                             ▼
┌───────────────────┐       ┌───────────────────────────────┐
│ CareersResolver   │       │ ProviderRegistry              │
│ Agent (grounded)  │       │ greenhouse · ashby · lever ·  │
│ → candidate URLs  │       │ workday · … · generic         │
│ → VERIFY via HTTP │       │ SSRF-safe fetch + normalize   │
└───────────────────┘       └───────────────┬───────────────┘
                                            │
                                            ▼
                                NormalizedJob[] → filter → UI
                                            │
                                            ▼
                    sequential POST workflow/start (existing)
```

### 2.1 Separation of concerns

| Module | Responsibility |
|--------|----------------|
| `utils/job_finder/http.py` | SSRF-safe GET/POST JSON/text |
| `utils/job_finder/blocklists.py` | Job-board host blocklist; private IP ranges |
| `utils/job_finder/normalize.py` | Canonical `NormalizedJob` dataclass |
| `utils/job_finder/providers/*` | One provider per ATS |
| `utils/job_finder/registry.py` | Detect provider from URL; try fetch |
| `agents/job_finder_resolver.py` | Company name → candidate careers URLs (LLM+grounding) |
| `agents/job_finder_chat.py` | Conversational phrasing / intent parse (optional thin) |
| `utils/job_finder/orchestrator.py` | State machine + tool calls (**no new top-level `services/` package** — repo uses `api/` + `utils/` + `agents/`) |
| `api/job_finder.py` | HTTP + WS broadcasts |
| `ui/src/pages/job-finder.ts` | Star UI |

### 2.2 Data model

**New table (preferred): `job_finder_sessions`**

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK users | index |
| `status` | str | `active` / `archived` |
| `confirmed_filters` | JSONB | title, locations, arrangements, job_types, keywords, extras |
| `messages` | JSONB | ordered chat messages (role, content, meta, ts) |
| `last_board` | JSONB | `{provider, board_url, company_name, fetched_at}` |
| `last_listings` | JSONB | cached normalized jobs for last fetch (cap size) |
| `created_at` / `updated_at` | timestamptz | |

Alternative (lighter): store finder state only in Redis with TTL + optional Postgres for history. **Prefer Postgres JSONB** for supportability and “resume chat” — mirror Hiring Outreach persistence philosophy.

**Do not** put finder chat history on `workflow_sessions` — those rows are per application.

Migration ID: next after `20260715_027` → e.g. `20260720_028_add_job_finder_sessions`.

### 2.3 Message meta schema (lock early)

```json
{
  "id": "uuid",
  "role": "assistant|user|system",
  "content": "markdown-safe plain text",
  "created_at": "ISO-8601",
  "meta": {
    "type": "text|filter_proposal|job_picker|status|error",
    "filters": {},
    "jobs": [
      {
        "id": "provider:external_id",
        "title": "",
        "company": "",
        "location": "",
        "url": "https://...",
        "description_text": "optional truncated",
        "provider": "greenhouse",
        "posted_at": null
      }
    ],
    "selected_job_ids": []
  }
}
```

Hard caps: `last_listings` ≤ 100 jobs; description_text ≤ 8k chars per job when persisting; full description fetched again at analyze time if needed.

### 2.4 Normalized job (providers output)

```python
@dataclass(frozen=True)
class NormalizedJob:
    provider: str
    external_id: str
    title: str
    company: str
    location: str
    url: str                 # https only
    description_html: str | None
    description_text: str | None
    posted_at: datetime | None
    raw: dict | None         # debug only; strip before client if large
```

### 2.5 InputMethod for workflow

Current `InputMethod` values (`workflows/state_schema.py`): `url` | `manual` | `file` | `text` | `extension`.

**Add** `InputMethod.JOB_FINDER = "job_finder"` for analytics and job_input_data provenance (update any exhaustiveness checks / tests).

When starting from finder:

- `job_text` = cleaned description (required; respect `MAX_TEXT_LENGTH = 50000`)
- `job_url` / `source_url` = posting URL (http/https only; discarded otherwise — existing guard)
- `detected_title` / `detected_company` = from listing when available
- `source` = `job_finder`
- `input_method` = `job_finder`

---

## 3. Security & compliance

### 3.1 SSRF hardening (mandatory — learn from career-ops + RoleMule)

RoleMule already documents SSRF rules in `.cursor/rules/security-python.mdc` and has `_validate_job_url` in `agents/job_analyzer.py`. Job Finder **adds controlled allowlisted fetches** (new capability) — still never “fetch any user URL as JD.”

- HTTPS only
- DNS resolve and reject private/link-local/metadata IPs (`127.0.0.0/8`, `10.0.0.0/8`, `169.254.169.254`, etc.) — same ranges as security-python checklist
- Host must match **provider allowlist** OR pass **careers-host heuristic** after resolver verification
- `redirect="error"` (or manual redirect with re-validation per hop) — career-ops tests this explicitly
- Timeouts: connect 3s, total 15s (listings); 20s for Workday POST; always set httpx timeout
- Response size cap (e.g. 5 MB)
- User-Agent: RoleMule bot string + contact URL
- Reuse / extend shared helpers rather than duplicating IP checks in every provider

### 3.2 Job-board blocklist

Maintain `JOB_BOARD_HOST_SUFFIXES` (examples — expand in implementation; **do not echo brand names in UI errors**):

- Major aggregator / job-board host suffixes
- URL shorteners (from career-ops trust list): `bit.ly`, `t.co`, etc.

If resolver returns a blocked host → discard candidate and continue / ask for careers URL.

### 3.3 Prompt injection

- Treat careers HTML as untrusted
- Strip scripts; convert to text with bleach/html2text pattern already used in project
- Never execute page JS (no Playwright in v1 unless Phase 3 explicitly adds a sandboxed fetcher later)

### 3.4 Privacy

- Finder sessions owned by `user_id`; all GETs check ownership
- Do not log full JD text at info level — sanitize / truncate
- BYOK keys never leave existing encryption paths

---

## 4. Providers roadmap

### Tier 1 (Phase 2) — must ship

| Provider | Detection | Fetch |
|----------|-----------|-------|
| Greenhouse | `boards.greenhouse.io`, `job-boards.greenhouse.io` | `boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` |
| Ashby | `jobs.ashbyhq.com` | Ashby posting API / GraphQL public board |
| Lever | `jobs.lever.co`, `jobs.eu.lever.co` | `api.lever.co/v0/postings/{slug}?mode=json` |
| Workday | `*.myworkdayjobs.com` | CXS POST jobs endpoint (parse tenant/site) |
| SmartRecruiters | SmartRecruiters careers hosts | public postings API |

### Tier 2 (Phase 3)

Teamtailor, Recruitee, BambooHR, Workable, Breezy, Pinpoint, Rippling, Phenom, Jobvite, Personio (XML), SuccessFactors/CSOD where public search exists.

### Tier 3 — generic careers

1. Resolver returns company careers URL.
2. Detector looks for embedded ATS widgets / known script hosts / JSON-LD `JobPosting`.
3. If JSON-LD list present → normalize.
4. Else → graceful failure + ask user to paste careers ATS URL or use New Application.

**Performance:** registry tries detect() cheaply (URL regex) before network; only one provider fetches.

---

## 5. Agents

### 5.1 CareersResolverAgent

**File:** `agents/job_finder_resolver.py`

**Input:** company name, optional user location hint, confirmed filters (for query phrasing only).

**Output JSON:**

```json
{
  "company_name": "normalized",
  "candidates": [
    {"url": "https://...", "provider_hint": "greenhouse|ashby|lever|workday|unknown", "confidence": "high|medium|low"}
  ],
  "notes": "short"
}
```

**Rules:**

- Use grounding when enabled (`job_finder_grounding_enabled`, default True; off for Ollama) — clone `_should_enable_grounding` pattern from `agents/company_research.py`
- Prefer official careers / ATS URLs
- Never return blocked job-board hosts
- Max 5 candidates
- Orchestrator **must verify** each candidate with ProviderRegistry before accepting

### 5.2 Chat / intent (thin)

Prefer deterministic orchestrator state machine over a free-form agent for tool selection. Optional small LLM call to parse user reply into `{company, filter_overrides, intent}` when not a simple button click.

Intents: `confirm_filters` | `edit_filters` | `set_company` | `select_jobs` | `paste_careers_url` | `relax_filters` | `done` | `help`

---

## 6. API design

### 6.1 Router

`api/job_finder.py` registered at `/api/v1/job-finder` (+ legacy `/api/job-finder` `include_in_schema=False` if project convention requires).

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/sessions` | Create finder session; seed filter proposal from profile |
| `GET` | `/sessions/active` | Resume active session or 404 |
| `GET` | `/sessions/{id}` | Session + messages (ownership) |
| `POST` | `/sessions/{id}/messages` | User turn → orchestrate → assistant messages |
| `POST` | `/sessions/{id}/select` | Selected job ids → start workflows |
| `POST` | `/sessions/{id}/careers-url` | Manual careers URL fallback |
| `DELETE` | `/sessions/{id}` | Archive / clear |

### 6.2 Select → workflow bridge

`POST .../select` body:

```json
{ "job_ids": ["greenhouse:123", "greenhouse:456"] }
```

For each job:

1. Ensure description_text present (re-fetch single job if needed). Sanitize with `sanitize_html` / text extract via `utils/security.py` patterns before persist/start.
2. Call shared internal helper wrapping workflow start logic (prefer extracting `start_workflow_from_fields(...)` from `api/workflow.py` to avoid HTTP self-calls).
3. Collect results: `{ job_id, ok, application_id?, session_id?, error_code? }`.
4. Return summary; emit WS events as workflows run (existing workflow broadcasts).

Partial success is OK (some `RES_3002`, some started).

**Critical — `workflow_creating:{user_id}` lock:**  
`POST /workflow/start` uses Redis `SET NX EX 10` per user (`api/workflow.py`). Multi-select **must start workflows sequentially** (await each start + lock release), not in parallel. Parallel starts will 429 (“A workflow is already being created”). Document this in API + UI (“Adding 1 of N…”). Optional small backoff if lock contention still races.

### 6.3 WebSocket events (on `/ws/user`)

| type | when |
|------|------|
| `job_finder_assistant_delta` | streamed tokens (optional) |
| `job_finder_message` | complete assistant message (incl. picker meta) |
| `job_finder_status` | resolving / fetching / filtering |
| `job_finder_error` | turn failed |

Clone envelope shape from `api/websocket.py`. Frontend: listen on existing `rolemule:ws` bus (`navbar-notifications.ts`).

Streaming is optional in first UI ship; **status + final message** is enough if deltas slip. Prefer deltas for star feel if cheap (reuse `generate_stream` patterns from mock interview).

### 6.4 Rate limits

| Action | Limit | Key |
|--------|-------|-----|
| Chat turn (`POST .../messages`) | **30 / hour / user** | `{user_id}:job_finder_chat:30ph` |
| Resolve+fetch heavy turn | count inside chat turn (same bucket) | — |
| Select → workflow start | existing **30 / hour** | `{user_id}:workflow_start:30ph` |

Tune chat limit in settings if needed; document in `caching-redis.mdc`.

### 6.5 Redis

| Key | Purpose | TTL |
|-----|---------|-----|
| `job_finder_turn:{user_id}:{session_id}` | NX lock concurrent turns | 60–120s |
| `job_finder_board:{provider}:{slug}` | Cached listing payload | 15–30 min |
| `job_finder_company_map:{hash(company)}` | Verified board URL cache | 24h |

Fail open on Redis errors for locks only if safe; prefer fail closed on duplicate concurrent turns (`RES_3003` / conflict) like interview prep.

### 6.6 Settings

Add `job_finder_grounding_enabled: bool = True` in `config/settings.py` (env `JOB_FINDER_GROUNDING_ENABLED`).

---

## 7. Frontend execution

### 7.1 Files to add/change

| File | Change |
|------|--------|
| `ui/dashboard/find-jobs.html` | New page template |
| `ui/src/pages/job-finder.ts` | Page logic |
| `ui/src/job-finder/*` | modules: api, render, ws, filters, picker |
| `ui/vite.entries.json` | Register `job-finder` |
| `main.py` | `GET /dashboard/find-jobs` |
| `ui/dashboard/index.html` | Action card CTA |
| `ui/partials/navbar_dashboard.html` | Optional Find jobs link |
| `ui/static/css/` or page `<style nonce>` | Finder-specific layout using CSS variables |

### 7.2 Frontend behaviors

- `loadUserData()` + profile_completed redirect (clone dashboard-home)
- Open `/ws/user` before first message if streaming
- Polling fallback: GET session every 3s while `status=working` if no WS
- `CFG_6001` → `showApiKeyAlert()`
- `RES_3002` → warning toast (shared helper)
- `escapeHtml` for all titles/companies in picker; `decodeEntities` for `textContent`
- `data-action` delegation for send / select / confirm filters
- After successful select: `addTrackedSession` + optional redirect prompt via `showConfirm` (“View Applications?”) — default stay in chat for multi-company flow

### 7.3 Performance UX

- Optimistic user bubble insert
- Disable send while turn in flight
- Skeleton picker (3 cards)
- Cache last listings in session memory to re-filter client-side when user says “remote only” without re-fetch when possible

---

## 8. Phased execution

---

### Phase 0 — Prep & lock

**Effort:** 0.5 day  
**Shippable:** Doc only

#### Tasks

- [ ] Create branch `feat/job-finder-chat` from current mainline
- [ ] Confirm next Alembic revision after `20260715_027`
- [ ] Skim: `api/workflow.py` start path, `api/websocket.py` speak_delta, `agents/company_research.py` grounding, `docs/hiring-outreach-web-plan.md`, career-ops `providers/greenhouse.mjs` patterns
- [ ] Finalize blocklist v0 host suffixes in this doc’s appendix (engineering-only; not shown in UI)

#### Code review

- [ ] Product decisions table matches latest user locks (Applications home; no pick cap; discover+analyze only; all careers ATS)

#### Tests

- None

#### Exit criteria

- [ ] Branch exists; this doc is source of truth

---

### Phase 1 — Foundation (DB, HTTP, types, registry shell)

**Effort:** 1–2 days  
**Shippable alone:** Yes (no UI)

#### Tasks

- [ ] Migration `job_finder_sessions` + SQLAlchemy model + `to_dict()`
- [ ] `utils/job_finder/http.py` SSRF-safe client
- [ ] `blocklists.py`, `normalize.py`, `types.py`
- [ ] `providers/base.py` Protocol: `detect(url) -> bool`, `fetch(url) -> list[NormalizedJob]`
- [ ] `registry.py` with empty/ provider stubs
- [ ] Settings flag `job_finder_grounding_enabled`
- [ ] Unit tests for SSRF cases (private IP, bad scheme, redirect, oversize)

#### Code review

- [ ] No bare HTTPException
- [ ] Allowlist + blocklist coverage
- [ ] JSONB `flag_modified` plan documented for messages updates

#### Tests

- [ ] `tests/test_utils/test_job_finder_http.py`
- [ ] `tests/test_utils/test_job_finder_blocklists.py`
- [ ] Migration upgrade/downgrade smoke if project has pattern

#### Exit criteria

- [ ] Can register a fake provider and fetch via registry in unit test

---

### Phase 2 — Tier-1 providers

**Effort:** 2–3 days  
**Shippable alone:** Yes (library)

#### Tasks

- [ ] Implement Greenhouse, Ashby, Lever, Workday, SmartRecruiters
- [ ] HTML→text helper for Greenhouse `content`
- [ ] Provider unit tests with **fixture JSON** (no live network in CI)
- [ ] Optional `@pytest.mark.integration` live smoke (manual/local)

#### Code review

- [ ] Each provider: host assert, `redirect=error`, timeout, normalize URLs https
- [ ] Workday tenant parsing edge cases covered
- [ ] No job-board hosts accepted as provider boards

#### Tests

- [ ] `tests/test_utils/test_job_finder_providers_tier1.py` (fixtures under `tests/fixtures/job_finder/`)

#### Exit criteria

- [ ] All Tier-1 providers pass fixture tests
- [ ] Registry detect→fetch works for sample URLs

---

### Phase 3 — Tier-2 providers + generic detector

**Effort:** 2–4 days  
**Shippable alone:** Yes (library expansion)

#### Tasks

- [ ] Teamtailor, Recruitee, BambooHR, Workable, Breezy, Pinpoint, Rippling (+ Phenom if stable)
- [ ] JSON-LD `JobPosting` extractor for generic careers pages
- [ ] Detector that inspects HTML for known ATS script markers → re-route to Tier-1/2
- [ ] Expand fixtures

#### Code review

- [ ] Generic path cannot fetch blocked hosts
- [ ] Fail soft with typed errors (`BoardNotFound`, `UnsupportedCareersPage`)

#### Tests

- [ ] `tests/test_utils/test_job_finder_providers_tier2.py`
- [ ] `tests/test_utils/test_job_finder_jsonld.py`

#### Exit criteria

- [ ] ≥10 providers green on fixtures
- [ ] Generic detector unit-tested with sample HTML

---

### Phase 4 — Careers resolver agent

**Effort:** 1–2 days  
**Shippable alone:** Yes (agent + tests)

#### Tasks

- [ ] `agents/job_finder_resolver.py` + JSON schema + sanitization
- [ ] Grounding gate + Ollama off
- [ ] Orchestrator helper: resolve → verify via registry → return board or error
- [ ] Company map cache helpers in `utils/cache.py`

#### Code review

- [ ] CFG_6001 only via `require_user_llm_context` at API boundary (agent assumes key present)
- [ ] Candidates filtered through blocklist
- [ ] `thinking_budget=0`; `asyncio.wait_for`

#### Tests

- [ ] `tests/test_agents/test_job_finder_resolver.py` (mock LLM + mock registry verify)

#### Exit criteria

- [ ] Given mocked grounded response with Greenhouse URL, verify path returns normalized jobs from fixture provider

---

### Phase 5 — Orchestrator (conversation state machine)

**Effort:** 2 days  
**Shippable alone:** Partially (service tests)

#### Tasks

- [ ] `utils/job_finder/orchestrator.py`
- [ ] Filter seeding from `UserProfile`
- [ ] States: `propose_filters` → `await_filter_confirm` → `await_company` → `resolving` → `listing` → `await_selection` → `post_select`
- [ ] Client-side refilter support when listings cached
- [ ] Intent parsing (rules first; LLM fallback)

#### Code review

- [ ] One company per turn enforced
- [ ] No workflow start inside resolve/list — only on select
- [ ] Message list append always `flag_modified`

#### Tests

- [ ] `tests/test_utils/test_job_finder_orchestrator.py`

#### Exit criteria

- [ ] Full happy-path unit test: confirm filters → company → list → select ids returned for bridge

---

### Phase 6 — API + Redis + WebSocket

**Effort:** 2 days  
**Shippable alone:** Yes (API with mocked orchestrator)

#### Tasks

- [ ] `api/job_finder.py` endpoints
- [ ] Register router in `main.py` `include_routers()` under `/api/v1/job-finder` **and** legacy `/api/job-finder` with `include_in_schema=False` (match hiring-outreach / interview-prep pattern)
- [ ] Rate limits + turn lock
- [ ] WS broadcast helpers in `api/websocket.py`
- [ ] Update `.cursor/rules/websocket-patterns.mdc` + `.cursor/rules/caching-redis.mdc` (new keys/TTLs)

#### Code review

- [ ] Ownership checks on every session id
- [ ] `report_exception` on background paths if any
- [ ] Error codes: `CFG_6001`, `RATE_4xxx`, `RES_3001/3003`, validation

#### Tests

- [ ] `tests/test_api/test_job_finder.py` — auth, CFG_6001, 429, ownership, select partial success
- [ ] WS unit/integration if existing patterns allow

#### Exit criteria

- [ ] API green in CI with mocks; OpenAPI shows `/api/v1/job-finder/*`

---

### Phase 7 — Star UI

**Effort:** 2–3 days  
**Shippable alone:** Yes (behind route; wire CTA)

#### Tasks

- [ ] `find-jobs.html` + `job-finder.ts` + modules
- [ ] Vite entry + `make build-frontend`
- [ ] Dashboard action card (elevated copy)
- [ ] Filter chips, picker, composer, empty/error/loading
- [ ] Mobile pass + a11y pass
- [ ] Match design tokens; screenshot candidate for landing later

#### Code review

- [ ] CSP / no inline styles / event delegation
- [ ] `escapeHtml` / `decodeEntities`
- [ ] Profile redirect + logout handler on page
- [ ] Visual polish checklist (§1.3)

#### Tests

- [ ] E2E mocked: `e2e/tests/job-finder.spec.ts` (+ `@smoke` subset if stable)
- [ ] `rate-limit.spec.ts` entry for finder 429
- [ ] `api-validation.spec.ts` mock render smoke

#### Exit criteria

- [ ] Manual UX review on desktop + mobile width
- [ ] Feature usable end-to-end against local mocks

---

### Phase 8 — Add-to-applications bridge

**Effort:** 1–2 days  

#### Tasks

- [ ] Extract or call shared workflow start helper with finder fields
- [ ] Add `InputMethod.JOB_FINDER` / `source=job_finder`
- [ ] Wire select endpoint → **sequential** starts (respect `workflow_creating` 10s NX lock)
- [ ] Frontend progress: “Adding 1 of N…”; handle mixed `RES_3002` / success / 429
- [ ] Ensure dashboard list updates (WS + poll already)

#### Code review

- [ ] Releases `workflow_creating` lock on duplicate (existing path)
- [ ] No parallel `start_workflow` for same user
- [ ] Fingerprint / URL dedupe still apply
- [ ] No “Apply” wording in UI
- [ ] Descriptions sanitized before start

#### Tests

- [ ] API tests for select→start (single + multi sequential)
- [ ] Simulated lock contention / ordering test
- [ ] Dedupe cases from finder-originated text/url
- [ ] Analytics hook if events need `source=job_finder`

#### Exit criteria

- [ ] Real local run: find fixture company → select → application appears → workflow progresses

---

### Phase 9 — Docs, marketing, rules, harden

**Effort:** 1–2 days  

#### Tasks

- [ ] `.cursor/rules/job-finder-feature.mdc` (+ Claude mirror if used)
- [ ] Update `CLAUDE.md` / `.cursorrules` indexes
- [ ] `USER_GUIDE.md`, `ui/help.html`, `README.md`, `CHANGELOG.md`
- [ ] Landing page section / screenshot for Job Finder (`landing-page.mdc`)
- [ ] `site/` marketing sync if applicable (`scripts/build_marketing_legal_pages.py`)
- [ ] Feature flag optional? (default on once stable)

#### Code review

- [ ] No job-board brand names in user-facing docs
- [ ] Discover+analyze wording consistent
- [ ] adding-new-features checklist completed

#### Tests

- [ ] Smoke e2e includes Find jobs CTA visible on dashboard
- [ ] Full pytest subset for job_finder green in CI

#### Exit criteria

- [ ] Docs merged; landing updated; rule file exists; CI green

---

## 9. Per-phase “Definition of Done” template

Copy for every phase PR:

```markdown
## Phase N DoD
- [ ] Tasks in plan checked
- [ ] Code review completed (security + RoleMule conventions)
- [ ] Unit/API/e2e tests added as listed
- [ ] `make build-frontend` if UI touched
- [ ] No new bare HTTPException / inline styles / native confirms
- [ ] Logs use sanitize_log_value
- [ ] CHANGELOG note if user-facing
```

---

## 10. Observability

- Structured logs: session_id, user_id, provider, company (sanitized), latency_ms, job_count, cache_hit
- Metrics candidates: resolve_success_rate, provider_fetch_latency, select_start_success, blocklist_hits
- Errors: report_exception on unexpected failures

---

## 11. Performance budget

| Step | Target |
|------|--------|
| Filter proposal (no LLM or 1 tiny call) | < 500ms |
| Company resolve (grounded) | < 8s p95 |
| Tier-1 listing fetch (cached miss) | < 3s p95 |
| Listing fetch (cache hit) | < 200ms |
| Chat stream first token | < 1.5s when streaming |
| Select N jobs | N × workflow accept path; UI non-blocking |

Cache board listings aggressively; do not re-ground company on every filter tweak.

---

## 12. Risk register

| Risk | Mitigation |
|------|------------|
| Resolver returns job boards | Blocklist + verify |
| Workday URL variance | Robust parser + fixtures + fallback paste URL |
| Grounding cost/latency | Cache company→board; Flash model; short prompts |
| Users expect auto-apply | Clear copy; never label CTA “Apply” |
| Scope creep (50 providers) | Tier-1 ship gate; Tier-2 follow; generic last |
| SSRF | Dedicated http module + tests |
| Chat becomes unmaintainable free-form | State machine first |
| Duplicate floods | Existing 30/hr + RES_3002 |
| Multi-select hits `workflow_creating` lock | Sequential starts + UI progress |
| HTML JD XSS | `sanitize_html` / text extract before persist and render |

---

## 13. Analytics (optional but recommended)

Events:

- `job_finder_opened`
- `job_finder_filters_confirmed`
- `job_finder_company_searched` (provider, success)
- `job_finder_jobs_listed` (count)
- `job_finder_jobs_selected` (count)
- `job_finder_workflow_started` (application_id)
- `job_finder_board_not_found`

Respect cookie consent / PostHog patterns in `analytics-consent-onboarding.mdc`.

---

## 14. Rollout plan

1. Merge behind optional env `JOB_FINDER_ENABLED=true` (default true in dev, true in prod when ready).
2. Internal dogfood with Tier-1 only if needed (feature flag `JOB_FINDER_PROVIDERS=tier1`).
3. Enable Tier-2.
4. Marketing push + landing screenshot.
5. Monitor resolve_success_rate and error mix for 1 week.

---

## 15. File tree (target)

```
agents/job_finder_resolver.py
api/job_finder.py
utils/job_finder/
  __init__.py
  http.py
  blocklists.py
  normalize.py
  types.py
  registry.py
  filters.py
  orchestrator.py
  providers/
    __init__.py
    base.py
    greenhouse.py
    ashby.py
    lever.py
    workday.py
    smartrecruiters.py
    teamtailor.py
    ...
    jsonld_generic.py
models/database.py          # JobFinderSession
alembic/versions/20260720_0001_028_add_job_finder_sessions.py
ui/dashboard/find-jobs.html
ui/src/pages/job-finder.ts
ui/src/job-finder/
tests/test_utils/test_job_finder_*.py
tests/test_agents/test_job_finder_resolver.py
tests/test_api/test_job_finder.py
tests/fixtures/job_finder/
e2e/tests/job-finder.spec.ts
docs/job-finder-chat-plan.md  # this file
.cursor/rules/job-finder-feature.mdc
```

---

## 16. Filter seeding map (profile → finder)

| Profile field | Finder filter |
|---------------|---------------|
| `professional_title` | query / title keywords (confirm) |
| `city`, `state`, `country` | location preference (confirm) |
| `job_types` | employment type filter |
| `work_arrangements` | remote/hybrid/onsite filter |
| `desired_company_sizes` | soft preference (ask if use) |
| `desired_salary_range` | optional; often skip for listing filter |
| `willing_to_relocate` | affects location strictness |

`UserWorkflowPreferences` (tone, gate threshold, etc.) are **not** listing filters — do not confuse.

---

## 17. Error catalog (API)

| Situation | Code | HTTP |
|-----------|------|------|
| No LLM ready | `CFG_6001` | 422 |
| Validation | `VAL_2xxx` | 422 |
| Session not found | `RES_3001` | 404 |
| Turn lock busy | `RES_3003` | 409 |
| Chat rate limit | `RATE_4xxx` | 429 |
| Workflow rate limit on select | `RATE_4xxx` | 429 |
| Duplicate app on select item | `RES_3002` | 409 (per item in batch result; batch HTTP 200 with partial errors OK) |

Prefer **HTTP 200 + per-item errors** on `select` for partial success UX.

---

## 18. Manual QA script (pre-release)

1. Incomplete profile → redirect setup  
2. No API key → CFG_6001 banner  
3. Confirm filters → edit title → confirm  
4. Known Greenhouse company → list → select 1 → appears on Applications  
5. Select duplicate → warning, others ok  
6. Blocked aggregator URL pasted → rejected with friendly message  
7. Unknown company → ask careers URL → paste Tier-1 URL → list works  
8. Mobile 375px layout  
9. Keyboard-only send + select  
10. 30th workflow start → 429 handling  

---

## 19. Open questions (resolve in Phase 0 if possible)

| # | Question | Recommendation |
|---|----------|----------------|
| 1 | Nav link + action card, or action card only? | Both: action card primary; subtle nav link |
| 2 | Multi-select default on? | Yes, with clear count + Add CTA |
| 3 | Persist chat across devices? | Yes via Postgres sessions |
| 4 | Playwright for stubborn careers sites? | Not in initial tiers; revisit only if metrics demand |
| 5 | Show provider name in UI? | Soft “via company careers page”; provider id in meta/debug only |
| 6 | Package location for orchestrator? | **Locked:** `utils/job_finder/orchestrator.py` (no new `services/`) |
| 7 | Onboarding tour mention? | Optional Phase 9; not required to ship |

---

## 20. Appendix — engineering blocklist seeds (not UI copy)

Maintain in code as suffixes/domains. Expand over time. **Never print these brand names in user-facing strings** — say “job board links aren’t supported; use the company’s careers page.”

Include major job aggregators, social job tabs, and URL shorteners (see career-ops `_trust-validator.mjs` shortener list as a starting point for shorteners only).

Exact list lives in `utils/job_finder/blocklists.py` when implemented.

---

## 21. Document review log

### Review 1 — Product + repo alignment (2026-07-20)

Checked against:

- Locked UX decisions from product thread (Applications home; filter confirm; no pick cap; discover+analyze; design system; all careers ATS)
- `api/workflow.py` start inputs, 30/hr, RES_3002, locks
- Profile fields (no `target_role`); career prefs as filter source
- `require_user_llm_context` / CFG_6001
- Dashboard routing (`main.py`, action cards in `ui/dashboard/index.html`)
- Hiring outreach plan structure as execution template
- career-ops provider + SSRF patterns

**Fixes applied in this draft:** Applications always default; removed max-3 pick cap; clarified discover+analyze; mapped filters to `UserProfile` not `UserWorkflowPreferences`; explicit workflow bridge; star UI section.

### Review 2 — Phases, security, tests, gaps (2026-07-20)

Re-read:

- `.cursor/rules/adding-new-features.mdc` checklist
- `.cursor/rules/security-python.mdc` SSRF + httpx timeout
- `.cursor/rules/caching-redis.mdc` / websocket-patterns
- WebSocket speak_delta + user bus (`ui/src/mock-interview/`)
- Soft-delete / ownership patterns
- CSP / frontend-js-strict / mobile-responsive
- Next migration after `20260715_027`
- `utils/security.py` bleach/`sanitize_html` for JD HTML
- Risk of LLM inventing jobs → enforced verify-via-provider
- `workflow_creating:{user_id}` NX 10s lock in `api/workflow.py`
- Confirmed **no** top-level `services/` package in repo

**Fixes applied:** SSRF tied to existing RoleMule rules; separate chat vs workflow rate limits; partial success on select; **sequential multi-start** requirement; orchestrator under `utils/job_finder/`; performance budgets; analytics; rollout flag; JSON-LD generic tier; Intent list; DoD template; manual QA script; file tree; error catalog; open questions; legacy router registration; cache rule updates.

### Review 3 — Ship readiness + consistency (2026-07-20)

Re-validated against live repo:

- `InputMethod` currently `url|manual|file|text|extension` — plan adds `job_finder`
- Workflow rate limit key `workflow_start:30ph` / limit 30 confirmed in `api/workflow.py`
- Profile filter fields: `professional_title`, `job_types`, `work_arrangements`, location columns — **not** `UserWorkflowPreferences`
- Vite entry pattern in `ui/vite.entries.json`; dashboard CTA pattern in `ui/dashboard/index.html`
- `RES_3003` exists for lock conflicts
- Controlled allowlisted fetches ≠ removed “fetch any JD URL” product path
- Extension + New Application remain parallel
- Landing/docs phase for star launch; no Auto-apply wording
- Tiered providers = company careers ATS only
- Each phase ends with code review + tests
- CLI / onboarding tour explicitly optional/out of scope for core ship

**Residual follow-ups (non-blocking for Phase 1):** finalize nav-link vs action-card-only (§19 #1); exact blocklist host list in code; `JOB_FINDER_ENABLED` default for prod dogfood.

---

## 22. One-page summary (for stakeholders)

**Job Finder** is a chat on `/dashboard/find-jobs` that finds roles on **company careers pages**, lets users pick them, and runs RoleMule’s normal analysis. **Applications stays home.** RoleMule **does not apply** for the user. Job boards are unsupported. Built in 10 phases with review+tests each; ATS adapters inspired by career-ops; chat/streaming patterns from RoleMule’s Practice Interview; product packaging as a **star feature** with first-class UI and landing presence.
