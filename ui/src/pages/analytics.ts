/**
 * PostHog analytics — respects cookie consent preferences.
 */
import { Analytics } from '../analytics/analytics';

function initAnalytics(): void {
  Analytics.init();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAnalytics);
} else {
  initAnalytics();
}

window.Analytics = Analytics;
