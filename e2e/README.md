# ApplyPilot — E2E Test Suite

End-to-end browser tests using [Playwright](https://playwright.dev/).

**1,380 tests · 29 spec files · TypeScript strict · zero compile errors**

---

## Quick Start

```bash
cd e2e
npm install
npx playwright install chromium   # first time only

# Run all Tier 1 (CI-safe, no server needed)
npm run test:ci

# Smoke tests only (~3 min)
npm run test:smoke

# Headed mode (see browser)
npm run test:headed

# Interactive UI mode
npm run test:ui
```

---

## Test Tiers

### Tier 1 — Mocked, CI-safe (~1,200 tests)

All routes intercepted via `page.route()`. No live server, no database, no LLM needed.

| File | Tests | What it covers |
|------|------:|----------------|
| `dashboard-pages.spec.ts` | 208 | All dashboard tabs, settings, career tools, stat cards, mobile |
| `landing.spec.ts` | 186 | Hero, navbar, sections, footer, a11y, cookie consent, static assets |
| `auth-pages.spec.ts` | 151 | Login/register/forgot/reset/verify — structure + validation |
| `interview-prep.spec.ts` | 85 | Generate state, 4 question tabs, content validation, mobile layout |
| `profile-setup.spec.ts` | 72 | 5-step wizard, field validation, step navigation, skills |
| `application-detail.spec.ts` | 68 | **10 tabs** (Optimize CV + Mock Session + Outreach), sub-tabs, cover letter, company research, mobile |
| `onboarding.spec.ts` | 45 | Auto-show, step navigation, skip/complete, `window.Onboarding` API, a11y |
| `complete-coverage.spec.ts` | 42 | Authenticated page coverage: dashboard, settings, career tools, history |
| `security.spec.ts` | 40 | XSS prevention, JWT format, CSP headers, API security |
| `extension.spec.ts` | 39 | Manifest V3, content script, service worker, popup JS |
| `error-handling.spec.ts` | 39 | 401/403/429/500 responses, network errors, form validation |
| `smoke.spec.ts` | 46 | Critical path — `@smoke` PR gate + optional `@live` registration |
| `workflow-mocked.spec.ts` | 31 | Workflow processing/complete/error/access-control (mocked) |
| `form-edge-cases.spec.ts` | 29 | Unicode, boundary values, special chars, XSS injection |
| `auth-complete.spec.ts` | 29 | Google OAuth (mocked), email verification, account lockout |
| `dashboard.spec.ts` | 28 | Dashboard nav, onboarding, mocked settings, tools, history |
| `journey.spec.ts` | 27 | Multi-step user journeys: new app, career tools, settings, auth redirect |
| `keyboard-nav.spec.ts` | 25 | Tab/Enter/Space/Escape/Backspace/ArrowDown across all pages |
| `visual-regression.spec.ts` | 24 | Page structure at desktop, tablet, and mobile viewports |
| `performance.spec.ts` | 23 | Page load timing assertions |
| `accessibility.spec.ts` | 23 | ARIA labels, landmarks, heading hierarchy |
| `api-validation.spec.ts` | 21 | API response shapes: full/partial/null fields, error bodies, auth tokens |
| `websocket.spec.ts` | 20 | Workflow states (processing/failed), progress polling, network resilience |
| `file-upload.spec.ts` | 19 | Resume/job upload, fixture files, API mock responses |
| `rate-limit.spec.ts` | 12 | 429 + Retry-After: login, registration, career tools, workflow, forgot-password |

### Tier 2 — Live server required (~56 tests)

These register real users and call real endpoints.
**Do not run in CI without a running server and database.**

| File | Tests | Requirements |
|------|------:|--------------|
| `auth.spec.ts` | 18 | Real register/login/logout → DB writes |
| `tools.spec.ts` | 16 | Career tool submissions (requires authenticated session) |
| `profile.spec.ts` | 12 | Profile CRUD, API key management, data export |
| `workflow.spec.ts` | 10 | Full workflow: submit → poll → results (LLM optional) |

---

## Running Tests

### CI Commands (Tier 1 only — no server required)

```bash
# Run all mocked Tier 1 tests
npx playwright test \
  landing auth-pages auth-complete dashboard dashboard-pages \
  profile-setup application-detail interview-prep onboarding \
  workflow-mocked smoke security error-handling complete-coverage \
  visual-regression extension api-validation keyboard-nav rate-limit \
  journey form-edge-cases performance accessibility websocket file-upload \
  --project=chromium --workers=4

# Smoke gate only (~3 min, mocked — use in PR CI)
SMOKE=1 SKIP_SERVER=1 npx playwright test tests/smoke.spec.ts --grep @smoke --project=chromium

# Live registration smoke (local / nightly)
SMOKE=1 npx playwright test tests/smoke.spec.ts --grep @live --project=chromium

# Sharded (4 parallel jobs, ~4 min total)
npx playwright test --project=chromium --shard=1/4
npx playwright test --project=chromium --shard=2/4
npx playwright test --project=chromium --shard=3/4
npx playwright test --project=chromium --shard=4/4
```

### Development Commands

```bash
# All tests
npm test

# Single file
npx playwright test tests/onboarding.spec.ts --project=chromium

# Filter by describe section (lettered prefix system A–P)
npx playwright test tests/onboarding.spec.ts --grep "H\. window\.Onboarding"
npx playwright test tests/interview-prep.spec.ts --grep "L\. Content Validation"

# Specific test by name
npx playwright test --grep "Back button is hidden on first step"

# Live-server Tier 2 tests
uvicorn main:app --host 0.0.0.0 --port 8000 &
npx playwright test tests/auth.spec.ts tests/tools.spec.ts --project=chromium
```

### npm Scripts

| Command | Description |
|---------|-------------|
| `npm test` | Run all tests |
| `npm run test:smoke` | All smoke tests (`@smoke` + `@live`) |
| `npm run test:smoke:ci` | Mocked PR gate only (`@smoke`, ~3 min) |
| `npm run test:smoke:live` | Live registration smoke only (`@live`) |
| `npm run test:ci` | Full Tier 1 suite for CI |
| `npm run test:headed` | Visible browser window |
| `npm run test:ui` | Interactive Playwright UI |
| `npm run test:debug` | Debug mode with breakpoints |
| `npm run test:chromium` | Chromium only |
| `npm run test:firefox` | Firefox only |
| `npm run test:webkit` | WebKit/Safari only |
| `npm run test:mobile` | Mobile viewports |
| `npm run report` | Open HTML test report |
| `npm run codegen` | Record test by clicking |

---

## File Structure

```
e2e/
├── playwright.config.ts        # Playwright configuration
├── package.json                # Dependencies and scripts
├── tsconfig.json               # TypeScript (strict: true)
├── global.setup.ts             # Global setup
├── pages/                      # Page Object Models
│   ├── BasePage.ts
│   ├── LoginPage.ts
│   ├── RegisterPage.ts
│   ├── DashboardPage.ts
│   ├── ProfileSetupPage.ts
│   ├── NewApplicationPage.ts
│   ├── ToolsPage.ts
│   ├── SettingsPage.ts
│   ├── InterviewPrepPage.ts
│   ├── ResetPasswordPage.ts
│   ├── VerifyEmailPage.ts
│   └── index.ts
├── fixtures/
│   ├── test-data.ts            # generateTestEmail(), testProfile, testJobPostings
│   ├── auth.setup.ts
│   └── files/
│       ├── sample-resume.txt
│       └── sample-job.txt
├── utils/
│   └── api-mocks.ts            # MOCK_JWT, setupAuth, setupAllMocks, setupProfileMocks
└── tests/                      # 29 spec files, 1,380 tests
    ├── api-validation.spec.ts  # API response shape validation
    ├── accessibility.spec.ts
    ├── application-detail.spec.ts
    ├── auth.spec.ts            # Tier 2
    ├── auth-complete.spec.ts
    ├── auth-pages.spec.ts
    ├── complete-coverage.spec.ts
    ├── dashboard.spec.ts
    ├── dashboard-pages.spec.ts
    ├── error-handling.spec.ts
    ├── extension.spec.ts
    ├── file-upload.spec.ts
    ├── form-edge-cases.spec.ts
    ├── interview-prep.spec.ts
    ├── journey.spec.ts         # Multi-step user journeys
    ├── keyboard-nav.spec.ts    # Keyboard navigation
    ├── landing.spec.ts
    ├── onboarding.spec.ts      # Onboarding tour (window.Onboarding)
    ├── performance.spec.ts
    ├── profile.spec.ts         # Tier 2
    ├── profile-setup.spec.ts
    ├── rate-limit.spec.ts      # 429 handling
    ├── security.spec.ts
    ├── smoke.spec.ts
    ├── tools.spec.ts           # Tier 2
    ├── visual-regression.spec.ts
    ├── websocket.spec.ts
    ├── workflow.spec.ts        # Tier 2
    └── workflow-mocked.spec.ts
```

---

## Core Utilities (`utils/api-mocks.ts`)

**Always import from here — never recreate locally:**

```typescript
import { setupAuth, setupAllMocks, setupProfileMocks, MOCK_JWT } from '../utils/api-mocks';

// Inject a valid 3-part JWT + cookie_consent into localStorage
await setupAuth(page);

// Also mock profile + applications + preferences API endpoints
await setupAllMocks(page);
```

### MOCK_JWT

`MOCK_JWT` is a real 3-part JWT string (`header.payload.sig`). Many client scripts validate `token.split('.').length === 3` and redirect to `/auth/login` on failure. **Never use bare strings like `'mock-token'`.**

### Cookie Consent

Cookie consent MUST include `version: '1.0'`. The banner overlays the page and blocks all pointer events if the version is missing. `setupAuth` sets this correctly.

---

## Writing New Tests

### 1. Always use `(route: any)` on route callbacks

```typescript
// ✅ Required — TypeScript strict mode
await page.route('**/api/v1/profile', (route: any) => route.fulfill({
  status: 200, contentType: 'application/json',
  body: JSON.stringify({ name: 'Test' }),
}));

// ❌ Fails TypeScript compilation
await page.route('**/api/v1/profile', route => route.fulfill({ ... }));
```

### 2. Mock data — arrays not strings

```typescript
// ✅ Correct
three_key_selling_points: ['Point A', 'Point B', 'Point C'],
required_skills: ['Python', 'FastAPI'],

// ❌ Breaks .map() calls in render functions
three_key_selling_points: 'Point A',
```

### 3. Wait for dynamic content

```typescript
// ✅ Always wait for SPA state transitions
await page.goto(PAGE_URL);
await page.locator('#mainContent').waitFor({ state: 'visible', timeout: 10000 });

// ❌ May assert before data loads
await page.goto(PAGE_URL);
await expect(page.locator('#mainContent')).toBeVisible();
```

### 4. Section organisation (lettered prefix)

```typescript
test.describe('A. Page Structure', () => { ... });
test.describe('B. Generate State', () => { ... });
test.describe('C. First Step Content', () => { ... });
// ... up to P for largest files
```

This enables `--grep "C\."` filtering in CI.

### 5. Avoid `isAttached()` — use `count() > 0`

```typescript
// ✅
if (await element.count() > 0) { ... }

// ❌ TS2339 — method does not exist
if (await element.isAttached()) { ... }
```

---

## Onboarding Tour Tests

`onboarding.spec.ts` tests the `window.Onboarding` JS API. Key selectors:

| Element | Selector |
|---------|----------|
| Overlay | `#onboarding-overlay` |
| Title | `#onboarding-title` |
| Next | `[data-action="onboarding-next"]` |
| Back | `[data-action="onboarding-prev"]` |
| Skip | `[data-action="onboarding-skip"]` |
| Progress dots | `#onboarding-progress .progress-dot` |

Suppress the tour in non-onboarding tests:

```typescript
await page.addInitScript(() => {
  localStorage.setItem('onboarding_completed', JSON.stringify({
    version: '2.0', completedAt: new Date().toISOString(),
  }));
});
```

---

## Rate Limit Pattern

```typescript
await page.route('**/api/v1/auth/login', (route: any) => route.fulfill({
  status: 429,
  contentType: 'application/json',
  headers: { 'Retry-After': '60' },
  body: JSON.stringify({ detail: 'Too many attempts', error_code: 'RATE_4001' }),
}));

// Assert: no JS errors, page still visible, user stays on same page
const errors: string[] = [];
page.on('pageerror', e => errors.push(e.message));
// ... trigger the action ...
expect(errors.length).toBe(0);
await expect(page).toHaveURL(/login/);
```

---

## Common Issues & Fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `mainContent` never visible | `.map()` on non-array mock field | Ensure all iterable fields are arrays |
| Cookie banner blocks clicks | Missing `version:'1.0'` | Use `setupAuth(page)` which sets it correctly |
| Redirects to `/dashboard` during access control test | Login bounce-back from valid token | Assert URL moved *away* from protected path |
| `browserType.launch` executable error | Playwright browsers not installed | `npx playwright install chromium --with-deps` |
| Wizard won't advance past step N | Required fields not filled | Fill all required fields before clicking Next |
| TS7006 `route` implicit any | Missing type annotation | Always write `(route: any) =>` |
| `isAttached` TypeScript error | Not in Playwright 1.40 API | Replace with `count() > 0` |
| Onboarding overlay blocks tests | `onboarding_completed` not set | Add to `addInitScript` to suppress tour |
| `waitForURL` throws `ERR_ABORTED` | Frame abort during redirect | Wrap in `Promise.all([waitForURL(...).catch(()=>{}), ...])`  |

---

## CI/CD Integration

GitHub Actions runs the **E2E smoke gate** only (`e2e-smoke` in `.github/workflows/ci.yml`): ~46 `@smoke` tests from `tests/smoke.spec.ts` on chromium. The full ~1,380 Playwright suite is **not** the default CI gate — run it locally when needed.

**Runs smoke E2E when app-related files change** (paths filter): `ui/`, `e2e/`, `api/`, `agents/`, `workflows/`, `models/`, `utils/`, `middleware/`, `main.py`, `alembic/`, `requirements.txt`, `extension/`, or the CI workflow itself.

**Skips E2E** on docs-only / rules-only PRs (e.g. `docs/`, `CHANGELOG.md`, `.cursor/rules/` with no app code).

```yaml
# ci.yml (simplified)
e2e-smoke:
  needs: changes          # dorny/paths-filter@v3
  if: needs.changes.outputs.e2e == 'true'
  run: npx playwright test tests/smoke.spec.ts --grep @smoke --project=chromium --workers=4
```

**Local equivalents:**

```bash
# Same as CI smoke gate
cd e2e && npx playwright test tests/smoke.spec.ts --grep @smoke --project=chromium --workers=4

# Full suite (optional / local)
CI=1 npx playwright test --project=chromium --workers=4
```

---

## Debugging

```bash
# Visible browser
npm run test:headed

# Interactive step-through UI
npm run test:ui

# Debug with breakpoints
npm run test:debug

# Show trace for a failed test
npx playwright show-trace test-results/path/to/trace.zip
```

Screenshots are captured automatically on failure (`test-results/`).  
Video is recorded on first retry (`test-results/`).
