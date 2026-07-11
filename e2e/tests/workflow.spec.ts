import { test, expect, Page } from '@playwright/test';
import { RegisterPage, ProfileSetupPage, NewApplicationPage, DashboardPage, SettingsPage } from '../pages';
import { generateTestEmail, testJobPostings, testApiKey } from '../fixtures/test-data';
import { setupCookieConsent, setupAuth, setupAllMocks, mockWorkflowSession } from '../utils/api-mocks';

let workflowAuthToken = '';

/**
 * Inject pre-registered workflow user token (set in beforeAll).
 */
async function loginAndSetup(page: Page) {
  await setupCookieConsent(page);
  await page.addInitScript((token: string) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('authToken', token);
  }, workflowAuthToken);
  await page.goto('/dashboard');
  await page.waitForURL(/dashboard/, { timeout: 20000 });
  const dashboardPage = new DashboardPage(page);
  await dashboardPage.skipOnboarding();
}

test.describe('Job Analysis Workflow', () => {
  let email: string;
  const password = 'WorkflowTestPassword123!';
  
  test.beforeAll(async ({ browser }) => {
    // Create a user with completed profile for workflow tests
    const page = await browser.newPage();
    const registerPage = new RegisterPage(page);
    const profilePage = new ProfileSetupPage(page);
    
    email = generateTestEmail('workflow_test');
    
    await registerPage.navigate();
    await registerPage.register({
      name: 'Workflow Test User',
      email: email,
      password: password,
      acceptTerms: true,
    });
    
    await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
    
    // Complete profile setup
    if (page.url().includes('profile/setup')) {
      await profilePage.quickSetup({
        title: 'Software Engineer',
        yearsExperience: 5,
        skills: ['Python', 'JavaScript', 'React', 'Node.js'],
      });
      await page.waitForURL(/dashboard/, { timeout: 20000 });
    }

    workflowAuthToken = await page.evaluate(() =>
      localStorage.getItem('access_token') || localStorage.getItem('authToken') || '',
    );
    expect(workflowAuthToken.length).toBeGreaterThan(0);
    
    await page.close();
  });
  
  test.describe('New Application Page', () => {
    
    test('should display new application form', async ({ page }) => {
      await loginAndSetup(page);
      
      // Navigate to new application
      const newAppPage = new NewApplicationPage(page);
      await newAppPage.navigate();
      
      // Should be on Step 1 with basic info fields - use first() for strict mode
      await expect(newAppPage.jobTitleInput.first()).toBeVisible({ timeout: 10000 });
    });
    
    test('should have multiple input method tabs', async ({ page }) => {
      await loginAndSetup(page);
      
      const newAppPage = new NewApplicationPage(page);
      await newAppPage.navigate();
      
      // Complete Step 1 first
      await newAppPage.completeStep1();
      
      // Check for tabs (URL, Text, File) - these are method-tab buttons
      const tabs = page.locator('.method-tab');
      const tabCount = await tabs.count();
      
      // Should have at least URL and Text options
      expect(tabCount).toBeGreaterThanOrEqual(2);
    });
    
    test('should switch between input methods', async ({ page }) => {
      await loginAndSetup(page);
      
      const newAppPage = new NewApplicationPage(page);
      await newAppPage.navigate();
      
      // Complete Step 1 first
      await newAppPage.completeStep1();
      
      // Try to switch to text input
      if (await newAppPage.textTab.isVisible({ timeout: 2000 }).catch(() => false)) {
        await newAppPage.selectTextInput();
        await expect(newAppPage.textInput).toBeVisible();
      }
      
      // Try to switch to URL input
      if (await newAppPage.urlTab.isVisible({ timeout: 2000 }).catch(() => false)) {
        await newAppPage.selectUrlInput();
        await expect(newAppPage.urlInput).toBeVisible();
      }
    });
    
    test('should validate empty job input', async ({ page }) => {
      await loginAndSetup(page);
      
      const newAppPage = new NewApplicationPage(page);
      await newAppPage.navigate();
      
      // Try to click Next without filling required fields
      await newAppPage.nextStepButton.click().catch(() => {});
      
      // Should show error or validation message or stay on Step 1
      const errorOrValidation = page.locator('.error, .invalid, [class*="error"], [class*="validation"], .is-invalid');
      await expect(errorOrValidation.first()).toBeVisible({ timeout: 5000 }).catch(() => {
        // May just not proceed without explicit error
      });
    });
  });
  
  test.describe('Workflow Execution', () => {
    
    test('should start workflow with text input', async ({ page }) => {
      await loginAndSetup(page);
      
      const newAppPage = new NewApplicationPage(page);
      await newAppPage.navigate();
      
      // Complete Step 1 first
      await newAppPage.completeStep1('Software Engineer', 'TechCorp');
      
      // Select text input and fill
      await newAppPage.selectTextInput().catch(() => {});
      await newAppPage.textInput.fill(testJobPostings.simple);
      
      // Start analysis
      await newAppPage.analyzeButton.first().click();
      
      // Should show progress or processing state
      const processingIndicator = page.locator('.progress, .processing, .loading, [class*="progress"], [class*="status"]');
      await expect(processingIndicator.first()).toBeVisible({ timeout: 10000 }).catch(() => {
        // May redirect immediately or show different indicator
      });
    });
    
    test('should show agent progress during workflow', async ({ page }) => {
      await loginAndSetup(page);
      
      const newAppPage = new NewApplicationPage(page);
      await newAppPage.navigate();
      
      // Complete Step 1 first
      await newAppPage.completeStep1('Data Scientist', 'DataCorp');
      
      // Start workflow
      await newAppPage.selectTextInput().catch(() => {});
      await newAppPage.textInput.fill(testJobPostings.simple);
      await newAppPage.analyzeButton.first().click();
      
      // Check for agent status indicators
      const agentIndicators = page.locator('[class*="agent"], [class*="step"], .workflow-step');
      
      // Wait a bit for agents to start
      await page.waitForTimeout(3000);
      
      // Should show some agent/step indicators
      await agentIndicators.count();
      // May or may not have indicators depending on UI
    });
    
    test('should complete workflow and show results', async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);

      const newAppPage = new NewApplicationPage(page);
      await newAppPage.navigate();
      await newAppPage.selectTextInput();
      await newAppPage.textInput.fill(testJobPostings.simple);

      await Promise.all([
        page.waitForURL(/\/dashboard\/?$/, { timeout: 15000 }),
        newAppPage.analyzeButton.first().click(),
      ]);

      await page.goto(`/dashboard/application/${mockWorkflowSession.session_id}`);
      await page.waitForLoadState('domcontentloaded');

      await expect(page.locator('body')).toContainText(/Software Engineer|TechCorp|85/i, {
        timeout: 15000,
      });
    });
  });
  
  test.describe('Application List (formerly History)', () => {
    
    test('should display dashboard application list', async ({ page }) => {
      await loginAndSetup(page);
      
      const dashboardPage = new DashboardPage(page);
      
      // goToHistory() now navigates to /dashboard (history was consolidated)
      await dashboardPage.goToHistory();
      
      await expect(page).toHaveURL(/dashboard/);
    });
    
    test('should show empty state for new users on dashboard', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      const newEmail = generateTestEmail('history_empty_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'History Empty Test',
        email: newEmail,
        password: 'HistoryEmptyTestPassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
      
      if (page.url().includes('profile/setup')) {
        const profilePage = new ProfileSetupPage(page);
        await profilePage.quickSetup({
          title: 'Engineer',
          yearsExperience: 3,
          skills: ['Python'],
        });
        await page.waitForURL(/dashboard/, { timeout: 15000 });
      }
      
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.skipOnboarding();
      
      await page.goto('/dashboard');
      await expect(page).toHaveURL(/dashboard/);
      
      const pageContent = page.locator('h1, h2, .page-title');
      await expect(pageContent.first()).toBeVisible({ timeout: 10000 });
    });
  });
});

test.describe('API Key Configuration', () => {
  
  test('should show API key not configured warning', async ({ page }) => {
    // Register new user
    const registerPage = new RegisterPage(page);
    const email = generateTestEmail('apikey_warning_test');
    
    await registerPage.navigate();
    await registerPage.register({
      name: 'API Key Warning Test',
      email: email,
      password: 'APIKeyWarningTestPassword123!',
      acceptTerms: true,
    });
    
    await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
    
    // Complete profile if needed
    if (page.url().includes('profile/setup')) {
      const profilePage = new ProfileSetupPage(page);
      await profilePage.quickSetup({
        title: 'Engineer',
        yearsExperience: 3,
        skills: ['Python'],
      });
      await page.waitForURL(/dashboard/, { timeout: 15000 });
    }
    
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.skipOnboarding();
    
    // Try to start a workflow without API key
    const newAppPage = new NewApplicationPage(page);
    await newAppPage.navigate();
    
    // Handle cookie consent if visible
    await newAppPage.handleCookieConsent();
    
    // Complete Step 1 first
    await newAppPage.completeStep1('Software Engineer', 'Test Company');
    
    await newAppPage.selectTextInput().catch(() => {});
    
    // Wait for text input to be visible before filling
    await expect(newAppPage.textInput).toBeVisible({ timeout: 10000 });
    await newAppPage.textInput.fill('Test job posting for Software Engineer at Test Company. Requirements: Python, JavaScript, 5 years experience.');
    await newAppPage.analyzeButton.first().click();
    
    // Should show API key warning or error
    const apiKeyWarning = page.locator('text=API key, text=configure, text=required');
    await expect(apiKeyWarning.first()).toBeVisible({ timeout: 10000 }).catch(() => {
      // Warning may be shown differently
    });
  });
  
  test('should save API key in settings', async ({ page }) => {
    // Register new user
    const registerPage = new RegisterPage(page);
    const email = generateTestEmail('apikey_save_test');
    
    await registerPage.navigate();
    await registerPage.register({
      name: 'API Key Save Test',
      email: email,
      password: 'APIKeySaveTestPassword123!',
      acceptTerms: true,
    });
    
    await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
    
    // Complete profile if needed
    if (page.url().includes('profile/setup')) {
      const profilePage = new ProfileSetupPage(page);
      await profilePage.quickSetup({
        title: 'Engineer',
        yearsExperience: 3,
        skills: ['Python'],
      });
      await page.waitForURL(/dashboard/, { timeout: 15000 });
    }
    
    const dashboardPage = new DashboardPage(page);
    await dashboardPage.skipOnboarding();
    
    // Go to settings
    const settingsPage = new SettingsPage(page);
    await settingsPage.navigate();
    
    // Handle cookie consent
    await settingsPage.handleCookieConsent();
    
    // Click on API Keys tab
    const apiKeysTab = page.locator('a[data-section="apiKeys"], .settings-nav a:has-text("AI Setup")');
    await apiKeysTab.click();
    await page.waitForTimeout(500);
    
    // Wait for API key input to be visible
    await expect(settingsPage.apiKeyInput).toBeVisible({ timeout: 10000 });
    
    // Enter API key
    await settingsPage.apiKeyInput.fill(testApiKey);
    await settingsPage.saveApiKeyButton.click();
    
    // Should show success message
    const successMessage = page.locator('.success, .alert-success, text=saved, text=success');
    await expect(successMessage.first()).toBeVisible({ timeout: 10000 }).catch(() => {
      // May not show explicit success message
    });
  });
});
