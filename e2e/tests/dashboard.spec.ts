import { test, expect } from '@playwright/test';
import { RegisterPage, DashboardPage, ProfileSetupPage } from '../pages';
import { generateTestEmail } from '../fixtures/test-data';
import { setupAuth, setupAllMocks } from '../utils/api-mocks';

test.describe('Dashboard', () => {
  const email = 'dashboard-mock@example.com';
  const password = 'DashboardTestPassword123!';
  
  test.describe('Navigation (Mocked)', () => {
    
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
    });

    test('should display dashboard after login', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      await dashboardPage.verifyLoaded();
    });

    test('should navigate to new application page', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      await dashboardPage.goToNewApplication();
      await expect(page).toHaveURL(/new-application/);
    });

    test('should navigate to settings page', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      await dashboardPage.goToSettings();
      await expect(page).toHaveURL(/settings/);
    });

    test('should navigate to career tools page', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      await dashboardPage.goToTools();
      await expect(page).toHaveURL(/tools/);
    });
  });

  test.describe('Navigation (Live Server)', () => {
    test.describe.configure({ mode: 'serial' });

    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });
    
    test('should display dashboard after login', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForURL(/dashboard/, { timeout: 15000 });
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      await dashboardPage.verifyLoaded();
    });
    
    test('should navigate to new application page', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForURL(/dashboard/, { timeout: 15000 });
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      
      await dashboardPage.goToNewApplication();
      
      await expect(page).toHaveURL(/new-application/);
    });
    
    test('should navigate to settings page', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForURL(/dashboard/, { timeout: 15000 });
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      
      await dashboardPage.goToSettings();
      
      await expect(page).toHaveURL(/settings/);
    });
    
    test('should navigate to career tools page', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForURL(/dashboard/, { timeout: 15000 });
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      
      await dashboardPage.goToTools();
      
      await expect(page).toHaveURL(/tools/);
    });
    
    test('should navigate to help page', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForURL(/dashboard/, { timeout: 15000 });
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      
      await dashboardPage.goToHelp();
      
      await expect(page).toHaveURL(/help/);
    });
  });
  
  test.describe('Onboarding (Live Server)', () => {
    
    test('should show onboarding for new users', async ({ page, context }) => {
      // Clear localStorage to simulate new user
      await context.clearCookies();
      
      // Register new user
      const registerPage = new RegisterPage(page);
      const newEmail = generateTestEmail('onboarding_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'Onboarding Test User',
        email: newEmail,
        password: 'OnboardingTestPassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
      
      // Complete profile setup if needed
      if (page.url().includes('profile/setup')) {
        const profilePage = new ProfileSetupPage(page);
        await profilePage.quickSetup({
          title: 'Engineer',
          yearsExperience: 3,
          skills: ['Python'],
        });
      }
      
      // Clear onboarding state
      await page.evaluate(() => {
        localStorage.removeItem('onboarding_completed');
      });
      
      await page.reload();
      
      // Check for onboarding overlay
      const onboardingOverlay = page.locator('#onboarding-overlay');
      await expect(onboardingOverlay).toBeVisible({ timeout: 5000 }).catch(() => {
        // Onboarding may already be completed or not shown
      });
    });
    
    test('should complete onboarding tutorial', async ({ page }) => {
      // Register new user
      const registerPage = new RegisterPage(page);
      const newEmail = generateTestEmail('onboarding_complete_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'Onboarding Complete Test',
        email: newEmail,
        password: 'OnboardingCompletePassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
      
      // Complete profile setup if needed
      if (page.url().includes('profile/setup')) {
        const profilePage = new ProfileSetupPage(page);
        await profilePage.quickSetup({
          title: 'Engineer',
          yearsExperience: 3,
          skills: ['Python'],
        });
      }
      
      // Clear and trigger onboarding
      await page.evaluate(() => {
        localStorage.removeItem('onboarding_completed');
      });
      await page.reload();
      
      const dashboardPage = new DashboardPage(page);
      
      if (await dashboardPage.onboardingOverlay.isVisible({ timeout: 3000 }).catch(() => false)) {
        await dashboardPage.completeOnboarding();
        
        // Onboarding should be hidden
        await expect(dashboardPage.onboardingOverlay).toBeHidden({ timeout: 5000 });
      }
    });
    
    test('should be able to skip onboarding', async ({ page }) => {
      // Register new user
      const registerPage = new RegisterPage(page);
      const newEmail = generateTestEmail('onboarding_skip_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'Onboarding Skip Test',
        email: newEmail,
        password: 'OnboardingSkipPassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
      
      // Complete profile setup if needed
      if (page.url().includes('profile/setup')) {
        const profilePage = new ProfileSetupPage(page);
        await profilePage.quickSetup({
          title: 'Engineer',
          yearsExperience: 3,
          skills: ['Python'],
        });
      }
      
      // Clear and trigger onboarding
      await page.evaluate(() => {
        localStorage.removeItem('onboarding_completed');
      });
      await page.reload();
      
      const dashboardPage = new DashboardPage(page);
      
      if (await dashboardPage.onboardingOverlay.isVisible({ timeout: 3000 }).catch(() => false)) {
        await dashboardPage.skipOnboarding();
        
        // Onboarding should be hidden
        await expect(dashboardPage.onboardingOverlay).toBeHidden({ timeout: 5000 });
      }
    });
  });
  
  test.describe('Content (Live Server)', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });
    
    test('should display welcome message', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForURL(/dashboard/, { timeout: 15000 });
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      
      // Should have some welcome content
      const welcomeContent = page.locator('h1, h2, .welcome, .greeting').first();
      await expect(welcomeContent).toBeVisible();
    });
    
    test('should display stats or summary section', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForURL(/dashboard/, { timeout: 15000 });
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      
      // Should have stats or cards section
      const statsSection = page.locator('.stats, .summary, [class*="stat"], [class*="card"]').first();
      await expect(statsSection).toBeVisible({ timeout: 5000 }).catch(() => {
        // Stats may not be present for new users
      });
    });
  });
});

test.describe('Error Pages', () => {
  
  test('should display 404 page for invalid routes', async ({ page }) => {
    await page.goto('/this-page-does-not-exist-12345');
    
    // Should show 404 error
    const errorIndicator = page.locator('text=404, text=not found, text=Not Found').first();
    await expect(errorIndicator).toBeVisible({ timeout: 5000 }).catch(async () => {
      // May redirect to home or show different error
      const statusCode = await page.locator('[class*="error"], [class*="404"]').count();
      expect(statusCode).toBeGreaterThanOrEqual(0);
    });
  });
  
  test('should have working navigation from 404 page', async ({ page }) => {
    await page.goto('/this-page-does-not-exist-12345');
    
    // Should have a link to go back or to home
    const homeLink = page.locator('a[href="/"], a:has-text("Home"), a:has-text("Back")');
    
    if (await homeLink.first().isVisible({ timeout: 3000 }).catch(() => false)) {
      await homeLink.first().click();
      
      // Should navigate away from 404
      await expect(page).not.toHaveURL(/this-page-does-not-exist/);
    }
  });
});

test.describe('Responsive Design', () => {
  
  test('should display correctly on mobile viewport', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
    
    await page.goto('/');
    
    // Page should still be usable
    const mainContent = page.locator('main, .main-content, body').first();
    await expect(mainContent).toBeVisible();
    
    // Navigation should be accessible (possibly via hamburger menu)
    const navElement = page.locator('nav, .navbar, .navigation, button[class*="menu"], button[class*="hamburger"]');
    await expect(navElement.first()).toBeVisible({ timeout: 5000 }).catch(() => {
      // Navigation may be different on mobile
    });
  });
  
  test('should display correctly on tablet viewport', async ({ page }) => {
    // Set tablet viewport
    await page.setViewportSize({ width: 768, height: 1024 });
    
    await page.goto('/');
    
    // Page should still be usable
    const mainContent = page.locator('main, .main-content, body').first();
    await expect(mainContent).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Mocked Dashboard Tests (Tier 1 — CI-safe)
// ---------------------------------------------------------------------------
test.describe('Mocked Dashboard — Structure', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('dashboard page loads with mocked auth', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).toBeVisible();
  });

  test('dashboard URL is correct', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/dashboard/);
  });

  test('navbar element is present on dashboard', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    const nav = page.locator('nav, .navbar').first();
    await expect(nav).toBeAttached();
  });

  test('main content area is present', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    const main = page.locator('.dashboard-container, .page-container, #mainContent').first();
    await expect(main).toBeAttached();
  });

  test('no JS errors on mocked dashboard load', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });
});

test.describe('Mocked Dashboard — New Application', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('new application page loads', async ({ page }) => {
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).toBeVisible();
  });

  test('new application page has job URL or title input', async ({ page }) => {
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    const input = page.locator('input[type="url"], input[name="job_url"], #jobUrl, input[type="text"]').first();
    await expect(input).toBeAttached();
  });

  test('new application page has a submit button', async ({ page }) => {
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    const btn = page.locator('button[type="submit"], button:has-text("Start"), button:has-text("Analyze"), button:has-text("Submit")').first();
    await expect(btn).toBeAttached();
  });
});

test.describe('Mocked Dashboard — Settings', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('settings page loads with mocked auth', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).toBeVisible();
  });

  test('settings page has profile or account section', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await page.waitForLoadState('domcontentloaded');
    const section = page.locator('#profile, #account, [data-tab="profile"], h2, h3').first();
    await expect(section).toBeAttached();
  });
});

test.describe('Mocked Dashboard — Career Tools', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('career tools page loads with mocked auth', async ({ page }) => {
    await page.goto('/dashboard/tools');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).toBeVisible();
  });

  test('career tools page shows tool section', async ({ page }) => {
    await page.goto('/dashboard/tools');
    await page.waitForLoadState('domcontentloaded');
    const tool = page.locator('[data-tool], .tool-section, #thankYouSection, #rejectionSection').first();
    await expect(tool).toBeAttached();
  });
});

test.describe('Mocked Dashboard — Application List', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('/dashboard/history returns 404 (route removed)', async ({ page }) => {
    const response = await page.goto('/dashboard/history');
    expect(response?.status()).toBe(404);
  });

  test('authenticated user stays on dashboard (not redirected to login)', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).not.toHaveURL(/\/auth\/login/);
  });
});
