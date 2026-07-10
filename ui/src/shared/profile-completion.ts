/**
 * Sync localStorage profile_completed from GET /api/v1/profile/.
 * Dashboard pages must not redirect using stale localStorage alone.
 */
import { getApiBase, getAuthToken, getLoginUrl } from './auth';

interface ProfileCompletionResponse {
  completion_status?: { profile_completed?: boolean };
}

export async function syncProfileCompletionFromApi(): Promise<boolean> {
  const token = getAuthToken();
  if (!token) return false;

  const loginUrl = getLoginUrl();

  try {
    const response = await fetch(`${getApiBase()}/profile/`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.status === 401) {
      window.location.href = loginUrl;
      return false;
    }
    if (response.status === 404) {
      window.location.href = '/profile/setup?edit=true';
      return false;
    }
    if (!response.ok) return false;

    const data = (await response.json()) as ProfileCompletionResponse;
    const completed = Boolean(data.completion_status?.profile_completed);
    localStorage.setItem('profile_completed', completed ? 'true' : 'false');

    if (!completed) {
      window.location.href = '/profile/setup?edit=true';
      return false;
    }
    return true;
  } catch (e) {
    console.error('syncProfileCompletionFromApi:', e);
    return false;
  }
}
