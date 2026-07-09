/**
 * Migrated from ui/static/js/cookie-consent.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
/**
 * Cookie Consent Banner
 * GDPR-compliant cookie consent management.
 * 
 * Usage: Include this script in your HTML pages.
 * The banner will automatically appear if consent hasn't been given.
 * 
 * API:
 * - CookieConsent.hasConsent() - Check if user has given consent
 * - CookieConsent.getPreferences() - Get user's cookie preferences
 * - CookieConsent.showBanner() - Manually show the banner
 * - CookieConsent.acceptAll() - Accept all cookies
 * - CookieConsent.rejectAll() - Reject all optional cookies
 * - CookieConsent.savePreferences(prefs) - Save specific preferences
 */

(function() {
    'use strict';

    const CONSENT_KEY = 'cookie_consent';
    const CONSENT_VERSION = '1.0';

    // Default preferences
    const DEFAULT_PREFERENCES = {
        essential: true,      // Always required - can't be disabled
        functional: false,    // Preference cookies
        analytics: false,     // Analytics cookies (future use)
        version: CONSENT_VERSION,
        timestamp: null
    };

    // Cookie Consent Manager
    const CookieConsent = {
        /**
         * Initialize the cookie consent system.
         * When PostHog analytics is disabled (POSTHOG_ENABLED=false, the default
         * for self-hosted deployments), there is no tracking to consent to, so
         * the banner is skipped entirely.
         */
        init: function() {
            if (!window.APP_CONFIG?.posthogEnabled) {
                return;
            }
            // Check if consent already given
            if (!this.hasConsent()) {
                this.showBanner();
            }
        },

        /**
         * Check if user has given consent
         */
        hasConsent: function() {
            const consent = this._getStoredConsent();
            return consent !== null && consent.version === CONSENT_VERSION;
        },

        /**
         * Get stored consent preferences
         */
        getPreferences: function() {
            const consent = this._getStoredConsent();
            return consent || { ...DEFAULT_PREFERENCES };
        },

        /**
         * Get stored consent from localStorage
         */
        _getStoredConsent: function() {
            try {
                const stored = localStorage.getItem(CONSENT_KEY);
                if (stored) {
                    return JSON.parse(stored);
                }
            } catch (e) {
                console.warn('Error reading cookie consent:', e);
            }
            return null;
        },

        /**
         * Save consent to localStorage
         */
        _saveConsent: function(preferences) {
            try {
                preferences.timestamp = new Date().toISOString();
                preferences.version = CONSENT_VERSION;
                localStorage.setItem(CONSENT_KEY, JSON.stringify(preferences));
            } catch (e) {
                console.warn('Error saving cookie consent:', e);
            }
        },

        /**
         * Accept all cookies
         */
        acceptAll: function() {
            const preferences = {
                essential: true,
                functional: true,
                analytics: true
            };
            this._saveConsent(preferences);
            this.hideBanner();
            this._dispatchEvent('accept', preferences);
        },

        /**
         * Reject all optional cookies (keep essential only)
         */
        rejectAll: function() {
            const preferences = {
                essential: true,
                functional: false,
                analytics: false
            };
            this._saveConsent(preferences);
            this.hideBanner();
            this._dispatchEvent('reject', preferences);
        },

        /**
         * Save specific preferences
         */
        savePreferences: function(preferences) {
            const prefs = {
                essential: true, // Always true
                functional: preferences.functional || false,
                analytics: preferences.analytics || false
            };
            this._saveConsent(prefs);
            this.hideBanner();
            this._dispatchEvent('save', prefs);
        },

        /**
         * Show the cookie consent banner
         */
        showBanner: function() {
            // Remove existing banner if any
            this.hideBanner();

            // Create banner HTML
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

            banner.addEventListener('click', function (e) {
                const el = /** @type {HTMLElement} */ (e.target);
                const actionEl = /** @type {HTMLElement|null} */ (el.closest('[data-action]'));
                if (!actionEl) return;
                switch (actionEl.dataset['action']) {
                    case 'show-cookie-preferences': e.preventDefault(); CookieConsent.showPreferences(); break;
                    case 'cookie-reject-all': CookieConsent.rejectAll(); break;
                    case 'cookie-accept-all': CookieConsent.acceptAll(); break;
                }
            });

            // Animate in
            setTimeout(() => {
                banner.classList.add('visible');
            }, 100);
        },

        /**
         * Show preferences panel
         */
        showPreferences: function() {
            const prefs = this.getPreferences();
            
            // Create modal
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

            modal.addEventListener('click', function (e) {
                const el = /** @type {HTMLElement} */ (e.target);
                const actionEl = /** @type {HTMLElement|null} */ (el.closest('[data-action]'));
                if (!actionEl) return;
                switch (actionEl.dataset['action']) {
                    case 'hide-cookie-preferences': CookieConsent.hidePreferences(); break;
                    case 'cookie-save-from-modal': CookieConsent.saveFromModal(); break;
                }
            });

            // Animate in
            setTimeout(() => {
                modal.classList.add('visible');
            }, 10);
        },

        /**
         * Hide preferences modal
         */
        hidePreferences: function() {
            const modal = document.getElementById('cookie-preferences-modal');
            if (modal) {
                modal.classList.remove('visible');
                setTimeout(() => {
                    modal.remove();
                }, 300);
            }
        },

        /**
         * Save preferences from modal
         */
        saveFromModal: function() {
            const functional = document.getElementById('pref-functional')?.checked || false;
            const analytics = document.getElementById('pref-analytics')?.checked || false;
            
            this.savePreferences({ functional, analytics });
            this.hidePreferences();
        },

        /**
         * Hide the cookie consent banner
         */
        hideBanner: function() {
            const banner = document.getElementById('cookie-consent-banner');
            if (banner) {
                banner.classList.remove('visible');
                setTimeout(() => {
                    banner.remove();
                }, 300);
            }
        },

        /**
         * Dispatch custom event
         */
        _dispatchEvent: function(type, preferences) {
            // Dispatch detailed event
            const event = new CustomEvent('cookieConsent', {
                detail: { type, preferences }
            });
            window.dispatchEvent(event);

            // Also dispatch a simple event for analytics integration
            window.dispatchEvent(new CustomEvent('cookieConsentUpdated'));
        },

        /**
         * @deprecated CSS is now in app.css — this method is intentionally empty.
         */
        _addStyles: function() { return; /* styles live in app.css */ },

        _addStylesLEGACY_UNUSED: function() {
            if (document.getElementById('cookie-consent-styles')) return;

            const styles = document.createElement('style');
            styles.id = 'cookie-consent-styles';
            styles.textContent = `
                #cookie-consent-banner {
                    position: fixed;
                    bottom: 0;
                    left: 0;
                    right: 0;
                    background: linear-gradient(135deg, rgba(15, 15, 35, 0.98), rgba(25, 25, 55, 0.98));
                    backdrop-filter: blur(10px);
                    border-top: 1px solid rgba(99, 102, 241, 0.3);
                    padding: 20px;
                    z-index: 99999;
                    transform: translateY(100%);
                    transition: transform 0.3s ease-out;
                    box-shadow: 0 -5px 30px rgba(0, 0, 0, 0.3);
                }
                
                #cookie-consent-banner.visible {
                    transform: translateY(0);
                }
                
                .cookie-consent-content {
                    max-width: 1200px;
                    margin: 0 auto;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 30px;
                    flex-wrap: wrap;
                }
                
                .cookie-consent-text h4 {
                    color: #fff;
                    margin: 0 0 8px 0;
                    font-size: 1.1rem;
                }
                
                .cookie-consent-text p {
                    color: rgba(255, 255, 255, 0.7);
                    margin: 0;
                    font-size: 0.9rem;
                    line-height: 1.5;
                }
                
                .cookie-links {
                    margin-top: 8px !important;
                }
                
                .cookie-links a {
                    color: #6366f1;
                    text-decoration: none;
                }
                
                .cookie-links a:hover {
                    text-decoration: underline;
                }
                
                .cookie-consent-actions {
                    display: flex;
                    gap: 12px;
                    flex-shrink: 0;
                }
                
                .cookie-btn {
                    padding: 10px 20px;
                    border-radius: 8px;
                    font-weight: 500;
                    font-size: 0.9rem;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    border: none;
                }
                
                .cookie-btn-accept {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                
                .cookie-btn-accept:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                }
                
                .cookie-btn-reject,
                .cookie-btn-secondary {
                    background: rgba(255, 255, 255, 0.1);
                    color: rgba(255, 255, 255, 0.8);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                }
                
                .cookie-btn-reject:hover,
                .cookie-btn-secondary:hover {
                    background: rgba(255, 255, 255, 0.15);
                }
                
                /* Preferences Modal */
                #cookie-preferences-modal {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    z-index: 100000;
                    opacity: 0;
                    transition: opacity 0.3s ease;
                }
                
                #cookie-preferences-modal.visible {
                    opacity: 1;
                }
                
                .cookie-modal-backdrop {
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0, 0, 0, 0.7);
                }
                
                .cookie-modal-content {
                    position: absolute;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    background: linear-gradient(135deg, rgba(20, 20, 45, 0.98), rgba(30, 30, 60, 0.98));
                    border: 1px solid rgba(99, 102, 241, 0.3);
                    border-radius: 16px;
                    width: 90%;
                    max-width: 500px;
                    max-height: 80vh;
                    overflow: auto;
                }
                
                .cookie-modal-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 20px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }
                
                .cookie-modal-header h3 {
                    color: #fff;
                    margin: 0;
                    font-size: 1.2rem;
                }
                
                .cookie-modal-close {
                    background: none;
                    border: none;
                    color: rgba(255, 255, 255, 0.6);
                    font-size: 1.2rem;
                    cursor: pointer;
                    padding: 5px;
                }
                
                .cookie-modal-close:hover {
                    color: #fff;
                }
                
                .cookie-modal-body {
                    padding: 20px;
                }
                
                .cookie-category {
                    margin-bottom: 20px;
                    padding-bottom: 20px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }
                
                .cookie-category:last-child {
                    margin-bottom: 0;
                    padding-bottom: 0;
                    border-bottom: none;
                }
                
                .cookie-category-header {
                    display: flex;
                    align-items: center;
                }
                
                .cookie-category-header label {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    cursor: pointer;
                    flex: 1;
                }
                
                .cookie-category-header input[type="checkbox"] {
                    width: 18px;
                    height: 18px;
                    cursor: pointer;
                }
                
                .cookie-category-name {
                    color: #fff;
                    font-weight: 500;
                }
                
                .cookie-required {
                    background: rgba(99, 102, 241, 0.2);
                    color: #818cf8;
                    padding: 2px 8px;
                    border-radius: 4px;
                    font-size: 0.75rem;
                    margin-left: auto;
                }
                
                .cookie-category-desc {
                    color: rgba(255, 255, 255, 0.6);
                    font-size: 0.85rem;
                    margin: 10px 0 0 28px;
                    line-height: 1.5;
                }
                
                .cookie-modal-footer {
                    display: flex;
                    justify-content: flex-end;
                    gap: 12px;
                    padding: 20px;
                    border-top: 1px solid rgba(255, 255, 255, 0.1);
                }
                
                @media (max-width: 768px) {
                    .cookie-consent-content {
                        flex-direction: column;
                        text-align: center;
                    }
                    
                    .cookie-consent-actions {
                        width: 100%;
                        justify-content: center;
                    }
                    
                    .cookie-btn {
                        flex: 1;
                    }
                }
            `;
            document.head.appendChild(styles);
        },
    };

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => CookieConsent.init());
    } else {
        CookieConsent.init();
    }

    // Expose to global scope
    window.CookieConsent = CookieConsent;
})();
