import { test, expect, type Page } from '@playwright/test';
import { LoginPage, RegisterPage, DashboardPage, ProfileSetupPage } from '../pages';
import { generateTestEmail } from '../fixtures/test-data';
import { setupAuth, setupAllMocks } from '../utils/api-mocks';

/**
 * Smoke Tests — PR gate (@smoke) + optional live-server regression (@live)
 *
 * CI PR gate (~3 min, mocked API, server still serves HTML):
 *   npm run test:smoke:ci
 *
 * Full smoke including live DB registration (local / nightly):
 *   npm run test:smoke
 *
 * Live registration only:
 *   npm run test:smoke:live
 */

const SMOKE_SESSION_ID = 'smoke-session-001';
const SMOKE_APP_URL = `/dashboard/application/${SMOKE_SESSION_ID}`;
const SMOKE_INTERVIEW_URL = `/dashboard/interview-prep/${SMOKE_SESSION_ID}`;
const SMOKE_JOB_DESCRIPTION =
  'Senior Software Engineer at Example Corp. Requirements: Python, FastAPI, React, PostgreSQL. '.repeat(3);

const SMOKE_WORKFLOW_RESULTS = {
  application_id: 'smoke-app-001',
  session_id: SMOKE_SESSION_ID,
  status: 'completed',
  job_analysis: {
    job_title: 'Senior Software Engineer',
    company_name: 'Example Corp',
    employment_type: 'Full-time',
  },
  profile_matching: { overall_match_score: 0.82 },
  company_research: { industry: 'Technology', mission_vision: 'Build great products.' },
  cover_letter: { letter: 'Dear Hiring Manager,\n\nI am excited to apply.\n' },
  resume_recommendations: { overview: 'Strong match overall.' },
};

async function mockCompletedApplication(page: Page): Promise<void> {
  await page.route(`**/api/v1/workflow/status/${SMOKE_SESSION_ID}`, (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'completed', session_id: SMOKE_SESSION_ID }),
  }));
  await page.route(`**/api/v1/workflow/results/${SMOKE_SESSION_ID}`, (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(SMOKE_WORKFLOW_RESULTS),
  }));
  await page.route('**/api/v1/applications/**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ updated: true }),
  }));
}

async function mockInterviewPrepGenerateState(page: Page): Promise<void> {
  await page.route(`**/api/v1/interview-prep/${SMOKE_SESSION_ID}`, (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ has_interview_prep: false }),
  }));
  await page.route(`**/api/v1/workflow/results/${SMOKE_SESSION_ID}`, (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      job_analysis: {
        job_title: 'Senior Software Engineer',
        company_name: 'Example Corp',
      },
    }),
  }));
}

async function expectPageDistScriptsLoad(page: Page, path: string): Promise<void> {
  await page.goto(path, { waitUntil: 'load' });
  await page.waitForLoadState('domcontentloaded');
  const scriptSrcs = await page.locator('script[src*="/static/dist/js/"]').evaluateAll((nodes) =>
    nodes
      .map((node) => (node as HTMLScriptElement).getAttribute('src'))
      .filter((src): src is string => !!src),
  );
  expect(scriptSrcs.length, `expected dist JS on ${path}`).toBeGreaterThan(0);
  for (const src of scriptSrcs) {
    const url = new URL(src, page.url()).toString();
    const response = await page.request.get(url);
    expect(response.status(), `expected 200 for ${url}`).toBe(200);
  }
}

// ---------------------------------------------------------------------------
// LIVE SERVER — real registration / DB (skip in CI via @smoke gate)
// ---------------------------------------------------------------------------
test.describe('Live Server Smoke', { tag: '@live' }, () => {

  test.describe('Authentication Flow', () => {
    let testEmail: string;
    const testPassword = 'SmokeTest123!';

    test('user can register', async ({ page }) => {
      testEmail = generateTestEmail('smoke');
      const registerPage = new RegisterPage(page);
      
      await registerPage.navigate();
      await registerPage.handleCookieConsent();
      await registerPage.register({
        name: 'Smoke Test User',
        email: testEmail,
        password: testPassword,
        acceptTerms: true,
      });
      
      // Should redirect to profile setup or dashboard
      await page.waitForURL(/profile\/setup|dashboard/, { timeout: 15000 });
      expect(page.url()).toMatch(/profile\/setup|dashboard/);
    });

    test('user can login', async ({ page }) => {
      // Use a fresh user for login test
      const email = generateTestEmail('smoke_login');
      const registerPage = new RegisterPage(page);
      
      // First register
      await registerPage.navigate();
      await registerPage.handleCookieConsent();
      await registerPage.register({
        name: 'Smoke Login Test',
        email: email,
        password: testPassword,
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile\/setup|dashboard/, { timeout: 15000 });
      
      // Logout by clearing storage
      await page.evaluate(() => localStorage.clear());
      
      // Now login
      const loginPage = new LoginPage(page);
      await loginPage.navigate();
      await loginPage.login(email, testPassword);
      
      await page.waitForURL(/profile\/setup|dashboard/, { timeout: 15000 });
      expect(page.url()).toMatch(/profile\/setup|dashboard/);
    });
  });

  test.describe('Profile Setup', () => {
    test.describe.configure({ timeout: 60000 });

    test('profile setup wizard completes', async ({ page }) => {
      const email = generateTestEmail('smoke_profile');
      const registerPage = new RegisterPage(page);
      
      await registerPage.navigate();
      await registerPage.handleCookieConsent();
      await registerPage.register({
        name: 'Smoke Profile Test',
        email: email,
        password: 'SmokeTest123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile\/setup|dashboard/, { timeout: 30000 });
      
      if (page.url().includes('profile/setup')) {
        const profilePage = new ProfileSetupPage(page);
        await profilePage.quickSetup({
          title: 'Software Engineer',
          yearsExperience: 5,
          skills: ['JavaScript', 'Python'],
        });
        
        await page.waitForURL(/dashboard/, { timeout: 30000 });
      }
      
      expect(page.url()).toContain('dashboard');
    });
  });

  test.describe('Dashboard & Navigation', () => {
    test.describe.configure({ mode: 'serial', timeout: 60000 });
    let page: any;
    
    test.beforeAll(async ({ browser }) => {
      test.setTimeout(60000);
      page = await browser.newPage();
      const email = generateTestEmail('smoke_dash');
      const registerPage = new RegisterPage(page);
      
      await registerPage.navigate();
      await registerPage.handleCookieConsent();
      await registerPage.register({
        name: 'Smoke Dashboard Test',
        email: email,
        password: 'SmokeTest123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile\/setup|dashboard/, { timeout: 30000 });
      
      if (page.url().includes('profile/setup')) {
        const profilePage = new ProfileSetupPage(page);
        await profilePage.quickSetup({
          title: 'Engineer',
          yearsExperience: 3,
          skills: ['Python'],
        });
      }
      
      await page.waitForURL(/dashboard/, { timeout: 30000 });
      
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
    });
    
    test.afterAll(async () => {
      await page?.close();
    });

    test('dashboard loads after login', async () => {
      await expect(page.locator('nav, .navbar, .sidebar').first()).toBeVisible();
    });

    test('can navigate to new application', async () => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      const link = page.locator('a.action-btn[href="/dashboard/new-application"]');
      await expect(link).toBeVisible({ timeout: 10000 });
      await link.click();
      await page.waitForURL(/new-application/, { timeout: 10000 });
      expect(page.url()).toContain('new-application');
    });

    test('can navigate to career tools', async () => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      const link = page.locator('a.action-btn[href="/dashboard/tools"]');
      await expect(link).toBeVisible({ timeout: 10000 });
      await link.click();
      await page.waitForURL(/tools/, { timeout: 10000 });
      expect(page.url()).toContain('tools');
    });

    test('can navigate to settings', async () => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      const link = page.locator('a.nav-btn[href="/dashboard/settings"]');
      await expect(link).toBeVisible({ timeout: 10000 });
      await link.click();
      await page.waitForURL(/settings/, { timeout: 10000 });
      expect(page.url()).toContain('settings');
    });
  });

  test.describe('New Application Form', () => {
    test.describe.configure({ timeout: 60000 });

    test('new application form has required elements', async ({ page }) => {
      const email = generateTestEmail('smoke_app');
      const registerPage = new RegisterPage(page);
      
      await registerPage.navigate();
      await registerPage.handleCookieConsent();
      await registerPage.register({
        name: 'Smoke App Test',
        email: email,
        password: 'SmokeTest123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile\/setup|dashboard/, { timeout: 30000 });
      
      if (page.url().includes('profile/setup')) {
        const profilePage = new ProfileSetupPage(page);
        await profilePage.quickSetup({
          title: 'Engineer',
          yearsExperience: 3,
          skills: ['Python'],
        });
      }
      
      await page.waitForURL(/dashboard/, { timeout: 30000 });
      
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      
      // Navigate to new application
      await page.goto('/dashboard/new-application');
      
      // Verify form elements exist
      const hasTextarea = await page.locator('textarea').count() > 0;
      const hasInput = await page.locator('input').count() > 0;
      const hasButton = await page.locator('button').count() > 0;
      
      expect(hasTextarea || hasInput).toBeTruthy();
      expect(hasButton).toBeTruthy();
    });
  });

  test.describe('Career Tools', () => {
    test.describe.configure({ timeout: 60000 });

    test('career tools page loads with tabs', async ({ page }) => {
      const email = generateTestEmail('smoke_tools');
      const registerPage = new RegisterPage(page);
      
      await registerPage.navigate();
      await registerPage.handleCookieConsent();
      await registerPage.register({
        name: 'Smoke Tools Test',
        email: email,
        password: 'SmokeTest123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile\/setup|dashboard/, { timeout: 30000 });
      
      if (page.url().includes('profile/setup')) {
        const profilePage = new ProfileSetupPage(page);
        await profilePage.quickSetup({
          title: 'Engineer',
          yearsExperience: 3,
          skills: ['Python'],
        });
      }
      
      await page.waitForURL(/dashboard/, { timeout: 30000 });
      
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      
      // Navigate to tools
      await page.goto('/dashboard/tools');
      
      // Verify tabs/tool sections exist
      const hasTabs = await page.locator('.nav-link, .tab, [role="tab"]').count() > 0;
      const hasForms = await page.locator('form, .tool-form, .card').count() > 0;
      
      expect(hasTabs || hasForms).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// MOCKED SMOKE — default PR gate (fast, no DB registration)
// ---------------------------------------------------------------------------
test.describe('Mocked Smoke Tests', { tag: '@smoke' }, () => {

  test.describe('Infrastructure', () => {
    test('API health check responds', async ({ request }) => {
      const response = await request.get('/health');
      expect(response.ok()).toBeTruthy();
    });

    test('unknown route returns 404', async ({ request }) => {
      const response = await request.get('/this-does-not-exist-12345');
      expect(response.status()).toBe(404);
    });

    test('auth endpoints respond', async ({ request }) => {
      const response = await request.post('/api/v1/auth/login', {
        data: { email: 'test@test.com', password: 'test' },
      });
      expect(response.status()).toBeGreaterThanOrEqual(400);
      expect(response.status()).toBeLessThan(500);
    });

    test('profile endpoint requires auth', async ({ request }) => {
      const response = await request.get('/api/v1/profile');
      expect([401, 403, 429].includes(response.status())).toBeTruthy();
    });
  });

  test.describe('Dashboard Loads With Mock Auth', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
    });

    test('dashboard page loads with auth token', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      expect(page.url()).toContain('dashboard');
    });

    test('dashboard has a welcome card', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('.welcome-card')).toBeVisible({ timeout: 5000 });
    });

    test('dashboard displays stat cards', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('.stats-cards')).toBeVisible({ timeout: 5000 });
    });

    test('dashboard navbar is visible', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('nav, .navbar').first()).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('New Application Form (Mocked)', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
    });

    test('new application page loads', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('domcontentloaded');
      expect(page.url()).toContain('new-application');
    });

    test('new application form has job description textarea', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('#jobDescription')).toBeVisible({ timeout: 5000 });
    });

    test('new application form has analyze button', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('[data-action="process-application"]')).toBeVisible({ timeout: 5000 });
    });

    test('cancel button links back to /dashboard', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('domcontentloaded');
      const cancelLink = page.locator('.form-actions a[href="/dashboard"], .form-actions a.btn-secondary');
      await expect(cancelLink.first()).toBeVisible();
    });
  });

  test.describe('Settings Page (Mocked)', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
      await page.route('**/api/v1/settings**', r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) }));
    });

    test('settings page loads', async ({ page }) => {
      await page.goto('/dashboard/settings');
      await page.waitForLoadState('domcontentloaded');
      expect(page.url()).toContain('settings');
    });

    test('settings page has navigation links', async ({ page }) => {
      await page.goto('/dashboard/settings');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('[data-section]').first()).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Career Tools Page (Mocked)', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
    });

    test('career tools page loads', async ({ page }) => {
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
      expect(page.url()).toContain('tools');
    });

    test('career tools page has 6 tool navigation links', async ({ page }) => {
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('[data-tool]')).toHaveCount(6);
    });

    test('thank you tool section is default', async ({ page }) => {
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('#thankYouSection')).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Access Control (Mocked)', () => {
    test('unauthenticated dashboard redirects to login', async ({ page }) => {
      // No auth setup — clear any existing token
      await page.goto('/dashboard');
      await page.waitForURL(/auth\/login/, { timeout: 8000 });
      expect(page.url()).toContain('auth/login');
    });

    test('unauthenticated new-application redirects to login', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForURL(/auth\/login|\//, { timeout: 8000 });
      expect(page.url()).not.toContain('new-application');
    });

    test('unauthenticated settings redirects to login', async ({ page }) => {
      await page.goto('/dashboard/settings');
      await page.waitForURL(/auth\/login|\//, { timeout: 8000 });
      expect(page.url()).not.toContain('settings');
    });

    test('unauthenticated tools redirects to login', async ({ page }) => {
      await page.goto('/dashboard/tools');
      await page.waitForURL(/auth\/login|\//, { timeout: 8000 });
      expect(page.url()).not.toContain('/tools');
    });
  });

  test.describe('Public Pages (Mocked)', () => {
    test('login page is accessible without auth', async ({ page }) => {
      await page.goto('/auth/login');
      await expect(page.locator('#email')).toBeVisible();
    });

    test('register page is accessible without auth', async ({ page }) => {
      await page.goto('/auth/register');
      await expect(page.locator('#full-name')).toBeVisible();
    });

    test('reset-password page is accessible', async ({ page }) => {
      await page.goto('/auth/reset-password');
      await expect(page.locator('#forgotPasswordSection #email')).toBeVisible();
    });

    test('homepage loads correctly', async ({ page }) => {
      await page.goto('/');
      await expect(page.locator('body')).toBeVisible();
    });

    test('help page loads correctly', async ({ page }) => {
      await page.goto('/help');
      await expect(page.locator('body')).toBeVisible();
    });

    test('cookie consent banner can be accepted', async ({ page }) => {
      await page.goto('/');
      await page.evaluate(() => localStorage.removeItem('cookie_consent'));
      await page.reload();
      await page.waitForLoadState('domcontentloaded');
      const banner = page.locator('#cookie-consent-banner');
      await expect(banner).toHaveClass(/visible/, { timeout: 5000 });
      await page.locator('[data-action="cookie-accept-all"]').click();
      await expect(banner).not.toHaveClass(/visible/);
      const stored = await page.evaluate(() => localStorage.getItem('cookie_consent'));
      expect(stored).toBeTruthy();
    });
  });

  test.describe('Critical Paths (Mocked)', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
    });

    test('application detail page loads with job title and tabs', async ({ page }) => {
      await mockCompletedApplication(page);
      await page.goto(SMOKE_APP_URL);
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('#mainContent')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('#jobTitle')).toContainText('Senior Software Engineer');
      await expect(page.locator('.page-tab[data-tab]').first()).toBeVisible();
    });

    test('analyze button triggers workflow start API', async ({ page }) => {
      let workflowStarted = false;
      await page.route('**/api/v1/workflow/start', (route) => {
        workflowStarted = true;
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ session_id: SMOKE_SESSION_ID, status: 'processing' }),
        });
      });
      await page.route(`**/api/v1/workflow/status/${SMOKE_SESSION_ID}`, (route) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'processing' }),
      }));

      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('domcontentloaded');
      await page.locator('#jobDescription').fill(SMOKE_JOB_DESCRIPTION);
      await page.locator('[data-action="process-application"]').click();
      await expect.poll(() => workflowStarted, { timeout: 5000 }).toBe(true);
    });

    test('key page bundled scripts return HTTP 200', async ({ page }) => {
      await mockCompletedApplication(page);
      await expectPageDistScriptsLoad(page, '/');
      await expectPageDistScriptsLoad(page, '/help');
      await expectPageDistScriptsLoad(page, '/dashboard');
      await expectPageDistScriptsLoad(page, SMOKE_APP_URL);
    });

    test('settings privacy tab shows export data button', async ({ page }) => {
      await page.route('**/api/v1/settings**', (route) => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      }));
      await page.goto('/dashboard/settings');
      await page.waitForLoadState('domcontentloaded');
      await page.locator('[data-section="privacy"]').click();
      await expect(page.locator('#privacySection')).toBeAttached();
      await expect(page.locator('[data-action="exportData"]').first()).toBeVisible({ timeout: 5000 });
    });

    test('help search reveals matching FAQ items', async ({ page }) => {
      await page.goto('/help');
      await page.waitForLoadState('domcontentloaded');
      const totalItems = await page.locator('.faq-item').count();
      expect(totalItems).toBeGreaterThan(1);
      await page.locator('#helpSearch').fill('export my data');
      const visibleItems = page.locator('.faq-item:not(.is-search-hidden)');
      await expect(visibleItems.first()).toContainText(/export my data/i, { timeout: 5000 });
      const visibleCount = await visibleItems.count();
      expect(visibleCount).toBeGreaterThan(0);
      expect(visibleCount).toBeLessThan(totalItems);
    });

    test('interview prep page loads in generate state', async ({ page }) => {
      await mockInterviewPrepGenerateState(page);
      await page.goto(SMOKE_INTERVIEW_URL);
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('[data-action="generate-interview-prep"]')).toBeVisible({ timeout: 10000 });
    });

    test('thank you tool submit triggers tools API', async ({ page }) => {
      let apiCalled = false;
      await page.route('**/api/v1/tools/thank-you**', (route) => {
        apiCalled = true;
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            thank_you_note: 'Dear Jane, thank you for your time.',
            subject_line: 'Thank You — Interview',
          }),
        });
      });

      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
      await page.locator('#interviewerName').fill('Jane Smith');
      await page.locator('#companyName').fill('Acme Corp');
      await page.locator('#jobTitle').fill('Senior Engineer');
      await page.locator('#interviewType').selectOption('video');
      await page.locator('#thankYouSubmit').click();
      await expect.poll(() => apiCalled, { timeout: 5000 }).toBe(true);
    });
  });
});
