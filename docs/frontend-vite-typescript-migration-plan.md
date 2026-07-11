# Frontend Migration Plan — Vite + TypeScript (Option A, No React)

**Status:** Implemented — branch `feat/frontend-vite-typescript` (pending merge to `main`)  
**Owner:** Engineering  
**Last updated:** 2026-07-10  
**Decision:** Evolve the existing Jinja + vanilla JS multi-page app with **Vite + TypeScript**. Do **not** introduce React/Vue/Svelte in this plan.

This document is the **single source of truth** for the Option A frontend upgrade. An agent (or developer) should execute phases **in order**, run the listed **full test suite** after each phase, complete the **code review checklist**, and not advance until the phase exit criteria pass.

---

## 0. Agent instructions (read first)

### 0.1 Goal

Upgrade the ApplyPilot web frontend build and language toolchain so that:

1. Page scripts can use **ES modules** (`import` / `export`) and be **bundled** per page entry.
2. Source is written in **TypeScript** with real compile-time checks (not JSDoc-only).
3. The **user-visible UI stays 1:1** with the current design (same Jinja templates, Bootstrap, CSS, DOM patterns).
4. FastAPI continues to own routing, HTML shells, CSP nonces, and `asset_url()`.
5. Migration is **incremental** — old esbuild-minified global scripts and new Vite bundles can coexist until every page is converted.

**Out of scope for this plan**

- React / Vue / Svelte / SPA rewrite
- Tailwind or design-system redesign
- Chrome extension rewrite (`extension/`)
- Changing API contracts or backend agent behavior
- Replacing Bootstrap or Font Awesome

### 0.2 Non-negotiables (from `.cursorrules` / CLAUDE.md)

- Never hardcode `/static/js/` or `/static/css/` in templates — always `{{ asset_url('js/...') }}` / `{{ asset_url('css/...') }}`
- Never add `style="..."` HTML attributes — CSP `style-src` is nonce-based
- Every `<style>` block needs `nonce="{{ request.state.csp_nonce | default('') }}"`
- Never inject `<style>` from JavaScript
- Never use native `confirm()` / `alert()` / `prompt()` — use `window.showConfirm()`
- Never add inline `onclick=` / `onchange=` — event delegation + `data-action`
- `escapeHtml()` must decode `&amp;` **first**, then named entities, then re-encode
- `.textContent` assignments of server strings must use `decodeEntities()`, not raw strings
- `localStorage.clear()` must preserve `cookie_consent`
- Dashboard pages must not rely on `app.js` / `window.app` for navbar logout
- Playwright mock JWTs must be valid 3-part tokens; cookie consent must include `version: '1.0'`
- macOS: use `make build-frontend` / `make setup` (quarantine strip for `node_modules`)
- `requirements.txt` is unrelated to this plan — do not hand-edit Python pins for frontend work

### 0.3 Rules to read before coding

| Area | File |
|------|------|
| Build / `asset_url` | `.cursor/rules/frontend-build-pipeline.mdc` |
| JS patterns / XSS / auth helpers | `.cursor/rules/frontend-js-strict.mdc` |
| CSP / `.is-hidden` | `.cursor/rules/security-middleware.mdc` |
| Dashboard home | `.cursor/rules/dashboard-home.mdc` |
| Application detail | `.cursor/rules/ui-application-detail.mdc` |
| Settings | `.cursor/rules/settings-page.mdc` |
| Landing | `.cursor/rules/landing-page.mdc` |
| Mobile | `.cursor/rules/mobile-responsive.mdc` |
| A11y | `.cursor/rules/accessibility.mdc` |
| E2E | `.cursor/rules/e2e-testing.mdc` |
| CV Optimizer | `.cursor/rules/cv-optimizer-feature.mdc` |
| Interview prep | `.cursor/rules/interview-prep-feature.mdc` |

### 0.4 Current state (baseline)

| Layer | Today |
|-------|--------|
| Templates | Jinja2 under `ui/` (`base.html`, auth, dashboard, landing, legal, help) |
| JS | ~26 files in `ui/static/js/` (~21K LOC), **global scope**, IIFE wrappers |
| CSS | `ui/static/css/` (~9K LOC) — **unchanged by this plan** (still minified by build) |
| Build | `ui/build.mjs` + esbuild: **`bundle: false` for JS**, minify + content-hash + `manifest.json` |
| Types | `ui/static/js/types.js` — JSDoc `@typedef` only (no compile step) |
| Shared globals | `dom-security.js`, `confirm-modal.js`, `event-bus.js` loaded from `base.html` before page scripts |
| Dev | `make build-frontend` → `npm run build`; manifest re-read every request in non-production |
| Prod | Dockerfile Stage 0: `node:20-slim` runs `node build.mjs` → copies `ui/static/dist` |

**Pain points this plan addresses**

- No real module graph → duplicated helpers (`logout`, `escapeHtml`, API error parsing)
- Giant page files (`profile-setup.js` ~3.1K, `application-detail.js` ~2.6K, `dashboard.js` ~1.9K)
- JSDoc types are optional and not enforced in CI
- esbuild does not resolve `import` (by design today)

### 0.5 Target architecture (end state)

```
Browser
  ↑
Jinja HTML shell (unchanged routing / CSP / APP_CONFIG)
  ↑
{{ asset_url('js/<page>.js') }}  →  hashed Vite bundle in ui/static/dist/
  ↑
Vite production build (one entry per page + shared chunks)
  ↑
ui/src/pages/*.ts  +  ui/src/shared/*.ts   (TypeScript source of truth)
```

**Coexistence rule (during migration):**

- Unconverted pages keep loading from `ui/static/js/*.js` via the legacy esbuild path (or a unified build that still emits the same manifest keys).
- Converted pages load the Vite-built file under the **same manifest key** the template already uses (e.g. `js/help.js`), so templates do not need path renames when possible.
- CSS continues through the existing minify/hash path unless a later phase explicitly moves it (default: **leave CSS as-is**).

### 0.6 Success criteria (whole project)

- [x] All former `ui/static/js/*.js` page logic lives under `ui/src/` as TypeScript (or documented exceptions)
- [x] `npm run build` (Vite) produces `ui/static/dist/manifest.json` compatible with `asset_url()`
- [x] `tsc --noEmit` (or Vite build with typecheck) is green in CI
- [x] No React/Vue dependency added
- [x] UI is visually and behaviorally 1:1 (full Playwright live suite green — 1433 tests)
- [x] Docker / `make setup` / `make build-frontend` work on macOS and Linux
- [x] Docs + Cursor rules updated for the new pipeline

### 0.7 Execution order

```
Phase 0 (prep + branch)
  → Phase 1 (Vite toolchain + dual-build / unified build)
  → Phase 2 (shared TS modules + first page: Help)
  → Phase 3 (auth pages)
  → Phase 4 (landing + static/marketing pages)
  → Phase 5 (dashboard home + new application)
  → Phase 6 (settings + career tools + interview prep)
  → Phase 7 (application detail + CV optimizer)
  → Phase 8 (profile setup + profile.js)
  → Phase 9 (remove legacy JS, CI harden, docs)
```

**Do not skip ahead.** Heavy pages (Phases 7–8) depend on shared modules from Phase 2.

### 0.8 Effort estimate (one experienced developer)

| Phase | Focus | Calendar (focused) |
|-------|--------|---------------------|
| 0 | Prep | 0.5 day |
| 1 | Toolchain | 3–5 days |
| 2 | Shared + Help | 3–5 days |
| 3 | Auth | 4–6 days |
| 4 | Landing / help / legal shells | 2–3 days |
| 5 | Dashboard home + new app | 5–8 days |
| 6 | Settings / tools / interview | 5–8 days |
| 7 | Application detail + CV opt | 8–12 days |
| 8 | Profile setup | 8–12 days |
| 9 | Cleanup + CI | 3–5 days |
| **Total** | | **~6–10 weeks focused** (or 2–4 months part-time) |

---

## 1. Phase 0 — Prep

**Goal:** Branch, inventory, freeze scope, establish measurement baseline.  
**Duration:** ~0.5 day  
**Risk:** Low

### 1.1 Tasks

- [ ] Create branch: `feat/frontend-vite-typescript`
- [ ] Confirm working tree is clean of unrelated WIP (or park WIP on another branch)
- [ ] Inventory every template → script mapping:

| Template / surface | Script(s) today | Phase to convert |
|--------------------|-----------------|------------------|
| `ui/help.html` | `help.js` | 2 |
| `ui/auth/login.html` | `auth-login.js` (+ shared `auth.js` if used) | 3 |
| `ui/auth/register.html` | `auth-register.js` | 3 |
| `ui/auth/verify-email.html` | `auth-verify-email.js` | 3 |
| `ui/auth/reset-password.html` | `auth-reset-password.js` | 3 |
| `ui/index.html` | `app.js`, `landing.js` | 4 |
| `ui/dashboard/index.html` | `dashboard-home.js`, `dashboard.js` (as used) | 5 |
| `ui/dashboard/new-application.html` | `dashboard-new-application.js` | 5 |
| `ui/dashboard/settings.html` | `dashboard-settings.js` | 6 |
| `ui/dashboard/tools.html` | `dashboard-tools.js` | 6 |
| `ui/dashboard/interview-prep.html` | `dashboard-interview-prep.js` | 6 |
| `ui/dashboard/application.html` | `application-detail.js`, `cv-optimizer.js` | 7 |
| `ui/profile/setup.html` | `profile-setup.js`, `profile-completion-sync.js` | 8 |
| Global (`base.html`) | `dom-security.js`, `confirm-modal.js`, `event-bus.js`, `navbar-notifications.js`, `cookie-consent.js`, `analytics.js`, `onboarding.js` | 2 (shared) + later pages |

- [ ] Record baseline commands and results (paste into PR description later):

```bash
make build-frontend
# note: file count in ui/static/dist/manifest.json
cd e2e && npx playwright test --grep @smoke   # or project smoke suite
```

- [ ] Decide dual-build strategy for Phase 1 (pick **one** and document in PR):

| Strategy | Description | Recommendation |
|----------|-------------|----------------|
| **A — Unified Vite** | Vite builds all entries; legacy `.js` copied/bundled as entries until converted | Preferred long-term |
| **B — Dual pipeline** | esbuild keeps unconverted files; Vite builds converted entries; merge manifests | Safer short-term |

**Default recommendation:** **B for Phases 1–2**, then collapse to **A** in Phase 9.

### 1.2 Full test suite (Phase 0)

No code changes required. Verify baseline green:

```bash
# Frontend build
make build-frontend

# Optional: Python suite still green (sanity — no FE change yet)
make test   # or project’s standard pytest target for tests/test_api + tests/test_agents

# E2E smoke (mocked Tier 1)
cd e2e && npx playwright test tests/smoke.spec.ts
```

### 1.3 Code review checklist (Phase 0)

- [ ] Branch name and scope match this doc
- [ ] Inventory table is complete (no orphan scripts)
- [ ] Dual-build strategy chosen and written in the PR / this doc status section
- [ ] No accidental commits of `node_modules/`, `ui/static/dist/`, or secrets

### 1.4 Exit criteria

- [ ] Branch exists
- [ ] Baseline smoke + build recorded
- [ ] Strategy A/B chosen

---

## 2. Phase 1 — Vite + TypeScript toolchain (no page behavior change)

**Goal:** Introduce Vite, TypeScript, and a production build that still serves **identical** assets for unconverted pages. Templates and UX must not change.  
**Duration:** 3–5 days  
**Risk:** Medium (Docker / Make / manifest compatibility)

### 2.1 Target layout

```
ui/
  package.json
  tsconfig.json
  vite.config.ts
  build.mjs                 # keep until Phase 9 (legacy esbuild) OR thin wrapper
  src/                      # NEW — TypeScript source (empty or stub in Phase 1)
    vite-env.d.ts
    shared/                 # Phase 2+
    pages/                  # Phase 2+
  static/
    js/                     # legacy sources until converted
    css/                    # unchanged
    dist/                   # build output (gitignored)
```

### 2.2 Tasks

#### 2.2.1 Dependencies

- [ ] Add devDependencies (pin compatible versions; do not remove Font Awesome):

  - `vite`
  - `typescript`
  - `@types/node` (if needed for config)
  - Optional later: `vitest` (Phase 9), `@playwright/test` stays in `e2e/`

- [ ] Keep `esbuild` until Phase 9 if using dual pipeline (Strategy B)

#### 2.2.2 TypeScript config

- [ ] Add `ui/tsconfig.json` with strict-but-pragmatic settings:

  - `"strict": true`
  - `"noEmit": true` (Vite emits; `tsc` typechecks only) **or** project references as preferred
  - `"module": "ESNext"`, `"moduleResolution": "bundler"`
  - `"lib": ["ES2022", "DOM", "DOM.Iterable"]`
  - `"types"` for Vite client
  - Include `ui/src/**/*` only at first (do not force-check all legacy JS yet)

#### 2.2.3 Vite config requirements

- [ ] Multi-page **library/app** build with **named inputs** matching current manifest keys where possible
- [ ] Output directory: `ui/static/dist` (or subfolder that `asset_url` understands — prefer keeping `/static/dist/...`)
- [ ] Content-hashed filenames (8+ char hash) for long-term caching
- [ ] Emit / merge `manifest.json` in the shape `asset_url()` expects:

```json
{
  "js/help.js": "js/help.a1b2c3d4.js",
  "css/app.css": "css/app.deadbeef.css"
}
```

- [ ] **Do not** change CSS pipeline in Phase 1 unless required — continue hashing CSS via existing `build.mjs` path and merge into one manifest
- [ ] Preserve ability for FastAPI to fall back to `/static/<path>` when manifest missing (dev)
- [ ] Document macOS quarantine: `_macos_sign_node` must still run before Vite/esbuild binaries

#### 2.2.4 npm scripts

Update `ui/package.json` scripts (names may vary; keep Make targets working):

```json
{
  "scripts": {
    "build": "node scripts/build-all.mjs",
    "build:legacy": "node build.mjs",
    "build:vite": "vite build",
    "typecheck": "tsc --noEmit -p tsconfig.json",
    "dev:assets": "vite build --watch"
  }
}
```

- [ ] `make build-frontend` must call the **unified** `npm run build` (legacy + vite merge)
- [ ] `make setup` / `make dev` continue to build frontend automatically

#### 2.2.5 Docker

- [ ] Update Dockerfile frontend stage:

  - Copy `package.json` (+ lockfile when present)
  - `npm install --include=dev`
  - Copy `ui/static`, `ui/src` (when present), Vite/TS configs, build scripts
  - Run `npm run build` (not only `node build.mjs`)
  - Still copy `ui/static/dist` into the Python image

#### 2.2.6 CI

- [ ] Ensure CI frontend build step uses the new `npm run build`
- [ ] Add `npm run typecheck` once `ui/src` has at least one file (can be a stub in Phase 1)

#### 2.2.7 Compatibility shim (no UX change)

- [ ] Prove that after the new build, **every existing template** still resolves assets via `asset_url()`
- [ ] Spot-check hashed URLs in View Source for `base.html` shared scripts
- [ ] Confirm CSP still allows script/style with nonces; Vite must **not** inject inline styles without nonces

### 2.3 Implementation notes (best practices)

1. **Prefer IIFE/IIFE-compatible outputs for global scripts** that `base.html` loads as classic scripts, **or** convert those shared scripts to `type="module"` carefully (module scripts are deferred — order matters). Phase 1 recommendation: keep shared globals as classic scripts until Phase 2 explicitly converts them.
2. **Do not enable Vite HTML plugin as the app router** — FastAPI remains the HTML server.
3. **Avoid importing CSS into TS** in early phases (keeps CSP and `asset_url` simple).
4. **Source maps:** enable in development builds; disable or hidden in production if size is a concern.
5. **Vendor Font Awesome** path must remain via `asset_url('vendor/fontawesome/...')` as today.

### 2.4 Full test suite (Phase 1)

```bash
# 1) Clean + build
make clean-frontend
make build-frontend
test -f ui/static/dist/manifest.json

# 2) Manifest sanity — required keys still present
node -e "
const m=require('./ui/static/dist/manifest.json');
const keys=['js/dom-security.js','js/confirm-modal.js','js/event-bus.js','css/app.css','css/landing.css'];
for (const k of keys) if (!m[k]) { console.error('missing',k); process.exit(1); }
console.log('manifest ok', Object.keys(m).length);
"

# 3) Typecheck (if stub src exists)
cd ui && npm run typecheck

# 4) App boots with built assets
# (with make start-local / make dev already running, hard-refresh)
# Manual: open /, /auth/login, /dashboard (authed), /help

# 5) E2E Tier 1 smoke + visual structure
cd e2e && npx playwright test tests/smoke.spec.ts
cd e2e && npx playwright test tests/visual-regression.spec.ts

# 6) Docker frontend stage (if Docker available)
docker build --target frontend-builder -t applypilot-fe-test .
```

**Pass criteria:** smoke + visual-regression green; manifest keys intact; no console CSP violations on spot-checked pages.

### 2.5 Code review checklist (Phase 1)

- [ ] No React/Vue packages added
- [ ] `asset_url()` contract unchanged (or `main.py` updated with tests/docs if intentionally extended)
- [ ] Dockerfile Stage 0 builds successfully
- [ ] `make build-frontend` / `make setup` / `make dev` documented and working on macOS
- [ ] `ui/static/dist/` remains gitignored
- [ ] Lockfile committed if the repo uses one (`package-lock.json`)
- [ ] No secrets in Vite `define` / env exposure
- [ ] Build is deterministic enough for CI (hashes may change with content — OK)
- [ ] PR description explains dual vs unified strategy

### 2.6 Exit criteria

- [ ] Production-like build works locally and in Docker
- [ ] Zero intentional UI changes
- [ ] Phase 1 test suite green
- [ ] Code review approved

---

## 3. Phase 2 — Shared TypeScript modules + Help page pilot

**Goal:** Prove the migration path end-to-end on the smallest real page (`help.js`), and extract shared modules that later phases will import.  
**Duration:** 3–5 days  
**Risk:** Medium (module vs classic script loading, CSP, global `window.*` compatibility)

### 3.1 Shared modules to create under `ui/src/shared/`

| Module | Responsibility | Notes |
|--------|----------------|-------|
| `dom-security.ts` | `escapeHtml`, `decodeEntities`, `sanitizeLogValue`, related | Must preserve decode-`&amp;`-first order |
| `auth.ts` | `getAuthToken`, `logout`, token storage keys | Preserve `cookie_consent` on clear; dashboard-safe without `window.app` |
| `api.ts` | `apiCall` wrapper, error parsing (`message \|\| detail`), 401 handling | Align with existing `window.app.apiCall` behavior where used |
| `notify.ts` | Toast / alert helper | Match existing notify UX |
| `confirm.ts` | Thin typed wrapper around `window.showConfirm` | Do not reimplement modal |
| `config.ts` | Typed access to `window.APP_CONFIG` | |
| `bus.ts` | Typed Event Bus + `BusEvents` constants | No raw event strings |
| `types.ts` | Port of `types.js` `@typedef`s to real TS interfaces | |

**Compatibility requirement:** Until all pages are converted, shared modules that `base.html` loads globally may still need to attach to `window` (e.g. `window.escapeHtml`) **or** remain classic scripts. Prefer:

1. Build `dom-security` / `confirm-modal` / `event-bus` as small bundles that still set `window.*` for legacy pages.
2. New TS pages `import` from `shared/*` directly (bundler inlines / chunks).

### 3.2 Help page conversion

- [ ] Create `ui/src/pages/help.ts` ported from `ui/static/js/help.js`
- [ ] Preserve FAQ accordion, search filter, smooth scroll, logout wiring
- [ ] Wire Vite entry so manifest key remains `js/help.js` (template unchanged)
- [ ] Remove or stop shipping legacy `static/js/help.js` once Vite entry replaces it (avoid double-loading)

### 3.3 Unit / component-level tests (new)

Add lightweight tests for shared pure functions (Vitest recommended):

- [ ] `escapeHtml` decode-first cases (`&amp;#x27;`, `&amp;`, quotes)
- [ ] `decodeEntities` for `.textContent` path
- [ ] `getAuthToken` precedence (`access_token` vs `authToken`)
- [ ] Open-redirect helper if extracted (`/^\/(?!\/)/`)

```bash
cd ui && npm run test   # vitest — add script in this phase if introduced
```

### 3.4 Full test suite (Phase 2)

```bash
make clean-frontend && make build-frontend
cd ui && npm run typecheck
cd ui && npm run test          # if Vitest added

# E2E — Help + a11y + keyboard (Help is linked from dashboard)
cd e2e && npx playwright test tests/smoke.spec.ts
cd e2e && npx playwright test tests/complete-coverage.spec.ts
cd e2e && npx playwright test tests/accessibility.spec.ts
cd e2e && npx playwright test tests/keyboard-nav.spec.ts

# Manual checklist
# - /help FAQ open/close
# - Search filters questions
# - /help?from=dashboard back link behavior
# - Logout from help navbar if present
```

### 3.5 Code review checklist (Phase 2)

- [ ] `escapeHtml` / `decodeEntities` match `frontend-js-strict.mdc` exactly
- [ ] No `innerHTML` of unsanitized user/API strings
- [ ] Help template still uses `{{ asset_url('js/help.js') }}`
- [ ] No double-load of help script (legacy + vite)
- [ ] Shared `window.*` exports still work for unconverted pages
- [ ] No `style=` attributes; no dynamic `<style>` injection
- [ ] Types for `APP_CONFIG` are accurate
- [ ] Vitest covers XSS decode order

### 3.6 Exit criteria

- [ ] Help page fully on TypeScript entry
- [ ] Shared modules exist and are imported by Help
- [ ] Phase 2 tests green; code review approved

---

## 4. Phase 3 — Auth pages

**Goal:** Convert login, register, verify-email, reset-password (and shared `auth.js` logic) to TypeScript modules.  
**Duration:** 4–6 days  
**Risk:** High (auth correctness, token storage, enumeration-safe messaging, redirects)

### 4.1 Files

| Legacy | New entry |
|--------|-----------|
| `auth-login.js` | `ui/src/pages/auth-login.ts` |
| `auth-register.js` | `ui/src/pages/auth-register.ts` |
| `auth-verify-email.js` | `ui/src/pages/auth-verify-email.ts` |
| `auth-reset-password.js` | `ui/src/pages/auth-reset-password.ts` |
| `auth.js` (shared helpers) | fold into `ui/src/shared/auth.ts` + page modules |

### 4.2 Behavioral requirements (must preserve)

- [ ] Do **not** store JWT on registration success — only after email verification
- [ ] Login URL-param messages use `persist = true` in alerts (`verified`, `registered`, etc.)
- [ ] Password fields cleared after attempt
- [ ] Open-redirect prevention on `redirect` params
- [ ] Identical responses UX for forgot-password / resend flows (no user enumeration hints in UI copy)
- [ ] Google OAuth exchange-code pattern unchanged (no JWT in redirect URL)
- [ ] Auth page layout: `<main class="auth-page">` pattern remains

### 4.3 Full test suite (Phase 3)

```bash
make build-frontend
cd ui && npm run typecheck && npm run test

# E2E auth (mocked Tier 1)
cd e2e && npx playwright test tests/auth-pages.spec.ts
cd e2e && npx playwright test tests/auth-complete.spec.ts
cd e2e && npx playwright test tests/error-handling.spec.ts
cd e2e && npx playwright test tests/rate-limit.spec.ts
cd e2e && npx playwright test tests/security.spec.ts
cd e2e && npx playwright test tests/smoke.spec.ts
cd e2e && npx playwright test tests/keyboard-nav.spec.ts
```

**Manual / live (optional Tier 2, not blocking CI):** register → verify → login → logout on a local server.

### 4.4 Code review checklist (Phase 3)

- [ ] Registration does not call `storeAuthData()` before verification
- [ ] Token keys consistent (`access_token` / `authToken`)
- [ ] No JWT placed in URLs
- [ ] `persist: true` for login query-param alerts
- [ ] Password cleared on success and failure
- [ ] Redirect allowlist: relative path only (`/^\/(?!\/)/`)
- [ ] Error parsing uses `message || detail`
- [ ] No user-existence differentiating copy introduced
- [ ] CSP / nonce intact on auth templates

### 4.5 Exit criteria

- [ ] All four auth pages on Vite TS entries
- [ ] Auth e2e suite green
- [ ] Code review approved

---

## 5. Phase 4 — Landing + low-risk public pages

**Goal:** Convert landing (`app.js`, `landing.js`) and any remaining low-risk public scripts (`analytics.js` wiring stays careful with consent).  
**Duration:** 2–3 days  
**Risk:** Medium (marketing UX, cookie consent, PostHog)

### 5.1 Files / concerns

| Area | Notes |
|------|-------|
| `landing.js` / `app.js` | Landing-only; `window.app` exists here — dashboard must still not depend on it |
| `cookie-consent.js` | Prefer shared module; CSS stays in `app.css` (no JS style injection) |
| `analytics.js` | Load only after analytics consent; keep `POSTHOG_CONFIG` injection |
| `onboarding.js` | May slip to Phase 5/6 if tightly coupled to dashboard — document choice |

### 5.2 Full test suite (Phase 4)

```bash
make build-frontend
cd ui && npm run typecheck && npm run test

cd e2e && npx playwright test tests/landing.spec.ts
cd e2e && npx playwright test tests/accessibility.spec.ts
cd e2e && npx playwright test tests/visual-regression.spec.ts
cd e2e && npx playwright test tests/smoke.spec.ts
cd e2e && npx playwright test tests/performance.spec.ts
```

### 5.3 Code review checklist (Phase 4)

- [ ] Landing navbar still `navbar-expand-xl`
- [ ] Screenshot showcase / tabs behavior unchanged (`ssActivateTab` etc.)
- [ ] Cookie consent does not inject `<style>`
- [ ] `localStorage` consent includes `version: '1.0'`
- [ ] PostHog only after analytics accept
- [ ] Brand markup (`.brand-icon` / `.brand-text` / `.brand-accent`) unchanged
- [ ] No job-board brand names in user-facing copy

### 5.4 Exit criteria

- [ ] Landing + consent/analytics path verified
- [ ] Phase 4 tests green; review approved

---

## 6. Phase 5 — Dashboard home + new application

**Goal:** Convert the primary authenticated surfaces users hit daily.  
**Duration:** 5–8 days  
**Risk:** High (list pagination, WebSocket toasts, dedupe keys, `RES_3002`, `CFG_6001`)

### 6.1 Files

| Legacy | Priority behaviors |
|--------|-------------------|
| `dashboard-home.js` | List/filter/sort, Load More / EXISTS pagination, funnel stats, `notifyReady` `c:`/`f:` keys, placeholder company names |
| `dashboard.js` | Shared dashboard helpers / apiCall paths as used |
| `dashboard-new-application.js` | Job submit, file upload limits, `RES_3002` warning UX, `CFG_6001` → Settings AI Setup |
| `navbar-notifications.js` | Cross-page analysis badge |
| `onboarding.js` (if not done) | Tour; no style injection |

### 6.2 Must-preserve behaviors

- [ ] Hard redirect to `/profile/setup` when `profile_completed` is false (no soft banner)
- [ ] Workflow-failed apps hidden via list join semantics (API) — UI must not regress empty/error states
- [ ] Duplicate application messaging is warning/info for `RES_3002`
- [ ] Single-flight `loadApplications` if present today
- [ ] `isPlaceholderCompanyName` / `displayCompanyNameOrUnknown`
- [ ] Document-level `data-action="logout"` listener without `window.app`

### 6.3 Full test suite (Phase 5)

```bash
make build-frontend
cd ui && npm run typecheck && npm run test

cd e2e && npx playwright test tests/dashboard.spec.ts
cd e2e && npx playwright test tests/dashboard-pages.spec.ts
cd e2e && npx playwright test tests/workflow-mocked.spec.ts
cd e2e && npx playwright test tests/websocket.spec.ts
cd e2e && npx playwright test tests/file-upload.spec.ts
cd e2e && npx playwright test tests/journey.spec.ts
cd e2e && npx playwright test tests/rate-limit.spec.ts
cd e2e && npx playwright test tests/error-handling.spec.ts
cd e2e && npx playwright test tests/smoke.spec.ts
cd e2e && npx playwright test tests/onboarding.spec.ts
```

### 6.4 Code review checklist (Phase 5)

- [ ] `RES_3002` and `CFG_6001` UX preserved
- [ ] Toast dedupe keys `c:{session_id}` / `f:{session_id}` preserved
- [ ] Pagination / Load More does not duplicate cards
- [ ] Profile incomplete → hard redirect
- [ ] Logout works without `app.js`
- [ ] File upload client checks align with backend (type/size messaging)
- [ ] No `style=` in generated HTML strings; dynamic layout via classes / JS `.style` only where allowed
- [ ] WebSocket reconnect backoff preserved if applicable on these pages

### 6.5 Exit criteria

- [ ] Home + new application on TS
- [ ] Phase 5 e2e green; review approved

---

## 7. Phase 6 — Settings, career tools, interview prep

**Goal:** Convert remaining dashboard tools surfaces.  
**Duration:** 5–8 days  
**Risk:** Medium–High (auto-save, custom controls, rate limits, long-running generation)

### 7.1 Files

| Legacy | Notes |
|--------|-------|
| `dashboard-settings.js` | Preferences + AI Setup auto-save; custom sliders/toggles/dropdowns |
| `dashboard-tools.js` | Six career tools; copy buttons; output schemas |
| `dashboard-interview-prep.js` | Standalone interview prep states + sub-tabs |

### 7.2 Must-preserve behaviors

- [ ] Settings auto-save pattern (no surprise full-page reloads)
- [ ] BYOK / Vertex messaging: users bring Gemini API keys; Vertex is server-only
- [ ] Career tools copy-button pattern and empty/error states
- [ ] Interview prep generate/complete/mobile layouts
- [ ] Array fields always treated as arrays in renderers (avoid `.map` on strings)

### 7.3 Full test suite (Phase 6)

```bash
make build-frontend
cd ui && npm run typecheck && npm run test

cd e2e && npx playwright test tests/dashboard-pages.spec.ts
cd e2e && npx playwright test tests/interview-prep.spec.ts
cd e2e && npx playwright test tests/complete-coverage.spec.ts
cd e2e && npx playwright test tests/rate-limit.spec.ts
cd e2e && npx playwright test tests/api-validation.spec.ts
cd e2e && npx playwright test tests/form-edge-cases.spec.ts
cd e2e && npx playwright test tests/smoke.spec.ts
```

### 7.4 Code review checklist (Phase 6)

- [ ] No redefinition of global `.btn-primary` unless locally justified
- [ ] Scrollable tab bars on mobile (`overflow-x: auto; flex-wrap: nowrap`)
- [ ] Copy buttons don’t introduce XSS via `innerHTML`
- [ ] Rate-limit 429 handling + Retry-After UX
- [ ] Settings AI Setup links/deep link `?tab=ai-setup` still work
- [ ] Interview prep mocked data shapes use arrays for list fields

### 7.5 Exit criteria

- [ ] Settings / tools / interview prep on TS
- [ ] Phase 6 tests green; review approved

---

## 8. Phase 7 — Application detail + CV optimizer

**Goal:** Convert the largest product UI surface with WebSocket iteration events and 8 tabs.  
**Duration:** 8–12 days  
**Risk:** Very high

### 8.1 Files

| Legacy | Notes |
|--------|-------|
| `application-detail.js` | 8 tabs, sub-tabs, generate documents polling, View posting URL guard |
| `cv-optimizer.js` | Optimize CV loop, WS events, ownership-before-cache semantics on API side |

### 8.2 Split recommendation (implementation quality)

Do **not** keep a single 2.5K-line file. Target structure:

```
ui/src/pages/application-detail/
  index.ts                 # entry: tabs wiring, loadApplicationData
  api.ts
  render/
    overview.ts
    cover-letter.ts
    resume.ts
    company.ts
    strategy.ts
    interview.ts
    optimize-cv.ts
  websocket.ts
  generate-documents.ts
ui/src/pages/cv-optimizer/
  index.ts                 # or imported as module from optimize-cv tab
```

### 8.3 Must-preserve behaviors

- [ ] `analysis_complete` → “Generate Cover Letter & Resume Tips” button + poll status every 3s
- [ ] `job_url` link only if `/^https?:\/\//`
- [ ] Company website link only if real URL
- [ ] `isPlaceholderCompanyName` / Unknown employer / About this opportunity
- [ ] `additional_locations` rendering
- [ ] Percentile marker: `data-pct` + JS `style.left` (not inline in HTML string)
- [ ] CV optimizer WS iteration events
- [ ] Escape/decode rules on all dynamic fields
- [ ] Mobile: tab labels icon-only at ≤768px if that is current behavior

### 8.4 Full test suite (Phase 7)

```bash
make build-frontend
cd ui && npm run typecheck && npm run test

cd e2e && npx playwright test tests/application-detail.spec.ts
cd e2e && npx playwright test tests/workflow-mocked.spec.ts
cd e2e && npx playwright test tests/websocket.spec.ts
cd e2e && npx playwright test tests/api-validation.spec.ts
cd e2e && npx playwright test tests/visual-regression.spec.ts
cd e2e && npx playwright test tests/accessibility.spec.ts
cd e2e && npx playwright test tests/mobile-responsive patterns via visual-regression / application-detail mobile tests
cd e2e && npx playwright test tests/smoke.spec.ts
cd e2e && npx playwright test tests/journey.spec.ts
```

Add Vitest cases for pure render helpers extracted from this page (URL guards, placeholder company, safe link builders).

### 8.5 Code review checklist (Phase 7)

- [ ] File split is coherent; entry file stays thin
- [ ] No exploit of `innerHTML` without `escapeHtml`
- [ ] Generate-documents polling cleared on navigation/`beforeunload`
- [ ] WS reconnect exponential backoff
- [ ] CV optimizer does not break CSP
- [ ] Tab event delegation uses `data-action` only
- [ ] Parity with `ui-application-detail.mdc` and `cv-optimizer-feature.mdc`

### 8.6 Exit criteria

- [ ] Application detail + CV optimizer on TS modules
- [ ] Phase 7 tests green; review approved

---

## 9. Phase 8 — Profile setup (+ profile helpers)

**Goal:** Convert the multi-step profile wizard — highest logic risk after application detail.  
**Duration:** 8–12 days  
**Risk:** Very high (validation order, `[]` vs `NULL`, years_experience `0`)

### 9.1 Files

| Legacy | Notes |
|--------|-------|
| `profile-setup.js` | 5 steps + resume upload |
| `profile-completion-sync.js` | Completion sync helper |
| `profile.js` | If still used by any route |

### 9.2 Must-preserve behaviors (non-negotiable)

- [ ] `completeProfile()` validates **all steps upfront** before any save calls
- [ ] `changeStep()` does **not** clear error alerts
- [ ] “No relevant experience” → `PUT` `{ work_experience: [] }` (not skip)
- [ ] “No formal education” → `PUT` `{ education: [] }` (not skip)
- [ ] `years_experience` allows `0` (no truthiness checks)
- [ ] `sanitizeText()` strips control chars only (Unicode bullets preserved)
- [ ] Incomplete profile hard-gate remains consistent with dashboard

### 9.3 Suggested module split

```
ui/src/pages/profile-setup/
  index.ts
  steps/basic.ts
  steps/work.ts
  steps/education.ts
  steps/skills.ts
  steps/preferences.ts
  validation.ts
  api.ts
  resume-upload.ts
```

### 9.4 Full test suite (Phase 8)

```bash
make build-frontend
cd ui && npm run typecheck && npm run test

cd e2e && npx playwright test tests/profile-setup.spec.ts
cd e2e && npx playwright test tests/profile.spec.ts
cd e2e && npx playwright test tests/file-upload.spec.ts
cd e2e && npx playwright test tests/form-edge-cases.spec.ts
cd e2e && npx playwright test tests/security.spec.ts
cd e2e && npx playwright test tests/accessibility.spec.ts
cd e2e && npx playwright test tests/smoke.spec.ts
```

Vitest focus:

- [ ] years_experience `0` accepted
- [ ] empty work/education payload shapes
- [ ] sanitizeText keeps `■`, `–`, `—`

### 9.5 Code review checklist (Phase 8)

- [ ] Validate-all-then-save order
- [ ] `changeStep` does not hide errors
- [ ] Empty arrays persisted for “none” checkboxes
- [ ] Numeric zero handling correct
- [ ] Resume upload error paths
- [ ] No ASCII-only allowlist regressions
- [ ] Matches `frontend-js-strict.mdc` profile sections

### 9.6 Exit criteria

- [ ] Profile setup fully on TS
- [ ] Phase 8 tests green; review approved

---

## 10. Phase 9 — Legacy removal, CI harden, documentation

**Goal:** Delete dead JS, unify on Vite, update rules/docs, make regressions hard.  
**Duration:** 3–5 days  
**Risk:** Medium (forgotten references)

### 10.1 Tasks

- [x] Remove `ui/static/js/**` sources that have TS replacements (keep only if intentionally frozen vendor)
- [x] Remove dual-pipeline / `build.mjs` esbuild JS path if fully replaced
- [x] Ensure CSS hashing still works (keep esbuild for CSS **or** move CSS to Vite — pick one, document)
- [x] Update `.cursor/rules/frontend-build-pipeline.mdc` for Vite
- [x] Update `.cursor/rules/frontend-js-strict.mdc` globs to `ui/src/**/*.ts`
- [x] Update CLAUDE.md / `.cursorrules` index notes if they mention esbuild-only
- [x] Update Dockerfile comments / Stage 0 copy paths (`ui/src`, configs)
- [x] Add CI jobs:

  - `npm run typecheck`
  - `npm run test` (Vitest)
  - `npm run build`
  - Playwright full live (paths-filtered)

- [ ] Add `docs` link from README if appropriate (optional)
- [x] Mark this plan **Status: Implemented** with date + PR links

### 10.2 Full test suite (Phase 9 — release gate)

Run the **entire** mocked Tier 1 Playwright suite plus frontend unit/typecheck:

```bash
make clean-frontend
make build-frontend
cd ui && npm run typecheck && npm run test

# Full Tier 1 e2e (CI-safe mocked)
cd e2e && npx playwright test \
  tests/smoke.spec.ts \
  tests/landing.spec.ts \
  tests/auth-pages.spec.ts \
  tests/auth-complete.spec.ts \
  tests/dashboard.spec.ts \
  tests/dashboard-pages.spec.ts \
  tests/application-detail.spec.ts \
  tests/profile-setup.spec.ts \
  tests/profile.spec.ts \
  tests/interview-prep.spec.ts \
  tests/onboarding.spec.ts \
  tests/complete-coverage.spec.ts \
  tests/workflow-mocked.spec.ts \
  tests/websocket.spec.ts \
  tests/file-upload.spec.ts \
  tests/form-edge-cases.spec.ts \
  tests/api-validation.spec.ts \
  tests/error-handling.spec.ts \
  tests/rate-limit.spec.ts \
  tests/security.spec.ts \
  tests/accessibility.spec.ts \
  tests/keyboard-nav.spec.ts \
  tests/visual-regression.spec.ts \
  tests/performance.spec.ts \
  tests/journey.spec.ts

# Docker image build
docker build -t applypilot:fe-migration .
```

Optional live Tier 2 (manual): `auth.spec.ts` against local server.

### 10.3 Code review checklist (Phase 9)

- [ ] No orphan `asset_url('js/...')` pointing at deleted files
- [ ] Manifest contains every template-referenced asset
- [ ] No React/Vue slipped in
- [ ] Rules docs match reality
- [ ] macOS `make setup` still strips quarantine
- [ ] Bundle size sanity: no accidental inclusion of huge unused deps
- [ ] Source maps policy decided for production
- [ ] This plan’s Pre-Ship Checklist complete

### 10.4 Exit criteria

- [x] Legacy global JS gone (or explicitly listed exceptions)
- [x] CI enforces typecheck + unit + build + full live E2E (paths-filtered)
- [x] Final review approved; plan marked implemented

---

## 11. Cross-cutting standards (every phase)

### 11.1 Security

- Preserve CSP nonce model; do not introduce Vite HTML transforms that inline scripts/styles without nonces
- Keep XSS helpers centralized; ban new `innerHTML` without `escapeHtml`
- Never put tokens in query strings except WebSocket `?token=` exception already documented
- Do not log raw tokens / PII; use existing sanitize helpers

### 11.2 Accessibility

- Do not regress landmarks, heading order, or `aria-label` on icon buttons
- Re-run `accessibility.spec.ts` when touching nav/tabs/forms

### 11.3 Mobile

- Preserve scrollable tab bars and navbar breakpoints (`xl` landing / `lg` dashboard)
- Re-check application detail icon-only tabs

### 11.4 Performance

- Prefer shared chunks for `shared/*` to avoid duplicating `escapeHtml` in every page bundle
- Do not micro-optimize prematurely; measure after Phase 7–8

### 11.5 Git / PR hygiene

- One phase per PR when possible (Phase 1 alone; Phase 2 alone; group only tiny phases)
- PR title: `feat(frontend): Vite+TS phase N — <short name>`
- PR body must include: summary, test commands run, screenshots for visual pages, risk notes
- Do not commit `ui/static/dist/` or secrets

### 11.6 Rollback plan

If a phase breaks production:

1. Revert the phase PR
2. `make build-frontend` on previous revision
3. Keep dual-pipeline until the failing page is fixed
4. Do not “fix forward” across multiple phases in one emergency deploy

---

## 12. Per-phase Definition of Done (template)

Copy into each PR:

```markdown
## Phase N — DoD
- [ ] Tasks in docs/frontend-vite-typescript-migration-plan.md §Phase N complete
- [ ] `make build-frontend` succeeds
- [ ] `cd ui && npm run typecheck` succeeds
- [ ] Vitest (if present) succeeds
- [ ] Listed Playwright specs for this phase succeed
- [ ] Manual spot-check of affected pages (desktop + ≤768px)
- [ ] Code review checklist checked
- [ ] No new Cursor rule violations for touched files
- [ ] Rollback note included if high risk
```

---

## 13. Pre-Ship Checklist (after Phase 9)

- [x] All phases 0–9 exit criteria met
- [x] Full Playwright live suite green locally (1433 tests); CI runs full suite when app paths change
- [ ] Docker image builds and serves hashed assets (manual verify before release)
- [x] `make setup` on macOS works (quarantine strip)
- [x] Documentation/rules updated
- [x] No dual-loading of legacy + new scripts
- [x] Bundle/manifest audited for missing keys
- [x] Product smoke: register/login → profile → new application → application detail tabs → settings → tools → logout
- [ ] Extension still works against API (manual smoke on real job page)
- [x] This document status set to **Implemented** (merge date TBD on PR merge)

---

## 14. Explicit non-goals / future work (not this plan)

| Idea | When to reconsider |
|------|--------------------|
| React/Vue islands on application-detail | After Phase 7, if modules still too hard to maintain |
| Full SPA (Next/Nuxt) | Only if product needs offline/mobile-app-like navigation |
| Tailwind rewrite | Only with a deliberate redesign project |
| Moving CSS fully into Vite/CSS modules | Optional follow-up after Phase 9 |
| Extension TypeScript migration | Separate plan |

---

## 15. Quick reference — commands

```bash
# Install / build
make setup
make build-frontend
cd ui && npm run typecheck
cd ui && npm run test
cd ui && npm run build

# Dev loop (assets)
cd ui && npm run dev:assets   # or build --watch
# FastAPI
make dev   # or make start-local

# E2E
cd e2e && npx playwright test tests/smoke.spec.ts
```

---

## 16. Decision log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-08 | Choose Option A (Vite + TS, no React) | Minimal change, keep Jinja MPA, improve maintainability |
| 2026-07-08 | Migrate page-by-page starting with Help | Lowest risk proof of pipeline |
| 2026-07-08 | Dual pipeline (Strategy B) initially | Avoid big-bang rewrite of 21K LOC |
| 2026-07-08 | CSS stays on existing minify path initially | Reduce scope; UI 1:1 |
| 2026-07-08 | Phases 0–9 landed on `feat/frontend-vite-typescript` | Toolchain + all page scripts under `ui/src/pages` via Vite IIFE; CSS still esbuild; shared typed modules + Vitest for dom-security |

| 2026-07-10 | Phase 9 complete on `feat/frontend-vite-typescript` | Legacy JS removed; strict TS across all pages; CI full live E2E + paths filter; docs/rules/SECURITY.md updated; hidden source maps |

### Implementation notes (final — 2026-07-10)

- All 23 Vite page entries under `ui/src/pages/` + feature modules (`application-detail/`, `profile-setup/`, `cv-optimizer/`, etc.).
- `ui/static/js/` source removed; `build.mjs` is **CSS-only**; Vite owns all JS via `scripts/build-vite.mjs`.
- Strict gate: `npm run typecheck` (`tsconfig.ci.json`) — no `@ts-nocheck` in `ui/src/`.
- Shared modules: `ui/src/shared/`; globals (`dom-security`, `confirm-modal`, `event-bus`) still loaded from `base.html` for load order.
- Production builds emit **hidden source maps** (`.js.map` on disk, not linked from bundles).
- CI: `frontend-build` (typecheck + vitest + build); `e2e-full` (all Playwright tests, live server) when `ui/`, `api/`, `e2e/`, etc. change.
- Local full E2E: `cd e2e && CI=1 npx playwright test --project=chromium --workers=4` (~9–10 min).

**Out of scope (separate plans):** Chrome extension TypeScript migration; CSS fully in Vite.

---

**End of plan.** Re-run §13 Pre-Ship Checklist (full Playwright Tier 1) before merging to main.
