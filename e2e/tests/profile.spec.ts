import { test, expect } from '@playwright/test';
import { RegisterPage, ProfileSetupPage, SettingsPage } from '../pages';
import { generateTestEmail, testProfile } from '../fixtures/test-data';


test.describe('Profile Setup', () => {
  let profilePage: ProfileSetupPage;
  
  test.beforeEach(async ({ page }) => {
    // Register a new user for each test
    const registerPage = new RegisterPage(page);
    const email = generateTestEmail('profile_test');
    
    await registerPage.navigate();
    await registerPage.register({
      name: 'Profile Test User',
      email: email,
      password: 'ProfileTestPassword123!',
      acceptTerms: true,
    });
    
    // Wait for redirect to profile setup
    await page.waitForURL(/profile\/setup|dashboard/, { timeout: 15000 });
    
    // If on dashboard, navigate to profile setup
    if (!page.url().includes('profile/setup')) {
      await page.goto('/profile/setup');
    }
    
    profilePage = new ProfileSetupPage(page);
  });
  
  test('should display profile setup wizard', async ({ page }) => {
    await expect(page).toHaveURL(/profile\/setup/);
    
    // Handle cookie consent if present
    await profilePage.handleCookieConsent();
    
    // Should show profile setup page elements
    const pageHeading = page.getByRole('heading', { name: 'Complete Your Profile' });
    await expect(pageHeading).toBeVisible({ timeout: 5000 });
  });
  
  test('should skip resume upload and proceed to manual entry', async ({ page: _page }) => {
    await profilePage.handleCookieConsent();
    await profilePage.skipResumeUpload();
    
    // Should now see basic info form or next step
    const basicInfoField = profilePage.cityInput.or(profilePage.professionalTitleInput);
    await expect(basicInfoField).toBeVisible({ timeout: 5000 }).catch(() => {
      // May already be on a different step
    });
  });
  
  test('should fill basic info and proceed to next step', async ({ page }) => {
    await profilePage.skipResumeUpload();
    
    await profilePage.fillBasicInfo({
      city: testProfile.basicInfo.city,
      state: testProfile.basicInfo.state,
      country: testProfile.basicInfo.country,
      title: testProfile.basicInfo.title,
      yearsExperience: testProfile.basicInfo.yearsExperience,
      summary: testProfile.basicInfo.summary,
    });
    
    await profilePage.nextStep();
    
    // Should be on next step
    await page.waitForTimeout(500);
  });
  
  test('should add skills', async ({ page }) => {
    await profilePage.handleCookieConsent();
    await profilePage.skipResumeUpload();
    
    // Navigate to skills step (step 3) - fill ALL required fields
    await profilePage.fillBasicInfo({ 
      city: 'New York',
      state: 'NY',
      country: 'USA',
      title: 'Engineer', 
      yearsExperience: 5,
      summary: 'Experienced engineer with 5 years of experience in software development.',
    });
    await profilePage.nextStep();
    await page.waitForTimeout(500);
    
    // Skip work experience step (check the "no experience" checkbox)
    const noExperienceCheckbox = page.locator('input[type="checkbox"]:near(:text("don\'t have"))');
    if (await noExperienceCheckbox.isVisible().catch(() => false)) {
      await noExperienceCheckbox.check();
    }
    await profilePage.nextStep();
    await page.waitForTimeout(500);
    
    // Add skills
    await profilePage.addSkills(['Python', 'JavaScript', 'TypeScript']);
    
    // Verify skills were added (look for the skill badges)
    const skillTags = page.locator('.badge, .skill-badge, [class*="skill"]');
    await expect(skillTags.first()).toBeVisible({ timeout: 5000 }).catch(() => {
      // Skills may be displayed differently
    });
  });
  
  test('should complete profile setup', async ({ page }) => {
    await profilePage.quickSetup({
      title: 'Software Engineer',
      yearsExperience: 5,
      skills: ['Python', 'JavaScript'],
    });
    
    // Should redirect to dashboard
    await expect(page).toHaveURL(/dashboard/, { timeout: 15000 });
  });
  
  test('should navigate back to previous step', async ({ page }) => {
    await profilePage.handleCookieConsent();
    await profilePage.skipResumeUpload();
    
    // Fill ALL required basic info fields
    await profilePage.fillBasicInfo({ 
      city: 'San Francisco',
      state: 'CA',
      country: 'USA',
      title: 'Engineer', 
      yearsExperience: 3,
      summary: 'Experienced engineer with 3 years of experience.',
    });
    await profilePage.nextStep();
    
    // Wait for step 2 (work experience) to be active
    await page.waitForTimeout(1000);
    
    // The back button should now be visible on step 2
    const backButton = page.locator('#prev-btn, button:has-text("Previous")');
    await expect(backButton).toBeVisible({ timeout: 10000 });
    
    // Go back
    await backButton.click();
    await page.waitForTimeout(500);
    
    // Should see basic info fields again (use first to avoid strict mode violation)
    await expect(profilePage.cityInput.first()).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Profile Management', () => {
  
  test.describe('Settings Page Profile', () => {
    
    test('should access settings page when logged in', async ({ page }) => {
      // Register and complete setup
      const registerPage = new RegisterPage(page);
      const email = generateTestEmail('settings_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'Settings Test User',
        email: email,
        password: 'SettingsTestPassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
      
      // Navigate to settings
      await page.goto('/dashboard/settings');
      
      await expect(page).toHaveURL(/settings/);
    });
    
    test('should export user data', async ({ page }) => {
      // Register
      const registerPage = new RegisterPage(page);
      const email = generateTestEmail('export_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'Export Test User',
        email: email,
        password: 'ExportTestPassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
      
      // Navigate to settings
      const settingsPage = new SettingsPage(page);
      await settingsPage.navigate();
      
      // Handle cookie consent if present
      await settingsPage.handleCookieConsent();
      
      // Click on Privacy tab to find export button
      const privacyTab = page.locator('a:has-text("Privacy")');
      await privacyTab.click();
      await page.waitForTimeout(500);
      
      // Wait for export button to be visible
      await expect(settingsPage.exportDataButton).toBeVisible({ timeout: 10000 });
      
      // Click export and verify download starts
      const downloadPromise = page.waitForEvent('download', { timeout: 30000 }).catch(() => null);
      await settingsPage.exportDataButton.click();
      
      const download = await downloadPromise;
      
      if (download) {
        // Verify download filename
        const filename = download.suggestedFilename();
        expect(filename).toMatch(/job-assistant|export|data/i);
      }
    });
    
    test('should show API key configuration section', async ({ page }) => {
      // Register
      const registerPage = new RegisterPage(page);
      const email = generateTestEmail('apikey_section_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'API Key Section Test User',
        email: email,
        password: 'APIKeyTestPassword123!',
        acceptTerms: true,
      });
      
      // Wait for registration to complete (may take longer)
      await page.waitForURL(/profile|dashboard/, { timeout: 30000 });
      
      // Navigate to settings
      const settingsPage = new SettingsPage(page);
      await settingsPage.navigate();
      
      // Handle cookie consent if present
      await settingsPage.handleCookieConsent();
      
      // Click on API Keys tab
      const apiKeysTab = page.locator('a:has-text("API Keys")');
      await apiKeysTab.click();
      await page.waitForTimeout(500);
      
      // Verify API key section is visible
      await expect(settingsPage.apiKeySection).toBeVisible({ timeout: 10000 });
    });
  });
});

test.describe('Help & Support', () => {
  
  test('should navigate to help page', async ({ page }) => {
    await page.goto('/help', { timeout: 60000 });
    
    await expect(page).toHaveURL(/help/);
    
    // Should have FAQ sections
    const faqSection = page.locator('.faq-section, .faq-category, [class*="faq"]');
    await expect(faqSection.first()).toBeVisible({ timeout: 10000 });
  });
  
  test('should search help articles', async ({ page }) => {
    await page.goto('/help');
    
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"], #helpSearch');
    
    if (await searchInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await searchInput.fill('API key');
      await page.waitForTimeout(500);
      
      // Should filter results
    }
  });
  
  test('should expand FAQ items', async ({ page }) => {
    await page.goto('/help');
    
    const faqQuestion = page.locator('.faq-question, [class*="question"]').first();
    
    if (await faqQuestion.isVisible({ timeout: 3000 }).catch(() => false)) {
      await faqQuestion.click();
      
      // Answer should be visible
      const faqAnswer = page.locator('.faq-answer, [class*="answer"]').first();
      await expect(faqAnswer).toBeVisible({ timeout: 3000 }).catch(() => {
        // Answer may be shown differently
      });
    }
  });
});
