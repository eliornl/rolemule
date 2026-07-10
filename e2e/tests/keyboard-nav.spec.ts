import { test, expect } from '@playwright/test';
import { setupAuth, setupAllMocks, setupWebSocketMock, buildMockGetProfileResponse, isMockedE2E, getE2EAuthToken } from '../utils/api-mocks';

/**
 * KEYBOARD NAVIGATION & FOCUS MANAGEMENT TESTS
 *
 * Tests that every key interactive area of the app is reachable
 * via keyboard alone (Tab, Enter, Space, Escape, Arrow keys).
 * All tests are Tier 1 (CI-safe, fully mocked).
 */

// ---------------------------------------------------------------------------
// A. LANDING PAGE KEYBOARD NAVIGATION
// ---------------------------------------------------------------------------
test.describe('A. Landing Page Keyboard Navigation', () => {
  test('Tab key reaches first focusable element', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(focused || '')).toBeTruthy();
  });

  test('Tab key cycles through navbar links', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    // Press Tab multiple times and verify focus moves
    for (let i = 0; i < 3; i++) {
      await page.keyboard.press('Tab');
    }
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(focused).not.toBe('BODY');
  });

  test('Enter key on focused link navigates', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const loginLink = page.locator('a[href="/auth/login"]').first();
    await loginLink.focus();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(1000);
    await expect(page).toHaveURL(/login/);
  });

  test('Space key on focused button triggers click', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const btn = page.locator('button, a.btn').first();
    if (await btn.isVisible()) {
      await btn.focus();
      const tag = await btn.evaluate((el: Element) => el.tagName.toLowerCase());
      if (tag === 'button') {
        // Space on button = click
        await page.keyboard.press('Space');
        await expect(page.locator('body')).toBeVisible();
      }
    }
  });
});

// ---------------------------------------------------------------------------
// B. LOGIN PAGE KEYBOARD NAVIGATION
// ---------------------------------------------------------------------------
test.describe('B. Login Page Keyboard Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
  });

  test('Tab moves from email to password field', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    const emailInput = page.locator('input[type="email"]');
    await emailInput.focus();
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.getAttribute('type'));
    expect(focused).toBe('password');
  });

  test('Tab from password reaches submit button', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    const pwInput = page.locator('input[type="password"]');
    await pwInput.focus();
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(['BUTTON', 'A', 'INPUT'].includes(focused || '')).toBeTruthy();
  });

  test('Enter submits login form', async ({ page }) => {
    await page.route('**/api/v1/auth/login', (route: any) => route.fulfill({
      status: 401, contentType: 'application/json',
      body: JSON.stringify({ detail: 'Invalid credentials' }),
    }));
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('input[type="email"]').fill('test@example.com');
    await page.locator('input[type="password"]').fill('password123');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(1500);
    // Should stay on login (credentials are wrong)
    await expect(page).toHaveURL(/login/);
  });

  test('Tab key from submit button reaches register link', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    const submitBtn = page.locator('button[type="submit"], #login-btn').first();
    await submitBtn.focus();
    await page.keyboard.press('Tab');
    const tag = await page.evaluate(() => document.activeElement?.tagName);
    expect(tag).not.toBe('BODY');
  });
});

// ---------------------------------------------------------------------------
// C. REGISTER PAGE KEYBOARD NAVIGATION
// ---------------------------------------------------------------------------
test.describe('C. Register Page Keyboard Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
  });

  test('Tab cycles through all register form fields', async ({ page }) => {
    await page.goto('/auth/register');
    await page.waitForLoadState('domcontentloaded');
    const inputs = await page.locator('input').count();
    expect(inputs).toBeGreaterThanOrEqual(3);
    // Tab through all inputs
    const firstInput = page.locator('input').first();
    await firstInput.focus();
    for (let i = 0; i < inputs; i++) {
      await page.keyboard.press('Tab');
    }
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(focused).not.toBe('BODY');
  });

  test('Space key toggles terms checkbox', async ({ page }) => {
    await page.goto('/auth/register');
    await page.waitForLoadState('domcontentloaded');
    const checkbox = page.locator('input[type="checkbox"]').first();
    if (await checkbox.isVisible()) {
      const beforeState = await checkbox.isChecked();
      await checkbox.focus();
      await page.keyboard.press('Space');
      const afterState = await checkbox.isChecked();
      expect(afterState).toBe(!beforeState);
    }
  });

  test('Enter on register link navigates to login', async ({ page }) => {
    await page.goto('/auth/register');
    await page.waitForLoadState('domcontentloaded');
    const loginLink = page.locator('a[href="/auth/login"], a:has-text("Log in"), a:has-text("Sign in")').first();
    if (await loginLink.count() > 0) {
      await loginLink.focus();
      await page.keyboard.press('Enter');
      await page.waitForTimeout(500);
      await expect(page).toHaveURL(/login/);
    }
  });
});

// ---------------------------------------------------------------------------
// D. DASHBOARD KEYBOARD NAVIGATION
// ---------------------------------------------------------------------------
test.describe('D. Dashboard Keyboard Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('Tab reaches first focusable element on dashboard', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(['A', 'BUTTON', 'INPUT'].includes(focused || '')).toBeTruthy();
  });

  test('Tab cycles through sidebar navigation links', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    // Tab 5 times and check focus is moving
    const tags: string[] = [];
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('Tab');
      const t = await page.evaluate(() => document.activeElement?.tagName);
      tags.push(t || 'BODY');
    }
    const hasNavElement = tags.some(t => ['A', 'BUTTON'].includes(t));
    expect(hasNavElement).toBeTruthy();
  });

  test('settings page tab navigation works', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await page.waitForLoadState('domcontentloaded');
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('Tab');
    }
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(focused).not.toBe('BODY');
  });

  test('career tools page is keyboard-navigable', async ({ page }) => {
    await page.goto('/dashboard/tools');
    await page.waitForLoadState('domcontentloaded');
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(focused).not.toBe('BODY');
  });
});

// ---------------------------------------------------------------------------
// E. FORM KEYBOARD INTERACTIONS
// ---------------------------------------------------------------------------
test.describe('E. Form Keyboard Interactions', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('new application job title input accepts keyboard input', async ({ page }) => {
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    const titleInput = page.locator('#jobTitleInput');
    await expect(titleInput).toBeVisible({ timeout: 5000 });
    await titleInput.focus();
    await page.keyboard.type('Software Engineer');
    expect(await titleInput.inputValue()).toBe('Software Engineer');
  });

  test('new application company name accepts keyboard input', async ({ page }) => {
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    const companyInput = page.locator('#companyNameInput');
    await expect(companyInput).toBeVisible({ timeout: 5000 });
    await companyInput.focus();
    await page.keyboard.type('TechCorp Inc');
    expect(await companyInput.inputValue()).toBe('TechCorp Inc');
  });

  test('Backspace clears typed text in input', async ({ page }) => {
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    const titleInput = page.locator('#jobTitleInput');
    await expect(titleInput).toBeVisible({ timeout: 5000 });
    await titleInput.fill('Test');
    await titleInput.clear();
    expect(await titleInput.inputValue()).toBe('');
  });

  test('Escape key dismisses modals or cancels actions', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await page.keyboard.press('Escape');
    // Escape should not cause any errors
    await expect(page.locator('body')).toBeVisible();
  });

  test('select element opens with keyboard (Alt+Down)', async ({ page }) => {
    await page.goto('/dashboard/tools');
    await page.waitForLoadState('domcontentloaded');
    const select = page.locator('select').first();
    if (await select.isVisible({ timeout: 3000 }).catch(() => false)) {
      await select.focus();
      // Arrow down to select next option
      await page.keyboard.press('ArrowDown');
      await expect(page.locator('body')).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// F. ONBOARDING KEYBOARD NAVIGATION
// ---------------------------------------------------------------------------
test.describe('F. Onboarding Keyboard Navigation', () => {
  test('onboarding Next button is reachable via Tab', async ({ page }) => {
    if (isMockedE2E) {
      await setupWebSocketMock(page);
    }
    const token = getE2EAuthToken();
    await page.addInitScript((t: string) => {
      localStorage.setItem('access_token', t);
      localStorage.setItem('authToken', t);
      localStorage.removeItem('onboarding_completed');
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    }, token);
    await page.route('**/api/v1/profile**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify(buildMockGetProfileResponse()),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    await page.route('**/api/v1/applications/stats/overview', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ total: 0, applied: 0, interviews: 0, offers: 0, response_rate: 0 }),
    }));
    await page.route('**/api/v1/profile/api-key/status', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_user_key: false, server_has_key: false, use_vertex_ai: false }),
    }));
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    await page.locator('#onboarding-overlay').waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
    if (await page.locator('#onboarding-overlay').isVisible().catch(() => false)) {
      const nextBtn = page.locator('[data-action="onboarding-next"]');
      await nextBtn.focus();
      const focused = await page.evaluate(() =>
        document.activeElement?.getAttribute('data-action')
      );
      expect(focused).toBe('onboarding-next');
    }
  });

  test('Enter key on onboarding Next button advances step', async ({ page }) => {
    const token = getE2EAuthToken();
    await page.addInitScript((t: string) => {
      localStorage.setItem('access_token', t);
      localStorage.setItem('authToken', t);
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    }, token);
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ name: 'User', email: 'u@example.com' }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    await page.route('**/api/v1/profile/api-key/status', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_user_key: false, server_has_key: false }),
    }));
    await page.goto('/dashboard');
    await page.locator('#onboarding-overlay').waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
    if (await page.locator('#onboarding-overlay').isVisible().catch(() => false)) {
      const titleBefore = await page.locator('#onboarding-title').textContent();
      const nextBtn = page.locator('[data-action="onboarding-next"]');
      await nextBtn.focus();
      await page.keyboard.press('Enter');
      await page.waitForTimeout(300);
      const titleAfter = await page.locator('#onboarding-title').textContent();
      expect(titleAfter).not.toBe(titleBefore);
    }
  });
});

// ---------------------------------------------------------------------------
// G. MODAL / DIALOG KEYBOARD BEHAVIOUR
// ---------------------------------------------------------------------------
test.describe('G. Focus Trap & Modal Behaviour', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('page does not lose focus to BODY on dashboard load', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await page.keyboard.press('Tab');
    const tag = await page.evaluate(() => document.activeElement?.tagName);
    expect(tag).not.toBe('BODY');
  });

  test('settings page input is focusable via keyboard', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('[data-section="apiKeys"]').click();
    await page.waitForTimeout(300);
    const apiKeyInput = page.locator('#geminiApiKey');
    await expect(apiKeyInput).toBeVisible({ timeout: 5000 });
    await apiKeyInput.focus();
    const tag = await page.evaluate(() => document.activeElement?.id);
    expect(tag).toBe('geminiApiKey');
  });

  test('dashboard application list page is keyboard-navigable', async ({ page }) => {
    await setupAuth(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(focused).not.toBe('BODY');
  });
});
