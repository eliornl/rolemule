/**
 * Registration page — form validation, email verification redirect, Google OAuth.
 */
import { getApiBase } from '../shared/auth';
import type { RegisterResponse } from '../shared/auth-api';
import {
  fetchOAuthStatus,
  parseOAuthErrorMessages,
  showOAuthButtons,
  storeRegisterAuthData,
} from '../shared/auth-session';
import { stripHtmlForAlert } from '../shared/dom-security';
import { validateRegisterEmail } from '../shared/auth-validation';
import { validateStrongPassword } from '../shared/auth-ui';

const REDIRECT_DELAY = 2000;

const PASSWORD_REQ = {
  MIN_LENGTH: 8,
  UPPERCASE: /[A-Z]/,
  LOWERCASE: /[a-z]/,
  NUMBER: /\d/,
  SPECIAL: /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/,
};

interface RegisterDom {
  registerForm: HTMLFormElement | null;
  registerBtn: HTMLButtonElement | null;
  registerText: HTMLElement | null;
  loadingSpinner: HTMLElement | null;
  errorAlert: HTMLElement | null;
  successAlert: HTMLElement | null;
  errorMessage: HTMLElement | null;
  successMessage: HTMLElement | null;
  fullNameField: HTMLInputElement | null;
  emailField: HTMLInputElement | null;
  passwordField: HTMLInputElement | null;
  confirmPasswordField: HTMLInputElement | null;
  termsCheckbox: HTMLInputElement | null;
  passwordToggle: HTMLElement | null;
  confirmPasswordToggle: HTMLElement | null;
  reqLength: HTMLElement | null;
  reqUppercase: HTMLElement | null;
  reqLowercase: HTMLElement | null;
  reqNumber: HTMLElement | null;
  reqSpecial: HTMLElement | null;
}

const DOM: RegisterDom = {
  registerForm: document.getElementById('registerForm') as HTMLFormElement | null,
  registerBtn: document.getElementById('register-btn') as HTMLButtonElement | null,
  registerText: document.querySelector('.register-text'),
  loadingSpinner: document.querySelector('.loading-spinner'),
  errorAlert: document.getElementById('error-alert'),
  successAlert: document.getElementById('success-alert'),
  errorMessage: document.getElementById('error-message'),
  successMessage: document.getElementById('success-message'),
  fullNameField: document.getElementById('full-name') as HTMLInputElement | null,
  emailField: document.getElementById('email') as HTMLInputElement | null,
  passwordField: document.getElementById('password') as HTMLInputElement | null,
  confirmPasswordField: document.getElementById('confirm-password') as HTMLInputElement | null,
  termsCheckbox: document.getElementById('terms-agreement') as HTMLInputElement | null,
  passwordToggle: document.getElementById('password-toggle'),
  confirmPasswordToggle: document.getElementById('confirm-password-toggle'),
  reqLength: document.getElementById('req-length'),
  reqUppercase: document.getElementById('req-uppercase'),
  reqLowercase: document.getElementById('req-lowercase'),
  reqNumber: document.getElementById('req-number'),
  reqSpecial: document.getElementById('req-special'),
};

let passwordTimer = 0;
let emailTimer = 0;
let nameTimer = 0;

function showError(message: string): void {
  if (!DOM.errorMessage || !DOM.errorAlert || !DOM.successAlert) return;
  DOM.errorMessage.textContent = message;
  DOM.errorAlert.classList.remove('d-none');
  DOM.successAlert.classList.add('d-none');
  DOM.errorAlert.setAttribute('aria-live', 'polite');
}

function showSuccess(message: string): void {
  if (!DOM.successMessage || !DOM.successAlert || !DOM.errorAlert) return;
  DOM.successMessage.textContent = message;
  DOM.successAlert.classList.remove('d-none');
  DOM.errorAlert.classList.add('d-none');
  DOM.successAlert.setAttribute('aria-live', 'polite');
}

function showInfo(message: string): void {
  if (!DOM.successMessage || !DOM.successAlert || !DOM.errorAlert) return;
  DOM.successMessage.textContent = message;
  DOM.successAlert.classList.remove('d-none', 'alert-success');
  DOM.successAlert.classList.add('alert-info');
  DOM.errorAlert.classList.add('d-none');
  DOM.successAlert.setAttribute('aria-live', 'polite');
  window.setTimeout(() => {
    DOM.successAlert?.classList.remove('alert-info');
    DOM.successAlert?.classList.add('alert-success');
  }, 5000);
}

function hideAlerts(): void {
  DOM.errorAlert?.classList.add('d-none');
  DOM.successAlert?.classList.add('d-none');
}

function setLoading(loading: boolean): void {
  if (!DOM.registerText || !DOM.loadingSpinner || !DOM.registerBtn) return;
  if (loading) {
    DOM.registerText.style.display = 'none';
    DOM.loadingSpinner.style.display = 'inline';
    DOM.registerBtn.disabled = true;
    DOM.registerBtn.setAttribute('aria-busy', 'true');
  } else {
    DOM.registerText.style.display = 'inline';
    DOM.loadingSpinner.style.display = 'none';
    DOM.registerBtn.setAttribute('aria-busy', 'false');
    updateSubmitButton();
  }
}

function getAuthToken(): string | null {
  const urlParams = new URLSearchParams(window.location.search);
  const urlToken = urlParams.get('token') || urlParams.get('access_token');
  if (urlToken) return urlToken;
  return localStorage.getItem('access_token') || localStorage.getItem('authToken');
}

function isAuthenticated(): boolean {
  return getAuthToken() !== null;
}

function validateFullName(name: string): boolean {
  const isValid = name.trim().length >= 2;
  const container = document.getElementById('fullname-container');
  if (!DOM.fullNameField || !container) return isValid;

  if (name.length > 0) {
    DOM.fullNameField.classList.toggle('is-valid', isValid);
    DOM.fullNameField.classList.toggle('is-invalid', !isValid);
    container.classList.toggle('email-validation-valid', isValid);
    container.classList.remove('email-validation-invalid');
  } else {
    DOM.fullNameField.classList.remove('is-valid', 'is-invalid');
    container.classList.remove('email-validation-valid', 'email-validation-invalid');
  }
  return isValid;
}

function validatePassword(password: string): boolean {
  const req = {
    length: password.length >= PASSWORD_REQ.MIN_LENGTH,
    uppercase: PASSWORD_REQ.UPPERCASE.test(password),
    lowercase: PASSWORD_REQ.LOWERCASE.test(password),
    number: PASSWORD_REQ.NUMBER.test(password),
    special: PASSWORD_REQ.SPECIAL.test(password),
  };
  if (DOM.reqLength) DOM.reqLength.className = req.length ? 'valid' : 'invalid';
  if (DOM.reqUppercase) DOM.reqUppercase.className = req.uppercase ? 'valid' : 'invalid';
  if (DOM.reqLowercase) DOM.reqLowercase.className = req.lowercase ? 'valid' : 'invalid';
  if (DOM.reqNumber) DOM.reqNumber.className = req.number ? 'valid' : 'invalid';
  if (DOM.reqSpecial) DOM.reqSpecial.className = req.special ? 'valid' : 'invalid';

  const isValid = Object.values(req).every((v) => v);
  const container = document.getElementById('password-container');
  if (!DOM.passwordField || !container) return isValid;

  if (password.length > 0) {
    DOM.passwordField.classList.toggle('is-valid', isValid);
    DOM.passwordField.classList.toggle('is-invalid', !isValid);
    container.classList.toggle('email-validation-valid', isValid);
    container.classList.remove('email-validation-invalid');
  } else {
    DOM.passwordField.classList.remove('is-valid', 'is-invalid');
    container.classList.remove('email-validation-valid', 'email-validation-invalid');
  }
  return isValid;
}

function validatePasswordMatch(): boolean {
  if (!DOM.passwordField || !DOM.confirmPasswordField) return false;
  const password = DOM.passwordField.value;
  const confirmPassword = DOM.confirmPasswordField.value;
  const container = document.getElementById('confirm-password-container');
  if (!container) return false;

  if (confirmPassword.length > 0) {
    const matches = password === confirmPassword;
    DOM.confirmPasswordField.classList.toggle('is-valid', matches);
    DOM.confirmPasswordField.classList.toggle('is-invalid', !matches);
    container.classList.toggle('email-validation-valid', matches);
    container.classList.remove('email-validation-invalid');
    return matches;
  }
  DOM.confirmPasswordField.classList.remove('is-valid', 'is-invalid');
  container.classList.remove('email-validation-valid', 'email-validation-invalid');
  return false;
}

function updateSubmitButton(): void {
  if (
    !DOM.passwordField ||
    !DOM.confirmPasswordField ||
    !DOM.fullNameField ||
    !DOM.emailField ||
    !DOM.termsCheckbox ||
    !DOM.registerBtn
  ) {
    return;
  }
  const pw = DOM.passwordField.value;
  const cpw = DOM.confirmPasswordField.value;
  DOM.registerBtn.disabled = !(
    validatePassword(pw) &&
    pw === cpw &&
    cpw.length > 0 &&
    DOM.termsCheckbox.checked &&
    DOM.fullNameField.value.length > 0 &&
    DOM.emailField.value.length > 0
  );
}

function togglePasswordVisibility(field: HTMLInputElement, toggle: HTMLElement): void {
  const icon = toggle.querySelector('i');
  if (!icon) return;
  if (field.type === 'password') {
    field.type = 'text';
    icon.classList.replace('fa-eye', 'fa-eye-slash');
    toggle.setAttribute('aria-label', 'Hide password');
  } else {
    field.type = 'password';
    icon.classList.replace('fa-eye-slash', 'fa-eye');
    toggle.setAttribute('aria-label', 'Show password');
  }
}

function renderRegisterEmailFeedback(
  input: HTMLInputElement,
  emailResult: ReturnType<typeof validateRegisterEmail>,
): void {
  const feedbackEl = document.querySelector('#email-feedback') as HTMLElement | null;
  const container = input.closest('.email-validation-container') as HTMLElement | null;
  if (!container) return;
  container.classList.remove('email-validation-valid', 'email-validation-invalid');

  const email = input.value.trim();
  if (email.length === 0) {
    input.classList.remove('is-valid', 'is-invalid');
    feedbackEl?.classList.remove('d-block');
    return;
  }

  if (emailResult.isValid) {
    input.classList.remove('is-invalid');
    input.classList.add('is-valid');
    container.classList.add('email-validation-valid');
    if (feedbackEl) {
      feedbackEl.innerHTML = '';
      feedbackEl.classList.remove('d-block');
    }
  } else {
    input.classList.remove('is-valid');
    input.classList.add('is-invalid');
    container.classList.add('email-validation-invalid');
    if (feedbackEl) {
      feedbackEl.innerHTML = '';
      if (emailResult.suggestion) {
        feedbackEl.appendChild(document.createTextNode(`${emailResult.message} `));
        const link = document.createElement('a');
        link.className = 'suggestion-link';
        link.href = '#';
        link.textContent = emailResult.suggestion;
        link.addEventListener('click', (e) => {
          e.preventDefault();
          if (DOM.emailField) {
            DOM.emailField.value = emailResult.suggestion ?? '';
            DOM.emailField.dispatchEvent(new Event('input'));
          }
        });
        feedbackEl.appendChild(link);
        feedbackEl.appendChild(document.createTextNode('?'));
      } else {
        feedbackEl.textContent = emailResult.message;
      }
      feedbackEl.classList.add('d-block');
    }
  }
}

function parseRegisterError(result: RegisterResponse | string): string {
  if (typeof result === 'string') return result;
  if (Array.isArray(result.errors) && result.errors[0]) {
    return String(result.errors[0]);
  }
  return (
    result.detail ||
    result.message ||
    result.error ||
    'Registration failed. Please try again.'
  );
}

async function handleRegistrationSubmit(e: Event): Promise<void> {
  e.preventDefault();
  hideAlerts();
  setLoading(true);
  if (!DOM.emailField || !DOM.registerForm) {
    setLoading(false);
    return;
  }

  const emailValue = DOM.emailField.value.trim();
  const emailResult = validateRegisterEmail(emailValue);
  if (!emailResult.isValid) {
    showError(stripHtmlForAlert(emailResult.message));
    DOM.emailField.classList.add('is-invalid');
    setLoading(false);
    return;
  }

  const formData = new FormData(DOM.registerForm);
  const registerData = {
    full_name: formData.get('full_name'),
    email: formData.get('email'),
    password: formData.get('password'),
    confirm_password: formData.get('confirm_password'),
  };

  try {
    const response = await fetch(`${getApiBase()}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(registerData),
    });

    let result: RegisterResponse;
    try {
      result = (await response.json()) as RegisterResponse;
    } catch {
      throw new Error('Invalid response from server');
    }

    if (response.ok) {
      if (result.user?.email_verified) {
        storeRegisterAuthData(result);
        showSuccess('Account created! Redirecting...');
        window.setTimeout(() => {
          window.location.href = '/profile/setup';
        }, REDIRECT_DELAY);
      } else {
        localStorage.setItem('pendingVerificationEmail', DOM.emailField.value.trim().toLowerCase());
        showSuccess('Account created! Check your email for the verification code...');
        window.setTimeout(() => {
          window.location.href = `/auth/verify-email?email=${encodeURIComponent(
            DOM.emailField!.value.trim().toLowerCase(),
          )}`;
        }, REDIRECT_DELAY);
      }
    } else {
      showError(parseRegisterError(result));
    }
  } catch (error) {
    console.error('Registration error:', error);
    showError('Connection error. Please check your internet connection and try again.');
  } finally {
    setLoading(false);
  }
}

function setupEventListeners(): void {
  if (
    !DOM.passwordField ||
    !DOM.confirmPasswordField ||
    !DOM.termsCheckbox ||
    !DOM.fullNameField ||
    !DOM.emailField ||
    !DOM.passwordToggle ||
    !DOM.confirmPasswordToggle ||
    !DOM.registerForm
  ) {
    return;
  }

  DOM.passwordField.addEventListener('input', () => {
    window.clearTimeout(passwordTimer);
    passwordTimer = window.setTimeout(() => {
      validatePassword(DOM.passwordField!.value);
      if (DOM.confirmPasswordField!.value.length > 0) validatePasswordMatch();
      updateSubmitButton();
    }, 300);
  });

  DOM.confirmPasswordField.addEventListener('input', () => {
    validatePasswordMatch();
    updateSubmitButton();
  });

  DOM.termsCheckbox.addEventListener('change', updateSubmitButton);

  DOM.fullNameField.addEventListener('input', () => {
    window.clearTimeout(nameTimer);
    nameTimer = window.setTimeout(() => {
      validateFullName(DOM.fullNameField!.value);
      updateSubmitButton();
    }, 300);
  });

  DOM.emailField.addEventListener('input', function (this: HTMLInputElement) {
    window.clearTimeout(emailTimer);
    emailTimer = window.setTimeout(() => {
      const emailResult = validateRegisterEmail(this.value.trim());
      renderRegisterEmailFeedback(this, emailResult);
      updateSubmitButton();
    }, 300);
  });

  DOM.passwordToggle.addEventListener('click', () => {
    if (DOM.passwordField) togglePasswordVisibility(DOM.passwordField, DOM.passwordToggle!);
  });

  DOM.confirmPasswordToggle.addEventListener('click', () => {
    if (DOM.confirmPasswordField) {
      togglePasswordVisibility(DOM.confirmPasswordField, DOM.confirmPasswordToggle!);
    }
  });

  DOM.registerForm.addEventListener('submit', (e) => {
    void handleRegistrationSubmit(e);
  });
}

function checkOAuthErrors(): void {
  const urlParams = new URLSearchParams(window.location.search);
  const error = urlParams.get('error');
  const message = urlParams.get('message');
  if (!error) return;
  showError(parseOAuthErrorMessages(error, message));
  window.history.replaceState({}, document.title, window.location.pathname);
}

function handleGoogleSignup(): void {
  window.location.href = `${getApiBase()}/auth/google?redirect_url=/profile/setup`;
}

async function checkGoogleOAuthStatus(): Promise<void> {
  if (await fetchOAuthStatus()) {
    showOAuthButtons('oauth-divider', 'google-signup-btn');
  }
}

function initializeRegistrationPage(): void {
  try {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('error') === 'user_not_found') {
      ['authToken', 'access_token', 'token_type', 'user_data', 'profile_completed'].forEach(
        (k) => localStorage.removeItem(k),
      );
      showInfo('Your account was not found in the database. Please register again.');
    }

    if (isAuthenticated()) {
      const profileCompleted = localStorage.getItem('profile_completed') === 'true';
      window.location.href = profileCompleted ? '/dashboard' : '/profile/setup';
      return;
    }

    DOM.fullNameField?.focus();
    setupEventListeners();
    DOM.passwordToggle?.setAttribute('aria-label', 'Show password');
    DOM.confirmPasswordToggle?.setAttribute('aria-label', 'Show password');
  } catch (error) {
    console.error('Registration page initialization failed:', error);
  }
}

function initRegisterPage(): void {
  initializeRegistrationPage();
  checkOAuthErrors();
  void checkGoogleOAuthStatus();
  document.getElementById('google-signup-btn')?.addEventListener('click', handleGoogleSignup);

  window.addEventListener('beforeunload', () => {
    window.clearTimeout(passwordTimer);
    window.clearTimeout(emailTimer);
    window.clearTimeout(nameTimer);
  });
}

window.addEventListener('load', initRegisterPage);

declare global {
  interface Window {
    handleGoogleSignup?: () => void;
  }
}

window.handleGoogleSignup = handleGoogleSignup;
