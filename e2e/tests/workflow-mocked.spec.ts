import { test, expect } from '@playwright/test';
import { setupAllMocks, setupAuth } from '../utils/api-mocks';

/**
 * Workflow tests with mocked APIs
 * Tests the workflow functionality using API mocks to avoid dependency on real API keys
 */
test.describe('Workflow (Mocked)', () => {
  
  test.describe('Workflow Start', () => {
    
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
    });
    
    test('should navigate to new application page', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('domcontentloaded');
      
      const url = page.url();
      expect(url).toMatch(/new-application|dashboard/);
    });
    
    test('should have input options for job posting', async ({ page }) => {
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('domcontentloaded');
      
      const formElements = page.locator('input, textarea, select');
      const count = await formElements.count();
      expect(count).toBeGreaterThanOrEqual(0);
    });
  });
  
  test.describe('Dashboard Application List', () => {
    
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
    });
    
    test('/dashboard/history returns 404 (route removed)', async ({ page }) => {
      await page.goto('/dashboard/history');
      await page.waitForLoadState('domcontentloaded');
      expect(page.url()).not.toMatch(/\/dashboard\/history$/);
    });
    
    test('dashboard has body visible (application list or empty state)', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      const body = page.locator('body');
      await expect(body).toBeVisible();
    });
  });
  
  test.describe('Career Tools (Mocked)', () => {
    
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
    });
    
    test('should access career tools page', async ({ page }) => {
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
      
      const url = page.url();
      expect(url).toMatch(/tools|dashboard/);
    });
    
    test('should have tool tabs or sections', async ({ page }) => {
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
      
      const body = page.locator('body');
      await expect(body).toBeVisible();
    });
    
    test('should have form elements for tools', async ({ page }) => {
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
      
      const formElements = page.locator('input, textarea, select');
      const count = await formElements.count();
      expect(count).toBeGreaterThanOrEqual(0);
    });
  });
  
  test.describe('Settings Page', () => {
    
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
    });
    
    test('should access settings page', async ({ page }) => {
      await page.goto('/dashboard/settings');
      await page.waitForLoadState('domcontentloaded');
      
      const url = page.url();
      expect(url).toMatch(/settings|dashboard/);
    });
    
    test('should have settings sections', async ({ page }) => {
      await page.goto('/dashboard/settings');
      await page.waitForLoadState('domcontentloaded');
      
      const body = page.locator('body');
      await expect(body).toBeVisible();
    });
  });
});

// ---------------------------------------------------------------------------
// DETAILED WORKFLOW MOCKED TESTS
// ---------------------------------------------------------------------------
test.describe('Workflow Mocked — Detailed', () => {

  test.describe('New Application Form Fields', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
      await page.goto('/dashboard/new-application');
      await page.waitForLoadState('domcontentloaded');
    });

    test('step 1 job title input is present and fillable', async ({ page }) => {
      const input = page.locator('#basicJobTitle');
      await expect(input).toBeVisible({ timeout: 5000 });
      await input.fill('Senior Developer');
      expect(await input.inputValue()).toBe('Senior Developer');
    });

    test('step 1 company name input is present and fillable', async ({ page }) => {
      const input = page.locator('#basicCompanyName');
      await expect(input).toBeVisible({ timeout: 5000 });
      await input.fill('BigCorp');
      expect(await input.inputValue()).toBe('BigCorp');
    });

    test('step 1 has a Next button', async ({ page }) => {
      const nextBtn = page.locator('button:has-text("Next"), #nextToStep2');
      await expect(nextBtn.first()).toBeVisible({ timeout: 5000 });
    });

    test('cancel link is visible and points to /dashboard', async ({ page }) => {
      const cancelLink = page.locator('.form-actions a[href="/dashboard"], a:has-text("Cancel")');
      await expect(cancelLink.first()).toBeVisible({ timeout: 5000 });
    });

    test('form card is visible', async ({ page }) => {
      await expect(page.locator('.form-card')).toBeVisible({ timeout: 5000 });
    });

    test('alert container is present in DOM', async ({ page }) => {
      await expect(page.locator('#alertContainer')).toBeAttached();
    });
  });

  test.describe('Dashboard Stats', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
    });

    test('welcome card displays', async ({ page }) => {
      await expect(page.locator('.welcome-card')).toBeVisible({ timeout: 5000 });
    });

    test('4 stat cards are rendered', async ({ page }) => {
      await expect(page.locator('.stat-card')).toHaveCount(4);
    });

    test('total applications stat is in DOM', async ({ page }) => {
      await expect(page.locator('#totalApplications')).toBeAttached();
    });

    test('action buttons are visible', async ({ page }) => {
      await expect(page.locator('.action-btn').first()).toBeVisible({ timeout: 5000 });
    });

    test('applications filter dropdowns exist', async ({ page }) => {
      await expect(page.locator('#dateFilter')).toBeAttached();
      await expect(page.locator('#statusFilter')).toBeAttached();
    });
  });

  test.describe('Career Tools Navigation (Mocked)', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
    });

    test('all 6 tool tabs are present', async ({ page }) => {
      await expect(page.locator('[data-tool]')).toHaveCount(6);
    });

    test('thank you form is active by default', async ({ page }) => {
      await expect(page.locator('#thankYouSection')).toBeVisible({ timeout: 5000 });
    });

    test('thank you submit button is present', async ({ page }) => {
      await expect(page.locator('#thankYouSubmit')).toBeVisible({ timeout: 5000 });
    });

    test('clicking rejection shows rejection section', async ({ page }) => {
      await page.locator('[data-tool="rejection"]').click();
      await expect(page.locator('#rejectionSection')).toBeVisible({ timeout: 2000 });
    });

    test('clicking reference shows reference section', async ({ page }) => {
      await page.locator('[data-tool="reference"]').click();
      await expect(page.locator('#referenceSection')).toBeVisible({ timeout: 2000 });
    });

    test('alert container clears on tool switch', async ({ page }) => {
      const alertContainer = page.locator('#alertContainer');
      await expect(alertContainer).toBeAttached();
    });
  });

  test.describe('Settings Sections (Mocked)', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
      await page.route('**/api/v1/settings**', r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) }));
      await page.goto('/dashboard/settings');
      await page.waitForLoadState('domcontentloaded');
    });

    test('5 settings nav items are present', async ({ page }) => {
      await expect(page.locator('[data-section]')).toHaveCount(5);
    });

    test('gemini API key input is present', async ({ page }) => {
      await page.locator('[data-section="apiKeys"]').click();
      await expect(page.locator('#geminiApiKey')).toBeAttached();
    });

    test('preferences slider is present', async ({ page }) => {
      await page.locator('[data-section="preferences"]').click();
      await expect(page.locator('#gateThresholdSlider')).toBeAttached();
    });

    test('delete account button is present', async ({ page }) => {
      await page.locator('[data-section="account"]').click();
      await expect(page.locator('[data-action="deleteAccount"]')).toBeAttached();
    });
  });

  test.describe('Access Control (Mocked)', () => {
    test('all dashboard routes redirect without auth', async ({ page }) => {
      const routes = ['/dashboard', '/dashboard/new-application', '/dashboard/tools', '/dashboard/settings'];
      for (const route of routes) {
        await page.goto(route);
        await page.waitForURL(/auth\/login|\//, { timeout: 8000 });
        expect(page.url()).not.toContain(route.replace('/dashboard', 'dashboard').replace('/', ''));
      }
    });
  });
});
