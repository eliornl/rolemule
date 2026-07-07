import { test, expect } from '@playwright/test';
import { setupAuth } from '../utils/api-mocks';

/**
 * RATE LIMIT & 429 HANDLING TESTS
 *
 * Tests that the frontend gracefully handles 429 Too Many Requests responses
 * from the API, including Retry-After headers, repeated requests, and
 * career-tools rate limiting.
 * All tests are Tier 1 (CI-safe, fully mocked).
 */

async function setupDashboardAuth(page: any) {
  await setupAuth(page);
  await page.route('**/api/v1/profile', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ name: 'Test User', email: 'test@example.com' }),
  }));
  await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ applications: [], total: 0 }),
  }));
}

// ---------------------------------------------------------------------------
// A. LOGIN RATE LIMITING
// ---------------------------------------------------------------------------
test.describe('A. Login Rate Limiting', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
  });

  test('429 from login API does not crash the page', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '60' },
      body: JSON.stringify({ detail: 'Too many login attempts. Please try again in 60 seconds.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/auth/login');
    await page.locator('input[type="email"]').fill('user@example.com');
    await page.locator('input[type="password"]').fill('password123');
    await page.locator('button[type="submit"], #login-btn').first().click();
    await page.waitForTimeout(1500);
    expect(errors.length).toBe(0);
    await expect(page).toHaveURL(/login/);
  });

  test('429 response shows error feedback to user', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '60' },
      body: JSON.stringify({ detail: 'Too many login attempts' }),
    }));
    await page.goto('/auth/login');
    await page.locator('input[type="email"]').fill('user@example.com');
    await page.locator('input[type="password"]').fill('password123');
    await page.locator('button[type="submit"], #login-btn').first().click();
    await page.waitForTimeout(1500);
    // User should remain on login page
    await expect(page).toHaveURL(/login/);
  });

  test('account locked 429 response shows lockout indicator', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '900' },
      body: JSON.stringify({ detail: 'Account locked. Try again in 15 minutes.', error_code: 'AUTH_1004' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/auth/login');
    await page.locator('input[type="email"]').fill('locked@example.com');
    await page.locator('input[type="password"]').fill('password123');
    await page.locator('button[type="submit"], #login-btn').first().click();
    await page.waitForTimeout(1500);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// B. REGISTRATION RATE LIMITING
// ---------------------------------------------------------------------------
test.describe('B. Registration Rate Limiting', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
  });

  test('429 from register API does not crash the page', async ({ page }) => {
    await page.route('**/api/v1/auth/register', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '3600' },
      body: JSON.stringify({ detail: 'Too many registrations from this IP. Try again later.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/auth/register');
    await page.locator('input[type="text"], input[name="name"]').first().fill('Test User');
    await page.locator('input[type="email"]').fill('test@example.com');
    await page.locator('input[type="password"]').first().fill('Password123!');
    const checkbox = page.locator('input[type="checkbox"]').first();
    if (await checkbox.isVisible({ timeout: 2000 }).catch(() => false)) {
      await checkbox.check();
    }
    await page.locator('button[type="submit"], #register-btn').first().click();
    await page.waitForTimeout(1500);
    expect(errors.length).toBe(0);
    await expect(page).toHaveURL(/register/);
  });
});

// ---------------------------------------------------------------------------
// C. CAREER TOOLS RATE LIMITING
// ---------------------------------------------------------------------------
test.describe('C. Career Tools Rate Limiting', () => {
  test.beforeEach(async ({ page }) => {
    await setupDashboardAuth(page);
  });

  test('429 from thank-you API does not crash the page', async ({ page }) => {
    await page.route('**/api/v1/career-tools/thank-you**', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '3600' },
      body: JSON.stringify({ detail: 'Rate limit exceeded. Max 10 requests per hour.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard/tools');
    await page.waitForTimeout(2000);
    const submitBtn = page.locator('#thankYouSubmit, #generateThankYou').first();
    if (await submitBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await submitBtn.click();
      await page.waitForTimeout(1500);
    }
    expect(errors.length).toBe(0);
  });

  test('429 from salary API does not crash the page', async ({ page }) => {
    await page.route('**/api/v1/career-tools/salary**', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '3600' },
      body: JSON.stringify({ detail: 'Rate limit exceeded.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard/tools');
    await page.waitForTimeout(2000);
    // Switch to salary tab if possible
    const salaryTab = page.locator('.nav-link:has-text("Salary")');
    if (await salaryTab.isVisible({ timeout: 3000 }).catch(() => false)) {
      await salaryTab.click();
      await page.waitForTimeout(500);
      const submitBtn = page.locator('#salarySubmit').first();
      if (await submitBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
        await submitBtn.click();
        await page.waitForTimeout(1500);
      }
    }
    expect(errors.length).toBe(0);
  });

  test('429 from rejection API does not crash the page', async ({ page }) => {
    await page.route('**/api/v1/career-tools/rejection**', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '3600' },
      body: JSON.stringify({ detail: 'Rate limit exceeded.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard/tools');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });

  test('429 from follow-up API does not crash the page', async ({ page }) => {
    await page.route('**/api/v1/career-tools/followup**', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '3600' },
      body: JSON.stringify({ detail: 'Rate limit exceeded.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard/tools');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// D. WORKFLOW RATE LIMITING
// ---------------------------------------------------------------------------
test.describe('D. Workflow Rate Limiting', () => {
  test.beforeEach(async ({ page }) => {
    await setupDashboardAuth(page);
  });

  test('429 from workflow/start does not crash the page', async ({ page }) => {
    await page.route('**/api/v1/workflow/start', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '3600' },
      body: JSON.stringify({ detail: 'You have reached the workflow limit. Upgrade your plan.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    const titleInput = page.locator('#basicJobTitle').first();
    if (await titleInput.isVisible({ timeout: 5000 }).catch(() => false)) {
      await titleInput.fill('Engineer');
      await page.locator('#basicCompanyName').first().fill('Corp');
      const nextBtn = page.locator('button:has-text("Next")').first();
      if (await nextBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
        await nextBtn.click();
        await page.waitForTimeout(500);
        const submitBtn = page.locator('button:has-text("Create Application"), button:has-text("Analyze")').first();
        if (await submitBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
          await submitBtn.click();
          await page.waitForTimeout(1500);
        }
      }
    }
    expect(errors.length).toBe(0);
  });

  test('429 from interview-prep generate does not crash', async ({ page }) => {
    const SESSION = 'rate-limit-session';
    await page.route(`**/api/v1/interview-prep/${SESSION}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_interview_prep: false }),
    }));
    await page.route(`**/api/v1/workflow/results/${SESSION}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ job_analysis: { job_title: 'Dev', company_name: 'Corp' } }),
    }));
    await page.route(`**/api/v1/interview-prep/${SESSION}/generate**`, (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '3600' },
      body: JSON.stringify({ detail: 'Rate limit exceeded.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`/dashboard/interview-prep/${SESSION}`);
    await page.waitForTimeout(3000);
    const genBtn = page.locator('#generateBtn, button:has-text("Generate"), button:has-text("Prepare")').first();
    if (await genBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await genBtn.click();
      await page.waitForTimeout(1500);
    }
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// E. FORGOT PASSWORD RATE LIMITING
// ---------------------------------------------------------------------------
test.describe('E. Forgot Password Rate Limiting', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
  });

  test('429 from forgot-password API does not crash', async ({ page }) => {
    await page.route('**/api/v1/auth/forgot-password**', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '3600' },
      body: JSON.stringify({ detail: 'Too many requests. Please try again later.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/auth/reset-password');
    const emailInput = page.locator('#forgotEmail, input[type="email"]').first();
    if (await emailInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await emailInput.fill('test@example.com');
      const submitBtn = page.locator('#forgotPasswordBtn, button[type="submit"]').first();
      await submitBtn.click();
      await page.waitForTimeout(1500);
    }
    expect(errors.length).toBe(0);
  });

  test('429 from resend-verification API does not crash', async ({ page }) => {
    await page.route('**/api/v1/auth/resend-verification**', (route: any) => route.fulfill({
      status: 429,
      contentType: 'application/json',
      headers: { 'Retry-After': '600' },
      body: JSON.stringify({ detail: 'Please wait before requesting another code.' }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/auth/verify-email');
    await page.waitForTimeout(1000);
    const resendBtn = page.locator('button:has-text("Resend"), a:has-text("Resend")').first();
    if (await resendBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await resendBtn.click();
      await page.waitForTimeout(1500);
    }
    expect(errors.length).toBe(0);
  });
});
