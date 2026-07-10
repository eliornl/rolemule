import type { PostHogConfig } from './types';

export const DEFAULT_POSTHOG_CONFIG: PostHogConfig = {
  apiKey: '',
  apiHost: 'https://us.i.posthog.com',
  debug: false,
  autocapture: true,
  capture_pageview: true,
  capture_pageleave: true,
  persistence: 'localStorage+cookie',
  disable_session_recording: false,
};

export function getPostHogConfig(): PostHogConfig {
  return { ...DEFAULT_POSTHOG_CONFIG, ...(window.POSTHOG_CONFIG || {}) };
}
