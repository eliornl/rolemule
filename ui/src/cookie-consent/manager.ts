import {
  CONSENT_VERSION,
  type CookieConsentModule,
  type CookiePreferences,
} from './types';
import {
  DEFAULT_PREFERENCES,
  dispatchConsentEvent,
  getStoredConsent,
  saveConsent,
} from './storage';

function wireBannerListeners(banner: HTMLElement, manager: CookieConsentModule): void {
  banner.addEventListener('click', (e) => {
    const actionEl = (e.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!actionEl) return;
    switch (actionEl.dataset.action) {
      case 'show-cookie-preferences':
        e.preventDefault();
        manager.showPreferences();
        break;
      case 'cookie-reject-all':
        manager.rejectAll();
        break;
      case 'cookie-accept-all':
        manager.acceptAll();
        break;
      default:
        break;
    }
  });
}

function wireModalListeners(modal: HTMLElement, manager: CookieConsentModule): void {
  modal.addEventListener('click', (e) => {
    const actionEl = (e.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!actionEl) return;
    switch (actionEl.dataset.action) {
      case 'hide-cookie-preferences':
        manager.hidePreferences();
        break;
      case 'cookie-save-from-modal':
        manager.saveFromModal();
        break;
      default:
        break;
    }
  });
}

export const CookieConsent: CookieConsentModule = {
  init(): void {
    if (!window.APP_CONFIG?.posthogEnabled) return;
    if (!this.hasConsent()) this.showBanner();
  },

  hasConsent(): boolean {
    const consent = getStoredConsent();
    return consent !== null && consent.version === CONSENT_VERSION;
  },

  getPreferences(): CookiePreferences {
    return getStoredConsent() || { ...DEFAULT_PREFERENCES };
  },

  acceptAll(): void {
    const preferences: CookiePreferences = {
      essential: true,
      functional: true,
      analytics: true,
    };
    saveConsent(preferences);
    this.hideBanner();
    dispatchConsentEvent('accept', preferences);
  },

  rejectAll(): void {
    const preferences: CookiePreferences = {
      essential: true,
      functional: false,
      analytics: false,
    };
    saveConsent(preferences);
    this.hideBanner();
    dispatchConsentEvent('reject', preferences);
  },

  savePreferences(preferences: Partial<Pick<CookiePreferences, 'functional' | 'analytics'>>): void {
    const prefs: CookiePreferences = {
      essential: true,
      functional: preferences.functional || false,
      analytics: preferences.analytics || false,
    };
    saveConsent(prefs);
    this.hideBanner();
    dispatchConsentEvent('save', prefs);
  },

  showBanner(): void {
    this.hideBanner();
    const banner = document.createElement('div');
    banner.id = 'cookie-consent-banner';
    banner.innerHTML = `
                <div class="cookie-consent-content">
                    <div class="cookie-consent-text">
                        <p class="cookie-heading" role="heading" aria-level="2"><strong>🍪 Cookie Notice</strong></p>
                        <p>This app uses cookies. Essential cookies are required for the app to function. Optional cookies help improve your experience.</p>
                        <p class="cookie-links">
                            <a href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a> · 
                            <a href="#" data-action="show-cookie-preferences">Customize</a>
                        </p>
                    </div>
                    <div class="cookie-consent-actions">
                        <button class="cookie-btn cookie-btn-reject" data-action="cookie-reject-all">
                            Essential Only
                        </button>
                        <button class="cookie-btn cookie-btn-accept" data-action="cookie-accept-all">
                            Accept All
                        </button>
                    </div>
                </div>
            `;
    document.body.appendChild(banner);
    wireBannerListeners(banner, this);
    window.setTimeout(() => banner.classList.add('visible'), 100);
  },

  showPreferences(): void {
    const prefs = this.getPreferences();
    const modal = document.createElement('div');
    modal.id = 'cookie-preferences-modal';
    modal.innerHTML = `
                <div class="cookie-modal-backdrop" data-action="hide-cookie-preferences"></div>
                <div class="cookie-modal-content">
                    <div class="cookie-modal-header">
                        <h3>Cookie Preferences</h3>
                        <button class="cookie-modal-close" data-action="hide-cookie-preferences" aria-label="Close preferences">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="cookie-modal-body">
                        <div class="cookie-category">
                            <div class="cookie-category-header">
                                <label>
                                    <input type="checkbox" checked disabled>
                                    <span class="cookie-category-name">Essential Cookies</span>
                                    <span class="cookie-required">Required</span>
                                </label>
                            </div>
                            <p class="cookie-category-desc">
                                Required for the website to function properly. These cannot be disabled.
                                Includes authentication, session management, and security features.
                            </p>
                        </div>
                        
                        <div class="cookie-category">
                            <div class="cookie-category-header">
                                <label>
                                    <input type="checkbox" id="pref-functional" ${prefs.functional ? 'checked' : ''}>
                                    <span class="cookie-category-name">Functional Cookies</span>
                                </label>
                            </div>
                            <p class="cookie-category-desc">
                                Remember your preferences and settings to provide a better experience.
                            </p>
                        </div>
                        
                        <div class="cookie-category">
                            <div class="cookie-category-header">
                                <label>
                                    <input type="checkbox" id="pref-analytics" ${prefs.analytics ? 'checked' : ''}>
                                    <span class="cookie-category-name">Analytics Cookies</span>
                                </label>
                            </div>
                            <p class="cookie-category-desc">
                                Help us understand how you use our website so we can improve it.
                                We use privacy-friendly analytics (PostHog) that respects your data.
                            </p>
                        </div>
                    </div>
                    <div class="cookie-modal-footer">
                        <button class="cookie-btn cookie-btn-secondary" data-action="hide-cookie-preferences">
                            Cancel
                        </button>
                        <button class="cookie-btn cookie-btn-accept" data-action="cookie-save-from-modal">
                            Save Preferences
                        </button>
                    </div>
                </div>
            `;
    document.body.appendChild(modal);
    wireModalListeners(modal, this);
    window.setTimeout(() => modal.classList.add('visible'), 10);
  },

  hidePreferences(): void {
    const modal = document.getElementById('cookie-preferences-modal');
    if (modal) {
      modal.classList.remove('visible');
      window.setTimeout(() => modal.remove(), 300);
    }
  },

  saveFromModal(): void {
    const functional =
      (document.getElementById('pref-functional') as HTMLInputElement | null)?.checked ||
      false;
    const analytics =
      (document.getElementById('pref-analytics') as HTMLInputElement | null)?.checked ||
      false;
    this.savePreferences({ functional, analytics });
    this.hidePreferences();
  },

  hideBanner(): void {
    const banner = document.getElementById('cookie-consent-banner');
    if (banner) {
      banner.classList.remove('visible');
      window.setTimeout(() => banner.remove(), 300);
    }
  },
};
