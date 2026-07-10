import type { CvOptimizerUiState } from './types';

export const MIN_SCORE_THRESHOLD = 7.0;
export const MAX_SCORE_THRESHOLD = 9.5;

export let sessionId: string | null = null;
export let uiState: CvOptimizerUiState = 'not_started';
export let optimizedCv = '';
export let coverLetter = '';
export let wsListenerAttached = false;
export let pollAbortController: AbortController | null = null;
export let pollTimeoutId: number | null = null;
export let eventListenersAttached = false;
export let hasAiConfigured = true;
export let apiKeyStatusLoaded = false;

export function setSessionId(id: string | null): void { sessionId = id; }
export function setUiState(state: CvOptimizerUiState): void { uiState = state; }
export function setOptimizedCv(text: string): void { optimizedCv = text; }
export function setCoverLetter(text: string): void { coverLetter = text; }
export function setWsListenerAttached(v: boolean): void { wsListenerAttached = v; }
export function setPollAbortController(c: AbortController | null): void { pollAbortController = c; }
export function setPollTimeoutId(id: number | null): void { pollTimeoutId = id; }
export function setEventListenersAttached(v: boolean): void { eventListenersAttached = v; }
export function setHasAiConfigured(v: boolean): void { hasAiConfigured = v; }
export function setApiKeyStatusLoaded(v: boolean): void { apiKeyStatusLoaded = v; }
