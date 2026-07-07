import { test, expect } from '@playwright/test';
import { MOCK_JWT } from '../utils/api-mocks';

/**
 * ONBOARDING TOUR TESTS  (/dashboard → auto-triggered)
 *
 * The onboarding system (onboarding.js) shows a multi-step modal for
 * first-time users. Key implementation facts:
 *   - Key: localStorage 'onboarding_completed'
 *   - Version: '2.0'
 *   - Overlay ID: #onboarding-overlay
 *   - Steps: welcome, extension, (api-key — conditional), analyze, tools, done
 *   - Buttons: [data-action="onboarding-skip|prev|next"]
 *   - Progress dots: .progress-dot
 *   - window.Onboarding exposed globally
 */

const ONBOARDING_KEY = 'onboarding_completed';

/** Inject auth + cookie consent WITHOUT onboarding_completed so the tour auto-shows */
async function setupNewUser(page: any) {
  await page.addInitScript((token: string) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('authToken', token);
    localStorage.setItem('cookie_consent', JSON.stringify({
      essential: true, functional: true, analytics: false,
      version: '1.0', timestamp: new Date().toISOString(),
    }));
    // Explicitly NOT setting onboarding_completed
  }, MOCK_JWT);
}

/** Inject auth + cookie consent WITH onboarding_completed so the tour is suppressed */
async function setupReturningUser(page: any) {
  await page.addInitScript((token: string, key: string) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('authToken', token);
    localStorage.setItem('cookie_consent', JSON.stringify({
      essential: true, functional: true, analytics: false,
      version: '1.0', timestamp: new Date().toISOString(),
    }));
    localStorage.setItem(key, JSON.stringify({ version: '2.0', completedAt: new Date().toISOString() }));
  }, MOCK_JWT, ONBOARDING_KEY);
}

/** Mock profile and API-key endpoints */
async function mockDashboardApis(page: any) {
  await page.route('**/api/v1/profile', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ name: 'Test User', email: 'test@example.com', profile_complete: true }),
  }));
  await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ applications: [], total: 0 }),
  }));
  await page.route('**/api/v1/profile/api-key/status', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ has_user_key: false, server_has_key: false }),
  }));
}

async function waitForOverlay(page: any, timeout = 5000) {
  await page.locator('#onboarding-overlay').waitFor({ state: 'visible', timeout });
}

// ---------------------------------------------------------------------------
// A. AUTO-SHOW BEHAVIOUR
// ---------------------------------------------------------------------------
test.describe('A. Auto-Show Behaviour', () => {
  test('overlay appears for new user on dashboard load', async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
    await expect(page.locator('#onboarding-overlay')).toBeVisible();
  });

  test('overlay does NOT appear for returning user', async ({ page }) => {
    await setupReturningUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    const overlay = page.locator('#onboarding-overlay');
    const visible = await overlay.isVisible().catch(() => false);
    expect(visible).toBe(false);
  });

  test('overlay does NOT appear on non-dashboard pages', async ({ page }) => {
    await setupNewUser(page);
    await page.goto('/');
    await page.waitForTimeout(2000);
    const overlay = page.locator('#onboarding-overlay');
    const visible = await overlay.isVisible().catch(() => false);
    expect(visible).toBe(false);
  });

  test('overlay is visible with class "visible" after animation', async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
    const hasVisible = await page.locator('#onboarding-overlay').evaluate((el: Element) =>
      el.classList.contains('visible')
    );
    expect(hasVisible).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// B. OVERLAY STRUCTURE
// ---------------------------------------------------------------------------
test.describe('B. Overlay Structure', () => {
  test.beforeEach(async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
  });

  test('modal element #onboarding-modal is present inside overlay', async ({ page }) => {
    await expect(page.locator('#onboarding-modal')).toBeVisible();
  });

  test('image element #onboarding-image is present', async ({ page }) => {
    await expect(page.locator('#onboarding-image')).toBeVisible();
  });

  test('title element #onboarding-title is present', async ({ page }) => {
    await expect(page.locator('#onboarding-title')).toBeVisible();
  });

  test('body element #onboarding-body is present', async ({ page }) => {
    await expect(page.locator('#onboarding-body')).toBeVisible();
  });

  test('progress element #onboarding-progress is present', async ({ page }) => {
    await expect(page.locator('#onboarding-progress')).toBeVisible();
  });

  test('Next button is present', async ({ page }) => {
    await expect(page.locator('[data-action="onboarding-next"]')).toBeVisible();
  });

  test('Skip Tour button is present', async ({ page }) => {
    await expect(page.locator('[data-action="onboarding-skip"]')).toBeVisible();
  });

  test('Back button is present', async ({ page }) => {
    await expect(page.locator('[data-action="onboarding-prev"]')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// C. FIRST STEP CONTENT (welcome)
// ---------------------------------------------------------------------------
test.describe('C. First Step — Welcome', () => {
  test.beforeEach(async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
  });

  test('welcome title contains "Welcome"', async ({ page }) => {
    const title = await page.locator('#onboarding-title').textContent();
    expect(title).toMatch(/welcome/i);
  });

  test('welcome image emoji is set', async ({ page }) => {
    const img = await page.locator('#onboarding-image').textContent();
    expect(img?.trim().length).toBeGreaterThan(0);
  });

  test('welcome body has descriptive text', async ({ page }) => {
    const body = await page.locator('#onboarding-body').textContent();
    expect(body!.trim().length).toBeGreaterThan(20);
  });

  test('Back button is hidden on first step', async ({ page }) => {
    const prevBtn = page.locator('#onboarding-prev');
    const visibility = await prevBtn.evaluate((el: HTMLElement) => el.style.visibility);
    expect(visibility).toBe('hidden');
  });

  test('Next button text contains "Next"', async ({ page }) => {
    const nextText = await page.locator('[data-action="onboarding-next"]').textContent();
    expect(nextText).toMatch(/next/i);
  });

  test('progress dots are rendered', async ({ page }) => {
    const dots = page.locator('#onboarding-progress .progress-dot');
    const count = await dots.count();
    expect(count).toBeGreaterThanOrEqual(4);
  });

  test('first progress dot is active', async ({ page }) => {
    const activeDot = page.locator('#onboarding-progress .progress-dot.active');
    await expect(activeDot.first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// D. NAVIGATION — NEXT BUTTON
// ---------------------------------------------------------------------------
test.describe('D. Navigation — Next', () => {
  test.beforeEach(async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
  });

  test('clicking Next advances to step 2', async ({ page }) => {
    const titleBefore = await page.locator('#onboarding-title').textContent();
    await page.locator('[data-action="onboarding-next"]').click();
    await page.waitForTimeout(200);
    const titleAfter = await page.locator('#onboarding-title').textContent();
    expect(titleAfter).not.toBe(titleBefore);
  });

  test('Back button becomes visible after advancing', async ({ page }) => {
    await page.locator('[data-action="onboarding-next"]').click();
    await page.waitForTimeout(200);
    const prevBtn = page.locator('#onboarding-prev');
    const visibility = await prevBtn.evaluate((el: HTMLElement) => el.style.visibility);
    expect(visibility).toBe('visible');
  });

  test('progress dot advances on step 2', async ({ page }) => {
    await page.locator('[data-action="onboarding-next"]').click();
    await page.waitForTimeout(200);
    const completed = page.locator('#onboarding-progress .progress-dot.completed');
    const count = await completed.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('clicking Next twice shows step 3 content', async ({ page }) => {
    await page.locator('[data-action="onboarding-next"]').click();
    await page.waitForTimeout(200);
    await page.locator('[data-action="onboarding-next"]').click();
    await page.waitForTimeout(200);
    const title = await page.locator('#onboarding-title').textContent();
    expect(title!.trim().length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// E. NAVIGATION — BACK BUTTON
// ---------------------------------------------------------------------------
test.describe('E. Navigation — Back', () => {
  test.beforeEach(async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
  });

  test('clicking Next then Back returns to step 1', async ({ page }) => {
    const titleBefore = await page.locator('#onboarding-title').textContent();
    await page.locator('[data-action="onboarding-next"]').click();
    await page.waitForTimeout(200);
    await page.locator('[data-action="onboarding-prev"]').click();
    await page.waitForTimeout(200);
    const titleAfter = await page.locator('#onboarding-title').textContent();
    expect(titleAfter).toBe(titleBefore);
  });

  test('Back button is hidden again on step 1 after going back', async ({ page }) => {
    await page.locator('[data-action="onboarding-next"]').click();
    await page.waitForTimeout(200);
    await page.locator('[data-action="onboarding-prev"]').click();
    await page.waitForTimeout(200);
    const prevBtn = page.locator('#onboarding-prev');
    const visibility = await prevBtn.evaluate((el: HTMLElement) => el.style.visibility);
    expect(visibility).toBe('hidden');
  });
});

// ---------------------------------------------------------------------------
// F. SKIP BEHAVIOUR
// ---------------------------------------------------------------------------
test.describe('F. Skip Behaviour', () => {
  test('clicking Skip hides the overlay', async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
    await page.locator('[data-action="onboarding-skip"]').click();
    await page.waitForTimeout(500);
    const overlay = page.locator('#onboarding-overlay');
    await expect(overlay).toBeHidden({ timeout: 3000 });
  });

  test('skipping saves onboarding_completed to localStorage', async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
    await page.locator('[data-action="onboarding-skip"]').click();
    await page.waitForTimeout(500);
    const stored = await page.evaluate((key: string) => localStorage.getItem(key), ONBOARDING_KEY);
    expect(stored).not.toBeNull();
  });

  test('stored skip value has version field', async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
    await page.locator('[data-action="onboarding-skip"]').click();
    await page.waitForTimeout(500);
    const stored = await page.evaluate((key: string) => {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    }, ONBOARDING_KEY);
    expect(stored).toHaveProperty('version');
  });

  test('after skip, page remains on dashboard', async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
    await page.locator('[data-action="onboarding-skip"]').click();
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/dashboard/);
  });
});

// ---------------------------------------------------------------------------
// G. COMPLETE FLOW (navigate to last step and finish)
// ---------------------------------------------------------------------------
test.describe('G. Complete Flow', () => {
  test('last step Next button shows "Get Started"', async ({ page }) => {
    await setupNewUser(page);
    // Mock with server has key = true so api-key step is skipped (fewer steps)
    await page.route('**/api/v1/profile/api-key/status', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_user_key: true, server_has_key: false }),
    }));
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ name: 'Test', email: 'test@example.com', profile_complete: true }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    await page.goto('/dashboard');
    await waitForOverlay(page);

    // Click through all steps until we reach the last
    for (let i = 0; i < 10; i++) {
      const nextText = await page.locator('[data-action="onboarding-next"]').textContent();
      if (nextText?.includes('Get Started')) break;
      await page.locator('[data-action="onboarding-next"]').click();
      await page.waitForTimeout(200);
    }

    const finalText = await page.locator('[data-action="onboarding-next"]').textContent();
    expect(finalText).toMatch(/get started/i);
  });

  test('completing tour hides overlay', async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);

    // Navigate to last step
    for (let i = 0; i < 10; i++) {
      const nextText = await page.locator('[data-action="onboarding-next"]').textContent();
      if (nextText?.includes('Get Started')) break;
      await page.locator('[data-action="onboarding-next"]').click();
      await page.waitForTimeout(200);
    }

    await page.locator('[data-action="onboarding-next"]').click();
    await page.waitForTimeout(500);
    const overlay = page.locator('#onboarding-overlay');
    await expect(overlay).toBeHidden({ timeout: 3000 });
  });

  test('completing tour saves onboarding_completed with version 2.0', async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);

    for (let i = 0; i < 10; i++) {
      const nextText = await page.locator('[data-action="onboarding-next"]').textContent();
      if (nextText?.includes('Get Started')) break;
      await page.locator('[data-action="onboarding-next"]').click();
      await page.waitForTimeout(200);
    }
    await page.locator('[data-action="onboarding-next"]').click();
    await page.waitForTimeout(500);

    const stored = await page.evaluate((key: string) => {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    }, ONBOARDING_KEY);
    expect(stored?.version).toBe('2.0');
  });
});

// ---------------------------------------------------------------------------
// H. WINDOW.ONBOARDING API
// ---------------------------------------------------------------------------
test.describe('H. window.Onboarding API', () => {
  test.beforeEach(async ({ page }) => {
    await setupReturningUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(500);
  });

  test('window.Onboarding is exposed globally', async ({ page }) => {
    const exists = await page.evaluate(() => typeof (window as any).Onboarding !== 'undefined');
    expect(exists).toBe(true);
  });

  test('window.Onboarding.start() shows the overlay', async ({ page }) => {
    await page.evaluate(() => (window as any).Onboarding.start());
    await page.waitForTimeout(500);
    await expect(page.locator('#onboarding-overlay')).toBeVisible();
  });

  test('window.Onboarding.skip() hides overlay after start', async ({ page }) => {
    await page.evaluate(() => (window as any).Onboarding.start());
    await page.waitForTimeout(500);
    await page.evaluate(() => (window as any).Onboarding.skip());
    await page.waitForTimeout(500);
    await expect(page.locator('#onboarding-overlay')).toBeHidden({ timeout: 3000 });
  });

  test('window.Onboarding.next() advances step', async ({ page }) => {
    await page.evaluate(() => (window as any).Onboarding.start());
    await page.waitForTimeout(500);
    const titleBefore = await page.locator('#onboarding-title').textContent();
    await page.evaluate(() => (window as any).Onboarding.next());
    await page.waitForTimeout(200);
    const titleAfter = await page.locator('#onboarding-title').textContent();
    expect(titleAfter).not.toBe(titleBefore);
  });

  test('window.Onboarding.prev() goes back', async ({ page }) => {
    await page.evaluate(() => (window as any).Onboarding.start());
    await page.waitForTimeout(500);
    await page.evaluate(() => (window as any).Onboarding.next());
    await page.waitForTimeout(200);
    const titleMid = await page.locator('#onboarding-title').textContent();
    await page.evaluate(() => (window as any).Onboarding.prev());
    await page.waitForTimeout(200);
    const titleBack = await page.locator('#onboarding-title').textContent();
    expect(titleBack).not.toBe(titleMid);
  });

  test('window.Onboarding.reset() clears localStorage key', async ({ page }) => {
    await page.route('**/api/v1/profile/api-key/status', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_user_key: false, server_has_key: false }),
    }));
    await page.evaluate(async () => await (window as any).Onboarding.reset());
    await page.waitForTimeout(1000);
    await expect(page.locator('#onboarding-overlay')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// I. API KEY STEP CONDITIONAL
// ---------------------------------------------------------------------------
test.describe('I. API Key Step — Conditional', () => {
  test('api-key step appears when server has no key', async ({ page }) => {
    await setupNewUser(page);
    await page.route('**/api/v1/profile/api-key/status', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_user_key: false, server_has_key: false }),
    }));
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ name: 'Test', email: 'test@example.com' }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    await page.goto('/dashboard');
    await waitForOverlay(page);

    // Click through until we see the api-key step or not
    const titles: string[] = [];
    for (let i = 0; i < 6; i++) {
      const t = await page.locator('#onboarding-title').textContent();
      titles.push(t || '');
      const nextText = await page.locator('[data-action="onboarding-next"]').textContent();
      if (nextText?.includes('Get Started')) break;
      await page.locator('[data-action="onboarding-next"]').click();
      await page.waitForTimeout(200);
    }
    expect(titles.some(t => /api key/i.test(t))).toBe(true);
  });

  test('api-key step is skipped when server has key', async ({ page }) => {
    await setupNewUser(page);
    await page.route('**/api/v1/profile/api-key/status', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_user_key: true, server_has_key: false }),
    }));
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ name: 'Test', email: 'test@example.com' }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    await page.goto('/dashboard');
    await waitForOverlay(page);

    const titles: string[] = [];
    for (let i = 0; i < 6; i++) {
      const t = await page.locator('#onboarding-title').textContent();
      titles.push(t || '');
      const nextText = await page.locator('[data-action="onboarding-next"]').textContent();
      if (nextText?.includes('Get Started')) break;
      await page.locator('[data-action="onboarding-next"]').click();
      await page.waitForTimeout(200);
    }
    expect(titles.some(t => /api key/i.test(t))).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// J. ACCESSIBILITY
// ---------------------------------------------------------------------------
test.describe('J. Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await setupNewUser(page);
    await mockDashboardApis(page);
    await page.goto('/dashboard');
    await waitForOverlay(page);
  });

  test('Next button is keyboard focusable', async ({ page }) => {
    const nextBtn = page.locator('[data-action="onboarding-next"]');
    await nextBtn.focus();
    const focused = await page.evaluate(() => document.activeElement?.getAttribute('data-action'));
    expect(focused).toBe('onboarding-next');
  });

  test('Skip button is keyboard focusable', async ({ page }) => {
    const skipBtn = page.locator('[data-action="onboarding-skip"]');
    await skipBtn.focus();
    const focused = await page.evaluate(() => document.activeElement?.getAttribute('data-action'));
    expect(focused).toBe('onboarding-skip');
  });

  test('modal is inside the overlay', async ({ page }) => {
    const modalParent = await page.locator('#onboarding-modal').evaluate(
      (el: Element) => el.closest('#onboarding-overlay') !== null
    );
    expect(modalParent).toBe(true);
  });
});
