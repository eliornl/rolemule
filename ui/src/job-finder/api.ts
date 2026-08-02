/**
 * Job Finder API helpers — Bearer auth via shared apiCall / apiJson.
 */
import { ApiError, apiJson } from '../shared/api';

export { ApiError };

export interface JobFinderJob {
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  provider?: string;
  posted_at?: string | null;
  description_text?: string;
}

export interface JobFinderMessageMeta {
  type?: string;
  jobs?: JobFinderJob[];
  [key: string]: unknown;
}

export interface JobFinderMessage {
  id: string;
  role: 'user' | 'assistant' | string;
  content: string;
  created_at?: string;
  meta?: JobFinderMessageMeta;
}

export interface JobFinderSession {
  id: string;
  status: string;
  phase: string;
  confirmed_filters: Record<string, unknown>;
  messages: JobFinderMessage[];
  last_board: Record<string, unknown>;
  last_listings: JobFinderJob[];
}

export interface SelectItemResult {
  job_id: string;
  ok: boolean;
  application_id?: string | null;
  session_id?: string | null;
  error_code?: string | null;
  message?: string | null;
}

export interface SelectResponse {
  results: SelectItemResult[];
  started: number;
  failed: number;
}

const BASE = '/job-finder';

export async function createSession(): Promise<JobFinderSession> {
  return apiJson<JobFinderSession>(`${BASE}/sessions`, { method: 'POST' });
}

export async function getActiveSession(): Promise<JobFinderSession> {
  return apiJson<JobFinderSession>(`${BASE}/sessions/active`);
}

export async function getSession(sessionId: string): Promise<JobFinderSession> {
  return apiJson<JobFinderSession>(
    `${BASE}/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export async function postMessage(
  sessionId: string,
  content: string,
): Promise<JobFinderSession> {
  return apiJson<JobFinderSession>(
    `${BASE}/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    },
  );
}

export async function selectJobs(
  sessionId: string,
  jobIds: string[],
): Promise<SelectResponse> {
  return apiJson<SelectResponse>(
    `${BASE}/sessions/${encodeURIComponent(sessionId)}/select`,
    {
      method: 'POST',
      body: JSON.stringify({ job_ids: jobIds }),
    },
  );
}

export async function archiveSession(sessionId: string): Promise<{ status: string; id: string }> {
  return apiJson<{ status: string; id: string }>(
    `${BASE}/sessions/${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
  );
}

/** Resume active session, or create one when none exists (404). */
export async function getOrCreateSession(): Promise<JobFinderSession> {
  try {
    return await getActiveSession();
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return createSession();
    }
    throw err;
  }
}
