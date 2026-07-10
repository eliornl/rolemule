import {
  clearLocalStoragePreservingConsent,
  getApiBase,
  getAuthToken,
} from '../shared/auth';
import { getUserHasPassword } from './state-access';
import { showAlert } from './notify';
import type { ApplicationStatsOverview } from './types';

export async function exportData(): Promise<void> {
  try {
    const response = await fetch(`${getApiBase()}/profile/export`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });
    if (response.ok) {
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `applypilot-data-${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      showAlert('Data export downloaded successfully!', 'success');
    } else {
      throw new Error('Failed to export data');
    }
  } catch (error) {
    console.error('Error exporting data:', error);
    showAlert('Error exporting data. Please try again.', 'danger');
  }
}

export function restartOnboarding(): void {
  localStorage.removeItem('onboarding_completed');
  window.location.href = '/dashboard';
}

export async function clearAllData(): Promise<void> {
  try {
    const res = await fetch(`${getApiBase()}/applications/stats/overview`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });
    if (res.ok) {
      const stats = (await res.json()) as ApplicationStatsOverview;
      if ((stats.total_applications || 0) === 0) {
        showAlert('You have no applications to clear.', 'info');
        return;
      }
    }
  } catch {
    /* proceed to modal if check fails */
  }

  const showConfirm = window.showConfirm;
  if (!showConfirm) return;
  const confirmed = await showConfirm({
    title: 'Clear All Applications',
    message:
      'This will permanently delete all your job applications and AI-generated results (cover letters, analyses, interview prep). Your account and profile stay intact.',
    confirmText: 'Yes, Clear Applications',
    type: 'danger',
  });
  if (!confirmed) return;
  await performDataClear();
}

async function performDataClear(): Promise<void> {
  try {
    const response = await fetch(`${getApiBase()}/profile/clear-data`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ confirm: true }),
    });
    if (response.ok) {
      showAlert('All application data has been cleared.', 'success');
      window.setTimeout(() => {
        window.location.href = '/dashboard';
      }, 2000);
    } else if (response.status === 429) {
      throw new Error('You have no applications to clear.');
    } else {
      const errData = (await response.json().catch(() => ({}))) as {
        message?: string;
        detail?: string;
      };
      throw new Error(errData.message || errData.detail || 'Failed to clear data');
    }
  } catch (error) {
    const err = error as Error;
    console.error('Error clearing data:', err);
    showAlert(err.message || 'Error clearing data. Please try again.', 'danger');
  }
}

export async function deleteAccount(): Promise<void> {
  const showConfirm = window.showConfirm;
  if (!showConfirm) return;
  const confirmed = await showConfirm({
    title: 'Delete Account',
    message:
      'This will permanently delete your account and all associated data. This action cannot be undone.',
    confirmText: 'Delete Account',
    type: 'danger',
  });
  if (!confirmed) return;

  let password = '';
  if (getUserHasPassword()) {
    const result = await showConfirm({
      title: 'Enter Your Password',
      message: 'Enter your current password to confirm account deletion.',
      confirmText: 'Delete Account',
      type: 'danger',
      inputPlaceholder: 'Your password',
      inputType: 'password',
    });
    if (result === null) return;
    password = String(result);
  }
  await performAccountDeletion(password);
}

async function performAccountDeletion(password: string): Promise<void> {
  try {
    const response = await fetch(`${getApiBase()}/profile/delete-account`, {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ password }),
    });
    if (response.ok) {
      clearLocalStoragePreservingConsent();
      window.location.href = '/auth/login?account_deleted=1';
    } else {
      const data = (await response.json().catch(() => ({}))) as {
        message?: string;
        detail?: string;
      };
      throw new Error(data.message || data.detail || 'Failed to delete account');
    }
  } catch (error) {
    console.error('Error deleting account:', error);
    showAlert('Error deleting account. Please try again.', 'danger');
  }
}
