# Hiring Outreach (Web) — Agent Execution Spec

**Status:** Ready to implement  
**Branch:** `feat/hiring-outreach-web` (from `feat/conversational-mock-interview`)  
**Owner:** Engineering  
**Last updated:** 2026-07-14  

On-demand **Hiring Outreach** for an application: find likely hiring contacts via **public web search grounding** and draft copy-ready messages. **No LinkedIn** (no scrape, API, MCP, or product copy that names LinkedIn). Never auto-send.

---

## 0. Agent instructions (read first)

### 0.1 Goal

On a session with **`job_analysis`** present (Company Research is preferred enrichment, not a hard gate), let the user open a **new standalone application-detail tab** (not the pipeline Company tab) and click **Find who to contact**. ApplyPilot:

1. Uses the user’s BYOK LLM + **web search grounding** (when enabled and not Ollama).
2. Returns 0–4 suggested contacts with **confidence** and evidence from public web sources.
3. Drafts a short outreach note and an email (`subject_line` + `email_body`) per contact (or a generic fallback when no named contact is found).
4. Shows results for **copy only** — user sends from their own tools.

### 0.2 Product decisions (locked)

| Decision | Choice |
|----------|--------|
| Scope | Public web only; strip any LinkedIn URLs from LLM output |
| UX home | **New standalone tab** on application detail (10th tab after Practice Interview) — empty-state CTA + results; same pattern as Optimize CV / Practice Interview. **Not** inside the pipeline Company tab. |
| Lifecycle | Clone Interview Prep: background task, Redis NX lock, JSONB, WS, CFG_6001 |
| Email shape | Clone Follow-up: `subject_line` + `email_body`; no `[bracket]` placeholders |
| Storage | New JSONB `WorkflowSession.hiring_outreach` (migration `027`) |
| Grounding | Settings flag `hiring_outreach_grounding_enabled` (default **True**); Ollama → grounding off |
| Rate limit | **5 generations / hour / user** |
| Prerequisite | `job_analysis` present; prefer usable `company_name` (handle unnamed with degraded path) |

### 0.3 Non-negotiables (from `.cursorrules`)

- Never raise bare `HTTPException` — use `APIError` / helpers from `utils/error_responses.py`
- Every JSONB write: `flag_modified(workflow_session, "hiring_outreach")`
- Background tasks use `get_session()`, not request-scoped `get_database()`
- All `run_in_executor` LLM calls wrapped in `asyncio.wait_for()`
- `thinking_budget=0` in every Gemini `GenerateContentConfig`
- Top-level background `except`: `await report_exception(exc, user_id=...)` + `logger.error(..., exc_info=True)`
- Never fetch user-supplied URLs server-side (SSRF) — grounding is provider-side search only
- Never name specific job sites in **user-facing** copy (use “company website”, “public web”, “news”)
- Never add inline `style=` in templates; nonce on `<style>` blocks
- Never use native `confirm()` / `alert()` in JS
- Integration tests in `tests/test_api/`; agent unit tests in `tests/test_agents/`
- Dynamic logs: `%s` + `sanitize_log_value()`; emails via `mask_email()`
- Sanitize LLM output with `sanitize_llm_output` before persist / cache

### 0.4 Rules to read before coding

| Area | File |
|------|------|
| Core / CFG_6001 / APIError | `.cursor/rules/applypilot-core.mdc` |
| Agents / standalone pattern | `.cursor/rules/agent-patterns.mdc` |
| LLM / grounding | `.cursor/rules/llm-integration.mdc` |
| Interview Prep parallel | `.cursor/rules/interview-prep-feature.mdc` |
| Career tools email rules | `.cursor/rules/career-tools.mdc` |
| Cache / rate limits | `.cursor/rules/caching-redis.mdc` |
| WebSocket broadcasts | `.cursor/rules/websocket-patterns.mdc` |
| Application detail tabs / UI | `.cursor/rules/ui-application-detail.mdc` |
| Frontend TS | `.cursor/rules/frontend-js-strict.mdc` |
| New feature checklist | `.cursor/rules/adding-new-features.mdc` |
| Unit / API tests | `.cursor/rules/unit-testing.mdc` |
| DB / JSONB / migrations | `.cursor/rules/database-patterns.mdc` |

### 0.5 Parallel implementations (clone these)

| Concern | Clone from |
|---------|------------|
| API + BG + lock + WS | `api/interview_prep.py`, `api/websocket.py` (`broadcast_interview_prep_*`) |
| Redis lock + result cache | `utils/cache.py` (`set_interview_prep_generating`, `cache_interview_prep`) |
| Email draft rules | `agents/followup_generator.py` (`CRITICAL WRITING RULES`, `subject_line` / `email_body`) |
| Grounding gate | `agents/company_research.py` (`_should_enable_grounding`, `use_google_search_grounding`) |
| Migration shape | `alembic/versions/20260714_0001_026_add_mock_interview_to_workflow_sessions.py` |
| Standalone tab pattern | Practice Interview / Optimize CV: `data-tab` + `#pane-*` + `init*Tab` on tab switch in `application-detail.ts` |

### 0.6 Implementation map

| ID | Item | Phase |
|----|------|-------|
| **#1** | Migration + model column `hiring_outreach` | 1 |
| **#2** | Redis lock + result cache helpers | 1 |
| **#3** | Settings flag for grounding | 1 |
| **#4** | `HiringOutreachAgent` + JSON schema + sanitizers | 2 |
| **#5** | API router + background task + WS | 3 |
| **#6** | New application-detail tab UI (generate / status / copy) | 4 |
| **#7** | Docs, feature rule, CHANGELOG, indexes | 5 |

### 0.7 Execution order

```
Phase 0 (prep) → Phase 1 (data + cache) → Phase 2 (agent) → Phase 3 (API) → Phase 4 (UI) → Phase 5 (docs)
```

**Do not skip phase exit criteria.** Each phase ends with code review + tests before starting the next.

### 0.8 Quality bar

- **Scalable:** One Redis NX lock per session; result cache on GET; no duplicate concurrent LLM runs.
- **High performance:** HTTP returns immediately after lock claim; single grounded LLM call per generate; poll/WS for completion.
- **Clean:** Thin API; agent owns prompts/mapping; typed response models; confidence always present; no LinkedIn in prompts or UI.

### 0.9 Out of scope

- LinkedIn (any integration or named user-facing copy)
- Auto-send / auto-connect
- Job-board scraping / auto-apply
- Visual resume builder
- Kanban CRM / follow-up reminders
- Live coding interviews

---

## 0.10 Target JSON schema (lock early)

Persist on `workflow_sessions.hiring_outreach`:

```json
{
  "version": 1,
  "generated_at": "<ISO-8601 UTC>",
  "grounding_used": true,
  "company_name": "Acme Corp",
  "job_title": "Backend Engineer",
  "summary": "Short note on search quality / caveats",
  "contacts": [
    {
      "name": "Optional full name or null",
      "role_type": "hiring_manager|recruiter|team_peer|generic",
      "likely_title": "Engineering Manager, Platform",
      "why_them": "Owns the team described in the posting",
      "confidence": "high|medium|low",
      "evidence": "Public company team page / press quote (no private data)",
      "source_hint": "company website|news|other_public",
      "short_message": "≤300 chars outreach note, no placeholders",
      "subject_line": "Email subject",
      "email_body": "Email body, first-name greeting if name known, close with Best regards,"
    }
  ],
  "fallback": {
    "used": false,
    "reason": null,
    "subject_line": null,
    "email_body": null,
    "short_message": null
  }
}
```

Rules:

- Max **4** contacts; may be **0** if none found → set `fallback.used = true` with generic drafts.
- `confidence` required on every contact; UI must show it.
- Strip `linkedin.com` / `lnkd.in` URLs from all string fields before save.
- Ban bracket placeholders (`[Your Name]`, `[Company]`, etc.) — same as career tools.

---

## 1. Phase 0 — Prep

**Estimated effort:** 0.5 day  
**Shippable alone:** N/A (checklist only)

### 1.1 Tasks

- [x] Create branch: `feat/hiring-outreach-web` from `feat/conversational-mock-interview`
- [ ] Skim: `api/interview_prep.py`, `agents/followup_generator.py`, company research grounding path, `render-overview.ts` Company block
- [ ] Confirm next migration: `down_revision = "20260714_026"` → revision `20260715_027` (or same-day `20260714_027` if preferred)
- [x] Confirm error codes: use `ErrorCode.RESOURCE_CONFLICT` (`RES_3003`) + HTTP 409 for lock contention (same as `api/interview_prep.py`)

### 1.2 Code review

- [ ] Confirm no LinkedIn product requirement remains in this doc’s locked decisions

### 1.3 Tests

- None (prep only)

### 1.4 Exit criteria

- [ ] Branch exists locally
- [ ] This plan file is the source of truth for implementation

---

## 2. Phase 1 — Data model + cache + settings

**Estimated effort:** 0.5–1 day  
**Shippable alone:** Yes (schema + helpers; no user-facing feature yet)

### 2.1 Alembic migration

**File:** `alembic/versions/20260715_0001_027_add_hiring_outreach_to_workflow_sessions.py`

```python
# revision = "20260715_027"
# down_revision = "20260714_026"

def upgrade() -> None:
    op.add_column(
        "workflow_sessions",
        sa.Column("hiring_outreach", JSONB, nullable=True),
    )

def downgrade() -> None:
    op.drop_column("workflow_sessions", "hiring_outreach")
```

### 2.2 SQLAlchemy model

**File:** `models/database.py`

- Add `hiring_outreach: Mapped[Optional[Dict[str, Any]]]` next to `mock_interview`
- Include in `to_dict()` as `"hiring_outreach": self.hiring_outreach or {}`
- Update `database-patterns.mdc` JSONB list for `WorkflowSession` when docs phase runs (can note here; formalize in Phase 5)

### 2.3 Settings

**File:** `config/settings.py`

```python
hiring_outreach_grounding_enabled: bool = Field(
    default=True,
    description="Enable provider web-search grounding for hiring outreach LLM calls",
)
```

Env: `HIRING_OUTREACH_GROUNDING_ENABLED` (Pydantic settings convention).

### 2.4 Redis helpers

**File:** `utils/cache.py`

Mirror interview prep:

| Helper | Key pattern | TTL |
|--------|-------------|-----|
| `cache_hiring_outreach` / `get_cached_hiring_outreach` / `invalidate_hiring_outreach` | `v1:hiring_outreach:{session_id}` | 7d |
| `set_hiring_outreach_generating` / `clear_…` / `is_…` | `v1:hiring_outreach_generating:{session_id}` | 10 min (NX) |

Also:

- Add `CACHE_PREFIX_HIRING_OUTREACH` / `CACHE_PREFIX_HIRING_OUTREACH_GENERATING`
- Register required top-level fields in `_CACHE_REQUIRED_FIELDS["hiring_outreach"]`: at least `version`, `contacts`, `fallback`
- Document row in `.cursor/rules/caching-redis.mdc` (Phase 5 may finalize)

### 2.5 Tasks checklist

- [ ] Migration file with upgrade + downgrade
- [ ] Model column + `to_dict()`
- [ ] Settings flag
- [ ] Cache + lock helpers + `_CACHE_REQUIRED_FIELDS`

### 2.6 Code review (Phase 1)

- [ ] `down_revision` points at `20260714_026`
- [ ] Column nullable (existing sessions OK)
- [ ] Lock uses SET NX (atomic claim)
- [ ] Cache keys use `CACHE_VERSION` prefix
- [ ] No secrets in keys/logs

### 2.7 Tests (Phase 1)

**File:** `tests/test_utils/test_hiring_outreach_cache.py` (or extend existing cache tests)

- [ ] `set_hiring_outreach_generating` returns True then False on second claim (mock Redis)
- [ ] `clear_hiring_outreach_generating` allows re-claim
- [ ] `cache_hiring_outreach` / `get_cached_hiring_outreach` round-trip; invalid payload missing `contacts` is evicted
- [ ] Optional: alembic upgrade/downgrade smoke if project has migration test helper

**Command:**

```bash
pytest tests/test_utils/test_hiring_outreach_cache.py -q
```

### 2.8 Exit criteria

- [ ] Migration applies cleanly on empty + existing DB
- [ ] Review checklist complete
- [ ] Phase 1 tests green

---

## 3. Phase 2 — Agent

**Estimated effort:** 1–1.5 days  
**Shippable alone:** Yes (unit-tested agent; no HTTP yet)

### 3.1 New module

**File:** `agents/hiring_outreach.py`

```python
class HiringOutreachAgent:
    async def generate(
        self,
        *,
        job_analysis: Dict[str, Any],
        company_research: Dict[str, Any],
        profile_matching: Dict[str, Any],
        user_profile: Dict[str, Any],
        user_api_key: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        preferred_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...
```

### 3.2 Prompt requirements

`SYSTEM_CONTEXT`:

- Expert career coach helping with **professional outreach** after applying.
- Use **public web** signals only (company site, news, team pages, press).
- **Do not** use or invent LinkedIn profile URLs; if search returns them, omit.
- Prefer hiring manager / recruiter / relevant team peer for **this role**.
- Always set confidence honestly; prefer fewer high-quality contacts over many guesses.
- CRITICAL WRITING RULES (copy from follow-up): no bracket placeholders; first-name greeting when name known; close `Best regards,` without sender full name; no fabricated personal facts.

User prompt includes:

- Company name, job title, key requirements (from `job_analysis`)
- Short company research summary / leadership if present
- Candidate fit highlights (from `profile_matching` / profile) — for drafting only
- Instruction to return **strict JSON** matching schema in §0.10

### 3.3 Grounding

```python
use_grounding = (
    settings.hiring_outreach_grounding_enabled
    and preferred_provider != "ollama"
    # also false when resolved provider is ollama
)
# Pass use_google_search_grounding=use_grounding to get_llm_client().generate(...)
# On grounding failure: retry once with grounding=False (same pattern as company research)
```

Set `grounding_used` in result to what was **actually** used on the successful call.

### 3.4 Post-processing

- Parse JSON; on failure → structured fallback only (no crash)
- Clamp contacts to ≤4
- Normalize `confidence` to `high|medium|low`
- `_strip_linkedin_urls(text)` on all strings
- `_reject_placeholders(text)` — if brackets remain, rewrite or clear field to safe default
- `sanitize_llm_output` on final dict (or recursive string sanitize)
- If `contacts` empty → populate `fallback` with generic email + short message

### 3.5 Tasks checklist

- [ ] Agent module + prompts + mapping helpers
- [ ] Grounding gate + failover
- [ ] LinkedIn URL strip + placeholder guard
- [ ] Empty-contact fallback drafts

### 3.6 Code review (Phase 2)

- [ ] Single LLM call path (plus optional grounding failover) — no N+1 searches in app code
- [ ] `asyncio.wait_for` around executor LLM if applicable
- [ ] No LinkedIn in system/user prompts or user-facing error strings
- [ ] No fabricated emails like `name@company.com` unless clearly marked low confidence / optional omit
- [ ] Prefer omitting personal email addresses unless publicly evidenced (safer: drafts without To: address)

### 3.7 Tests (Phase 2)

**File:** `tests/test_agents/test_hiring_outreach.py`

Mock LLM client (same pattern as other agent tests):

- [ ] Happy path: 2 contacts + drafts; `version == 1`
- [ ] LLM returns invalid JSON → fallback used, no exception
- [ ] Missing company name → degraded / fallback path
- [ ] Grounding disabled / ollama → `use_google_search_grounding=False` asserted on generate mock
- [ ] Response containing `linkedin.com` URL → stripped from stored fields
- [ ] Response containing `[Your Name]` → cleaned / rejected
- [ ] More than 4 contacts → truncated to 4

**Command:**

```bash
pytest tests/test_agents/test_hiring_outreach.py -q
```

### 3.8 Exit criteria

- [ ] Agent review complete
- [ ] Agent tests green
- [ ] No network calls in unit tests

---

## 4. Phase 3 — API + background task + WebSocket

**Estimated effort:** 1–1.5 days  
**Shippable alone:** Yes (API-only; UI can wait)

### 4.1 Router

**File:** `api/hiring_outreach.py`  
**Mount:** `main.py` → `/api/v1/hiring-outreach` (+ legacy `/api/hiring-outreach`, `include_in_schema=False`)

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/{session_id}` | Ownership; cache then DB; 404 if empty |
| `GET` | `/{session_id}/status` | `{ status: idle\|generating\|ready\|error, has_result }` |
| `POST` | `/{session_id}/generate?regenerate=` | CFG_6001 → rate limit → prereq `job_analysis` → NX lock → enqueue BG → 200/202 |
| `DELETE` | `/{session_id}` | Clear DB + invalidate cache; 204 |

### 4.2 Guards (order)

1. Auth + ownership (`WorkflowSession.user_id == current_user`)
2. `require_user_llm_context(db, user_id)` → `CFG_6001`
3. `check_rate_limit(identifier=f"{user_id}:hiring_outreach", limit=5, window_seconds=3600)`
4. Require `job_analysis`
5. If not regenerate and result exists → return existing (or 409 conflict — **prefer:** return cached result with `already_exists`; regenerate clears first)
6. `set_hiring_outreach_generating` → else `APIError` 409 conflict

### 4.3 Background task

```python
async def _generate_hiring_outreach_background(
    session_id: str,
    user_id: Optional[str] = None,
    user_api_key: Optional[str] = None,
    preferred_provider: Optional[str] = None,
    preferred_model: Optional[str] = None,
) -> None:
    try:
        async with get_session() as db:
            # load session, broadcast started, run agent, flag_modified, commit
            # cache_hiring_outreach, broadcast complete
    except Exception as e:
        logger.error("Hiring outreach failed for session %s: %s", sanitize_log_value(session_id), sanitize_log_value(str(e)), exc_info=True)
        await report_exception(e, user_id=user_id)
        await broadcast_hiring_outreach_error(...)
    finally:
        await clear_hiring_outreach_generating(session_id)
```

### 4.4 WebSocket

**File:** `api/websocket.py`

Add:

- `broadcast_hiring_outreach_started`
- `broadcast_hiring_outreach_complete`
- `broadcast_hiring_outreach_error`

Message types: `hiring_outreach_started` | `hiring_outreach_complete` | `hiring_outreach_error`  
Reuse `WS /api/v1/ws/workflow/{session_id}` (same as interview prep / mock interview).

Update `.cursor/rules/websocket-patterns.mdc` in Phase 5.

### 4.5 Tasks checklist

- [ ] Pydantic request/response models
- [ ] Four endpoints + ownership
- [ ] BG task with `get_session` + `report_exception`
- [ ] WS helpers
- [ ] Register router in `main.py`

### 4.6 Code review (Phase 3)

- [ ] No bare `HTTPException`
- [ ] Lock always cleared in `finally`
- [ ] `flag_modified` on every persist
- [ ] User API key never logged or stored on session
- [ ] Rate-limit headers if project pattern uses `check_rate_limit_with_headers`
- [ ] IDOR: other user’s `session_id` → 404/403 consistently with interview prep

### 4.7 Tests (Phase 3)

**File:** `tests/test_api/test_hiring_outreach.py`

Use `authed_client` / `authed_client_with_user` per unit-testing rules; mock agent + Redis:

- [ ] Unauthenticated → 401
- [ ] Wrong owner → 404/403
- [ ] No LLM credentials → `CFG_6001` / 422
- [ ] Missing `job_analysis` → validation / 400-class error
- [ ] Concurrent generate → 409
- [ ] Rate limit exceeded → 429
- [ ] GET after mocked complete → 200 with schema fields
- [ ] DELETE → 204 then GET empty/404
- [ ] Regenerate path clears previous result

**Command:**

```bash
pytest tests/test_api/test_hiring_outreach.py -q
```

### 4.8 Exit criteria

- [ ] API review complete
- [ ] API tests green
- [ ] Manual curl/smoke optional

---

## 5. Phase 4 — Frontend (new standalone tab)

**Estimated effort:** 1–1.5 days  
**Shippable alone:** Yes (feature complete for users)

**Why a new tab:** Company Research is **pipeline output** (workflow step 3). Hiring Outreach is **standalone on-demand** — same family as Optimize CV and Practice Interview. Do **not** bury it inside `#pane-company`.

### 5.1 Tab placement

**File:** `ui/dashboard/application.html`

- Add **10th** tab after Practice Interview, e.g.:
  - Label: **Outreach** (or **Find contacts**)
  - `data-tab="outreach"`
  - Pane: `#pane-outreach`
  - Mount: `#hiringOutreachContent`
- Update scrollable tab bar / mobile overflow rules if needed (see `mobile-responsive.mdc`)
- Update `ui-application-detail.mdc` tab count **9 → 10** and tab order in Phase 5

Clone empty-state layout from Optimize CV / Practice Interview (centered icon, short copy, primary button, AI Setup warning).

### 5.2 HTML / CSS

Inside `#pane-outreach` / `#hiringOutreachContent`:

- Empty state: icon + short description + **Find who to contact** button (`data-action="generateHiringOutreach"`)
- Loading state: spinner (WS + 5s poll fallback)
- Results: list of contact cards (name/title, confidence badge, why, evidence, short message, email subject/body, copy buttons)
- Fallback card when `fallback.used`
- Banner when CFG_6001 (reuse `showApiKeyAlert` / settings link pattern)
- Notice: “Public web only — verify before sending. We never send messages for you.”
- CSS classes only (no `style=`); companion `.is-hidden` rules where needed
- Do **not** change Company tab render logic except leaving it pipeline-only

### 5.3 TypeScript

Prefer small module (mirror mock-interview / cv-optimizer):

- `ui/src/hiring-outreach/` or `ui/src/pages/hiring-outreach.ts`
- `window.initHiringOutreachTab(sessionId)` called from `application-detail.ts` on `data-tab="outreach"`
- Register Vite entry if needed (`ui/vite.entries.json`) like `mock-interview`
- `escapeHtml` for all LLM strings; `decodeEntities` for `textContent`
- Event delegation `data-action` — never inline onclick
- Copy via existing clipboard helper — subject + `\n\n` + body
- Connect WS before POST generate; stop poll on complete/error

### 5.4 Vite / entry

- Add page/module entry if following Practice Interview split-bundle pattern
- `make build-frontend` after TS changes

### 5.5 Tasks checklist

- [ ] New tab button + pane in `application.html`
- [ ] HTML empty / loading / results / error states
- [ ] CSS (nonce style block or existing page styles)
- [ ] TS API client + render + listeners + `initHiringOutreachTab`
- [ ] Wire tab switch in `application-detail.ts`
- [ ] CFG_6001 handling
- [ ] WS + poll fallback

### 5.6 Code review (Phase 4)

- [ ] Not nested under Company / `#companyContent`
- [ ] Tab order: … → Optimize CV → Practice Interview → **Outreach**
- [ ] No `style=` attributes; no dynamic `<style>` injection
- [ ] No named job boards / LinkedIn in UI strings
- [ ] Confidence always visible
- [ ] Copy buttons work for short message and email
- [ ] Mobile: tab bar scrolls; cards readable ≤768px

### 5.7 Tests (Phase 4)

- [ ] If frontend unit tests exist for application-detail renders, add hiring-outreach render case
- [ ] E2E: mock `GET/POST /api/v1/hiring-outreach/...` — new tab visible, mock result renders without JS error
- [ ] E2E rate-limit: 429 on generate does not crash page (`rate-limit.spec.ts` if applicable)
- [ ] Update e2e / rules that hard-code “9 tabs”

**Commands (adjust to repo scripts):**

```bash
make build-frontend
# playwright: targeted application / hiring outreach mock test when added
```

### 5.8 Exit criteria

- [ ] UI review complete
- [ ] Build succeeds
- [ ] E2E/unit coverage for happy + CFG_6001 + 429 paths as specified

---

## 6. Phase 5 — Docs, rules, CHANGELOG

**Estimated effort:** 0.5 day  

### 6.1 New feature rule

**File:** `.cursor/rules/hiring-outreach-feature.mdc` (+ mirror `.claude/rules/` if project keeps both)

Document: endpoints, JSONB shape, lock keys, WS events, no LinkedIn, grounding flag, rate limit, **Outreach** tab actions.

### 6.2 Update indexes / guides

- [ ] `CLAUDE.md` / `.cursorrules` rule table row
- [ ] `.cursor/rules/ui-application-detail.mdc` — 10-tab layout + Outreach tab section
- [ ] `.cursor/rules/caching-redis.mdc` — TTLs
- [ ] `.cursor/rules/websocket-patterns.mdc` — event types
- [ ] `.cursor/rules/database-patterns.mdc` — JSONB column list
- [ ] `.cursor/rules/adding-new-features.mdc` — mention if needed
- [ ] `USER_GUIDE.md` — short “Hiring outreach” section
- [ ] `ui/help.html` if other on-demand features are listed
- [ ] `CHANGELOG.md` — Unreleased entry
- [ ] `README.md` feature bullet if applicable

### 6.3 Code review (Phase 5)

- [ ] Docs match shipped API paths and field names
- [ ] No LinkedIn named in user-facing docs
- [ ] Indexes link to the new `.mdc` file

### 6.4 Tests (Phase 5)

- [ ] No runtime change required; re-run Phase 2–4 test suites for regression:

```bash
pytest tests/test_agents/test_hiring_outreach.py tests/test_api/test_hiring_outreach.py tests/test_utils/test_hiring_outreach_cache.py -q
```

### 6.5 Exit criteria

- [ ] Docs/rules complete
- [ ] CHANGELOG updated
- [ ] Full targeted suite green

---

## 7. Phase exit criteria (every phase)

Before marking a phase done:

1. **Self code review** against §0.3 non-negotiables + that phase’s review checklist  
2. **Tests green** for that phase  
3. **Checkboxes** in this file updated  
4. Prefer **one PR per phase** (or squash only after all phases reviewed)

---

## 8. Suggested PR titles

| Phase | Title |
|-------|--------|
| 1 | `feat(outreach): add hiring_outreach JSONB, cache locks, grounding setting` |
| 2 | `feat(outreach): add HiringOutreachAgent with web grounding` |
| 3 | `feat(outreach): API, background task, and WebSocket events` |
| 4 | `feat(outreach): add Outreach tab for contact finding and drafts` |
| 5 | `docs(outreach): feature rules, user guide, and changelog` |

---

## 9. Risk register

| Risk | Mitigation |
|------|------------|
| Hallucinated names | Require confidence; UI “verify before sending”; prefer fewer contacts |
| Grounding cost / latency | One call; 5/hour rate limit; BG task; cache GET |
| Ollama users | No grounding; drafts from session context only; honest summary |
| LinkedIn leakage from search snippets | Post-process strip URLs; prompt ban |
| SSRF | Never fetch user URLs in app code; provider search only |
| Spam / ToS | Copy-only; never send |

---

## 10. Definition of done (feature)

- [ ] All phases 1–5 complete with review + tests  
- [ ] User can generate outreach from the new **Outreach** tab on a completed analysis  
- [ ] Results show confidence + copy actions  
- [ ] No LinkedIn integration or named LinkedIn UI copy  
- [ ] CFG_6001 and 429 handled in UI  
- [ ] Docs and CHANGELOG updated  
