import {
  CONSENT_KEY,
  CONSENT_VERSION,
  type CookiePreferences,
} from './types';

export const DEFAULT_PREFERENCES: CookiePreferences = {
  essential: true,
  functional: false,
  analytics: false,
  version: CONSENT_VERSION,
  timestamp: null,
};

export function getStoredConsent(): CookiePreferences | null {
  try {
    const stored = localStorage.getItem(CONSENT_KEY);
    if (stored) return JSON.parse(stored) as CookiePreferences;
  } catch (e) {
    console.warn('Error reading cookie consent:', e);
  }
  return null;
}

export function saveConsent(preferences: CookiePreferences): void {
  try {
    preferences.timestamp = new Date().toISOString();
    preferences.version = CONSENT_VERSION;
    localStorage.setItem(CONSENT_KEY, JSON.stringify(preferences));
  } catch (e) {
    console.warn('Error saving cookie consent:', e);
  }
}

export function dispatchConsentEvent(
  type: string,
  preferences: CookiePreferences,
): void {
  window.dispatchEvent(
    new CustomEvent('cookieConsent', { detail: { type, preferences } }),
  );
  window.dispatchEvent(new CustomEvent('cookieConsentUpdated'));
}
