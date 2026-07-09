/// <reference types="vite/client" />

export {};

declare global {
  interface Window {
    APP_CONFIG?: {
      apiBase?: string;
      loginUrl?: string;
      posthogEnabled?: boolean;
    };
    POSTHOG_CONFIG?: {
      apiKey?: string;
      apiHost?: string;
    };
    escapeHtml?: (str: string | null | undefined) => string;
    decodeEntities?: (str: string | null | undefined) => string;
    sanitizeLogValue?: (value: unknown) => string;
    stripHtmlForAlert?: (text: string | null | undefined) => string;
    validateRelativeRedirectPath?: (path: string | null | undefined) => string | null;
    showConfirm?: (opts: {
      title: string;
      message: string;
      confirmText?: string;
      cancelText?: string;
      type?: 'danger' | 'warning' | 'primary';
      inputPlaceholder?: string;
      inputType?: string;
      requiredInput?: string;
    }) => Promise<string | boolean | null>;
    resendCode?: () => Promise<void>;
    togglePassword?: (inputId: string) => void;
    handleGoogleLogin?: () => void;
    handleGoogleSignup?: () => void;
    eventBus?: {
      on: (event: string, callback: (event: { type: string; data: unknown; timestamp: number }) => void) => () => void;
      once: (event: string, callback: (event: { type: string; data: unknown; timestamp: number }) => void) => void;
      off: (event: string, callback: (event: { type: string; data: unknown; timestamp: number }) => void) => void;
      emit: (event: string, data?: unknown) => void;
    };
    BusEvents?: Record<string, string>;
    app?: {
      getAuthToken?: () => string | null;
      logout?: () => void;
      showNotification?: (msg: string, type?: string) => void;
      apiCall?: (url: string, options?: RequestInit) => Promise<Response>;
    };
    Onboarding?: unknown;
  }
}
