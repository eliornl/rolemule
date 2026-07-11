/**
 * GDPR cookie consent banner — skipped when PostHog is disabled.
 */
import { CookieConsent } from '../cookie-consent/manager';

function initCookieConsent(): void {
  CookieConsent.init();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initCookieConsent);
} else {
  initCookieConsent();
}

window.CookieConsent = CookieConsent;
