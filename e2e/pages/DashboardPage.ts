import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Dashboard page object
 */
export class DashboardPage extends BasePage {
  readonly url = '/dashboard';
  
  // Navigation
  readonly navbar: Locator;
  readonly helpLink: Locator;
  readonly settingsLink: Locator;
  readonly logoutButton: Locator;
  readonly newApplicationButton: Locator;
  readonly historyLink: Locator;
  readonly toolsLink: Locator;
  
  // Dashboard content
  readonly welcomeMessage: Locator;
  readonly statsCards: Locator;
  readonly recentApplications: Locator;
  readonly applicationCard: Locator;
  
  // Onboarding
  readonly onboardingOverlay: Locator;
  readonly onboardingSkipButton: Locator;
  readonly onboardingNextButton: Locator;
  
  constructor(page: Page) {
    super(page);
    
    // Navigation
    this.navbar = page.locator('nav.navbar').first();
    this.helpLink = page.locator('a[href*="help"], a:has-text("Help")');
    this.settingsLink = page.locator('a[href*="settings"], a:has-text("Settings")');
    this.logoutButton = page.locator('[data-action="logout"]');
    this.newApplicationButton = page.locator('a[href*="new-application"], button:has-text("New Application"), a:has-text("New Application"), a:has-text("Analyze Job")');
    this.historyLink = page.locator('a[href*="history"], a:has-text("History")');
    this.toolsLink = page.locator('a[href*="tools"], a:has-text("Tools"), a:has-text("Career Tools")');
    
    // Content
    this.welcomeMessage = page.locator('.welcome-message, h1, .greeting');
    this.statsCards = page.locator('.stats-card, .stat-card, [class*="stat"]');
    this.recentApplications = page.locator('.recent-applications, .applications-list, [class*="application"]');
    this.applicationCard = page.locator('.application-card, .workflow-card, [class*="card"]');
    
    // Onboarding
    this.onboardingOverlay = page.locator('#onboarding-overlay');
    this.onboardingSkipButton = page.locator('.onboarding-btn-skip, button:has-text("Skip")');
    this.onboardingNextButton = page.locator('.onboarding-btn-next, button:has-text("Next")');
  }
  
  /**
   * Navigate to dashboard
   */
  async navigate() {
    await this.goto(this.url);
    await this.waitForPageLoad();
  }
  
  /**
   * Skip onboarding tutorial if present
   */
  async skipOnboarding() {
    try {
      if (await this.onboardingOverlay.isVisible({ timeout: 3000 })) {
        await this.onboardingSkipButton.click();
        await this.onboardingOverlay.waitFor({ state: 'hidden', timeout: 3000 });
      }
    } catch {
      // Onboarding not present
    }
  }
  
  /**
   * Complete onboarding tutorial
   */
  async completeOnboarding() {
    try {
      if (await this.onboardingOverlay.isVisible({ timeout: 3000 })) {
        // Click through all steps
        for (let i = 0; i < 6; i++) {
          await this.onboardingNextButton.click();
          await this.page.waitForTimeout(500);
        }
        await this.onboardingOverlay.waitFor({ state: 'hidden', timeout: 3000 });
      }
    } catch {
      // Onboarding not present or already completed
    }
  }
  
  /**
   * Go to new application page
   */
  async goToNewApplication() {
    await this.newApplicationButton.click();
    await this.waitForURL(/new-application/);
  }
  
  /**
   * Go to settings page
   */
  async goToSettings() {
    await this.settingsLink.click();
    await this.waitForURL(/settings/);
  }
  
  /**
   * Go to help page
   */
  async goToHelp() {
    await this.helpLink.click();
    await this.waitForURL(/help/);
  }
  
  /**
   * Go to career tools page
   */
  async goToTools() {
    await this.toolsLink.click();
    await this.waitForURL(/tools/);
  }
  
  /**
   * Go to dashboard (application list — history page was consolidated here)
   */
  async goToHistory() {
    await this.goto('/dashboard');
    await this.waitForURL(/dashboard/);
  }
  
  /**
   * Logout
   */
  async logout() {
    await this.logoutButton.click();
    await this.waitForURL(/login/);
  }
  
  /**
   * Check if user is logged in (dashboard is accessible)
   */
  async isLoggedIn(): Promise<boolean> {
    try {
      await this.page.waitForURL(/dashboard/, { timeout: 5000 });
      return true;
    } catch {
      return false;
    }
  }
  
  /**
   * Get application count from stats
   */
  async getApplicationCount(): Promise<number> {
    const countText = await this.statsCards.first().textContent();
    const match = countText?.match(/\d+/);
    return match ? parseInt(match[0]) : 0;
  }
  
  /**
   * Click on an application card
   */
  async openApplication(index: number = 0) {
    await this.applicationCard.nth(index).click();
    await this.waitForURL(/application/);
  }
  
  /**
   * Verify dashboard is fully loaded
   */
  async verifyLoaded() {
    await expect(this.navbar).toBeVisible();
    await expect(this.newApplicationButton).toBeVisible();
  }
}
