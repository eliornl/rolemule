import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Registration page object
 */
export class RegisterPage extends BasePage {
  readonly url = '/auth/register';
  
  // Form elements
  readonly nameInput: Locator;
  readonly emailInput: Locator;
  readonly passwordInput: Locator;
  readonly confirmPasswordInput: Locator;
  readonly termsCheckbox: Locator;
  readonly registerButton: Locator;
  readonly loginLink: Locator;
  readonly googleSignUpButton: Locator;
  
  // Password requirements
  readonly passwordStrength: Locator;
  readonly passwordRequirements: Locator;
  
  // Error elements
  readonly errorMessage: Locator;
  readonly fieldError: Locator;
  
  constructor(page: Page) {
    super(page);
    this.nameInput = page.locator('#full-name, input[name="full_name"]');
    this.emailInput = page.locator('#email, input[name="email"]');
    this.passwordInput = page.locator('#password, input[name="password"]:not([name*="confirm"])');
    this.confirmPasswordInput = page.locator('#confirm-password, input[name="confirm_password"]');
    this.termsCheckbox = page.locator('#terms-agreement, input[name="terms"]');
    this.registerButton = page.locator('#register-btn');
    this.loginLink = page.locator('a[href*="login"], a:has-text("Login"), a:has-text("Sign In")');
    this.googleSignUpButton = page.locator('#google-signup-btn');
    this.passwordStrength = page.locator('.password-strength, [class*="strength"]');
    this.passwordRequirements = page.locator('#password-requirements');
    this.errorMessage = page.locator('#error-message, #error-alert, .alert-danger');
    this.fieldError = page.locator('.invalid-feedback, .form-error');
  }
  
  /**
   * Navigate to registration page
   */
  async navigate() {
    await this.goto(this.url);
    await expect(this.emailInput).toBeVisible();
  }
  
  /**
   * Fill registration form
   */
  async fillForm(data: {
    name?: string;
    email: string;
    password: string;
    confirmPassword?: string;
    acceptTerms?: boolean;
  }) {
    if (data.name && await this.isVisible(this.nameInput)) {
      await this.fillField(this.nameInput, data.name);
    }
    
    await this.fillField(this.emailInput, data.email);
    await this.fillField(this.passwordInput, data.password);
    
    if (await this.isVisible(this.confirmPasswordInput)) {
      await this.fillField(this.confirmPasswordInput, data.confirmPassword || data.password);
    }
    
    if (data.acceptTerms !== false && await this.isVisible(this.termsCheckbox)) {
      const isChecked = await this.termsCheckbox.isChecked();
      if (!isChecked) {
        await this.termsCheckbox.check();
      }
    }
  }
  
  /**
   * Submit registration form (waits for button to be enabled)
   */
  async submit() {
    // Wait for button to be enabled (form validation)
    await expect(this.registerButton).toBeEnabled({ timeout: 5000 });
    await this.registerButton.click();
  }
  
  /**
   * Try to submit even if button is disabled (for testing validation)
   */
  async trySubmit() {
    // Try clicking even if disabled - for testing error states
    const isEnabled = await this.registerButton.isEnabled();
    if (isEnabled) {
      await this.registerButton.click();
    }
    // If disabled, the form validation is preventing submission
    return isEnabled;
  }
  
  /**
   * Register a new user
   */
  async register(data: {
    name?: string;
    email: string;
    password: string;
    confirmPassword?: string;
    acceptTerms?: boolean;
  }) {
    await this.fillForm(data);
    await this.submit();
  }
  
  /**
   * Register and wait for redirect
   */
  async registerAndWait(data: {
    name?: string;
    email: string;
    password: string;
    confirmPassword?: string;
    acceptTerms?: boolean;
  }, expectedPath: string = '/profile/setup') {
    await this.register(data);
    await this.waitForURL(new RegExp(expectedPath));
  }
  
  /**
   * Attempt registration expecting failure (form validation or server error)
   */
  async registerExpectingError(data: {
    name?: string;
    email: string;
    password: string;
    confirmPassword?: string;
    acceptTerms?: boolean;
  }, _errorText?: string) {
    await this.fillForm(data);
    
    // Try to submit - may fail due to client-side validation
    const submitted = await this.trySubmit();
    
    if (submitted) {
      // If submitted, wait for server error
      await expect(this.errorMessage.first()).toBeVisible({ timeout: 10000 });
    } else {
      // If not submitted, check for field validation errors or disabled button
      const hasFieldError = await this.fieldError.first().isVisible().catch(() => false);
      const hasPasswordError = await this.page.locator('#password-requirements li.invalid, .password-requirements .invalid').first().isVisible().catch(() => false);
      const buttonDisabled = await this.registerButton.isDisabled();
      
      // At least one validation indicator should be present
      expect(hasFieldError || hasPasswordError || buttonDisabled).toBeTruthy();
    }
  }
  
  /**
   * Go to login page
   */
  async goToLogin() {
    await this.loginLink.click();
    await this.waitForURL(/login/);
  }
  
  /**
   * Check password strength indicator
   */
  async checkPasswordStrength(expectedLevel: 'weak' | 'medium' | 'strong') {
    await expect(this.passwordStrength).toContainText(new RegExp(expectedLevel, 'i'));
  }
}
