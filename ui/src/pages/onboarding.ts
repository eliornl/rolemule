/**
 * Migrated from ui/static/js/onboarding.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
/**
 * Onboarding Tutorial System
 * Interactive step-by-step guide for new users.
 * 
 * Usage:
 * - Automatically shows for new users (checks localStorage)
 * - Can be triggered manually: Onboarding.start()
 * - Skip/complete saves to localStorage
 * 
 * API:
 * - Onboarding.start() - Start the tutorial
 * - Onboarding.next() - Go to next step
 * - Onboarding.prev() - Go to previous step
 * - Onboarding.skip() - Skip the tutorial
 * - Onboarding.reset() - Reset and show again
 */

(function() {
    'use strict';

    const ONBOARDING_KEY = 'onboarding_completed';
    const ONBOARDING_VERSION = '2.0';

    // All possible tutorial steps
    const ALL_STEPS = [
        {
            id: 'welcome',
            title: 'Welcome to ApplyPilot! 🎉',
            content: `
                <p>Your AI-powered career co-pilot is ready to help you land your dream job.</p>
                <p>Let's take a quick tour so you know exactly what's available.</p>
            `,
            image: '🚀',
            position: 'center',
            condition: null // Always show
        },
        {
            id: 'extension',
            title: 'Install Chrome Extension',
            content: `
                <p>Get the most out of ApplyPilot with our <strong>Chrome Extension</strong>!</p>
                <p>With the extension, you can:</p>
                <ul>
                    <li>🌐 Analyze jobs from <strong>any job site or company careers page</strong></li>
                    <li>⚡ One-click job extraction</li>
                    <li>📋 Auto-detect job postings</li>
                </ul>
                <p>Load the extension in 3 steps:</p>
                <ol>
                    <li>Open <strong>chrome://extensions</strong> in Chrome</li>
                    <li>Enable <strong>Developer Mode</strong> (top-right toggle)</li>
                    <li>Click <strong>Load unpacked</strong> and select the <code>extension/</code> folder from the project directory</li>
                </ol>
            `,
            image: '🧩',
            position: 'center',
            condition: null // Always show
        },
        {
            id: 'api-key',
            title: 'Add Your Gemini API Key',
            content: `
                <p>AI features require <strong>your own Gemini API key</strong> from Google AI Studio.</p>
                <ol>
                    <li>Go to <a href="https://aistudio.google.com/api-keys" target="_blank" rel="noopener noreferrer">aistudio.google.com/api-keys</a></li>
                    <li>Click <strong>"Create API Key"</strong></li>
                    <li>Paste it in <strong>Settings → AI Setup</strong></li>
                </ol>
            `,
            image: '🔑',
            highlight: '[href*="settings"]',
            position: 'center',
            condition: 'needsApiKey' // Skipped automatically when user already has a key
        },
        {
            id: 'analyze',
            title: 'Analyze Job Postings',
            content: `
                <p>There are 3 ways to analyze a job:</p>
                <ol>
                    <li><strong>Chrome Extension:</strong> Browse to any job posting and click the extension to auto-extract</li>
                    <li><strong>Paste Job Description:</strong> Copy the full job description and paste it directly</li>
                    <li><strong>File Upload:</strong> Upload a saved job description file</li>
                </ol>
                <p>Our AI will analyze the job, research the company, match your profile, and create personalized materials!</p>
            `,
            image: '📋',
            highlight: '[href*="new-application"]',
            position: 'center',
            condition: null // Always show
        },
        {
            id: 'tools',
            title: 'Career Tools',
            content: `
                <p>Beyond job analysis, we have <strong>6 career tools</strong> to help throughout your search:</p>
                <ul>
                    <li>📝 Thank You Notes</li>
                    <li>📊 Rejection Analysis</li>
                    <li>👥 Reference Requests</li>
                    <li>⚖️ Job Comparison</li>
                    <li>📧 Follow-up Emails</li>
                    <li>💰 Salary Negotiation</li>
                </ul>
            `,
            image: '🛠️',
            highlight: '[href*="tools"]',
            position: 'center',
            condition: null // Always show
        }
    ];

    // Active steps (filtered based on conditions)
    let STEPS = [];

    const Onboarding = {
        currentStep: 0,
        overlay: null,
        modal: null,
        serverHasApiKey: false,

        /**
         * Check if onboarding should show — only for users who have never seen it
         */
        shouldShow: function() {
            try {
                return !localStorage.getItem(ONBOARDING_KEY);
            } catch (e) {
                return true;
            }
        },

        /**
         * Check if server has API key configured
         */
        checkServerApiKey: async function() {
            try {
                const token = localStorage.getItem('access_token') || localStorage.getItem('authToken');
                const res = await fetch('/api/v1/profile/api-key/status', {
                    headers: token ? { 'Authorization': 'Bearer ' + token } : {}
                });
                if (!res.ok) return false;
                const data = await res.json();
                // If user has key, server has key, or server uses Vertex AI — no setup needed
                return data.has_user_key || data.server_has_key || data.use_vertex_ai;
            } catch (e) {
                console.warn('Could not check API key status:', e);
                return false;
            }
        },

        /**
         * Filter steps based on conditions
         */
        filterSteps: function() {
            STEPS = ALL_STEPS.filter(step => {
                if (step.condition === null) return true;
                if (step.condition === 'needsApiKey') return !this.serverHasApiKey;
                return true;
            });
        },

        /**
         * True when the account already has job applications (returning user).
         */
        _userHasExistingApplications: async function() {
            try {
                const token = localStorage.getItem('access_token') || localStorage.getItem('authToken');
                if (!token) return false;
                const res = await fetch('/api/v1/applications/stats/overview', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (!res.ok) return false;
                const stats = await res.json();
                return (stats.total_applications || 0) > 0;
            } catch (e) {
                console.warn('Could not check application stats for onboarding:', e);
                return false;
            }
        },

        /**
         * Initialize onboarding
         */
        init: async function() {
            if (!this.shouldShow()) {
                return;
            }

            // Tour state is browser-local; returning users who cleared storage or switched
            // browsers should not see the welcome tour again.
            if (await this._userHasExistingApplications()) {
                this._markComplete();
                return;
            }

            // Check server API key status first
            this.serverHasApiKey = await this.checkServerApiKey();
            this.filterSteps();

            // Slight delay to let page render
            setTimeout(() => this.start(), 500);
        },

        /**
         * Start the tutorial
         */
        start: function() {
            // Re-filter in case called directly
            if (STEPS.length === 0) {
                this.filterSteps();
            }
            this.currentStep = 0;
            this._createOverlay();
            this._render();
        },

        /**
         * Go to next step
         */
        next: function() {
            if (this.currentStep < STEPS.length - 1) {
                this.currentStep++;
                this._render();
            } else {
                this.complete();
            }
        },

        /**
         * Go to previous step
         */
        prev: function() {
            if (this.currentStep > 0) {
                this.currentStep--;
                this._render();
            }
        },

        /**
         * Skip the tutorial
         */
        skip: function() {
            this._markComplete();
            this._destroy();
        },

        /**
         * Complete the tutorial
         */
        complete: function() {
            this._markComplete();
            this._destroy();
        },

        /**
         * Reset onboarding (show again)
         */
        reset: async function() {
            localStorage.removeItem(ONBOARDING_KEY);
            this.serverHasApiKey = await this.checkServerApiKey();
            this.filterSteps();
            this.start();
        },

        /**
         * Mark as completed in localStorage
         */
        _markComplete: function() {
            try {
                localStorage.setItem(ONBOARDING_KEY, JSON.stringify({
                    version: ONBOARDING_VERSION,
                    completedAt: new Date().toISOString()
                }));
            } catch (e) {
                console.warn('Could not save onboarding status:', e);
            }
        },

        /**
         * Create overlay and modal elements
         */
        _createOverlay: function() {

            // Create overlay
            this.overlay = document.createElement('div');
            this.overlay.id = 'onboarding-overlay';
            this.overlay.innerHTML = `
                <div class="onboarding-modal" id="onboarding-modal">
                    <div class="onboarding-image" id="onboarding-image"></div>
                    <div class="onboarding-content">
                        <h2 class="onboarding-title" id="onboarding-title"></h2>
                        <div class="onboarding-body" id="onboarding-body"></div>
                    </div>
                    <div class="onboarding-progress" id="onboarding-progress"></div>
                    <div class="onboarding-actions">
                        <button class="onboarding-btn onboarding-btn-skip" data-action="onboarding-skip">
                            Skip Tour
                        </button>
                        <div class="onboarding-nav">
                            <button class="onboarding-btn onboarding-btn-prev" id="onboarding-prev" data-action="onboarding-prev">
                                <i class="fas fa-arrow-left"></i> Back
                            </button>
                            <button class="onboarding-btn onboarding-btn-next" id="onboarding-next" data-action="onboarding-next">
                                Next <i class="fas fa-arrow-right"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
            document.body.appendChild(this.overlay);
            this.modal = document.getElementById('onboarding-modal');

            // Wire up buttons via event delegation (no inline onclick)
            this.overlay.addEventListener('click', function (e) {
                const el = /** @type {HTMLElement} */ (e.target);
                const actionEl = /** @type {HTMLElement|null} */ (el.closest('[data-action]'));
                if (!actionEl) return;
                switch (actionEl.dataset['action']) {
                    case 'onboarding-skip': Onboarding.skip(); break;
                    case 'onboarding-prev': Onboarding.prev(); break;
                    case 'onboarding-next': Onboarding.next(); break;
                }
            });

            // Animate in
            setTimeout(() => {
                this.overlay.classList.add('visible');
            }, 10);
        },

        /**
         * Render current step
         */
        _render: function() {
            const step = STEPS[this.currentStep];
            
            // Update content
            const imgEl = document.getElementById('onboarding-image');
            const titleEl = document.getElementById('onboarding-title');
            const bodyEl = document.getElementById('onboarding-body');
            const progressEl = document.getElementById('onboarding-progress');
            const prevBtn = document.getElementById('onboarding-prev');
            const nextBtn = document.getElementById('onboarding-next');

            if (!imgEl || !titleEl || !bodyEl || !progressEl || !prevBtn || !nextBtn) {
                return;
            }

            imgEl.textContent = step.image;
            titleEl.textContent = step.title;
            bodyEl.innerHTML = step.content;

            // Update progress dots
            const progressHtml = STEPS.map((s, i) => 
                `<span class="progress-dot ${i === this.currentStep ? 'active' : ''} ${i < this.currentStep ? 'completed' : ''}"></span>`
            ).join('');
            progressEl.innerHTML = progressHtml;

            // Update buttons
            prevBtn.style.visibility = this.currentStep === 0 ? 'hidden' : 'visible';
            
            if (this.currentStep === STEPS.length - 1) {
                nextBtn.innerHTML = 'Get Started <i class="fas fa-check"></i>';
            } else {
                nextBtn.innerHTML = 'Next <i class="fas fa-arrow-right"></i>';
            }

            // Handle element highlighting
            this._clearHighlights();
            if (step.highlight) {
                const element = document.querySelector(step.highlight);
                if (element) {
                    element.classList.add('onboarding-highlight');
                }
            }
        },

        /**
         * Clear all highlights
         */
        _clearHighlights: function() {
            document.querySelectorAll('.onboarding-highlight').forEach(el => {
                el.classList.remove('onboarding-highlight');
            });
        },

        /**
         * Destroy the overlay
         */
        _destroy: function() {
            this._clearHighlights();
            if (this.overlay) {
                this.overlay.classList.remove('visible');
                setTimeout(() => {
                    this.overlay.remove();
                    this.overlay = null;
                    this.modal = null;
                }, 300);
            }
        },

    };

    // Auto-initialize on dashboard pages
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            // Only auto-show on dashboard
            if (window.location.pathname.includes('/dashboard')) {
                Onboarding.init();
            }
        });
    } else {
        if (window.location.pathname.includes('/dashboard')) {
            Onboarding.init();
        }
    }

    // Expose to global scope
    window.Onboarding = Onboarding;
})();
