import { getAuthToken } from '../shared/auth';
import {
  getSessionId,
  getWs,
  getWsReconnectAttempts,
  getWsReconnectTimer,
  incrementWsReconnectAttempts,
  resetWsReconnectAttempts,
  setWs,
  setWsReconnectTimer,
} from './state-access';
import {
  WS_MAX_RECONNECT_ATTEMPTS,
  WS_RECONNECT_BASE_MS,
} from './state';
import { loadInterviewPrep } from './load';
import { stopPolling } from './poll';
import { showError, showState } from './ui';
import type { WsMessage } from './types';

export function disconnectWs(): void {
  const timer = getWsReconnectTimer();
  if (timer !== null) {
    clearTimeout(timer);
    setWsReconnectTimer(null);
  }
  const socket = getWs();
  if (socket) {
    try {
      socket.close();
    } catch {
      /* ignore */
    }
    setWs(null);
  }
}

function handleWsMessage(msg: WsMessage): void {
  if (!msg || typeof msg.type !== 'string') return;
  switch (msg.type) {
    case 'interview_prep_complete':
      stopPolling();
      disconnectWs();
      void loadInterviewPrep();
      break;
    case 'interview_prep_error':
      stopPolling();
      disconnectWs();
      showError('Generation failed. Please try again.');
      showState('generate');
      break;
    default:
      break;
  }
}

export function connectWs(): void {
  const sessionId = getSessionId();
  if (!sessionId) return;
  const token = getAuthToken();
  if (!token || typeof WebSocket === 'undefined') return;

  disconnectWs();

  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const url =
    `${proto}://${window.location.host}/api/v1/ws/workflow/` +
    `${encodeURIComponent(sessionId)}?token=${encodeURIComponent(token)}`;

  let socket: WebSocket;
  try {
    socket = new WebSocket(url);
  } catch (e) {
    console.warn('WebSocket connection failed, falling back to polling:', e);
    return;
  }

  setWs(socket);

  socket.onopen = () => {
    resetWsReconnectAttempts();
  };

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data as string) as WsMessage;
      handleWsMessage(msg);
    } catch (e) {
      console.error('Failed to parse WebSocket message:', e);
    }
  };

  socket.onerror = () => {
    console.warn('Interview prep WebSocket error — polling fallback active');
  };

  socket.onclose = (event) => {
    setWs(null);
    const noRetry =
      event.code === 1000 || event.code === 1008 || event.code === 4001;
    if (!noRetry && getWsReconnectAttempts() < WS_MAX_RECONNECT_ATTEMPTS) {
      const delay = Math.min(
        WS_RECONNECT_BASE_MS * 2 ** getWsReconnectAttempts(),
        30000,
      );
      incrementWsReconnectAttempts();
      setWsReconnectTimer(
        window.setTimeout(connectWs, delay),
      );
    }
  };
}
