import { STORAGE_KEYS } from './state';

export function checkAuthentication() {
    // @ts-ignore
    const app = window.app;
    if (app && typeof app.isAuthenticated === 'function') {
        if (!app.isAuthenticated()) { window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login'; }
        return;
    }
    // Fallback: read from localStorage directly
    const token = localStorage.getItem('access_token') || localStorage.getItem('authToken');
    if (!token) { window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login'; return; }
    if (token.split('.').length !== 3) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('authToken');
        window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
    }
}

export function logout() {
    // @ts-ignore
    if (window.app && typeof window.app.logout === 'function') { window.app.logout(); return; }
    localStorage.removeItem('access_token');
    localStorage.removeItem('authToken');
    window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
}
