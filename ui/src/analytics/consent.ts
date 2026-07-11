import type { CookieConsentPreferences } from './types';

export function hasAnalyticsConsent(): boolean {
  try {
    const consent = localStorage.getItem('cookie_consent');
    if (!consent) return false;
    const preferences = JSON.parse(consent) as CookieConsentPreferences;
    return preferences.analytics === true;
  } catch {
    return false;
  }
}
