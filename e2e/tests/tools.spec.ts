import { test, expect, Page } from '@playwright/test';
import { RegisterPage, ProfileSetupPage, DashboardPage } from '../pages';
import { generateTestEmail } from '../fixtures/test-data';
import { setupCookieConsent } from '../utils/api-mocks';

let toolsAuthToken = '';

// Helper — inject pre-registered user token (avoids login form + rate limits)
async function loginAndSetup(page: Page) {
  await setupCookieConsent(page);
  await page.addInitScript((token: string) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('authToken', token);
  }, toolsAuthToken);
  await page.goto('/dashboard');
  await page.waitForURL(/dashboard/, { timeout: 20000 });
  const dashboardPage = new DashboardPage(page);
  await dashboardPage.skipOnboarding();
}

test.describe('Career Tools', () => {
  let email: string;
  const password = 'ToolsTestPassword123!';
  
  test.beforeAll(async ({ browser }) => {
    // Create a user for tools tests
    const page = await browser.newPage();
    const registerPage = new RegisterPage(page);
    const profilePage = new ProfileSetupPage(page);
    
    email = generateTestEmail('tools_test');
    
    await registerPage.navigate();
    await registerPage.register({
      name: 'Tools Test User',
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
        skills: ['Python', 'JavaScript'],
      });
      await page.waitForURL(/dashboard/, { timeout: 20000 });
    }

    toolsAuthToken = await page.evaluate(() =>
      localStorage.getItem('access_token') || localStorage.getItem('authToken') || '',
    );
    expect(toolsAuthToken.length).toBeGreaterThan(0);
    
    await page.close();
  });
  
  test.describe('Tools Page Navigation', () => {
    
    test('should display career tools page', async ({ page }) => {
      await loginAndSetup(page);
      
      // Navigate to tools
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      await expect(page).toHaveURL(/tools/);
      // Verify the page title/header is visible
      await expect(page.locator('h2:has-text("Career Tools"), h4:has-text("Career Tools")')).toBeVisible({ timeout: 5000 });
    });
    
    test('should have multiple tool tabs', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Should have nav links for tools
      const tabs = page.locator('.tools-nav .nav-link');
      const tabCount = await tabs.count();
      
      // We have 6 tools: Thank You, Rejection, Reference, Compare Jobs, Follow-up, Salary
      expect(tabCount).toBeGreaterThanOrEqual(6);
    });
    
    test('should switch between tool tabs', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Default should be Thank You tab active
      await expect(page.locator('#thankYouSection')).toBeVisible();
      
      // Click on Rejection tab
      await page.locator('.nav-link:has-text("Rejection")').click();
      await expect(page.locator('#rejectionSection')).toBeVisible();
      
      // Click on Salary tab
      await page.locator('.nav-link:has-text("Salary")').click();
      await expect(page.locator('#salarySection')).toBeVisible();
    });
  });
  
  test.describe('Thank You Note Generator', () => {
    
    test('should display thank you note form', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Thank You is the default active tab
      await expect(page.locator('#thankYouSection')).toBeVisible();
      
      // Should show form fields
      await expect(page.locator('#interviewerName')).toBeVisible();
      await expect(page.locator('#companyName')).toBeVisible();
      await expect(page.locator('#jobTitle')).toBeVisible();
      await expect(page.locator('#interviewType')).toBeVisible();
    });
    
    test('should validate required fields', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Try to submit without filling required fields
      await page.locator('#thankYouSubmit').click();
      
      // HTML5 validation should prevent submission - check that required fields are present
      const interviewerInput = page.locator('#interviewerName');
      await expect(interviewerInput).toHaveAttribute('required', '');
    });
    
    test('should fill and submit thank you note form', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Fill form
      await page.locator('#interviewerName').fill('John Smith');
      await page.locator('#companyName').fill('Acme Corp');
      await page.locator('#jobTitle').fill('Software Engineer');
      await page.locator('#interviewType').selectOption('phone');
      
      // Verify fields are filled
      await expect(page.locator('#interviewerName')).toHaveValue('John Smith');
      await expect(page.locator('#companyName')).toHaveValue('Acme Corp');
      await expect(page.locator('#jobTitle')).toHaveValue('Software Engineer');
    });
  });
  
  test.describe('Rejection Analysis', () => {
    
    test('should display rejection analysis form', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to rejection tab
      await page.locator('.nav-link:has-text("Rejection")').click();
      await expect(page.locator('#rejectionSection')).toBeVisible();
      
      // Should show textarea for rejection email
      await expect(page.locator('#rejectionEmail')).toBeVisible();
    });
    
    test('should accept rejection email text', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to rejection tab
      await page.locator('.nav-link:has-text("Rejection")').click();
      
      // Fill rejection email
      const testEmail = 'Thank you for interviewing with us. We decided to move forward with another candidate.';
      await page.locator('#rejectionEmail').fill(testEmail);
      
      // Value should be filled
      await expect(page.locator('#rejectionEmail')).toHaveValue(testEmail);
    });
  });
  
  test.describe('Salary Negotiation Coach', () => {
    
    test('should display salary coach form', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to salary tab
      await page.locator('.nav-link:has-text("Salary")').click();
      await expect(page.locator('#salarySection')).toBeVisible();
      
      // Should show salary-related inputs
      await expect(page.locator('#offeredSalary')).toBeVisible();
      await expect(page.locator('#salaryJobTitle')).toBeVisible();
      await expect(page.locator('#salaryCompany')).toBeVisible();
    });
    
    test('should have job title and company inputs', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to salary tab
      await page.locator('.nav-link:has-text("Salary")').click();
      
      // Check for inputs
      await expect(page.locator('#salaryJobTitle')).toBeVisible();
      await expect(page.locator('#salaryCompany')).toBeVisible();
      await expect(page.locator('#offeredSalary')).toBeVisible();
    });
  });
  
  test.describe('Reference Request', () => {
    
    test('should display reference request form', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to reference tab
      await page.locator('.nav-link:has-text("Reference")').click();
      await expect(page.locator('#referenceSection')).toBeVisible();
      
      // Should show form fields
      await expect(page.locator('#referenceName')).toBeVisible();
      await expect(page.locator('#referenceRelationship')).toBeVisible();
    });
    
    test('should have relationship dropdown', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to reference tab
      await page.locator('.nav-link:has-text("Reference")').click();
      
      // Should have relationship select with options
      const relationshipSelect = page.locator('#referenceRelationship');
      await expect(relationshipSelect).toBeVisible();
      
      // Should have multiple options
      const options = relationshipSelect.locator('option');
      const optionCount = await options.count();
      expect(optionCount).toBeGreaterThan(1);
    });
  });
  
  test.describe('Follow-up Generator', () => {
    
    test('should display follow-up form', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to follow-up tab
      await page.locator('.nav-link:has-text("Follow")').click();
      await expect(page.locator('#followupSection')).toBeVisible();
      
      // Should show form fields
      await expect(page.locator('#followupStage')).toBeVisible();
      await expect(page.locator('#followupCompany')).toBeVisible();
      await expect(page.locator('#followupJobTitle')).toBeVisible();
    });
    
    test('should have stage selector', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to follow-up tab
      await page.locator('.nav-link:has-text("Follow")').click();
      
      // Should have stage select with options
      const stageSelect = page.locator('#followupStage');
      await expect(stageSelect).toBeVisible();
      
      // Should have multiple options
      const options = stageSelect.locator('option');
      const optionCount = await options.count();
      expect(optionCount).toBeGreaterThan(1);
    });
  });
  
  test.describe('Job Comparison', () => {
    
    test('should display job comparison form', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to comparison tab
      await page.locator('.nav-link:has-text("Compare")').click();
      await expect(page.locator('#comparisonSection')).toBeVisible();
      
      // Should show job input fields
      await expect(page.locator('#job1Title')).toBeVisible();
      await expect(page.locator('#job1Company')).toBeVisible();
      await expect(page.locator('#job2Title')).toBeVisible();
      await expect(page.locator('#job2Company')).toBeVisible();
    });
    
    test('should allow adding multiple jobs', async ({ page }) => {
      await loginAndSetup(page);
      
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('networkidle');
      
      // Switch to comparison tab
      await page.locator('.nav-link:has-text("Compare")').click();
      
      // Look for add job button for Job 3
      const addButton = page.locator('button:has-text("Add")').first();
      await expect(addButton).toBeVisible();
      
      // Click to add Job 3
      await addButton.click();
      
      // Job 3 fields should now be visible
      await expect(page.locator('#job3Title')).toBeVisible();
      await expect(page.locator('#job3Company')).toBeVisible();
    });
  });
});
