export interface PostHogConfig {
  apiKey?: string;
  apiHost?: string;
  debug?: boolean;
  autocapture?: boolean;
  capture_pageview?: boolean;
  capture_pageleave?: boolean;
  persistence?: string;
  disable_session_recording?: boolean;
}

export interface CookieConsentPreferences {
  analytics?: boolean;
  functional?: boolean;
  essential?: boolean;
  version?: string;
  timestamp?: string | null;
}

export interface QueuedAnalyticsCall {
  method: 'track' | 'identify' | 'page';
  args: unknown[];
}

export interface AnalyticsModule {
  initialized: boolean;
  queue: QueuedAnalyticsCall[];
  init: (apiKey?: string, options?: PostHogConfig) => void;
  track: (eventName: string, properties?: Record<string, unknown>) => void;
  identify: (userId: string, traits?: Record<string, unknown>) => void;
  page: (pageName: string, properties?: Record<string, unknown>) => void;
  reset: () => void;
  setUserProperties: (properties: Record<string, unknown>) => void;
  optOut: () => void;
  optIn: () => void;
  trackSignup: (method?: string) => void;
  trackLogin: (method?: string) => void;
  trackLogout: () => void;
  trackProfileCompleted: (completionPercent?: number) => void;
  trackWorkflowStarted: (details?: Record<string, unknown>) => void;
  trackWorkflowCompleted: (details?: Record<string, unknown>) => void;
  trackWorkflowFailed: (error: string, failedAgent?: string) => void;
  trackToolUsed: (toolName: string) => void;
  trackFeature: (featureName: string, action?: string) => void;
  trackHelpViewed: (helpType?: string, topic?: string) => void;
  trackError: (errorType: string, errorMessage: string, context?: string) => void;
}

export interface PostHogClient {
  init: (apiKey: string, options: Record<string, unknown>) => void;
  capture: (eventName: string, properties?: Record<string, unknown>) => void;
  identify: (userId: string, traits?: Record<string, unknown>) => void;
  reset: () => void;
  setPersonProperties: (properties: Record<string, unknown>) => void;
  opt_out_capturing: () => void;
  opt_in_capturing: () => void;
  debug: () => void;
}

declare global {
  interface Window {
    posthog?: PostHogClient;
  }
}

export {};
