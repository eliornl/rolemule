import { getPostHogConfig } from './config';
import { hasAnalyticsConsent } from './consent';
import { injectPostHogStub } from './posthog-snippet';
import type { AnalyticsModule, PostHogConfig, QueuedAnalyticsCall } from './types';

function loadPostHogSnippet(): void {
  injectPostHogStub();
}

function setupConsentListener(analytics: AnalyticsModule): void {
  window.addEventListener('storage', (e) => {
    if (e.key === 'cookie_consent' && hasAnalyticsConsent()) {
      loadPostHog(getPostHogConfig(), analytics);
    }
  });
  window.addEventListener('cookieConsentUpdated', () => {
    if (hasAnalyticsConsent() && !analytics.initialized) {
      loadPostHog(getPostHogConfig(), analytics);
    }
  });
}

function flushQueue(analytics: AnalyticsModule): void {
  while (analytics.queue.length > 0) {
    const event = analytics.queue.shift();
    if (!event) continue;
    if (event.method === 'track') {
      analytics.track(
        event.args[0] as string,
        (event.args[1] as Record<string, unknown>) || {},
      );
    } else if (event.method === 'identify') {
      analytics.identify(
        event.args[0] as string,
        (event.args[1] as Record<string, unknown>) || {},
      );
    } else if (event.method === 'page') {
      analytics.page(
        event.args[0] as string,
        (event.args[1] as Record<string, unknown>) || {},
      );
    }
  }
}

function loadPostHog(config: PostHogConfig, analytics: AnalyticsModule): void {
  loadPostHogSnippet();
  const posthog = window.posthog;
  if (!posthog) return;

  posthog.init(config.apiKey || '', {
    api_host: config.apiHost,
    autocapture: config.autocapture,
    capture_pageview: config.capture_pageview,
    capture_pageleave: config.capture_pageleave,
    persistence: config.persistence,
    disable_session_recording: config.disable_session_recording,
    loaded: (client: { debug: () => void }) => {
      if (config.debug) client.debug();
      analytics.initialized = true;
      flushQueue(analytics);
      console.log('Analytics: PostHog initialized');
    },
  });
  analytics.initialized = true;
}

export const Analytics: AnalyticsModule = {
  initialized: false,
  queue: [] as QueuedAnalyticsCall[],

  init(apiKey?: string, options: PostHogConfig = {}): void {
    if (this.initialized) {
      console.warn('Analytics already initialized');
      return;
    }
    const config = { ...getPostHogConfig(), ...options, apiKey: apiKey || getPostHogConfig().apiKey };
    if (!config.apiKey) {
      console.warn('Analytics: No PostHog API key configured. Analytics disabled.');
      return;
    }
    if (!hasAnalyticsConsent()) {
      console.log('Analytics: User has not consented to analytics cookies. Tracking disabled.');
      setupConsentListener(this);
      return;
    }
    loadPostHog(config, this);
  },

  track(eventName: string, properties: Record<string, unknown> = {}): void {
    if (!hasAnalyticsConsent()) return;
    if (!this.initialized || typeof window.posthog === 'undefined') {
      this.queue.push({ method: 'track', args: [eventName, properties] });
      return;
    }
    window.posthog.capture(eventName, {
      ...properties,
      page_path: window.location.pathname,
      page_url: window.location.href,
      timestamp: new Date().toISOString(),
    });
  },

  identify(userId: string, traits: Record<string, unknown> = {}): void {
    if (!hasAnalyticsConsent()) return;
    if (!this.initialized || typeof window.posthog === 'undefined') {
      this.queue.push({ method: 'identify', args: [userId, traits] });
      return;
    }
    window.posthog.identify(userId, traits);
  },

  page(pageName: string, properties: Record<string, unknown> = {}): void {
    if (!hasAnalyticsConsent()) return;
    if (!this.initialized || typeof window.posthog === 'undefined') {
      this.queue.push({ method: 'page', args: [pageName, properties] });
      return;
    }
    window.posthog.capture('$pageview', {
      $current_url: window.location.href,
      page_name: pageName,
      ...properties,
    });
  },

  reset(): void {
    window.posthog?.reset();
  },

  setUserProperties(properties: Record<string, unknown>): void {
    if (!hasAnalyticsConsent()) return;
    window.posthog?.setPersonProperties(properties);
  },

  optOut(): void {
    window.posthog?.opt_out_capturing();
  },

  optIn(): void {
    window.posthog?.opt_in_capturing();
  },

  trackSignup(method = 'email'): void {
    this.track('user_signed_up', { signup_method: method });
  },

  trackLogin(method = 'email'): void {
    this.track('user_logged_in', { login_method: method });
  },

  trackLogout(): void {
    this.track('user_logged_out');
    this.reset();
  },

  trackProfileCompleted(completionPercent = 100): void {
    this.track('profile_completed', { completion_percent: completionPercent });
  },

  trackWorkflowStarted(details: Record<string, unknown> = {}): void {
    this.track('workflow_started', {
      input_method: details.inputMethod || 'unknown',
      has_job_url: Boolean(details.jobUrl),
      ...details,
    });
  },

  trackWorkflowCompleted(details: Record<string, unknown> = {}): void {
    this.track('workflow_completed', {
      duration_seconds: details.duration || 0,
      match_score: details.matchScore ?? null,
      agents_completed: details.agentsCompleted || 0,
      ...details,
    });
  },

  trackWorkflowFailed(error: string, failedAgent = 'unknown'): void {
    this.track('workflow_failed', {
      error_message: error,
      failed_agent: failedAgent,
    });
  },

  trackToolUsed(toolName: string): void {
    this.track('career_tool_used', { tool_name: toolName });
  },

  trackFeature(featureName: string, action = 'clicked'): void {
    this.track('feature_interaction', {
      feature_name: featureName,
      action,
    });
  },

  trackHelpViewed(helpType = 'page', topic = ''): void {
    this.track('help_viewed', { help_type: helpType, topic });
  },

  trackError(errorType: string, errorMessage: string, context = ''): void {
    this.track('error_occurred', {
      error_type: errorType,
      error_message: errorMessage,
      context,
    });
  },
};
