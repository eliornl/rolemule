import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Reset Password page object
 */
export class ResetPasswordPage extends BasePage {
  readonly url = '/auth/reset-password';
  
  // Request reset form
  readonly emailInput: Locator;
  readonly requestResetButton: Locator;
  readonly successMessage: Locator;
  
  // Reset form (with token)
  readonly newPasswordInput: Locator;
  readonly confirmPasswordInput: Locator;
  readonly resetButton: Locator;
  
  // Navigation
  readonly backToLoginLink: Locator;
  
  // Error/validation
  readonly errorMessage: Locator;
  readonly fieldError: Locator;
  
  constructor(page: Page) {
    super(page);
    
    // Request reset form (first form on the page)
    this.emailInput = page.locator('#email, input[type="email"]').first();
    this.requestResetButton = page.locator('#forgotBtn');
    this.successMessage = page.locator('#forgotAlert.alert-success, .alert-success').first();
    
    // Reset with token form (second form, only visible with token)
    this.newPasswordInput = page.locator('#newPassword');
    this.confirmPasswordInput = page.locator('#confirmPassword');
    this.resetButton = page.locator('#resetBtn');
    
    // Navigation
    this.backToLoginLink = page.locator('a[href*="login"], a:has-text("Login"), a:has-text("Back")');
    
    // Errors
    this.errorMessage = page.locator('#forgotError, #resetError, .alert-danger').first();
    this.fieldError = page.locator('.field-error, .invalid-feedback');
  }
  
  /**
   * Navigate to reset password page
   */
  async navigate() {
    await this.goto(this.url);
    await this.waitForPageLoad();
  }
  
  /**
   * Navigate to reset page with token
   */
  async navigateWithToken(token: string) {
    await this.goto(`${this.url}?token=${token}`);
    await this.waitForPageLoad();
  }
  
  /**
   * Request password reset
   */
  async requestReset(email: string) {
    await this.fillField(this.emailInput, email);
    await this.requestResetButton.click();
    await this.waitForLoading();
  }
  
  /**
   * Reset password with new password
   */
  async resetPassword(newPassword: string, confirmPassword?: string) {
    await this.fillField(this.newPasswordInput, newPassword);
    await this.fillField(this.confirmPasswordInput, confirmPassword || newPassword);
    await this.resetButton.click();
    await this.waitForLoading();
  }
  
  /**
   * Check if success message is shown
   */
  async isSuccessShown(): Promise<boolean> {
    return await this.successMessage.isVisible({ timeout: 5000 }).catch(() => false);
  }
  
  /**
   * Check if error is shown
   */
  async isErrorShown(): Promise<boolean> {
    return await this.errorMessage.isVisible({ timeout: 3000 }).catch(() => false);
  }
  
  /**
   * Go back to login
   */
  async goToLogin() {
    await this.backToLoginLink.click();
    await this.waitForURL(/login/);
  }
}
