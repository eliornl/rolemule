import { getAuthToken } from '../shared/auth';

const API = '/api/v1/hiring-outreach';

async function request(
  path: string,
  options: RequestInit = {},
): Promise<{ ok: boolean; status: number; data: Record<string, unknown> }> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (options.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  const resp = await fetch(`${API}${path}`, {
    ...options,
    credentials: 'same-origin',
    headers,
  });
  const data = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
  return { ok: resp.ok, status: resp.status, data };
}

function raiseFromBody(data: Record<string, unknown>, fallback: string): never {
  const err = new Error(
    String(data['message'] ?? data['detail'] ?? fallback),
  ) as Error & { error_code?: string };
  err.error_code = data['error_code'] ? String(data['error_code']) : undefined;
  throw err;
}

export async function fetchHiringOutreach(
  sessionId: string,
): Promise<Record<string, unknown>> {
  const { ok, data } = await request(`/${encodeURIComponent(sessionId)}`);
  if (!ok) raiseFromBody(data, 'Failed to load hiring outreach');
  return data;
}

export async function fetchHiringOutreachStatus(
  sessionId: string,
): Promise<Record<string, unknown>> {
  const { ok, data } = await request(`/${encodeURIComponent(sessionId)}/status`);
  if (!ok) raiseFromBody(data, 'Failed to load status');
  return data;
}

export async function generateHiringOutreach(
  sessionId: string,
  regenerate = false,
): Promise<Record<string, unknown>> {
  const qs = regenerate ? '?regenerate=true' : '';
  const { ok, status, data } = await request(
    `/${encodeURIComponent(sessionId)}/generate${qs}`,
    { method: 'POST' },
  );
  if (!ok) raiseFromBody(data, `Failed to start generation (${status})`);
  return data;
}

export async function deleteHiringOutreach(sessionId: string): Promise<void> {
  const { ok, data } = await request(`/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
  if (!ok) raiseFromBody(data, 'Failed to clear hiring outreach');
}
