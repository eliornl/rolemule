/**
 * @fileoverview Sync localStorage profile_completed from GET /api/v1/profile/.
 *
 * Dashboard pages must not redirect using stale localStorage alone (e.g. after
 * server-side migrations). Call syncProfileCompletionFromApi() once on load
 * before protected UI init.
 */
(function () {
    'use strict';

    /** @returns {string|null} */
    function getDefaultAuthToken() {
        // @ts-ignore
        if (window.app && typeof window.app.getAuthToken === 'function') {
            // @ts-ignore
            return window.app.getAuthToken();
        }
        return localStorage.getItem('access_token') || localStorage.getItem('authToken');
    }

    /**
     * Fetch profile, set localStorage profile_completed from completion_status,
     * redirect to setup if incomplete or login if 401.
     *
     * @returns {Promise<boolean>} true if the user may stay on this page
     */
    async function syncProfileCompletionFromApi() {
        const token = getDefaultAuthToken();
        if (!token) return false;

        const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';
        const loginUrl = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';

        try {
            const response = await fetch(`${API_BASE}/profile/`, {
                headers: { Authorization: `Bearer ${token}` },
            });

            if (response.status === 401) {
                window.location.href = loginUrl;
                return false;
            }
            if (response.status === 404) {
                window.location.href = '/profile/setup?edit=true';
                return false;
            }
            if (!response.ok) {
                return false;
            }

            const data = await response.json();
            const completed = Boolean(data.completion_status?.profile_completed);
            localStorage.setItem('profile_completed', completed ? 'true' : 'false');

            if (!completed) {
                window.location.href = '/profile/setup?edit=true';
                return false;
            }
            return true;
        } catch (e) {
            console.error('syncProfileCompletionFromApi:', e);
            return false;
        }
    }

    window.syncProfileCompletionFromApi = syncProfileCompletionFromApi;
})();
