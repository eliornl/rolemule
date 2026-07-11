/**
 * Login page — email/password auth, Google OAuth, URL-param messages.
 */
import { getApiBase } from '../shared/auth';
import type { LoginResponse } from '../shared/auth-api';
import {
  fetchOAuthStatus,
  getExistingAuthToken,
  parseOAuthErrorMessages,
  redirectAfterLogin,
  showOAuthButtons,
  storeLoginAuthData,
} from '../shared/auth-session';
import { escapeHtml, stripHtmlForAlert } from '../shared/dom-security';
import { validateLoginEmail } from '../shared/auth-validation';
import { validateStrongPassword } from '../shared/auth-ui';

const VALIDATION_DELAY = 500;

type LoginAlertType = 'success' | 'error' | 'info';

interface LoginDom {
  form: HTMLFormElement | null;
  submitBtn: HTMLButtonElement | null;
  loginText: HTMLElement | null;
  loginSpinner: HTMLElement | null;
  emailField: HTMLInputElement | null;
  passwordField: HTMLInputElement | null;
  rememberMeField: HTMLInputElement | null;
  alertContainer: HTMLElement | null;
  passwordToggle: HTMLElement | null;
}

const DOM: LoginDom = {
  form: document.getElementById('loginForm') as HTMLFormElement | null,
  submitBtn: document.getElementById('login-btn') as HTMLButtonElement | null,
  loginText: document.querySelector('.login-text'),
  loginSpinner: document.querySelector('.login-spinner'),
  emailField: document.getElementById('email') as HTMLInputElement | null,
  passwordField: document.getElementById('password') as HTMLInputElement | null,
  rememberMeField: document.getElementById('remember-me') as HTMLInputElement | null,
  alertContainer: document.getElementById('alert-container'),
  passwordToggle: document.querySelector('.password-toggle'),
};

let emailValidationTimeout = 0;

function showAlert(message: string, type: LoginAlertType = 'info', persist = false): void {
  if (!DOM.alertContainer) return;
  const alertTypes: Record<LoginAlertType, { class: string; icon: string }> = {
    success: { class: 'alert-success', icon: 'fas fa-check-circle' },
    error: { class: 'alert-danger', icon: 'fas fa-exclamation-triangle' },
    info: { class: 'alert-info', icon: 'fas fa-info-circle' },
  };
  const alertInfo = alertTypes[type];
  DOM.alertContainer.innerHTML = `
    <div class="alert ${alertInfo.class} alert-dismissible" role="alert">
      <i class="${alertInfo.icon} me-2"></i>${escapeHtml(message)}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>`;
  if (!persist && type !== 'error') {
    window.setTimeout(() => {
      if (DOM.alertContainer) DOM.alertContainer.innerHTML = '';
    }, 5000);
  }
}

function hideAllAlerts(): void {
  if (DOM.alertContainer) DOM.alertContainer.innerHTML = '';
}

function setFormLoading(loading: boolean): void {
  if (
    !DOM.submitBtn ||
    !DOM.loginText ||
    !DOM.loginSpinner ||
    !DOM.emailField ||
    !DOM.passwordField ||
    !DOM.rememberMeField
  ) {
    return;
  }
  if (loading) {
    DOM.submitBtn.disabled = true;
    DOM.loginText.classList.add('d-none');
    DOM.loginSpinner.classList.remove('d-none');
    DOM.submitBtn.setAttribute('aria-busy', 'true');
    DOM.emailField.disabled = true;
    DOM.passwordField.disabled = true;
    DOM.rememberMeField.disabled = true;
  } else {
    DOM.submitBtn.disabled = false;
    DOM.loginText.classList.remove('d-none');
    DOM.loginSpinner.classList.add('d-none');
    DOM.submitBtn.setAttribute('aria-busy', 'false');
    DOM.emailField.disabled = false;
    DOM.passwordField.disabled = false;
    DOM.rememberMeField.disabled = false;
  }
}

function updatePasswordUI(password: string): void {
  const passwordInput = document.getElementById('password') as HTMLInputElement | null;
  const container = document.getElementById('password-container');
  const requirements = document.getElementById('password-requirements');
  if (!passwordInput || !container) return;

  if (password.length > 0 && validateStrongPassword(password)) {
    passwordInput.classList.add('is-valid');
    passwordInput.classList.remove('is-invalid');
    container.classList.add('email-validation-valid');
    container.classList.remove('email-validation-invalid');
    requirements?.classList.add('hidden');
  } else if (password.length > 0) {
    passwordInput.classList.remove('is-valid', 'is-invalid');
    container.classList.remove('email-validation-valid', 'email-validation-invalid');
    requirements?.classList.remove('hidden');
  } else {
    passwordInput.classList.remove('is-valid', 'is-invalid');
    container.classList.remove('email-validation-valid', 'email-validation-invalid');
    requirements?.classList.add('hidden');
  }
}

function renderEmailSuggestion(
  feedbackEl: HTMLElement,
  result: ReturnType<typeof validateLoginEmail>,
  emailInput: HTMLInputElement,
): void {
  feedbackEl.innerHTML = escapeHtml(result.message ?? 'Please enter a valid email address');
  if (result.suggestion) {
    const link = document.createElement('a');
    link.href = '#';
    link.classList.add('suggestion-link');
    link.textContent = ' Use this instead';
    link.addEventListener('click', (e) => {
      e.preventDefault();
      emailInput.value = result.suggestion ?? '';
      emailInput.dispatchEvent(new Event('input'));
    });
    feedbackEl.appendChild(link);
  }
}

async function performLogin(credentials: {
  email: string;
  password: string;
  remember_me?: boolean;
}): Promise<LoginResponse> {
  if (!credentials.email || !credentials.password) {
    throw new Error('Email and password are required');
  }
  const payload: Record<string, unknown> = {
    email: credentials.email,
    password: credentials.password,
  };
  if (Object.prototype.hasOwnProperty.call(credentials, 'remember_me')) {
    payload['remember_me'] = credentials.remember_me;
  }

  const response = await fetch(`${getApiBase()}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const result = (await response.json()) as LoginResponse & { detail?: string };

  if (!response.ok) {
    if (response.status === 403) {
      localStorage.setItem('pendingVerificationEmail', credentials.email.toLowerCase());
      window.location.href = `/auth/verify-email?email=${encodeURIComponent(credentials.email.toLowerCase())}`;
      throw new Error('VERIFICATION_REQUIRED');
    }
    let errorMessage = 'Invalid email or password';
    if (response.status === 423) {
      errorMessage = result.detail || 'Account temporarily locked. Please try again later.';
    } else if (response.status === 422 || response.status === 400) {
      errorMessage = 'Please enter both email and password';
    } else if (response.status === 500) {
      errorMessage = 'Server error. Please try again later.';
    }
    throw new Error(errorMessage);
  }
  return result;
}

function checkUrlMessages(): void {
  const params = new URLSearchParams(window.location.search);
  const knownParams: Record<string, { msg: string; type: LoginAlertType }> = {
    verified: { msg: 'Email verified successfully! You can now sign in.', type: 'success' },
    registered: { msg: 'Account created! Please sign in.', type: 'success' },
    password_reset: {
      msg: 'Password reset successfully. Please sign in with your new password.',
      type: 'success',
    },
    account_deleted: { msg: 'Your account has been deleted. Sorry to see you go.', type: 'info' },
  };
  for (const [key, { msg, type }] of Object.entries(knownParams)) {
    if (params.has(key)) {
      showAlert(msg, type, true);
      window.history.replaceState({}, document.title, window.location.pathname);
      return;
    }
  }
}

function checkOAuthErrors(): void {
  const urlParams = new URLSearchParams(window.location.search);
  const error = urlParams.get('error');
  const message = urlParams.get('message');
  if (!error) return;
  showAlert(parseOAuthErrorMessages(error, message), 'error');
  window.history.replaceState({}, document.title, window.location.pathname);
}

function handleGoogleLogin(): void {
  const redirectUrl = new URLSearchParams(window.location.search).get('redirect') || '/dashboard';
  window.location.href = `/api/v1/auth/google?redirect_url=${encodeURIComponent(redirectUrl)}`;
}

async function checkGoogleOAuthStatus(): Promise<void> {
  if (await fetchOAuthStatus()) {
    showOAuthButtons('oauth-divider', 'google-login-btn');
  }
}

function initLoginPage(): void {
  const passwordInput = document.getElementById('password') as HTMLInputElement | null;
  if (passwordInput) {
    passwordInput.addEventListener('input', function (this: HTMLInputElement) {
      updatePasswordUI(this.value);
    });
  }

  const emailInput = document.getElementById('email') as HTMLInputElement | null;
  if (emailInput) {
    const emailContainer = emailInput.closest('.email-validation-container');
    emailInput.addEventListener('input', () => {
      window.clearTimeout(emailValidationTimeout);
      emailContainer?.classList.remove('email-validation-valid', 'email-validation-invalid');

      emailValidationTimeout = window.setTimeout(() => {
        const result = validateLoginEmail(emailInput.value.trim());
        if (result.valid) {
          emailContainer?.classList.add('email-validation-valid');
          emailContainer?.classList.remove('email-validation-invalid');
          document.getElementById('email-feedback')?.classList.remove('show');
        } else if (emailInput.value.trim().length > 0) {
          emailContainer?.classList.add('email-validation-invalid');
          emailContainer?.classList.remove('email-validation-valid');
          const feedbackEl = document.getElementById('email-feedback');
          if (feedbackEl) {
            renderEmailSuggestion(feedbackEl, result, emailInput);
            feedbackEl.classList.add('show');
          }
        }
      }, VALIDATION_DELAY);
    });
  }

  DOM.form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideAllAlerts();
    if (!DOM.emailField || !DOM.passwordField || !DOM.rememberMeField) return;

    const email = DOM.emailField.value.trim();
    const password = DOM.passwordField.value;

    if (!email) {
      DOM.emailField.classList.add('is-invalid');
      showAlert('Please enter your email address', 'error');
      return;
    }
    if (!password) {
      DOM.passwordField.classList.add('is-invalid');
      showAlert('Please enter your password', 'error');
      return;
    }

    const emailResult = validateLoginEmail(email);
    if (!emailResult.valid) {
      DOM.emailField.classList.add('is-invalid');
      showAlert(stripHtmlForAlert(emailResult.message ?? 'Invalid email'), 'error');
      return;
    }

    try {
      setFormLoading(true);
      const authData = await performLogin({
        email,
        password,
        remember_me: DOM.rememberMeField.checked,
      });
      if (DOM.passwordField) DOM.passwordField.value = '';
      if (storeLoginAuthData(authData)) {
        showAlert('Login successful! Redirecting...', 'success');
        redirectAfterLogin(authData.profile_completed);
      } else {
        showAlert('Failed to save login data. Please try again.', 'error');
        setFormLoading(false);
      }
    } catch (error) {
      if (DOM.passwordField) DOM.passwordField.value = '';
      const err = error as Error;
      if (err.message === 'VERIFICATION_REQUIRED') return;
      let msg = err.message || 'Login failed. Please check your credentials.';
      if (msg.includes('401') || msg.includes('unauthorized')) {
        msg = 'Invalid email or password. Please try again.';
        DOM.passwordField?.classList.add('is-invalid');
      } else if (msg.includes('500')) {
        msg = 'Server error. Please try again later or contact support.';
      } else if (msg.includes('Failed to fetch') || msg.includes('network')) {
        msg = 'Network error. Please check your internet connection.';
      }
      showAlert(msg, 'error');
      setFormLoading(false);
    }
  });

  DOM.passwordToggle?.addEventListener('click', () => {
    if (!DOM.passwordField) return;
    const isPassword = DOM.passwordField.getAttribute('type') === 'password';
    DOM.passwordField.setAttribute('type', isPassword ? 'text' : 'password');
    if (DOM.passwordToggle) {
      DOM.passwordToggle.innerHTML = isPassword
        ? '<i class="fas fa-eye-slash"></i>'
        : '<i class="fas fa-eye"></i>';
    }
  });

  const existingToken = getExistingAuthToken();
  if (existingToken) {
    window.location.href = '/dashboard';
    return;
  }

  void checkGoogleOAuthStatus();
  checkOAuthErrors();
  checkUrlMessages();

  document.getElementById('google-login-btn')?.addEventListener('click', handleGoogleLogin);

  window.addEventListener('beforeunload', () => {
    window.clearTimeout(emailValidationTimeout);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initLoginPage);
} else {
  initLoginPage();
}

declare global {
  interface Window {
    handleGoogleLogin?: () => void;
  }
}

window.handleGoogleLogin = handleGoogleLogin;
