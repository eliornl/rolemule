import { getApiBase, getAuthToken, getLoginUrl, clearAuthStorage } from './auth';

export class ApiError extends Error {
  status: number;
  errorCode: string | null;
  body: Record<string, unknown>;

  constructor(
    message: string,
    status: number,
    body: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.errorCode = typeof body['error_code'] === 'string' ? body['error_code'] : null;
  }
}

function messageFromBody(body: Record<string, unknown>, fallback: string): string {
  if (typeof body['message'] === 'string' && body['message']) return body['message'];
  if (typeof body['detail'] === 'string' && body['detail']) return body['detail'];
  return fallback;
}

/**
 * Authenticated JSON API helper. On 401, clears tokens and redirects to login.
 */
export async function apiCall(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (!headers.has('Content-Type') && options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const url = path.startsWith('http') ? path : `${getApiBase()}${path.startsWith('/') ? '' : '/'}${path}`;
  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    clearAuthStorage();
    window.location.href = getLoginUrl();
    throw new ApiError('Unauthorized', 401);
  }

  return response;
}

export async function apiJson<T = Record<string, unknown>>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await apiCall(path, options);
  const body = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    throw new ApiError(
      messageFromBody(body, `Request failed (${response.status})`),
      response.status,
      body,
    );
  }
  return body as T;
}
