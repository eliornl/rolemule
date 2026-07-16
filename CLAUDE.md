# ApplyPilot — Claude Code Rules Index

**Product name:** ApplyPilot (repo folder: `applypilot`).

All detailed rules live in `.claude/rules/`. Read the relevant file(s) **before** working in that area. Never load all files — only pull what the task needs.

---

## Rule Files

| File | Read when... |
|------|-------------|
| `.claude/rules/applypilot-core.mdc` | any task — app name, `APIError`/`ErrorCode` (**`CFG_6001`**, **`RES_3002`**, content fingerprint NFKC + `utils/application_dedupe.py`, post-start duplicate / `uq_user_job_company`), **`POST /workflow/start` job file** (`.pdf`/`.txt`/`.docx`, 5 MB), background tasks, **workflow failure (no partial outputs, dashboard list join)**, route prefixes |
| `.claude/rules/python-conventions.mdc` | writing or editing any Python file |
| `.claude/rules/database-patterns.mdc` | touching models, migrations, JSONB fields, SQLAlchemy queries |
| `.claude/rules/auth-patterns.mdc` | auth endpoints, JWT, login, registration, token revocation, lockout |
| `.claude/rules/security-python.mdc` | any security-sensitive Python code (XSS, file upload, tokens, secrets) |
| `.claude/rules/codeql-security-scanning.mdc` | CodeQL CI, log sanitization, secret scanning test keys, Pydantic `field_validator`, extension entity decode |
| `.claude/rules/security-middleware.mdc` | middleware, CORS, CSP, `.is-hidden`, maintenance mode |
| `.claude/rules/settings-and-env.mdc` | env vars, `get_settings()`, `.env`, `ENCRYPTION_KEY` |
| `.claude/rules/llm-integration.mdc` | Multi-provider LLM (`get_llm_client`), per-user BYOK (Gemini/OpenAI/Anthropic/Ollama), model allowlists in `utils/llm/models.py`, grounding, **`CFG_6001`**, **`DEFAULT_MAX_TOKENS` (16k)**, **`generate_stream` / `SpeakFieldStreamer`** |
| `.claude/rules/agent-patterns.mdc` | workflow agents (**any agent failure fails the workflow**), standalone interview prep + CV optimizer + Practice Interview + Hiring Outreach, `workflow_preferences`, BYOK model override, **Company Research — `_has_usable_company_name` / unnamed-posting / disambiguation / staffing / `research_quality`** |
| `.claude/rules/interview-prep-feature.mdc` | interview prep agent, background task, Redis lock, rate limit (static Interview tab — not Practice Interview) |
| `.claude/rules/mock-interview-feature.mdc` | Mock Session / Practice Interview (HR/Pro/Manager), duration timer, browser STT/TTS, BYOK, speak streaming / `speak_delta`, ws-guard |
| `.claude/rules/hiring-outreach-feature.mdc` | Hiring Outreach — public web contacts + copy-only drafts, `hiring_outreach` JSONB, Redis lock, WS `hiring_outreach_*`, 10th Outreach tab |
| `.claude/rules/cv-optimizer-feature.mdc` | CV Optimizer loop, API, cache, WebSocket, application detail tab |
| `.claude/rules/career-tools.mdc` | 6 career tool agents, endpoints, rate limits, output schemas, copy button |
| `.claude/rules/caching-redis.mdc` | cache TTLs, Redis helpers, **job-analysis key (up to 50k chars of text)**, rate limiting, auth-specific keys |
| `.claude/rules/websocket-patterns.mdc` | WebSocket endpoints, connection limits, broadcast helpers, mock interview `speak_delta` + client session filter |
| `.claude/rules/logging-patterns.mdc` | `StructuredLogger`, **`sanitize_log_value()` / `mask_email()`**, redaction, `exc_info=True`, bulk-script safety |
| `.claude/rules/google-oauth.mdc` | OAuth flow, CSRF state in Redis, exchange-code pattern, open-redirect |
| `.claude/rules/email-and-misc-utils.mdc` | Gmail SMTP, resume parser, BYOK encryption |
| `.claude/rules/frontend-js-strict.mdc` | any `ui/src/**/*.ts` — TypeScript strict, null safety, event delegation, no `style=` attrs |
| `.claude/rules/landing-page.mdc` | `index.html`, landing page sections, screenshot showcase |
| `.claude/rules/dashboard-home.mdc` | dashboard app list, **`workflow_sessions` join (hide workflow-failed)**, **funnel stats formula**, search/filter/sort, **single-flight `loadApplications`**, **EXISTS pagination**, toasts (`notifyReady` **`c:`/`f:`** keys, duplicate headline), **`isPlaceholderCompanyName` / Unknown employer**, card CSS, session storage |
| `.claude/rules/ui-application-detail.mdc` | application detail page, **10-tab** layout (Optimize CV + Mock Session + Outreach), **View posting link**, **`additional_locations`**, render functions, **`isPlaceholderCompanyName` / Unknown / About this opportunity**, company research notices (`research_quality` / staffing), CSS classes |
| `.claude/rules/accessibility.mdc` | any template — WCAG 2.1 AA, heading hierarchy, landmarks, aria |
| `.claude/rules/analytics-consent-onboarding.mdc` | PostHog, cookie consent, onboarding tour |
| `.claude/rules/chrome-extension.mdc` | anything inside `extension/` — **popup vs service-worker submit paths**, **`source_url` → `job_url`**, **`extractPageContent` / split-view detail root**, dev/prod toggle, autofill, `InputMethod.EXTENSION` |
| `.claude/rules/adding-new-features.mdc` | adding a new endpoint, agent, tool, migration, asset, or preference |
| `.claude/rules/settings-page.mdc` | settings tabs, Preferences, AI Setup, auto-save, account-icon variants |
| `.claude/rules/frontend-build-pipeline.mdc` | Vite+TS page entries + esbuild CSS, `asset_url()`, manifest, `make build-frontend` |
| `.claude/rules/cli.mdc` | ApplyPilot CLI — Typer commands, `applypilot_client`, `tests/test_cli/`, docs |
| `.claude/rules/mobile-responsive.mdc` | breakpoints, navbar collapse, scrollable tab bars, mobile utilities |
| `.claude/rules/unit-testing.mdc` | ~300 agent + ~1,050 API + **364** CLI + **6** ASGI CLI integration tests; `live_server_helpers`; ASGITransport (not TestClient) for CLI ASGI; cov ≥97% includes root `test_cv_*` |
| `.claude/rules/e2e-testing.mdc` | ~1,380 Playwright specs; CI smoke-only (`e2e-smoke`); `setupAuth`, `page.route()`, JWT/cookie-consent setup |

---

## Non-Negotiables (always true — no file needed)

1. **Never raise bare `HTTPException`** — use `APIError` / `not_found_error()` / `rate_limit_error()` etc. from `utils/error_responses.py`
2. **Never call `flag_modified()` zero times on a JSONB mutation** — every write to a JSONB field needs it
3. **Background tasks use `get_session()`**, not `get_database()` (request-scoped)
4. **All `run_in_executor` LLM calls must be wrapped in `asyncio.wait_for()`**
5. **Never add inline `onclick=` / `onchange=` attributes** — use event delegation + `data-action`
6. **Never use `random` for security values** — always use `secrets`
7. **Never put a JWT in an HTTP redirect URL** — use the OAuth exchange-code pattern; WebSocket `?token=` is the only exception
8. **Never return user-existence hints from unauthenticated endpoints** — forgot-password and resend-verification always return identical responses
9. **`ENCRYPTION_KEY` must be set before any `JWT_SECRET` rotation**
10. **`DEBUG` must be `false` in any shared environment**
11. **Never hardcode `/static/js/` or `/static/css/` in templates** — always use `{{ asset_url('js/...') }}` / `{{ asset_url('css/...') }}`
12. **Never write `except Exception: pass`** — always log at minimum `logger.debug(..., exc_info=True)`
13. **Every background task top-level `except` must call `await report_exception(exc, user_id=user_id)`** and log with `exc_info=True`
14. **Every `logger.error(...)` inside an `except` block must include `exc_info=True`**
15. **Never add `style="..."` HTML attributes** — CSP blocks inline styles; use CSS classes
16. **Every `<style>` block in a template must include `nonce="{{ request.state.csp_nonce | default('') }}"`**
17. **Never use native `confirm()`, `alert()`, or `prompt()`** — use `window.showConfirm()` from `confirm-modal.js`
18. **Never inject `<style>` elements from JavaScript** — dynamically created `<style>` tags are blocked by CSP
19. **`thinking_budget=0` must always be set in `GenerateContentConfig`** — Gemini 2.5/3 Flash enables thinking by default, burning the output token budget
20. **`google-generativeai` is removed — never add it back** — use `google-genai` for both Vertex AI and BYOK paths
21. **`check_account_lockout()` returns a tuple — always unpack it** — `if await check_account_lockout(email):` is ALWAYS truthy; always write `is_locked, remaining = await check_account_lockout(email)`
22. **Never mention specific job site names in user-facing text** — use "any job site", "any job board", "company careers pages"
23. **`datetime.strptime()` results must have `.replace(tzinfo=timezone.utc)`** before comparing with timezone-aware datetimes
24. **`escapeHtml()` must decode `&amp;` FIRST** — canonical order: `&amp;` → `&`, then `&#x27;`, `&#039;`, `&quot;`, `&lt;`, `&gt;`, then re-encode
25. **`.textContent` assignments must use `decodeEntities()`** — `.textContent` does not interpret HTML entities; `escapeHtml()` is for `.innerHTML` only
26. **Dynamic logger calls must use `%s` + `sanitize_log_value()`** — not f-strings with user/request/exception data; never wrap `%d`/`%f` args with `sanitize_log_value()` (see `codeql-security-scanning.mdc`)
27. **Never commit `AIzaSy…` dummy API keys** — use `tests/gemini_test_keys.DUMMY_GEMINI_API_KEY`
28. **Pydantic v2: `@field_validator` + module-level functions** — not `@validator(cls, ...)`
26. **Required numeric profile fields — never reject `0` with truthiness** — e.g. `years_experience` in profile setup: `if (!value)` after `parseInt` fails for zero; use explicit empty/NaN checks. See `.claude/rules/frontend-js-strict.mdc` (“Required numeric fields”).
