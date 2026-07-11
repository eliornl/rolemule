import {
  apiKeyStatusLoaded,
  coverLetter,
  eventListenersAttached,
  hasAiConfigured,
  optimizedCv,
  pollAbortController,
  pollTimeoutId,
  sessionId,
  uiState,
  wsListenerAttached,
} from './state';

export {
  setApiKeyStatusLoaded,
  setCoverLetter,
  setEventListenersAttached,
  setHasAiConfigured,
  setOptimizedCv,
  setPollAbortController,
  setPollTimeoutId,
  setSessionId,
  setUiState,
  setWsListenerAttached,
} from './state';

export function getSessionId(): string | null { return sessionId; }
export function getUiState() { return uiState; }
export function getOptimizedCv(): string { return optimizedCv; }
export function getCoverLetter(): string { return coverLetter; }
export function getWsListenerAttached(): boolean { return wsListenerAttached; }
export function getPollAbortController(): AbortController | null { return pollAbortController; }
export function getPollTimeoutId(): number | null { return pollTimeoutId; }
export function getEventListenersAttached(): boolean { return eventListenersAttached; }
export function getHasAiConfigured(): boolean { return hasAiConfigured; }
export function getApiKeyStatusLoaded(): boolean { return apiKeyStatusLoaded; }
