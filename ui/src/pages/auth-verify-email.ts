/**
 * Email verification page — 6-digit code input, resend, post-verify redirect.
 */
import { getApiBase } from '../shared/auth';
import { errorMessageFromBody, type VerifyCodeResponse, type ResendVerificationResponse } from '../shared/auth-api';
import { escapeHtml, validateRelativeRedirectPath } from '../shared/dom-security';
import { setButtonLoading, type AuthAlertType } from '../shared/auth-ui';

let userEmail = '';
let resendCooldown = 0;

function showAlert(message: string, type: AuthAlertType): void {
  const container = document.getElementById('alertContainer');
  if (!container) return;
  const icon = type === 'success' ? 'check-circle' : 'exclamation-triangle';
  container.innerHTML = `
    <div class="alert alert-${type}" role="alert">
      <i class="fas fa-${icon} me-2"></i>
      ${escapeHtml(message)}
    </div>`;
}

function clearAlert(): void {
  const container = document.getElementById('alertContainer');
  if (container) container.innerHTML = '';
}

function getCodeInputs(): NodeListOf<HTMLInputElement> {
  return document.querySelectorAll('.code-input');
}

function checkCodeComplete(): void {
  const inputs = getCodeInputs();
  const code = Array.from(inputs)
    .map((i) => i.value)
    .join('');
  const btn = document.getElementById('verifyBtn') as HTMLButtonElement | null;
  if (btn) btn.disabled = code.length !== 6;
}

function getCode(): string {
  return Array.from(getCodeInputs())
    .map((i) => i.value)
    .join('');
}

function setupCodeInputs(): void {
  const inputs = getCodeInputs();

  inputs.forEach((input, index) => {
    input.addEventListener('input', function (this: HTMLInputElement) {
      const value = this.value.replace(/[^0-9]/g, '');
      this.value = value;

      if (value) {
        this.classList.add('filled');
        if (index < inputs.length - 1) {
          inputs[index + 1].focus();
        }
      } else {
        this.classList.remove('filled');
      }
      checkCodeComplete();
    });

    input.addEventListener('keydown', function (this: HTMLInputElement, e: KeyboardEvent) {
      if (e.key === 'Backspace' && !this.value && index > 0) {
        inputs[index - 1].focus();
        inputs[index - 1].value = '';
        inputs[index - 1].classList.remove('filled');
      }
      inputs.forEach((inp) => inp.classList.remove('error'));
    });

    input.addEventListener('paste', function (e: ClipboardEvent) {
      e.preventDefault();
      const pastedData = (e.clipboardData?.getData('text') ?? '')
        .replace(/[^0-9]/g, '')
        .slice(0, 6);

      pastedData.split('').forEach((char, i) => {
        if (inputs[i]) {
          inputs[i].value = char;
          inputs[i].classList.add('filled');
        }
      });

      if (pastedData.length === 6) {
        inputs[5].focus();
      } else if (pastedData.length > 0) {
        inputs[Math.min(pastedData.length, 5)].focus();
      }
      checkCodeComplete();
    });
  });
}

function storeAuthAfterVerify(data: VerifyCodeResponse): void {
  if (!data.access_token) return;

  localStorage.setItem('authToken', data.access_token);
  localStorage.setItem('access_token', data.access_token);
  if (data.user) {
    localStorage.setItem('user_data', JSON.stringify(data.user));
  }
  if (data.profile_completed !== undefined) {
    localStorage.setItem('profile_completed', String(data.profile_completed));
  }
  if (!data.profile_completed) {
    localStorage.removeItem('onboarding_completed');
  }
}

function showSuccessSection(data: VerifyCodeResponse): void {
  const successMsg = document.getElementById('successMessage');
  if (successMsg && data.message) successMsg.textContent = data.message;

  const continueBtn = document.getElementById('continueBtn') as HTMLAnchorElement | null;
  if (continueBtn) {
    const rawRedirect = data.redirect || '/profile/setup';
    const safeRedirect = validateRelativeRedirectPath(rawRedirect) || '/profile/setup';
    continueBtn.href = safeRedirect;
    if (safeRedirect.includes('dashboard')) {
      continueBtn.innerHTML = '<i class="fas fa-tachometer-alt me-2"></i> Go to Dashboard';
    }
  }

  document.getElementById('codeSection')?.classList.add('d-none');
  document.getElementById('successSection')?.classList.remove('d-none');
}

function clearCodeInputsWithError(): void {
  getCodeInputs().forEach((input) => {
    input.classList.add('error');
    input.value = '';
    input.classList.remove('filled');
  });
  (document.querySelector('.code-input') as HTMLElement | null)?.focus();
}

async function resendCode(): Promise<void> {
  if (resendCooldown > 0) return;

  const link = document.getElementById('resendLink');
  const timer = document.getElementById('resendTimer');
  if (!link || !timer) return;

  link.classList.add('disabled');

  try {
    const response = await fetch(`${getApiBase()}/auth/resend-verification`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: userEmail }),
    });

    const data = (await response.json()) as ResendVerificationResponse;

    if (response.ok) {
      showAlert('New verification code sent! Check your email.', 'success');
    } else if (data.message?.includes('already verified')) {
      showAlert('Your email is already verified! You can log in.', 'success');
    } else {
      showAlert('Failed to send code. Please try again.', 'danger');
    }

    if (response.ok) {
      resendCooldown = 60;
      link.classList.add('d-none');
      timer.classList.remove('d-none');

      const interval = window.setInterval(() => {
        resendCooldown -= 1;
        timer.textContent = `Resend in ${resendCooldown}s`;
        if (resendCooldown <= 0) {
          window.clearInterval(interval);
          link.classList.remove('d-none', 'disabled');
          timer.classList.add('d-none');
        }
      }, 1000);
    }
  } catch (error) {
    console.error('Resend error:', error);
    showAlert('Failed to resend code. Please try again.', 'danger');
    link.classList.remove('disabled');
  }
}

function initVerifyEmailPage(): void {
  const urlParams = new URLSearchParams(window.location.search);
  userEmail =
    urlParams.get('email') || localStorage.getItem('pendingVerificationEmail') || '';

  if (userEmail) {
    const emailEl = document.getElementById('userEmail');
    if (emailEl) emailEl.textContent = userEmail;
    document.getElementById('codeSection')?.classList.remove('d-none');
    document.getElementById('noEmailSection')?.classList.add('d-none');
    (document.querySelector('.code-input') as HTMLElement | null)?.focus();
  } else {
    document.getElementById('codeSection')?.classList.add('d-none');
    document.getElementById('noEmailSection')?.classList.remove('d-none');
  }

  setupCodeInputs();

  const resendLink = document.getElementById('resendLink');
  if (resendLink) {
    resendLink.addEventListener('click', (e) => {
      e.preventDefault();
      void resendCode();
    });
    resendLink.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        void resendCode();
      }
    });
  }

  const verifyForm = document.getElementById('verifyForm');
  if (verifyForm) {
    verifyForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearAlert();

      const code = getCode();
      if (code.length !== 6) return;

      const btn = document.getElementById('verifyBtn') as HTMLButtonElement | null;
      if (!btn) return;
      setButtonLoading(btn, true);

      try {
        const response = await fetch(`${getApiBase()}/auth/verify-code`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: userEmail, code }),
        });

        const data = (await response.json()) as VerifyCodeResponse & { detail?: string };

        if (response.ok) {
          localStorage.removeItem('pendingVerificationEmail');
          storeAuthAfterVerify(data);
          showSuccessSection(data);
        } else {
          showAlert(
            errorMessageFromBody(data, 'Invalid verification code. Please try again.'),
            'danger',
          );
          clearCodeInputsWithError();
        }
      } catch (error) {
        console.error('Verification error:', error);
        showAlert('An error occurred. Please try again.', 'danger');
      } finally {
        setButtonLoading(btn, false);
        checkCodeComplete();
      }
    });
  }

  const emailForm = document.getElementById('emailForm');
  if (emailForm) {
    emailForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const emailInput = document.getElementById('emailInput') as HTMLInputElement | null;
      if (!emailInput) return;
      userEmail = emailInput.value.trim();

      const btn = emailForm.querySelector('button') as HTMLButtonElement | null;
      if (!btn) return;
      setButtonLoading(btn, true);

      try {
        const response = await fetch(`${getApiBase()}/auth/resend-verification`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: userEmail }),
        });

        if (response.ok) {
          localStorage.setItem('pendingVerificationEmail', userEmail);
          const emailEl = document.getElementById('userEmail');
          if (emailEl) emailEl.textContent = userEmail;
          document.getElementById('noEmailSection')?.classList.add('d-none');
          document.getElementById('codeSection')?.classList.remove('d-none');
          (document.querySelector('.code-input') as HTMLElement | null)?.focus();
          showAlert('Verification code sent! Check your email.', 'success');
        } else {
          const data = (await response.json()) as ResendVerificationResponse;
          showAlert(errorMessageFromBody(data, 'Failed to send code.'), 'danger');
        }
      } catch (error) {
        console.error('Error:', error);
        showAlert('An error occurred. Please try again.', 'danger');
      } finally {
        setButtonLoading(btn, false);
      }
    });
  }

  window.resendCode = resendCode;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initVerifyEmailPage);
} else {
  initVerifyEmailPage();
}

declare global {
  interface Window {
    resendCode?: () => Promise<void>;
  }
}
