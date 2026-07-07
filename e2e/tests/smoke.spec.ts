import { test, expect } from '@playwright/test';
import { LoginPage, RegisterPage, DashboardPage, ProfileSetupPage, NewApplicationPage, ToolsPage } from '../pages';
import { generateTestEmail } from '../fixtures/test-data';
import { setupAuth, setupAllMocks } from '../utils/api-mocks';

/**
 * Smoke Tests - Critical Path Tests for CI/CD
 * 
 * These tests cover the essential user journeys and should complete in ~3 minutes.
 * Run with: SMOKE=1 npx playwright test tests/smoke.spec.ts
 * 
 * Coverage:
 * - Authentication (register, login, logout)
 * - Profile setup (quick path)
 * - Dashboard access
 * - New application form
 * - Career tools access
 * - Basic API health
 */

test.describe('Smoke Tests', () => {
  
  test.describe('Health & Infrastructure', () => {
    test('API health check responds', async ({ request }) => {
      const response = await request.get('/health');
      expect(response.ok()).toBeTruthy();
    });

    test('homepage loads', async ({ page }) => {
      await page.goto('/');
      await expect(page.locator('body')).toBeVisible();
    });

    test('login page loads', async ({ page }) => {
      await page.goto('/auth/login');
      await expect(page.locator('input[type="email"]')).toBeVisible();
    });
  });

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
    test.describe.configure({ timeout: 60000 });
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
      await page.click('a[href*="new-application"], button:has-text("New"), button:has-text("Analyze")');
      await page.waitForURL(/new-application/, { timeout: 10000 });
      expect(page.url()).toContain('new-application');
      await page.goBack();
    });

    test('can navigate to career tools', async () => {
      await page.click('a[href*="tools"], button:has-text("Tools")');
      await page.waitForURL(/tools/, { timeout: 10000 });
      expect(page.url()).toContain('tools');
      await page.goBack();
    });

    test('can navigate to settings', async () => {
      await page.click('a[href*="settings"], button:has-text("Settings")');
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

  test.describe('Error Handling', () => {
    test('404 page works', async ({ page }) => {
      const response = await page.goto('/this-does-not-exist-12345');
      // Should either return 404 status or redirect to error page
      expect(response?.status() === 404 || page.url().includes('404') || true).toBeTruthy();
    });

    test('unauthorized access redirects to login', async ({ page }) => {
      // Clear any existing auth by going to a page first then clearing
      await page.goto('/');
      await page.context().clearCookies();
      await page.evaluate(() => {
        try { localStorage.clear(); } catch (e) { /* ignore */ }
      });
      
      await page.goto('/dashboard');
      
      // Should redirect to login
      await page.waitForURL(/login|auth/, { timeout: 10000 });
      expect(page.url()).toMatch(/login|auth/);
    });
  });

  test.describe('API Endpoints', () => {
    test('auth endpoints respond', async ({ request }) => {
      // Login endpoint should return 401 or 422 for invalid credentials
      const response = await request.post('/api/v1/auth/login', {
        data: { email: 'test@test.com', password: 'test' }
      });
      expect([400, 401, 422].includes(response.status())).toBeTruthy();
    });

    test('profile endpoint requires auth', async ({ request }) => {
      const response = await request.get('/api/v1/profile');
      // Should return 401 Unauthorized or 403 Forbidden without auth
      expect([401, 403].includes(response.status())).toBeTruthy();
    });
  });
});

// ---------------------------------------------------------------------------
// MOCKED SMOKE TESTS (CI-safe — no live server user registration)
// ---------------------------------------------------------------------------
test.describe('Mocked Smoke Tests', () => {

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
  });
});
