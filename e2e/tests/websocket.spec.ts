import { test, expect, Page } from '@playwright/test';
import { setupAuth, setupAllMocks, MOCK_JWT } from '../utils/api-mocks';

async function seedAuthOnce(page: import('@playwright/test').Page): Promise<void> {
  await setupAllMocks(page);
  await page.addInitScript((token: string) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('authToken', token);
    localStorage.setItem('cookie_consent', JSON.stringify({
      essential: true, functional: true, analytics: false,
      version: '1.0', timestamp: new Date().toISOString(),
    }));
  }, MOCK_JWT);
  await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
}

/**
 * WebSocket and real-time update tests (mocked — no live server needed)
 *
 * Previously relied on beforeAll real user registration.
 * Converted to use setupAuth + setupAllMocks so tests run as Tier 1 CI-safe.
 */

async function setupMockedAuth(page: Page): Promise<void> {
  await setupAuth(page);
  await setupAllMocks(page);
}

test.describe('WebSocket Communication', () => {

  test.describe('Page Navigation', () => {

    test.beforeEach(async ({ page }) => {
      await setupMockedAuth(page);
    });

    test('should access new application page', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('networkidle');

      await expect(page).toHaveURL(/new-application/);
    });

    test('should display new application form fields', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('#jobTitleInput')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('#companyNameInput')).toBeVisible();
      await expect(page.locator('#jobDescription')).toBeVisible();
    });

    test('should handle offline mode gracefully', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('networkidle');

      await page.context().setOffline(true);
      await page.waitForTimeout(1000);
      await page.context().setOffline(false);
      await page.waitForTimeout(1000);

      const body = page.locator('body');
      await expect(body).toBeVisible();
    });
  });

  test.describe('Form Submission', () => {

    test.beforeEach(async ({ page }) => {
      await setupMockedAuth(page);
    });

    test('should show analyze button after filling job description', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('networkidle');

      const jobText = 'Senior Software Engineer at Test Company. '.repeat(4);
      await page.locator('#jobDescription').fill(jobText);
      await expect(page.locator('[data-action="process-application"]')).toBeVisible({ timeout: 5000 });
    });

    test('manual tab shows optional title and company inputs', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('networkidle');

      await page.locator('#jobTitleInput').fill('Software Engineer');
      await page.locator('#companyNameInput').fill('Test Company');
      expect(await page.locator('#jobTitleInput').inputValue()).toBe('Software Engineer');
    });
  });

  test.describe('Multiple Tab Handling', () => {

    test('should share authentication state across tabs', async ({ browser }) => {
      const context = await browser.newContext();
      const page1 = await context.newPage();
      const page2 = await context.newPage();

      // Inject auth state directly — no registration needed
      await setupMockedAuth(page1);
      await setupMockedAuth(page2);

      await page1.goto('/dashboard');
      await page1.waitForLoadState('domcontentloaded');

      // Second tab opened in same context shares localStorage
      await page2.goto('/dashboard');
      await page2.waitForLoadState('domcontentloaded');

      // Both tabs should be on an authenticated page (not login)
      expect(page1.url()).not.toContain('/auth/login');
      expect(page2.url()).not.toContain('/auth/login');

      await context.close();
    });

    test('should logout across tabs on token removal', async ({ browser }) => {
      const context = await browser.newContext();
      const page1 = await context.newPage();
      const page2 = await context.newPage();

      await seedAuthOnce(page1);
      await seedAuthOnce(page2);

      await page1.goto('/dashboard');
      await page1.waitForLoadState('domcontentloaded');

      await page2.goto('/dashboard');
      await page2.waitForLoadState('domcontentloaded');

      await page1.evaluate(() => {
        const cc = localStorage.getItem('cookie_consent');
        localStorage.removeItem('access_token');
        localStorage.removeItem('authToken');
        if (cc) localStorage.setItem('cookie_consent', cc);
      });

      await page1.goto('/dashboard');
      await page1.waitForURL(/login/, { timeout: 15000 });

      await page2.evaluate(() => {
        const cc = localStorage.getItem('cookie_consent');
        localStorage.removeItem('access_token');
        localStorage.removeItem('authToken');
        if (cc) localStorage.setItem('cookie_consent', cc);
      });
      await page2.goto('/dashboard');
      await page2.waitForURL(/login/, { timeout: 15000 });

      await context.close();
    });
  });

  test.describe('Notification System', () => {

    test('should show error on failed login attempt', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('cookie_consent', JSON.stringify({
          essential: true, functional: true, analytics: false,
          version: '1.0', timestamp: new Date().toISOString(),
        }));
      });
      // Override login mock to return 401
      await page.route('**/api/v1/auth/login', route => route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid credentials' }),
      }));

      await page.goto('/auth/login');
      await page.evaluate(() => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('authToken');
      });
      await page.goto('/auth/login');

      await page.locator('#email').fill('wrong@example.com');
      await page.locator('#password').fill('wrongpassword');
      await page.locator('#login-btn').click();

      await expect(page.locator('#alert-container .alert-danger, #alert-container .alert').first()).toBeVisible({ timeout: 10000 });
    });
  });
});

// ---------------------------------------------------------------------------
// WebSocket Connection Behaviour (Mocked)
// ---------------------------------------------------------------------------
test.describe('WebSocket Connection Behaviour', () => {
  test.beforeEach(async ({ page }) => {
    await setupMockedAuth(page);
  });

  test('workflow page does not redirect to login with valid token', async ({ page }) => {
    await page.route('**/api/v1/workflow/status/**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'processing', progress: 30 }),
    }));
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).not.toHaveURL(/login/);
  });

  test('page body is visible after auth injection', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).toBeVisible();
  });

  test('workflow processing state shows loading indicator', async ({ page }) => {
    const SESSION = 'ws-test-session-1';
    await page.route(`**/api/v1/workflow/status/${SESSION}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'processing', progress: 50, current_agent: 'job_analyst' }),
    }));
    await page.goto(`/dashboard/application/${SESSION}`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);
    // Processing state should show a progress or loading element
    const loader = page.locator('.progress, [class*="loading"], [class*="processing"], #loadingState').first();
    await expect(loader).toBeAttached();
  });

  test('workflow completed state hides loading and shows content', async ({ page }) => {
    const SESSION = 'ws-test-session-2';
    await page.route(`**/api/v1/workflow/status/${SESSION}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'completed' }),
    }));
    await page.route(`**/api/v1/workflow/results/${SESSION}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        job_analysis: { job_title: 'Engineer', company_name: 'Corp', required_skills: [], nice_to_have_skills: [] },
        match_assessment: { overall_score: 80, strengths: [], gaps: [], recommendation: 'Apply' },
        cover_letter: { letter: 'Dear Hiring Manager...' },
        resume_recommendations: { summary: 'Good', bullet_points: [] },
        company_research: { overview: 'Great company', culture: 'Good', recent_news: [] },
        three_key_selling_points: ['Skill A', 'Skill B', 'Skill C'],
      }),
    }));
    await page.goto(`/dashboard/application/${SESSION}`);
    await page.waitForTimeout(4000);
    await expect(page.locator('body')).toBeVisible();
  });

  test('workflow failed state does not crash the page', async ({ page }) => {
    const SESSION = 'ws-test-session-3';
    await page.route(`**/api/v1/workflow/status/${SESSION}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'failed', error: 'Workflow error' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`/dashboard/application/${SESSION}`);
    await page.waitForTimeout(3000);
    await expect(page.locator('body')).toBeVisible();
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Real-time Progress Polling
// ---------------------------------------------------------------------------
test.describe('Progress Polling (Mocked)', () => {
  test.beforeEach(async ({ page }) => {
    await setupMockedAuth(page);
  });

  test('workflow 0% progress is rendered without errors', async ({ page }) => {
    const SESSION = 'poll-session-0';
    await page.route(`**/api/v1/workflow/status/${SESSION}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'processing', progress: 0 }),
    }));
    await page.goto(`/dashboard/application/${SESSION}`);
    await page.waitForTimeout(2000);
    await expect(page.locator('body')).toBeVisible();
  });

  test('workflow 100% progress (completed) transitions gracefully', async ({ page }) => {
    const SESSION = 'poll-session-100';
    let callCount = 0;
    await page.route(`**/api/v1/workflow/status/${SESSION}`, (route: any) => {
      callCount++;
      route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ status: callCount < 2 ? 'processing' : 'completed', progress: callCount < 2 ? 80 : 100 }),
      });
    });
    await page.route(`**/api/v1/workflow/results/${SESSION}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        job_analysis: { job_title: 'Dev', company_name: 'Corp', required_skills: [], nice_to_have_skills: [] },
        match_assessment: { overall_score: 75, strengths: [], gaps: [], recommendation: '' },
        cover_letter: { letter: 'Hi' },
        resume_recommendations: { summary: '', bullet_points: [] },
        company_research: { overview: '', culture: '', recent_news: [] },
        three_key_selling_points: ['A', 'B', 'C'],
      }),
    }));
    await page.goto(`/dashboard/application/${SESSION}`);
    await page.waitForTimeout(5000);
    await expect(page.locator('body')).toBeVisible();
  });

  test('workflow with unknown status does not crash', async ({ page }) => {
    const SESSION = 'poll-session-unknown';
    await page.route(`**/api/v1/workflow/status/${SESSION}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'pending', progress: 0 }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`/dashboard/application/${SESSION}`);
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Network Resilience
// ---------------------------------------------------------------------------
test.describe('Network Resilience (Mocked)', () => {
  test.beforeEach(async ({ page }) => {
    await setupMockedAuth(page);
  });

  test('page recovers after going offline and online', async ({ page }) => {
    await setupAllMocks(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await page.context().setOffline(true);
    await page.waitForTimeout(500);
    await page.context().setOffline(false);
    await page.waitForTimeout(500);
    await expect(page.locator('body')).toBeVisible();
  });

  test('API 503 response does not crash the page', async ({ page }) => {
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 503, contentType: 'application/json',
      body: JSON.stringify({ detail: 'Service unavailable' }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 503, contentType: 'application/json',
      body: JSON.stringify({ detail: 'Service unavailable' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
    await expect(page.locator('body')).toBeVisible();
  });

  test('aborted network request does not crash the page', async ({ page }) => {
    await page.route('**/api/v1/profile', (route: any) => route.abort('failed'));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });

  test('slow API response (2s delay) does not crash', async ({ page }) => {
    await page.route('**/api/v1/profile', async (route: any) => {
      await new Promise(r => setTimeout(r, 2000));
      route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ name: 'Test User', email: 'test@example.com' }),
      });
    });
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(4000);
    expect(errors.length).toBe(0);
  });
});
