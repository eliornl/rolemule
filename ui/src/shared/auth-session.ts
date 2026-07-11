import { getApiBase } from './auth';

const AUTH_TOKEN_KEY = 'access_token';
const AUTH_TOKEN_LEGACY = 'authToken';

/** Store tokens after login (login page uses `user` key for user JSON). */
export function storeLoginAuthData(authData: {
  access_token?: string;
  user?: unknown;
  profile_completed?: boolean;
}): boolean {
  try {
    if (!authData.access_token) {
      console.error('Missing access_token in auth data');
      return false;
    }
    localStorage.setItem(AUTH_TOKEN_KEY, authData.access_token);
    localStorage.setItem(AUTH_TOKEN_LEGACY, authData.access_token);
    localStorage.setItem('user', JSON.stringify(authData.user));
    localStorage.setItem('profile_completed', String(authData.profile_completed));
    return true;
  } catch (error) {
    console.error('Failed to store authentication data:', error);
    return false;
  }
}

/**
 * Store tokens after registration only when email is already verified (dev bypass).
 * Normal registration must NOT call this — verify-code issues the token.
 */
export function storeRegisterAuthData(response: {
  access_token?: string;
  token_type?: string;
  user?: unknown;
  profile_completed?: boolean;
}): void {
  if (!response.access_token) return;
  localStorage.setItem(AUTH_TOKEN_KEY, response.access_token);
  localStorage.setItem(AUTH_TOKEN_LEGACY, response.access_token);
  localStorage.setItem('token_type', String(response.token_type ?? ''));
  localStorage.setItem('user_data', JSON.stringify(response.user));
  localStorage.setItem('profile_completed', String(response.profile_completed));
}

export function redirectAfterLogin(profileCompleted: boolean | undefined): void {
  const defaultDestination = profileCompleted ? '/dashboard' : '/profile/setup';
  const REDIRECT_DELAY = 1000;

  try {
    const urlParams = new URLSearchParams(window.location.search);
    let rawRedirect = urlParams.get('redirect');
    if (rawRedirect?.startsWith('/ui/')) {
      rawRedirect = rawRedirect
        .replace('/ui/dashboard/index.html', '/dashboard')
        .replace('/ui/profile/setup.html', '/profile/setup');
    }
    const validatedRedirect = window.validateRelativeRedirectPath?.(rawRedirect) ?? null;
    const safeDestination = validatedRedirect ?? defaultDestination;
    const redirectUrl = new URL(safeDestination, window.location.origin);
    if (redirectUrl.origin !== window.location.origin) {
      window.setTimeout(() => {
        window.location.assign(defaultDestination);
      }, REDIRECT_DELAY);
      return;
    }
    const navPath = redirectUrl.pathname + redirectUrl.search + redirectUrl.hash;
    window.setTimeout(() => {
      window.location.assign(navPath);
    }, REDIRECT_DELAY);
  } catch (error) {
    console.error(
      'Redirect failed:',
      window.sanitizeLogValue?.(error instanceof Error ? error.message : String(error)),
    );
    window.location.assign('/dashboard');
  }
}

export function getExistingAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY) || localStorage.getItem(AUTH_TOKEN_LEGACY);
}

export async function fetchOAuthStatus(): Promise<boolean> {
  try {
    const response = await fetch(`${getApiBase()}/auth/oauth/status`);
    if (!response.ok) return false;
    const data = (await response.json()) as { google_oauth_enabled?: boolean };
    return Boolean(data.google_oauth_enabled);
  } catch {
    return false;
  }
}

export function parseOAuthErrorMessages(error: string, message: string | null): string {
  const messages: Record<string, string> = {
    oauth_failed: message ? `OAuth error: ${message}` : 'Google authentication failed.',
    oauth_not_configured: 'Google sign-in is not available at the moment.',
    token_exchange_failed: 'Failed to complete authentication. Please try again.',
    no_access_token: 'Authentication incomplete. Please try again.',
    userinfo_failed: 'Could not retrieve your account information.',
    missing_user_info: 'Required account information is missing.',
    oauth_error: message ? `Error: ${message}` : 'An error occurred during authentication.',
  };
  return messages[error] ?? 'Authentication failed. Please try again.';
}

export function showOAuthButtons(dividerId: string, buttonId: string): void {
  const divider = document.getElementById(dividerId);
  const btn = document.getElementById(buttonId);
  if (divider) divider.style.display = 'flex';
  if (btn) btn.style.display = 'flex';
}
