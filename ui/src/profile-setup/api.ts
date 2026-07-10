import { API_BASE, STORAGE_KEYS } from './state';

export class ProfileApiError extends Error {
  details?: unknown;

  constructor(message: string, details?: unknown) {
    super(message);
    this.name = 'ProfileApiError';
    this.details = details;
  }
}

type LegacyAppApi = {
  apiCall?: (
    endpoint: string,
    method?: string,
    data?: unknown,
  ) => Promise<unknown>;
};

export function getAuthToken(): string | null {
  const urlParams = new URLSearchParams(window.location.search);
  const tokenFromUrl =
    urlParams.get('token') || urlParams.get('access_token');
  if (tokenFromUrl) return tokenFromUrl;
  return (
    localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN) ||
    localStorage.getItem('authToken')
  );
}

export function setAuthToken(token: string | null | undefined): void {
  if (!token) return;
  localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, token);
  localStorage.setItem('authToken', token);
}

export async function exchangeOAuthCodeIfPresent(): Promise<boolean> {
  const urlParams = new URLSearchParams(window.location.search);
  const code = urlParams.get('code');
  if (!code) return false;

  urlParams.delete('code');
  const newSearch = urlParams.toString();
  history.replaceState(
    null,
    '',
    window.location.pathname + (newSearch ? `?${newSearch}` : ''),
  );

  try {
    const response = await fetch(`${API_BASE}/auth/oauth/exchange-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    if (!response.ok) return false;
    const data = (await response.json()) as { access_token?: string };
    if (!data.access_token) return false;
    setAuthToken(data.access_token);
    return true;
  } catch (err) {
    const error = err instanceof Error ? err : new Error(String(err));
    console.error('OAuth code exchange failed:', error.message);
    return false;
  }
}

export async function makeAuthenticatedApiCall(
  endpoint: string,
  method = 'GET',
  body: unknown = null,
): Promise<Record<string, unknown>> {
  const app = (window.app ?? {}) as LegacyAppApi;
  if (app.apiCall) {
    const result = await app.apiCall(endpoint, method, body);
    return (result ?? {}) as Record<string, unknown>;
  }

  const token = getAuthToken();
  if (!token) {
    window.location.href =
      (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
    throw new Error('Authentication required');
  }

  const fetchOptions: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
  };
  if (body && method !== 'GET') {
    fetchOptions.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, fetchOptions);
  if (!response.ok) {
    const err = (await response.json().catch(() => ({}))) as Record<
      string,
      unknown
    >;
    if (response.status === 401) {
      window.location.href =
        (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
    }
    const message =
      (typeof err.message === 'string' && err.message) ||
      (typeof err.detail === 'string' && err.detail) ||
      `API error: ${response.status}`;
    throw new ProfileApiError(message, err.details);
  }
  return (await response.json()) as Record<string, unknown>;
}
