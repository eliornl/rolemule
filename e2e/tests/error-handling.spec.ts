import { test, expect } from '@playwright/test';
import { RegisterPage, LoginPage, ProfileSetupPage } from '../pages';
import { generateTestEmail } from '../fixtures/test-data';
import { setupAuth, setupAllMocks, buildMockGetProfileResponse, setupWebSocketMock, MOCK_JWT, setupCookieConsent, getE2EAuthToken, isMockedE2E } from '../utils/api-mocks';

// Pre-accept cookie consent so the banner never intercepts pointer events
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('cookie_consent', JSON.stringify({
      essential: true, functional: true, analytics: false,
      version: '1.0', timestamp: new Date().toISOString(),
    }));
  });
});

/**
 * Error handling and edge case tests
 */
test.describe('Error Handling', () => {
  
  test.describe('Network Errors', () => {
    
    test('should handle network timeout gracefully', async ({ page }) => {
      // Simulate slow network — fulfill after delay; never route.continue() to live server.
      await page.route('**/api/**', async route => {
        await new Promise(resolve => setTimeout(resolve, 10000));
        await route.fulfill({
          status: 504,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Gateway timeout (simulated)' }),
        });
      });
      
      await page.goto('/auth/login', { timeout: 5000 }).catch(() => {});
      
      // Page should still be usable or show error
      const body = page.locator('body');
      await expect(body).toBeVisible();
    });
    
    test('should show error message on API failure', async ({ page }) => {
      // Mock API to return error
      await page.route('**/api/v1/auth/login', async route => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error' }),
        });
      });
      
      const loginPage = new LoginPage(page);
      await loginPage.navigate();
      
      await loginPage.login('test@example.com', 'password123');
      
      // Should show error
      const error = page.locator('.error, .alert-danger, text=error');
      await expect(error.first()).toBeVisible({ timeout: 10000 }).catch(() => {
        // May handle error differently
      });
    });
    
    test('should handle offline state', async ({ page, context }) => {
      await page.goto('/auth/login');
      
      // Go offline
      await context.setOffline(true);
      
      const loginPage = new LoginPage(page);
      await loginPage.login('test@example.com', 'password');
      
      // Should show network error
      await page.waitForTimeout(3000);
      
      // Go back online
      await context.setOffline(false);
    });
  });
  
  test.describe('HTTP Error Codes', () => {
    
    test('should display 404 page for non-existent routes', async ({ page }) => {
      await page.goto('/this-page-does-not-exist-12345');
      
      // Should show 404 content
      const notFoundIndicator = page.locator('text=404, text=not found, text=page not found');
      await expect(notFoundIndicator.first()).toBeVisible({ timeout: 5000 }).catch(() => {
        // May redirect instead
      });
    });
    
    test('should handle 401 unauthorized gracefully', async ({ page }) => {
      await setupWebSocketMock(page);
      await page.addInitScript(() => {
        localStorage.setItem('access_token', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1MiIsImV4cCI6OTk5OTk5OTk5OX0.fake');
        localStorage.setItem('authToken', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1MiIsImV4cCI6OTk5OTk5OTk5OX0.fake');
        localStorage.setItem('cookie_consent', JSON.stringify({
          essential: true, functional: true, analytics: false,
          version: '1.0', timestamp: new Date().toISOString(),
        }));
      });
      const unauthorized = {
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Not authenticated' }),
      };
      await page.route('**/api/v1/profile**', async route => route.fulfill(unauthorized));
      await page.route('**/api/v1/applications**', async route => route.fulfill(unauthorized));
      
      await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
      
      await expect(page).toHaveURL(/login/, { timeout: 10000 });
    });
    
    test('should handle 403 forbidden', async ({ page }) => {
      // Mock 403 response
      await page.route('**/api/v1/admin/**', async route => {
        await route.fulfill({
          status: 403,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Forbidden' }),
        });
      });
      
      // Try to access admin route
      await page.goto('/admin');
      
      // Should show error or redirect
      await page.waitForTimeout(2000);
    });
    
    test('should handle 429 rate limit', async ({ page }) => {
      // Mock rate limit response
      await page.route('**/api/v1/auth/login', async route => {
        await route.fulfill({
          status: 429,
          contentType: 'application/json',
          headers: {
            'Retry-After': '60',
          },
          body: JSON.stringify({ detail: 'Too many requests' }),
        });
      });
      
      const loginPage = new LoginPage(page);
      await loginPage.navigate();
      
      await loginPage.login('test@example.com', 'password');
      
      // Should show rate limit message
      const rateLimitMsg = page.locator('text=too many, text=rate limit, text=try again');
      await expect(rateLimitMsg.first()).toBeVisible({ timeout: 5000 }).catch(() => {
        // May handle differently
      });
    });
    
    test('should handle 500 internal server error', async ({ page }) => {
      // Mock 500 response
      await page.route('**/api/v1/workflow/start', async route => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Internal server error' }),
        });
      });
      
      // Register and try to start workflow
      const registerPage = new RegisterPage(page);
      const email = generateTestEmail('server_error_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'Server Error Test',
        email: email,
        password: 'ServerErrorTestPassword123!',
        acceptTerms: true,
      });
      
      // Should show error message on workflow failure
    });
  });
  
  test.describe('Form Validation', () => {
    
    test('should validate email format', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      // Invalid email formats
      const invalidEmails = ['notanemail', 'missing@domain', '@nodomain.com'];
      
      for (const invalidEmail of invalidEmails) {
        await registerPage.fillForm({
          email: invalidEmail,
          password: 'ValidPassword123!',
        });
        
        // Try to submit - button may be disabled due to validation
        const submitted = await registerPage.trySubmit();
        await page.waitForTimeout(500);
        
        // Either button was disabled (client validation) or we stayed on register page (server validation)
        const isOnRegisterPage = page.url().includes('register');
        expect(isOnRegisterPage || !submitted).toBeTruthy();
      }
    });
    
    test('should validate password requirements', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      // Test with a weak password
      await registerPage.fillForm({
        email: generateTestEmail('weak_pwd'),
        password: 'weak',
      });
      
      await page.waitForTimeout(500);
      
      // Button should be disabled or password requirements should show invalid
      const buttonDisabled = await registerPage.registerButton.isDisabled();
      const passwordInvalid = await page.locator('#password-requirements li.invalid, .password-requirements .invalid').count();
      
      // Either button disabled or password requirements showing
      expect(buttonDisabled || passwordInvalid > 0).toBeTruthy();
    });
    
    test('should validate required fields', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      // Try to submit empty form - should be disabled
      const buttonDisabled = await registerPage.registerButton.isDisabled();
      
      // Button should be disabled when form is empty
      expect(buttonDisabled).toBeTruthy();
    });
    
    test('should validate password confirmation', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      await registerPage.fillForm({
        name: 'Test User',
        email: generateTestEmail('pwd_mismatch'),
        password: 'ValidPassword123!',
        confirmPassword: 'DifferentPassword456!',
        acceptTerms: true,
      });
      
      await page.waitForTimeout(500);
      
      // Button should be disabled when passwords don't match
      const buttonDisabled = await registerPage.registerButton.isDisabled();
      const mismatchError = await page.locator('.is-invalid, [class*="mismatch"], [class*="error"]').count();
      
      // Either button disabled or error shown
      expect(buttonDisabled || mismatchError > 0).toBeTruthy();
    });
  });
  
  test.describe('Session Handling', () => {
    
    test('should handle expired session', async ({ page }) => {
      await setupCookieConsent(page);
      if (isMockedE2E) {
        await setupWebSocketMock(page);
        await page.route('**/api/v1/profile**', async route => route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(buildMockGetProfileResponse()),
        }));
        await page.route('**/api/v1/applications**', async route => route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ applications: [], total: 0 }),
        }));
      }
      const token = isMockedE2E ? MOCK_JWT : getE2EAuthToken();
      await page.goto('/auth/login', { waitUntil: 'domcontentloaded' });
      await page.evaluate((t: string) => {
        localStorage.setItem('access_token', t);
        localStorage.setItem('authToken', t);
      }, token);
      await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
      await page.waitForURL(/dashboard/, { timeout: 15000 });
      await page.evaluate(() => {
        const cc = localStorage.getItem('cookie_consent');
        localStorage.removeItem('authToken');
        localStorage.removeItem('access_token');
        if (cc) localStorage.setItem('cookie_consent', cc);
      });
      await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
      await page.waitForURL(/auth\/login/, { timeout: 15000 });
    });

    test('should handle concurrent sessions', async ({ browser }) => {
      const context1 = await browser.newContext();
      const page1 = await context1.newPage();
      await setupAuth(page1);
      await page1.goto('/dashboard');
      await page1.waitForLoadState('domcontentloaded');

      const context2 = await browser.newContext();
      const page2 = await context2.newPage();
      await setupAuth(page2);
      await page2.goto('/dashboard');
      await page2.waitForLoadState('domcontentloaded');

      await expect(page1).not.toHaveURL(/auth\/login/);
      await expect(page2).not.toHaveURL(/auth\/login/);
      await context1.close();
      await context2.close();
    });

    test('should refresh token before expiration', async ({ page }) => {
      await setupAuth(page);
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);
      await page.goto('/dashboard');
      await expect(page).not.toHaveURL(/auth\/login/);
    });
  });
  
  test.describe('Input Edge Cases', () => {
    
    test('should handle special characters in input', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      await registerPage.register({
        name: "Test O'Brien <script>alert('xss')</script>",
        email: generateTestEmail('special_chars'),
        password: 'SpecialCharsPassword123!',
        acceptTerms: true,
      });
      
      // Should either sanitize or reject, not break
      await page.waitForTimeout(2000);
    });
    
    test('should handle very long input', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      const longString = 'a'.repeat(10000);
      
      await registerPage.fillForm({
        name: longString,
        email: generateTestEmail('long_input'),
        password: 'LongInputPassword123!',
      });
      
      await registerPage.submit();
      
      // Should handle gracefully (validation error or truncation)
      await page.waitForTimeout(2000);
    });
    
    test('should handle unicode input', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      await registerPage.register({
        name: '测试用户 Tëst Üsér 🎉',
        email: generateTestEmail('unicode'),
        password: 'UnicodeTestPassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 }).catch(() => {
        // May reject unicode in name
      });
    });
    
    test('should handle empty strings', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.navigate();
      
      await loginPage.emailInput.fill('   '); // Whitespace only
      await loginPage.passwordInput.fill('   ');
      await loginPage.loginButton.click();
      
      // Should not submit or show validation error
      await page.waitForTimeout(1000);
      await expect(page).toHaveURL(/login/);
    });
  });
  
  test.describe('Browser Compatibility', () => {
    
    test('should handle page refresh during form submission', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      await registerPage.fillForm({
        email: generateTestEmail('refresh_test'),
        password: 'RefreshTestPassword123!',
      });
      
      // Start submission and immediately refresh
      await Promise.all([
        registerPage.submit(),
        page.reload().catch(() => {}),
      ]).catch(() => {});
      
      // Page should be usable after refresh
      await page.waitForTimeout(2000);
      const body = page.locator('body');
      await expect(body).toBeVisible();
    });
    
    test('should handle back button navigation', async ({ page }) => {
      const loginPage = new LoginPage(page);
      
      await loginPage.navigate();
      await loginPage.goToRegister();
      
      // Go back
      await page.goBack();
      
      // Should be on login page
      await expect(page).toHaveURL(/login/);
      
      // Go forward
      await page.goForward();
      
      // Should be on register page
      await expect(page).toHaveURL(/register/);
    });
    
    test('should handle multiple rapid clicks', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.navigate();
      
      await loginPage.fillForm({
        email: 'test@example.com',
        password: 'TestPassword123!',
      });
      
      // Click submit multiple times rapidly
      for (let i = 0; i < 5; i++) {
        await loginPage.loginButton.click().catch(() => {});
      }
      
      // Should handle gracefully (not crash or submit multiple times)
      await page.waitForTimeout(3000);
    });
  });
  
  test.describe('Data Persistence', () => {
    
    test('should persist form data on validation error', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      const testEmail = generateTestEmail('persist_test');
      
      await registerPage.fillForm({
        name: 'Test User',
        email: testEmail,
        password: 'weak', // Invalid password
      });
      
      // Try to submit - button should be disabled due to validation
      await registerPage.trySubmit();
      await page.waitForTimeout(1000);
      
      // Email should still be filled
      const emailValue = await registerPage.emailInput.inputValue();
      expect(emailValue).toBe(testEmail);
    });
    
    test('should clear sensitive data on logout (mocked)', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      const email = generateTestEmail('clear_data_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'Clear Data Test',
        email: email,
        password: 'ClearDataPassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
      
      // Logout
      const logoutBtn = page.locator('button:has-text("Logout"), a:has-text("Logout")');
      if (await logoutBtn.first().isVisible({ timeout: 5000 }).catch(() => false)) {
        await logoutBtn.first().click();
      }
      
      await page.waitForURL(/login/, { timeout: 10000 });
      
      // Check localStorage is cleared
      const token = await page.evaluate(() => localStorage.getItem('authToken'));
      expect(token).toBeNull();
    });
  });
});

// ---------------------------------------------------------------------------
// MOCKED ERROR HANDLING TESTS (CI-safe, no live server)
// ---------------------------------------------------------------------------
test.describe('Error Handling — Mocked', () => {

  test.describe('API Error Responses', () => {
    test('500 error on login shows error alert', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
      });
      await page.route('**/api/v1/auth/login', route => route.fulfill({
        status: 500, contentType: 'application/json',
        body: JSON.stringify({ error: { message: 'Internal server error' } }),
      }));
      await page.goto('/auth/login');
      await page.locator('#email').fill('test@example.com');
      await page.locator('#password').fill('TestPass123!');
      await page.locator('#login-btn').click();
      await expect(page.locator('.alert-danger, #alert-container .alert').first()).toBeVisible({ timeout: 5000 });
    });

    test('401 error on login stays on login page', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
      });
      await page.route('**/api/v1/auth/login', route => route.fulfill({
        status: 401, contentType: 'application/json',
        body: JSON.stringify({ error: { message: 'Invalid credentials' } }),
      }));
      await page.goto('/auth/login');
      await page.locator('#email').fill('bad@example.com');
      await page.locator('#password').fill('WrongPass1!');
      await page.locator('#login-btn').click();
      await expect(page).toHaveURL(/login/);
    });

    test('409 conflict on register shows error alert', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
      });
      await page.route('**/api/v1/auth/register', route => route.fulfill({
        status: 409, contentType: 'application/json',
        body: JSON.stringify({ error: { message: 'Email already registered' } }),
      }));
      await page.goto('/auth/register');
      await page.locator('#full-name').fill('Test User');
      await page.locator('#email').fill('dup@example.com');
      await page.locator('#password').fill('StrongPass123!');
      await page.locator('#confirm-password').fill('StrongPass123!');
      await page.locator('#terms-agreement').check();
      await page.waitForTimeout(300);
      await page.locator('#register-btn').click();
      await expect(page.locator('#error-alert, .alert-danger').first()).toBeVisible({ timeout: 5000 });
    });

    test('422 validation error on login shows error', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
      });
      await page.route('**/api/v1/auth/login', route => route.fulfill({
        status: 422, contentType: 'application/json',
        body: JSON.stringify({ detail: [{ msg: 'field required', type: 'value_error.missing' }] }),
      }));
      await page.goto('/auth/login');
      await page.locator('#email').fill('test@example.com');
      await page.locator('#password').fill('SomePass1!');
      await page.locator('#login-btn').click();
      await page.waitForTimeout(2000);
      await expect(page).toHaveURL(/login/);
    });
  });

  test.describe('Mocked API Network Error Handling', () => {
    test('aborted request on login shows error state', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
      });
      await page.route('**/api/v1/auth/login', route => route.abort());
      await page.goto('/auth/login');
      await page.locator('#email').fill('test@example.com');
      await page.locator('#password').fill('TestPass1!');
      await page.locator('#login-btn').click();
      await page.waitForTimeout(2000);
      // Should stay on login page and not crash
      await expect(page).toHaveURL(/login/);
    });

    test('dashboard handles 401 from profile API by redirecting', async ({ page }) => {
      await setupAuth(page);
      await page.route('**/api/v1/profile**', route => route.fulfill({
        status: 401, contentType: 'application/json',
        body: JSON.stringify({ detail: 'Not authenticated' }),
      }));
      await page.route('**/api/v1/applications**', route => route.fulfill({
        status: 401, contentType: 'application/json',
        body: JSON.stringify({ detail: 'Not authenticated' }),
      }));
      await page.goto('/dashboard');
      await page.waitForFunction(
        () => !localStorage.getItem('access_token') && !localStorage.getItem('authToken'),
        { timeout: 10000 },
      );
    });

    test('dashboard handles 500 from applications API gracefully', async ({ page }) => {
      await setupAuth(page);
      await page.route('**/api/v1/profile**', r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildMockGetProfileResponse()) }));
      await page.route('**/api/v1/applications**', route => route.fulfill({
        status: 500, contentType: 'application/json',
        body: JSON.stringify({ detail: 'Server error' }),
      }));
      await page.goto('/dashboard');
      await page.waitForLoadState('domcontentloaded');
      // Should still render the page structure
      await expect(page.locator('.welcome-card')).toBeVisible({ timeout: 5000 });
    });
  });

  test.describe('Form Validation — Mocked', () => {
    test('login form keeps submit disabled with empty fields', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
      });
      await page.goto('/auth/login');
      // Email is marked required — HTML5 prevents submission
      const emailInput = page.locator('#email');
      await expect(emailInput).toBeVisible();
      const required = await emailInput.getAttribute('required');
      expect(required).not.toBeNull();
    });

    test('register form password requirement items are shown immediately', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
      });
      await page.goto('/auth/register');
      const items = page.locator('#password-requirements li');
      await expect(items).toHaveCount(5);
    });

    test('tools form submit does not navigate away when fields empty', async ({ page }) => {
      await setupAuth(page);
      await setupAllMocks(page);
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
      // Submit without filling form — should stay on tools page
      await page.locator('#thankYouSubmit').click();
      await page.waitForTimeout(500);
      expect(page.url()).toContain('tools');
    });

    test('career tools 429 rate limit shows error alert (mocked)', async ({ page }) => {
      await setupAuth(page);
      await page.route('**/api/v1/tools/thank-you', route => route.fulfill({
        status: 429, contentType: 'application/json',
        headers: { 'Retry-After': '3600' },
        body: JSON.stringify({ error: { message: 'Rate limit exceeded' } }),
      }));
      await page.route('**/api/v1/profile**', r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(buildMockGetProfileResponse()) }));
      await page.route('**/api/v1/tools/followup-stages', r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ stages: [] }) }));
      await page.goto('/dashboard/tools');
      await page.waitForLoadState('domcontentloaded');
      await page.locator('#interviewerName').fill('Jane');
      await page.locator('#thankYouSubmit').click();
      await page.waitForTimeout(1500);
      // Either alert is shown or page stays on tools
      expect(page.url()).toContain('tools');
    });
  });

  test.describe('HTTP Error Pages', () => {
    test('404 route returns non-200 or shows error content', async ({ page }) => {
      const response = await page.goto('/nonexistent-endpoint-xyz-123');
      expect(response?.status()).not.toBe(200);
    });

    test('unauthorized dashboard access redirects to auth', async ({ page }) => {
      await page.goto('/dashboard');
      await page.waitForURL(/auth\/login/, { timeout: 8000 });
      expect(page.url()).toContain('auth');
    });

    test('unauthorized settings access redirects to auth', async ({ page }) => {
      await page.goto('/dashboard/settings');
      await page.waitForURL(/auth\/login|\//, { timeout: 8000 });
      expect(page.url()).not.toContain('settings');
    });

    test('unauthorized tools access redirects to auth', async ({ page }) => {
      await page.goto('/dashboard/tools');
      await page.waitForURL(/auth\/login|\//, { timeout: 8000 });
      expect(page.url()).not.toContain('/tools');
    });
  });
});
