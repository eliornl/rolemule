/**
 * Module state for the Find jobs chat page.
 */
import type { JobFinderMessage } from './api';

let sessionId: string | null = null;
let phase = '';
let messages: JobFinderMessage[] = [];
let confirmedFilters: Record<string, unknown> = {};
let busy = false;
let wsListenerAttached = false;

export function getSessionId(): string | null {
  return sessionId;
}

export function setSessionId(id: string | null): void {
  sessionId = id;
}

export function getPhase(): string {
  return phase;
}

export function setPhase(value: string): void {
  phase = value;
}

export function getMessages(): JobFinderMessage[] {
  return messages;
}

export function setMessages(next: JobFinderMessage[]): void {
  messages = next;
}

export function getConfirmedFilters(): Record<string, unknown> {
  return confirmedFilters;
}

export function setConfirmedFilters(filters: Record<string, unknown>): void {
  confirmedFilters = filters;
}

export function isBusy(): boolean {
  return busy;
}

export function setBusy(value: boolean): void {
  busy = value;
}

export function getWsListenerAttached(): boolean {
  return wsListenerAttached;
}

export function setWsListenerAttached(value: boolean): void {
  wsListenerAttached = value;
}
