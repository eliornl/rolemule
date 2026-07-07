import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Email Verification page object
 */
export class VerifyEmailPage extends BasePage {
  readonly url = '/auth/verify-email';
  
  // Status messages
  readonly verifyingMessage: Locator;
  readonly successMessage: Locator;
  readonly errorMessage: Locator;
  readonly expiredMessage: Locator;
  
  // Actions
  readonly resendButton: Locator;
  readonly loginButton: Locator;
  readonly continueButton: Locator;
  
  // Resend form
  readonly emailInput: Locator;
  readonly submitResendButton: Locator;
  
  constructor(page: Page) {
    super(page);
    
    // Status messages
    this.verifyingMessage = page.locator('text=verifying, text=please wait');
    this.successMessage = page.locator('.success, .alert-success, text=verified, text=confirmed');
    this.errorMessage = page.locator('.error, .alert-danger, text=invalid, text=failed');
    this.expiredMessage = page.locator('text=expired, text=no longer valid');
    
    // Actions
    this.resendButton = page.locator('button:has-text("Resend"), a:has-text("Resend")');
    this.loginButton = page.locator('button:has-text("Login"), a:has-text("Login"), a[href*="login"]');
    this.continueButton = page.locator('button:has-text("Continue"), a:has-text("Continue"), a:has-text("Dashboard")');
    
    // Resend form
    this.emailInput = page.locator('input[type="email"], input[name="email"]');
    this.submitResendButton = page.locator('button[type="submit"], button:has-text("Send")');
  }
  
  /**
   * Navigate to verify email page
   */
  async navigate() {
    await this.goto(this.url);
    await this.waitForPageLoad();
  }
  
  /**
   * Navigate with verification token
   */
  async navigateWithToken(token: string) {
    await this.goto(`${this.url}?token=${token}`);
    await this.waitForPageLoad();
  }
  
  /**
   * Request resend verification email
   */
  async resendVerification(email?: string) {
    if (email && await this.emailInput.isVisible({ timeout: 2000 })) {
      await this.fillField(this.emailInput, email);
    }
    
    if (await this.resendButton.isVisible({ timeout: 2000 })) {
      await this.resendButton.click();
    } else if (await this.submitResendButton.isVisible({ timeout: 2000 })) {
      await this.submitResendButton.click();
    }
    
    await this.waitForLoading();
  }
  
  /**
   * Check verification status
   */
  async getStatus(): Promise<'verifying' | 'success' | 'error' | 'expired' | 'unknown'> {
    if (await this.successMessage.isVisible({ timeout: 2000 }).catch(() => false)) return 'success';
    if (await this.expiredMessage.isVisible({ timeout: 2000 }).catch(() => false)) return 'expired';
    if (await this.errorMessage.isVisible({ timeout: 2000 }).catch(() => false)) return 'error';
    if (await this.verifyingMessage.isVisible({ timeout: 2000 }).catch(() => false)) return 'verifying';
    return 'unknown';
  }
  
  /**
   * Continue to dashboard after verification
   */
  async continueToDashboard() {
    await this.continueButton.click();
    await this.waitForURL(/dashboard/);
  }
  
  /**
   * Go to login page
   */
  async goToLogin() {
    await this.loginButton.click();
    await this.waitForURL(/login/);
  }
}
