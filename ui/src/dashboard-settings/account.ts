import { getApiBase, getAuthToken } from '../shared/auth';
import { el } from './dom';
import { setUserHasPassword } from './state-access';
import type { UserProfilePayload } from './types';

export async function loadGoogleAccountStatus(): Promise<void> {
  try {
    const response = await fetch(`${getApiBase()}/profile/`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });
    if (!response.ok) return;
    const data = (await response.json()) as UserProfilePayload;
    const userInfo = data.user_info || {};
    const hasPassword =
      userInfo.auth_method === 'local' || Boolean(userInfo.has_password);
    setUserHasPassword(hasPassword);
    const passwordSection = el('passwordSection');
    if (passwordSection) {
      passwordSection.style.display = hasPassword ? 'block' : 'none';
    }
  } catch (error) {
    console.error('Error loading account status:', error);
  }
}
