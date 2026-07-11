export interface User {
  id?: string;
  email?: string;
  [key: string]: unknown;
}

export interface ApiCallOptions extends RequestInit {
  headers?: Record<string, string>;
  skipTokenRefresh?: boolean;
}

export interface ApiError extends Error {
  errorCode?: string;
  details?: unknown;
}

export type NotificationType = 'info' | 'success' | 'error' | 'warning';

export interface ModalOptions {
  confirmText?: string;
  cancelText?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
  size?: string;
  footer?: string;
}

export interface ApiFormResponse {
  success?: boolean;
  message?: string;
  redirect?: string;
  [key: string]: unknown;
}
