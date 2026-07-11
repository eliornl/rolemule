import { test as setup, expect } from '@playwright/test';
import { RegisterPage, ProfileSetupPage } from './pages';
import { generateTestEmail } from './fixtures/test-data';
import * as fs from 'fs';
import * as path from 'path';

const AUTH_FILE = path.join(__dirname, 'playwright/.auth/user.json');

/**
 * Global setup - runs once before all tests
 * Creates a test user and saves authentication state
 * Skips if valid auth state already exists (for faster runs)
 */
setup('global setup', async ({ page }) => {
  setup.setTimeout(120000);

  if (process.env.SKIP_SERVER || process.env.SMOKE) {
    console.log('\n⚡ Skipping global setup (mocked/smoke mode)\n');
    return;
  }

  // Ensure auth directory exists
  const authDir = path.dirname(AUTH_FILE);
  if (!fs.existsSync(authDir)) {
    fs.mkdirSync(authDir, { recursive: true });
  }
  
  // Check if auth state already exists and is recent (within 1 hour)
  const testDataFile = path.join(__dirname, 'playwright/.auth/test-user.json');
  if (fs.existsSync(AUTH_FILE) && fs.existsSync(testDataFile)) {
    const authStats = fs.statSync(AUTH_FILE);
    const ageMs = Date.now() - authStats.mtimeMs;
    const oneHourMs = 60 * 60 * 1000;
    
    if (ageMs < oneHourMs) {
      console.log(`\n⚡ Reusing existing auth state (${Math.round(ageMs / 1000 / 60)} min old)\n`);
      return; // Skip setup - auth is fresh enough
    }
  }
  
  // Generate unique test user
  const testUser = {
    email: generateTestEmail('e2e_global'),
    password: 'E2EGlobalTest123!',
    name: 'Playwright Global Test User',
  };
  
  // Save test user info to a file for other tests to use
  fs.writeFileSync(testDataFile, JSON.stringify(testUser, null, 2));
  
  console.log(`\n🔐 Setting up E2E tests with user: ${testUser.email}\n`);
  
  // Navigate to register page
  const registerPage = new RegisterPage(page);
  await registerPage.navigate();
  
  // Handle cookie consent if present
  await registerPage.handleCookieConsent();
  
  // Register the test user
  await registerPage.register({
    name: testUser.name,
    email: testUser.email,
    password: testUser.password,
    acceptTerms: true,
  });
  
  // Wait for redirect
  await page.waitForURL(/profile\/setup|dashboard/, { timeout: 20000 });
  
  // Complete profile setup if needed
  if (page.url().includes('profile/setup')) {
    console.log('📝 Completing profile setup...');
    const profilePage = new ProfileSetupPage(page);
    await profilePage.quickSetup({
      title: 'Software Engineer',
      yearsExperience: 5,
      skills: ['JavaScript', 'Python'],
    });
    await page.waitForURL(/dashboard/, { timeout: 15000 });
  }
  
  // Handle onboarding tutorial if present
  const onboardingSkip = page.locator('.onboarding-btn-skip, button:has-text("Skip Tour"), button:has-text("Skip")');
  if (await onboardingSkip.isVisible({ timeout: 2000 }).catch(() => false)) {
    await onboardingSkip.click();
  }
  
  // Verify we're authenticated and on dashboard
  await expect(page).toHaveURL(/dashboard/);
  console.log('✅ Successfully authenticated and on dashboard\n');
  
  // Save authentication state
  await page.context().storageState({ path: AUTH_FILE });
  console.log(`💾 Authentication state saved to ${AUTH_FILE}\n`);
});

export { AUTH_FILE };
