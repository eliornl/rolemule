/**
 * Migrated from ui/static/js/landing.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', () => {
        // Intersection Observer for scroll animations
        const observerOptions = {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('animate-visible');
                }
            });
        }, observerOptions);

        document.querySelectorAll('.animate-fade-up').forEach(el => {
            observer.observe(el);
        });

        // Navbar background on scroll
        const navbar = document.querySelector('.navbar');
        if (navbar) {
            window.addEventListener('scroll', () => {
                if (window.scrollY > 50) {
                    navbar.classList.add('navbar-scrolled');
                } else {
                    navbar.classList.remove('navbar-scrolled');
                }
            });
        }

        // Screenshot showcase — manual tab switching
        const ssTabs = document.querySelectorAll('.ss-tab');
        const ssPanels = document.querySelectorAll('.ss-panel');
        const ssPanelsContainer = /** @type {HTMLElement|null} */ (document.querySelector('.ss-panels'));

        /**
         * Activate a tab by ID and scroll the panel back to the top.
         * @param {string} tabId
         */
        function ssActivateTab(tabId) {
            ssTabs.forEach(t => {
                const tel = /** @type {HTMLElement} */ (t);
                const isActive = tel.dataset['ssTab'] === tabId;
                t.classList.toggle('active', isActive);
                t.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            ssPanels.forEach(p => {
                p.classList.toggle('active', p.id === `ss-panel-${tabId}`);
            });
            if (ssPanelsContainer) ssPanelsContainer.scrollTop = 0;
        }

        if (ssTabs.length > 0) {
            ssTabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    const el = /** @type {HTMLElement} */ (tab);
                    const targetTab = el.dataset['ssTab'];
                    if (targetTab) ssActivateTab(targetTab);
                });
            });
        }
    });

}());
