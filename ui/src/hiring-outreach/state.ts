/** Shared state for Hiring Outreach tab. */

export interface HoContact {
  name?: string | null;
  role_type?: string;
  likely_title?: string;
  why_them?: string;
  confidence?: string;
  evidence?: string;
  source_hint?: string;
  short_message?: string;
  subject_line?: string;
  email_body?: string;
}

export interface HoFallback {
  used?: boolean;
  reason?: string | null;
  subject_line?: string | null;
  email_body?: string | null;
  short_message?: string | null;
}

export interface HoOutreachData {
  summary?: string;
  contacts?: HoContact[];
  fallback?: HoFallback;
  generated_at?: string;
}

let sessionId: string | null = null;
let eventListenersAttached = false;
let wsListenerAttached = false;
let pollTimeoutId: number | null = null;
let isBusy = false;
let hasAiConfigured = true;
let apiKeyStatusLoaded = false;
let cachedOutreach: HoOutreachData | null = null;

export function getSessionId(): string | null {
  return sessionId;
}

export function setSessionId(id: string | null): void {
  sessionId = id;
}

export function getEventListenersAttached(): boolean {
  return eventListenersAttached;
}

export function setEventListenersAttached(v: boolean): void {
  eventListenersAttached = v;
}

export function getWsListenerAttached(): boolean {
  return wsListenerAttached;
}

export function setWsListenerAttached(v: boolean): void {
  wsListenerAttached = v;
}

export function getPollTimeoutId(): number | null {
  return pollTimeoutId;
}

export function setPollTimeoutId(id: number | null): void {
  pollTimeoutId = id;
}

export function getIsBusy(): boolean {
  return isBusy;
}

export function setIsBusy(v: boolean): void {
  isBusy = v;
}

export function getHasAiConfigured(): boolean {
  return hasAiConfigured;
}

export function setHasAiConfigured(v: boolean): void {
  hasAiConfigured = v;
}

export function getApiKeyStatusLoaded(): boolean {
  return apiKeyStatusLoaded;
}

export function setApiKeyStatusLoaded(v: boolean): void {
  apiKeyStatusLoaded = v;
}

export function getCachedOutreach(): HoOutreachData | null {
  return cachedOutreach;
}

export function setCachedOutreach(data: HoOutreachData | null): void {
  cachedOutreach = data;
}

export function getContactAt(index: number): HoContact | null {
  const contacts = cachedOutreach?.contacts;
  if (!Array.isArray(contacts) || index < 0 || index >= contacts.length) return null;
  return contacts[index] ?? null;
}
