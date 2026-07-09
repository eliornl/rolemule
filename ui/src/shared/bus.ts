export interface EventBusEvent {
  type: string;
  data: unknown;
  timestamp: number;
}

export type EventHandler = (event: EventBusEvent) => void;

export const BusEvents = {
  AUTH_LOGIN: 'auth:login',
  AUTH_LOGOUT: 'auth:logout',
  AUTH_SESSION_SET: 'auth:session_set',
  AUTH_TOKEN_REFRESHED: 'auth:token_refreshed',
  AUTH_REGISTER: 'auth:register',
  WORKFLOW_STARTED: 'workflow:started',
  WORKFLOW_PROGRESS: 'workflow:progress',
  WORKFLOW_COMPLETE: 'workflow:complete',
  WORKFLOW_ERROR: 'workflow:error',
  WORKFLOW_GATE_FAIL: 'workflow:gate_fail',
  WORKFLOW_CANCELLED: 'workflow:cancelled',
  PROFILE_UPDATED: 'profile:updated',
  PROFILE_SAVED: 'profile:saved',
  PROFILE_SETUP_COMPLETE: 'profile:setup_complete',
  APPLICATION_CREATED: 'application:created',
  APPLICATION_UPDATED: 'application:updated',
  APPLICATION_DELETED: 'application:deleted',
  APPLICATION_STATUS_CHANGED: 'application:status_changed',
  TOOL_GENERATED: 'tool:generated',
  TOOL_ERROR: 'tool:error',
  APIKEY_SAVED: 'apikey:saved',
  APIKEY_DELETED: 'apikey:deleted',
  SETTINGS_UPDATED: 'settings:updated',
  NOTIFY_SUCCESS: 'notify:success',
  NOTIFY_ERROR: 'notify:error',
  NOTIFY_WARNING: 'notify:warning',
  NOTIFY_INFO: 'notify:info',
} as const;

export type BusEventName = (typeof BusEvents)[keyof typeof BusEvents];

/** Prefer the global bus installed by event-bus.js when present. */
export function getEventBus(): {
  on: (event: string, callback: EventHandler) => () => void;
  once: (event: string, callback: EventHandler) => void;
  off: (event: string, callback: EventHandler) => void;
  emit: (event: string, data?: unknown) => void;
} | null {
  return window.eventBus ?? null;
}
