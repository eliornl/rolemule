import { test as setup, expect } from '@playwright/test';
import { RegisterPage } from '../pages';
import { generateTestEmail } from './test-data';

const authFile = 'playwright/.auth/user.json';

/**
 * Global setup - Create a test user and save authentication state
 */
setup('authenticate', async ({ page }) => {
  const registerPage = new RegisterPage(page);
  
  // Generate unique test user
  const testUser = {
    email: generateTestEmail('e2e_setup'),
    password: 'E2ETestPassword123!',
    name: 'E2E Test User',
  };
  
  // Store test user info for other tests
  process.env.TEST_USER_EMAIL = testUser.email;
  process.env.TEST_USER_PASSWORD = testUser.password;
  
  console.log(`Creating test user: ${testUser.email}`);
  
  // Navigate to register page
  await registerPage.navigate();
  
  // Register the test user
  await registerPage.register({
    name: testUser.name,
    email: testUser.email,
    password: testUser.password,
    acceptTerms: true,
  });
  
  // Wait for redirect (either to profile setup or dashboard)
  await page.waitForURL(/profile\/setup|dashboard/, { timeout: 15000 });
  
  // If redirected to profile setup, complete it quickly
  if (page.url().includes('profile/setup')) {
    // Skip resume upload
    const skipButton = page.locator('button:has-text("Fill in manually"), button:has-text("Skip")');
    if (await skipButton.isVisible({ timeout: 3000 })) {
      await skipButton.click();
    }
    
    // Fill minimal profile info and navigate through steps
    const nextButton = page.locator('button:has-text("Next"), button:has-text("Continue")');
    const completeButton = page.locator('button:has-text("Complete"), button:has-text("Finish"), button:has-text("Save")');
    
    // Fill basic info
    await page.locator('input[name="city"], #city').fill('Test City');
    await page.locator('input[name="professional_title"], #title, #professionalTitle').fill('Software Engineer');
    
    // Click through steps (some may be optional)
    for (let i = 0; i < 5; i++) {
      if (await nextButton.isVisible({ timeout: 2000 })) {
        await nextButton.click();
        await page.waitForTimeout(500);
      } else if (await completeButton.isVisible({ timeout: 2000 })) {
        await completeButton.click();
        break;
      }
    }
    
    // Wait for redirect to dashboard
    await page.waitForURL(/dashboard/, { timeout: 15000 });
  }
  
  // Handle onboarding if present
  const onboardingSkip = page.locator('.onboarding-btn-skip, button:has-text("Skip Tour")');
  if (await onboardingSkip.isVisible({ timeout: 3000 })) {
    await onboardingSkip.click();
  }
  
  // Verify we're on the dashboard
  await expect(page).toHaveURL(/dashboard/);
  
  // Save authentication state
  await page.context().storageState({ path: authFile });
  
  console.log('Authentication state saved');
});

/**
 * Export auth file path for use in other tests
 */
export { authFile };
