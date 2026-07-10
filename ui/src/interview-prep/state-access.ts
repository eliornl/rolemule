import {
  interviewPrepData,
  pollAbortController,
  sessionId,
  ws,
  wsReconnectAttempts,
  wsReconnectTimer,
} from './state';

export {
  incrementWsReconnectAttempts,
  resetWsReconnectAttempts,
  setInterviewPrepData,
  setPollAbortController,
  setSessionId,
  setWs,
  setWsReconnectAttempts,
  setWsReconnectTimer,
} from './state';

export function getSessionId(): string | null {
  return sessionId;
}

export function getInterviewPrepData(): Record<string, unknown> | null {
  return interviewPrepData;
}

export function getPollAbortController(): AbortController | null {
  return pollAbortController;
}

export function getWs(): WebSocket | null {
  return ws;
}

export function getWsReconnectTimer(): number | null {
  return wsReconnectTimer;
}

export function getWsReconnectAttempts(): number {
  return wsReconnectAttempts;
}
