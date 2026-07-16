/** Shared state for Practice Interview tab. */

import { decodeEntities } from '../shared/dom-security';

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
let lastPlan: Array<Record<string, unknown>> = [];
let lastCoveredPlanIds: string[] = [];

export function getSessionId(): string | null {
  return sessionId;
}
export function setSessionId(id: string | null): void {
  sessionId = id;
}

export function getLastPlan(): Array<Record<string, unknown>> {
  return lastPlan;
}
export function getLastCoveredPlanIds(): string[] {
  return lastCoveredPlanIds;
}
export function setPlanCoverage(
  plan: Array<Record<string, unknown>>,
  covered: string[],
): void {
  lastPlan = plan;
  lastCoveredPlanIds = covered;
}
export function clearPlanCoverage(): void {
  lastPlan = [];
  lastCoveredPlanIds = [];
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
  // sanitize_llm_output HTML-escapes stored speak; keep plain text for TTS / replay
  lastSpeak = decodeEntities(s);
}
