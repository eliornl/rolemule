import { getAuthToken } from '../shared/auth';

const API = '/api/v1/mock-interview';

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

function raiseFromBody(
  data: Record<string, unknown>,
  fallback: string,
  status?: number,
): never {
  const err = new Error(
    String(data['message'] ?? data['detail'] ?? fallback),
  ) as Error & { error_code?: string; status?: number };
  err.error_code = data['error_code'] ? String(data['error_code']) : undefined;
  if (typeof status === 'number') err.status = status;
  throw err;
}

export async function fetchMockInterview(sessionId: string): Promise<Record<string, unknown>> {
  const { ok, status, data } = await request(`/${encodeURIComponent(sessionId)}`);
  if (!ok) raiseFromBody(data, 'Failed to load', status);
  return data;
}

export async function fetchMockStatus(sessionId: string): Promise<Record<string, unknown>> {
  const { ok, status, data } = await request(`/${encodeURIComponent(sessionId)}/status`);
  if (!ok) raiseFromBody(data, 'Failed to load status', status);
  return data;
}

export async function startMockInterview(
  sessionId: string,
  style: string,
  durationMinutes: number,
): Promise<Record<string, unknown>> {
  const { ok, status, data } = await request(`/${encodeURIComponent(sessionId)}/start`, {
    method: 'POST',
    body: JSON.stringify({
      style,
      duration_minutes: durationMinutes,
      star_coach: true,
    }),
  });
  if (!ok) raiseFromBody(data, 'Failed to start', status);
  return data;
}

export async function submitTurn(
  sessionId: string,
  transcript: string,
  source: 'typed' | 'stt',
): Promise<Record<string, unknown>> {
  const { ok, status, data } = await request(`/${encodeURIComponent(sessionId)}/turn`, {
    method: 'POST',
    body: JSON.stringify({ transcript, source }),
  });
  if (!ok) raiseFromBody(data, 'Failed to submit answer', status);
  return data;
}

export async function finishMockInterview(
  sessionId: string,
  finalAnswer?: string,
  source: 'typed' | 'stt' = 'typed',
): Promise<Record<string, unknown>> {
  const trimmed = (finalAnswer || '').trim();
  const body =
    trimmed.length >= 5
      ? JSON.stringify({ final_answer: trimmed, source })
      : JSON.stringify({});
  const { ok, status, data } = await request(`/${encodeURIComponent(sessionId)}/finish`, {
    method: 'POST',
    body,
  });
  if (!ok) raiseFromBody(data, 'Failed to finish', status);
  return data;
}

export async function abortMockInterview(sessionId: string): Promise<Record<string, unknown>> {
  const { ok, status, data } = await request(`/${encodeURIComponent(sessionId)}/abort`, {
    method: 'POST',
  });
  if (!ok) raiseFromBody(data, 'Failed to abort', status);
  return data;
}
