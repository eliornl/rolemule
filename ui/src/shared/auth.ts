/**
 * Auth token helpers and logout — safe on dashboard pages without window.app.
 */

const TOKEN_KEYS = [
  'authToken',
  'access_token',
  'token_type',
  'user_data',
  'profile_completed',
] as const;

export function getAuthToken(): string | null {
  if (window.app && typeof window.app.getAuthToken === 'function') {
    return window.app.getAuthToken();
  }
  return localStorage.getItem('access_token') || localStorage.getItem('authToken');
}

export function clearAuthStorage(): void {
  for (const k of TOKEN_KEYS) {
    localStorage.removeItem(k);
  }
}

/**
 * Full localStorage clear for account deletion — preserves cookie_consent.
 */
export function clearLocalStoragePreservingConsent(): void {
  const cc = localStorage.getItem('cookie_consent');
  localStorage.clear();
  if (cc) localStorage.setItem('cookie_consent', cc);
}

export function getLoginUrl(): string {
  return (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
}

export function logout(): void {
  if (window.app && typeof window.app.logout === 'function') {
    window.app.logout();
    return;
  }
  clearAuthStorage();
  window.location.href = getLoginUrl();
}

export function getApiBase(): string {
  return (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';
}
