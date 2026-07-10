export const WS_MAX_RECONNECT_ATTEMPTS = 8;
export const WS_RECONNECT_BASE_MS = 1000;

export let sessionId: string | null = null;
export let interviewPrepData: Record<string, unknown> | null = null;
export let pollAbortController: AbortController | null = null;
export let ws: WebSocket | null = null;
export let wsReconnectTimer: number | null = null;
export let wsReconnectAttempts = 0;

export function setSessionId(id: string | null): void {
  sessionId = id;
}

export function setInterviewPrepData(data: Record<string, unknown> | null): void {
  interviewPrepData = data;
}

export function setPollAbortController(controller: AbortController | null): void {
  pollAbortController = controller;
}

export function setWs(socket: WebSocket | null): void {
  ws = socket;
}

export function setWsReconnectTimer(timer: number | null): void {
  wsReconnectTimer = timer;
}

export function setWsReconnectAttempts(attempts: number): void {
  wsReconnectAttempts = attempts;
}

export function incrementWsReconnectAttempts(): void {
  wsReconnectAttempts += 1;
}

export function resetWsReconnectAttempts(): void {
  wsReconnectAttempts = 0;
}
