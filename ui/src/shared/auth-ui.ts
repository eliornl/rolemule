import { escapeHtml } from './dom-security';

export type AuthAlertType = 'success' | 'danger' | 'warning' | 'info';

const ALERT_ICONS: Record<AuthAlertType, string> = {
  success: 'check-circle',
  danger: 'exclamation-triangle',
  warning: 'exclamation-circle',
  info: 'info-circle',
};

/** Render alert into a container element by id. */
export function showAlertIn(
  elementId: string,
  message: string,
  type: AuthAlertType,
): void {
  const alertEl = document.getElementById(elementId);
  if (!alertEl) return;
  const icon = ALERT_ICONS[type] ?? 'info-circle';
  alertEl.className = `alert alert-${type}`;
  alertEl.innerHTML = `<i class="fas fa-${icon} me-2"></i>${escapeHtml(message)}`;
  alertEl.classList.remove('d-none');
}

export function hideAlertElement(elementId: string): void {
  document.getElementById(elementId)?.classList.add('d-none');
}

export function setButtonLoading(btn: HTMLButtonElement, loading: boolean): void {
  const text = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.btn-spinner') ?? btn.querySelector('.btn-loader');
  if (loading) {
    text?.classList.add('d-none');
    spinner?.classList.remove('d-none');
    btn.disabled = true;
  } else {
    text?.classList.remove('d-none');
    spinner?.classList.add('d-none');
    btn.disabled = false;
  }
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function isValidEmail(email: string): boolean {
  return EMAIL_REGEX.test(email);
}

const PASSWORD_SPECIAL = /[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/;

export function validateStrongPassword(password: string): boolean {
  if (!password || password.length < 8) return false;
  return (
    /[A-Z]/.test(password) &&
    /[a-z]/.test(password) &&
    /[0-9]/.test(password) &&
    PASSWORD_SPECIAL.test(password)
  );
}

export function togglePasswordField(inputId: string): void {
  const input = document.getElementById(inputId) as HTMLInputElement | null;
  const icon = document.getElementById(`${inputId}Icon`);
  if (!input || !icon) return;
  if (input.type === 'password') {
    input.type = 'text';
    icon.classList.replace('fa-eye', 'fa-eye-slash');
  } else {
    input.type = 'password';
    icon.classList.replace('fa-eye-slash', 'fa-eye');
  }
}
