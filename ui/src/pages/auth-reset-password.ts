/**
 * Forgot / reset password page.
 */
import { getApiBase } from '../shared/auth';
import {
  errorMessageFromBody,
  type ForgotPasswordResponse,
  type ResetPasswordResponse,
} from '../shared/auth-api';
import {
  hideAlertElement,
  isValidEmail,
  setButtonLoading,
  showAlertIn,
  togglePasswordField,
  validateStrongPassword,
} from '../shared/auth-ui';
import { validateRelativeRedirectPath } from '../shared/dom-security';

function updatePasswordUI(): void {
  const input = document.getElementById('newPassword') as HTMLInputElement | null;
  const checkIcon = document.getElementById('newPasswordCheck');
  const requirements = document.getElementById('newPasswordReq');
  if (!input) return;

  if (validateStrongPassword(input.value)) {
    if (checkIcon) checkIcon.style.display = 'block';
    requirements?.classList.add('hidden');
  } else {
    if (checkIcon) checkIcon.style.display = 'none';
    requirements?.classList.remove('hidden');
  }
  updateConfirmPasswordUI();
}

function updateConfirmPasswordUI(): void {
  const newPassInput = document.getElementById('newPassword') as HTMLInputElement | null;
  const confPassInput = document.getElementById('confirmPassword') as HTMLInputElement | null;
  const checkIcon = document.getElementById('confirmPasswordCheck');
  if (!newPassInput || !confPassInput || !checkIcon) return;

  const matches =
    confPassInput.value.length > 0 &&
    newPassInput.value === confPassInput.value &&
    validateStrongPassword(newPassInput.value);
  checkIcon.style.display = matches ? 'block' : 'none';
}

function initResetPasswordPage(): void {
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get('token');

  if (token) {
    document.getElementById('forgotPasswordSection')?.classList.add('d-none');
    document.getElementById('resetPasswordSection')?.classList.remove('d-none');
    const resetTokenInput = document.getElementById('resetToken') as HTMLInputElement | null;
    if (resetTokenInput) resetTokenInput.value = token;
  }

  const emailInput = document.getElementById('email') as HTMLInputElement | null;
  if (emailInput) {
    emailInput.addEventListener('input', () => {
      const container = emailInput.closest('.email-validation-container');
      if (!container) return;
      const valid = isValidEmail(emailInput.value);
      container.classList.remove('email-validation-valid', 'email-validation-invalid');
      if (emailInput.value.length > 0) {
        container.classList.add(valid ? 'email-validation-valid' : 'email-validation-invalid');
      }
    });
  }

  document.querySelectorAll('.password-toggle[data-field]').forEach((btn) => {
    btn.addEventListener('click', function (this: HTMLElement) {
      togglePasswordField(this.dataset['field'] ?? '');
    });
  });

  document.getElementById('newPassword')?.addEventListener('input', updatePasswordUI);
  document.getElementById('confirmPassword')?.addEventListener('input', updateConfirmPasswordUI);

  const forgotForm = document.getElementById('forgotPasswordForm');
  if (forgotForm) {
    forgotForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('forgotBtn') as HTMLButtonElement | null;
      const email = document.getElementById('email') as HTMLInputElement | null;
      if (!btn || !email) return;

      hideAlertElement('forgotAlert');
      setButtonLoading(btn, true);

      try {
        const response = await fetch(`${getApiBase()}/auth/forgot-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email.value }),
        });
        const data = (await response.json()) as ForgotPasswordResponse;

        if (response.ok) {
          if (data.reset_url) {
            const resetBtn = document.getElementById('noEmailResetBtn') as HTMLAnchorElement | null;
            if (resetBtn) {
              const safe = validateRelativeRedirectPath(String(data.reset_url));
              resetBtn.href = safe || '/auth/reset-password';
            }
            document.getElementById('forgotPasswordSection')?.classList.add('d-none');
            document.getElementById('noEmailSection')?.classList.remove('d-none');
          } else {
            showAlertIn(
              'forgotAlert',
              data.message || 'If an account exists, you will receive a reset link shortly.',
              'success',
            );
          }
        } else {
          showAlertIn(
            'forgotAlert',
            errorMessageFromBody(data, 'An error occurred. Please try again.'),
            'danger',
          );
        }
      } catch (error) {
        console.error('Forgot password error:', error);
        showAlertIn('forgotAlert', 'Network error. Please try again.', 'danger');
      } finally {
        setButtonLoading(btn, false);
      }
    });
  }

  const resetForm = document.getElementById('resetPasswordForm');
  if (resetForm) {
    resetForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('resetBtn') as HTMLButtonElement | null;
      const tokenInput = document.getElementById('resetToken') as HTMLInputElement | null;
      const newPassEl = document.getElementById('newPassword') as HTMLInputElement | null;
      const confPassEl = document.getElementById('confirmPassword') as HTMLInputElement | null;
      if (!btn || !tokenInput || !newPassEl || !confPassEl) return;

      hideAlertElement('resetAlert');

      if (!validateStrongPassword(newPassEl.value)) {
        showAlertIn(
          'resetAlert',
          'Password must be at least 8 characters with uppercase, lowercase, number, and special character.',
          'danger',
        );
        return;
      }
      if (newPassEl.value !== confPassEl.value) {
        showAlertIn('resetAlert', 'Passwords do not match.', 'danger');
        return;
      }

      setButtonLoading(btn, true);

      try {
        const response = await fetch(`${getApiBase()}/auth/reset-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: tokenInput.value,
            new_password: newPassEl.value,
            confirm_password: confPassEl.value,
          }),
        });
        const data = (await response.json()) as ResetPasswordResponse;

        if (response.ok) {
          document.getElementById('resetPasswordSection')?.classList.add('d-none');
          document.getElementById('successSection')?.classList.remove('d-none');
        } else {
          showAlertIn(
            'resetAlert',
            errorMessageFromBody(data, 'Failed to reset password. Please try again.'),
            'danger',
          );
        }
      } catch (error) {
        console.error('Reset password error:', error);
        showAlertIn('resetAlert', 'Network error. Please try again.', 'danger');
      } finally {
        setButtonLoading(btn, false);
      }
    });
  }

  window.togglePassword = togglePasswordField;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initResetPasswordPage);
} else {
  initResetPasswordPage();
}

declare global {
  interface Window {
    togglePassword?: (inputId: string) => void;
  }
}
