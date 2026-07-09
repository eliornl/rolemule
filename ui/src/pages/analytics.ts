/**
 * Migrated from ui/static/js/analytics.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
/**
 * PostHog Analytics Integration
 * 
 * Provides product analytics tracking with privacy-first approach.
 * Respects user cookie consent preferences.
 * 
 * Usage:
 *   Analytics.track('workflow_started', { job_url: '...' });
 *   Analytics.identify(userId, { email: '...' });
 *   Analytics.page('Dashboard');
 * 
 * Events tracked:
 *   - User: signup, login, logout, profile_completed
 *   - Workflow: workflow_started, workflow_completed, workflow_failed
 *   - Tools: tool_used (with tool name)
 *   - Features: feature_clicked, help_viewed
 */

(function() {
    'use strict';

    // Configuration - set via window.POSTHOG_CONFIG or defaults
    const CONFIG = window.POSTHOG_CONFIG || {
        apiKey: '',  // Set this in your HTML or via environment
        apiHost: 'https://us.i.posthog.com',  // US cloud, or 'https://eu.i.posthog.com' for EU
        debug: false,
        autocapture: true,
        capture_pageview: true,
        capture_pageleave: true,
        persistence: 'localStorage+cookie',
        disable_session_recording: false,
    };

    /**
     * Check if user has consented to analytics cookies
     * Integrates with the cookie-consent.js module
     */
    function hasAnalyticsConsent() {
        try {
            const consent = localStorage.getItem('cookie_consent');
            if (!consent) return false;
            
            const preferences = JSON.parse(consent);
            return preferences.analytics === true;
        } catch (e) {
            return false;
        }
    }

    /**
     * Analytics module
     */
    const Analytics = {
        initialized: false,
        queue: [],  // Queue events before initialization

        /**
         * Initialize PostHog
         * @param {string} apiKey - PostHog project API key
         * @param {Object} options - Additional PostHog options
         */
        init: function(apiKey, options = {}) {
            if (this.initialized) {
                console.warn('Analytics already initialized');
                return;
            }

            // Merge options with defaults
            const config = { ...CONFIG, ...options, apiKey: apiKey || CONFIG.apiKey };

            if (!config.apiKey) {
                console.warn('Analytics: No PostHog API key configured. Analytics disabled.');
                return;
            }

            // Check cookie consent before initializing
            if (!hasAnalyticsConsent()) {
                console.log('Analytics: User has not consented to analytics cookies. Tracking disabled.');
                this._setupConsentListener();
                return;
            }

            this._loadPostHog(config);
        },

        /**
         * Load PostHog script and initialize
         */
        _loadPostHog: function(config) {
            // PostHog snippet (official)
            !function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);

            // Initialize PostHog
            posthog.init(config.apiKey, {
                api_host: config.apiHost,
                autocapture: config.autocapture,
                capture_pageview: config.capture_pageview,
                capture_pageleave: config.capture_pageleave,
                persistence: config.persistence,
                disable_session_recording: config.disable_session_recording,
                loaded: (posthog) => {
                    if (config.debug) {
                        posthog.debug();
                    }
                    this.initialized = true;
                    this._flushQueue();
                    console.log('Analytics: PostHog initialized');
                }
            });

            this.initialized = true;
        },

        /**
         * Listen for cookie consent changes
         */
        _setupConsentListener: function() {
            // Re-check consent when localStorage changes
            window.addEventListener('storage', (e) => {
                if (e.key === 'cookie_consent' && hasAnalyticsConsent()) {
                    this._loadPostHog(CONFIG);
                }
            });

            // Also listen for custom event from cookie-consent.js
            window.addEventListener('cookieConsentUpdated', () => {
                if (hasAnalyticsConsent() && !this.initialized) {
                    this._loadPostHog(CONFIG);
                }
            });
        },

        /**
         * Flush queued events after initialization
         */
        _flushQueue: function() {
            while (this.queue.length > 0) {
                const event = this.queue.shift();
                this[event.method].apply(this, event.args);
            }
        },

        /**
         * Track an event
         * @param {string} eventName - Name of the event
         * @param {Object} properties - Event properties
         */
        track: function(eventName, properties = {}) {
            if (!hasAnalyticsConsent()) return;

            if (!this.initialized || typeof posthog === 'undefined') {
                this.queue.push({ method: 'track', args: [eventName, properties] });
                return;
            }

            // Add common properties
            const enrichedProperties = {
                ...properties,
                page_path: window.location.pathname,
                page_url: window.location.href,
                timestamp: new Date().toISOString(),
            };

            posthog.capture(eventName, enrichedProperties);
        },

        /**
         * Identify a user
         * @param {string} userId - Unique user ID
         * @param {Object} traits - User traits/properties
         */
        identify: function(userId, traits = {}) {
            if (!hasAnalyticsConsent()) return;

            if (!this.initialized || typeof posthog === 'undefined') {
                this.queue.push({ method: 'identify', args: [userId, traits] });
                return;
            }

            posthog.identify(userId, traits);
        },

        /**
         * Track a page view
         * @param {string} pageName - Name of the page
         * @param {Object} properties - Additional properties
         */
        page: function(pageName, properties = {}) {
            if (!hasAnalyticsConsent()) return;

            if (!this.initialized || typeof posthog === 'undefined') {
                this.queue.push({ method: 'page', args: [pageName, properties] });
                return;
            }

            posthog.capture('$pageview', {
                $current_url: window.location.href,
                page_name: pageName,
                ...properties
            });
        },

        /**
         * Reset user identity (on logout)
         */
        reset: function() {
            if (typeof posthog !== 'undefined') {
                posthog.reset();
            }
        },

        /**
         * Set user properties without tracking an event
         * @param {Object} properties - Properties to set
         */
        setUserProperties: function(properties) {
            if (!hasAnalyticsConsent()) return;

            if (typeof posthog !== 'undefined') {
                posthog.setPersonProperties(properties);
            }
        },

        /**
         * Opt user out of tracking
         */
        optOut: function() {
            if (typeof posthog !== 'undefined') {
                posthog.opt_out_capturing();
            }
        },

        /**
         * Opt user back into tracking
         */
        optIn: function() {
            if (typeof posthog !== 'undefined') {
                posthog.opt_in_capturing();
            }
        },

        // =========================================================================
        // CONVENIENCE METHODS FOR COMMON EVENTS
        // =========================================================================

        /**
         * Track user signup
         * @param {string} method - 'email' or 'google'
         */
        trackSignup: function(method = 'email') {
            this.track('user_signed_up', { signup_method: method });
        },

        /**
         * Track user login
         * @param {string} method - 'email' or 'google'
         */
        trackLogin: function(method = 'email') {
            this.track('user_logged_in', { login_method: method });
        },

        /**
         * Track user logout
         */
        trackLogout: function() {
            this.track('user_logged_out');
            this.reset();
        },

        /**
         * Track profile completion
         * @param {number} completionPercent - Profile completion percentage
         */
        trackProfileCompleted: function(completionPercent = 100) {
            this.track('profile_completed', { completion_percent: completionPercent });
        },

        /**
         * Track workflow started
         * @param {Object} details - Workflow details
         */
        trackWorkflowStarted: function(details = {}) {
            this.track('workflow_started', {
                input_method: details.inputMethod || 'unknown',
                has_job_url: !!details.jobUrl,
                ...details
            });
        },

        /**
         * Track workflow completed
         * @param {Object} details - Workflow results
         */
        trackWorkflowCompleted: function(details = {}) {
            this.track('workflow_completed', {
                duration_seconds: details.duration || 0,
                match_score: details.matchScore || null,
                agents_completed: details.agentsCompleted || 0,
                ...details
            });
        },

        /**
         * Track workflow failed
         * @param {string} error - Error message
         * @param {string} failedAgent - Which agent failed
         */
        trackWorkflowFailed: function(error, failedAgent = 'unknown') {
            this.track('workflow_failed', {
                error_message: error,
                failed_agent: failedAgent
            });
        },

        /**
         * Track career tool usage
         * @param {string} toolName - Name of the tool used
         */
        trackToolUsed: function(toolName) {
            this.track('career_tool_used', {
                tool_name: toolName
            });
        },

        /**
         * Track feature interaction
         * @param {string} featureName - Name of the feature
         * @param {string} action - Action taken (clicked, viewed, etc.)
         */
        trackFeature: function(featureName, action = 'clicked') {
            this.track('feature_interaction', {
                feature_name: featureName,
                action: action
            });
        },

        /**
         * Track help/support interaction
         * @param {string} helpType - Type of help (faq, search, contact)
         * @param {string} topic - Topic viewed/searched
         */
        trackHelpViewed: function(helpType = 'page', topic = '') {
            this.track('help_viewed', {
                help_type: helpType,
                topic: topic
            });
        },

        /**
         * Track error occurrence
         * @param {string} errorType - Type of error
         * @param {string} errorMessage - Error message
         * @param {string} context - Where the error occurred
         */
        trackError: function(errorType, errorMessage, context = '') {
            this.track('error_occurred', {
                error_type: errorType,
                error_message: errorMessage,
                context: context
            });
        }
    };

    // Auto-initialize if API key is configured
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            Analytics.init();
        });
    } else {
        Analytics.init();
    }

    // Expose to global scope
    window.Analytics = Analytics;

})();
