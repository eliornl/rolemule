import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Settings page object
 */
export class SettingsPage extends BasePage {
  readonly url = '/dashboard/settings';
  
  // API Key section
  readonly apiKeySection: Locator;
  readonly apiKeyInput: Locator;
  readonly saveApiKeyButton: Locator;
  readonly deleteApiKeyButton: Locator;
  readonly apiKeyStatus: Locator;
  
  // Account section
  readonly changePasswordButton: Locator;
  readonly currentPasswordInput: Locator;
  readonly newPasswordInput: Locator;
  readonly confirmPasswordInput: Locator;
  readonly updatePasswordButton: Locator;
  
  // Data section
  readonly exportDataButton: Locator;
  readonly clearDataButton: Locator;
  readonly deleteAccountButton: Locator;
  
  // Help section
  readonly helpLink: Locator;
  readonly restartTourButton: Locator;
  
  // Notifications
  readonly notificationToggles: Locator;
  readonly saveNotificationsButton: Locator;
  
  // Confirmation modal
  readonly confirmModal: Locator;
  readonly confirmButton: Locator;
  readonly cancelButton: Locator;
  readonly confirmInput: Locator;
  
  constructor(page: Page) {
    super(page);
    
    // API Key
    this.apiKeySection = page.locator('#apiKeysSection');
    this.apiKeyInput = page.locator('#geminiApiKey');
    this.saveApiKeyButton = page.locator('#apiKeysSection button[type="submit"], #saveApiKeyBtn, button:has-text("Save API Key")');
    this.deleteApiKeyButton = page.locator('#deleteApiKeyBtn, button:has-text("Delete")');
    this.apiKeyStatus = page.locator('#apiKeyStatus, #apiKeyStatusText');
    
    // Account
    this.changePasswordButton = page.locator('button:has-text("Change Password")');
    this.currentPasswordInput = page.locator('input[name="current_password"], #currentPassword');
    this.newPasswordInput = page.locator('input[name="new_password"], #newPassword');
    this.confirmPasswordInput = page.locator('input[name="confirm_password"], #confirmPassword');
    this.updatePasswordButton = page.locator('button:has-text("Update Password")');
    
    // Data
    this.exportDataButton = page.locator('[data-action="exportData"], button:has-text("Export")');
    this.clearDataButton = page.locator('button:has-text("Clear Data"), button:has-text("Clear All")');
    this.deleteAccountButton = page.locator('button:has-text("Delete Account"), button:has-text("Delete My Account")');
    
    // Help
    this.helpLink = page.locator('a:has-text("Help"), a[href*="help"]');
    this.restartTourButton = page.locator('button:has-text("Restart Tour")');
    
    // Notifications
    this.notificationToggles = page.locator('input[type="checkbox"][name*="notification"]');
    this.saveNotificationsButton = page.locator('button:has-text("Save Preferences"), button:has-text("Save Notifications")');
    
    // Confirmation modal
    this.confirmModal = page.locator('.modal, .confirmation-modal, [role="dialog"]');
    this.confirmButton = page.locator('.modal button:has-text("Confirm"), .modal button:has-text("Delete"), .modal button:has-text("Yes")');
    this.cancelButton = page.locator('.modal button:has-text("Cancel"), .modal button:has-text("No")');
    this.confirmInput = page.locator('.modal input[type="text"], .modal input[placeholder*="DELETE"]');
  }
  
  /**
   * Navigate to settings page
   */
  async navigate() {
    await this.goto(this.url);
    await this.waitForPageLoad();
  }
  
  /**
   * Set API key
   */
  async setApiKey(apiKey: string) {
    await this.fillField(this.apiKeyInput, apiKey);
    await this.saveApiKeyButton.click();
    await this.waitForLoading();
  }
  
  /**
   * Delete API key
   */
  async deleteApiKey() {
    await this.deleteApiKeyButton.click();
    await this.waitForLoading();
  }
  
  /**
   * Check if API key is configured
   */
  async hasApiKey(): Promise<boolean> {
    const status = await this.apiKeyStatus.textContent();
    return status?.toLowerCase().includes('configured') || false;
  }
  
  /**
   * Change password
   */
  async changePassword(currentPassword: string, newPassword: string) {
    // Open change password form if needed
    if (await this.isVisible(this.changePasswordButton)) {
      await this.changePasswordButton.click();
    }
    
    await this.fillField(this.currentPasswordInput, currentPassword);
    await this.fillField(this.newPasswordInput, newPassword);
    await this.fillField(this.confirmPasswordInput, newPassword);
    await this.updatePasswordButton.click();
    await this.waitForLoading();
  }
  
  /**
   * Export user data
   */
  async exportData() {
    const downloadPromise = this.page.waitForEvent('download');
    await this.exportDataButton.click();
    const download = await downloadPromise;
    return download;
  }
  
  /**
   * Clear all data (requires confirmation)
   */
  async clearData() {
    await this.clearDataButton.click();
    
    // Handle confirmation modal
    await expect(this.confirmModal).toBeVisible();
    
    // Type DELETE if required
    if (await this.isVisible(this.confirmInput)) {
      await this.fillField(this.confirmInput, 'DELETE');
    }
    
    await this.confirmButton.click();
    await this.waitForLoading();
  }
  
  /**
   * Delete account (requires confirmation)
   */
  async deleteAccount() {
    await this.deleteAccountButton.click();
    
    // Handle confirmation modal
    await expect(this.confirmModal).toBeVisible();
    
    // Type DELETE if required
    if (await this.isVisible(this.confirmInput)) {
      await this.fillField(this.confirmInput, 'DELETE');
    }
    
    await this.confirmButton.click();
    await this.waitForLoading();
  }
  
  /**
   * Restart onboarding tour
   */
  async restartTour() {
    await this.restartTourButton.click();
    await this.waitForURL(/dashboard/);
  }
  
  /**
   * Go to help page
   */
  async goToHelp() {
    await this.helpLink.click();
    await this.waitForURL(/help/);
  }
  
  /**
   * Toggle notification setting
   */
  async toggleNotification(index: number) {
    await this.notificationToggles.nth(index).click();
  }
  
  /**
   * Save notification preferences
   */
  async saveNotifications() {
    await this.saveNotificationsButton.click();
    await this.waitForLoading();
  }
}
