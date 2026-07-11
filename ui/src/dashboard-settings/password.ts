import { getApiBase, getAuthToken } from '../shared/auth';
import { el, inputEl } from './dom';
import { showAlert } from './notify';

export function togglePasswordSection(): void {
  const header = document.querySelector('.password-header');
  const content = el('passwordFormContent');
  header?.classList.toggle('collapsed');
  content?.classList.toggle('expanded');
}

export function togglePasswordField(fieldId: string): void {
  const input = inputEl(fieldId);
  const icon = el(`${fieldId}-toggle-icon`);
  if (!input || !icon) return;
  if (input.type === 'password') {
    input.type = 'text';
    icon.classList.replace('fa-eye', 'fa-eye-slash');
  } else {
    input.type = 'password';
    icon.classList.replace('fa-eye-slash', 'fa-eye');
  }
}

export function validateNewPassword(password: string): boolean {
  const req = {
    length: password.length >= 8,
    uppercase: /[A-Z]/.test(password),
    lowercase: /[a-z]/.test(password),
    number: /[0-9]/.test(password),
    special: /[!@#$%^&*(),.?":{}|<>]/.test(password),
  };
  el('req-length')?.classList.toggle('valid', req.length);
  el('req-uppercase')?.classList.toggle('valid', req.uppercase);
  el('req-lowercase')?.classList.toggle('valid', req.lowercase);
  el('req-number')?.classList.toggle('valid', req.number);
  el('req-special')?.classList.toggle('valid', req.special);

  const allValid = Object.values(req).every((v) => v);
  const container = el('newPassword-container');
  if (!container) return allValid;
  if (password.length > 0) {
    container.classList.toggle('is-valid', allValid);
    container.classList.toggle('is-invalid', !allValid);
  } else {
    container.classList.remove('is-valid', 'is-invalid');
  }
  return allValid;
}

export function validateConfirmPassword(): boolean {
  const newPw = inputEl('newPassword');
  const confPw = inputEl('confirmPassword');
  const container = el('confirmPassword-container');
  if (!newPw || !confPw || !container) return false;

  if (confPw.value.length > 0) {
    const isMatch = newPw.value === confPw.value;
    container.classList.toggle('is-valid', isMatch);
    container.classList.toggle('is-invalid', !isMatch);
    return isMatch;
  }
  container.classList.remove('is-valid', 'is-invalid');
  return false;
}

export async function handlePasswordChange(event: Event): Promise<void> {
  event.preventDefault();
  const curPw = inputEl('currentPassword');
  const newPw = inputEl('newPassword');
  const confPw = inputEl('confirmPassword');
  if (!curPw || !newPw || !confPw) return;

  if (newPw.value !== confPw.value) {
    showAlert('New passwords do not match.', 'danger');
    return;
  }
  if (newPw.value.length < 8) {
    showAlert('Password must be at least 8 characters long.', 'danger');
    return;
  }

  try {
    const response = await fetch(`${getApiBase()}/auth/change-password`, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        current_password: curPw.value,
        new_password: newPw.value,
        confirm_password: confPw.value,
      }),
    });
    if (response.ok) {
      const data = (await response.json()) as { access_token?: string };
      if (data.access_token) {
        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('authToken', data.access_token);
      }
      showAlert('Password updated successfully!', 'success');
      (el('passwordForm') as HTMLFormElement | null)?.reset();
      el('newPassword-container')?.classList.remove('is-valid', 'is-invalid');
      el('confirmPassword-container')?.classList.remove('is-valid', 'is-invalid');
      document.querySelectorAll('.password-requirements li').forEach((li) => {
        li.classList.remove('valid');
      });
      document.querySelector('.password-header')?.classList.add('collapsed');
      el('passwordFormContent')?.classList.remove('expanded');
    } else {
      let errData: { message?: string; detail?: string };
      try {
        errData = (await response.json()) as { message?: string; detail?: string };
      } catch {
        errData = { detail: 'Server error occurred' };
      }
      throw new Error(errData.message || errData.detail || 'Failed to update password');
    }
  } catch (error) {
    const err = error as Error;
    console.error('Error updating password:', err);
    showAlert(err.message, 'danger');
  }
}
