export const CONSENT_KEY = 'cookie_consent';
export const CONSENT_VERSION = '1.0';

export interface CookiePreferences {
  essential: boolean;
  functional: boolean;
  analytics: boolean;
  version?: string;
  timestamp?: string | null;
}

export interface CookieConsentModule {
  init: () => void;
  hasConsent: () => boolean;
  getPreferences: () => CookiePreferences;
  acceptAll: () => void;
  rejectAll: () => void;
  savePreferences: (preferences: Partial<Pick<CookiePreferences, 'functional' | 'analytics'>>) => void;
  showBanner: () => void;
  showPreferences: () => void;
  hidePreferences: () => void;
  saveFromModal: () => void;
  hideBanner: () => void;
}
