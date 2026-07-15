/** Shared state for Practice Interview tab. */

export type MockStyle = 'hr' | 'pro' | 'manager';

export interface MockActiveRun {
  run_id: string;
  status: string;
  style: MockStyle;
  duration_minutes: number;
  ends_at?: string;
  turns?: Array<Record<string, unknown>>;
  debrief?: Record<string, unknown> | null;
}

let sessionId: string | null = null;
let eventListenersAttached = false;
let wsListenerAttached = false;
let pollTimeoutId: number | null = null;
let countdownTimerId: number | null = null;
let isBusy = false;
let lastSpeak = '';

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
export function getCountdownTimerId(): number | null {
  return countdownTimerId;
}
export function setCountdownTimerId(id: number | null): void {
  countdownTimerId = id;
}
export function getIsBusy(): boolean {
  return isBusy;
}
export function setIsBusy(v: boolean): void {
  isBusy = v;
}
export function getLastSpeak(): string {
  return lastSpeak;
}
export function setLastSpeak(s: string): void {
  lastSpeak = s;
}
