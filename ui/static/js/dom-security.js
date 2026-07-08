/**
 * Shared DOM / log sanitization helpers (loaded globally via base.html).
 * Exported on window for CodeQL barrier models and page scripts.
 */
(function () {
    'use strict';

    /** @param {unknown} value */
    function sanitizeLogValue(value) {
        if (value == null) return '';
        return String(value).replace(/[\r\n\x00-\x1f\x7f]/g, ' ');
    }

    /** @param {string|null|undefined} str */
    function decodeEntities(str) {
        if (str == null) return '';
        const textarea = document.createElement('textarea');
        textarea.innerHTML = String(str);
        return textarea.value;
    }

    /** @param {string|null|undefined} str */
    function escapeHtml(str) {
        if (str == null) return '';
        const decoded = decodeEntities(str);
        const div = document.createElement('div');
        div.textContent = decoded;
        return div.innerHTML;
    }

    /** @param {string|null|undefined} text */
    function stripHtmlForAlert(text) {
        if (text == null) return '';
        const doc = new DOMParser().parseFromString(String(text), 'text/html');
        return doc.body.textContent || '';
    }

    /**
     * Allow only same-origin relative paths for post-auth redirects.
     * @param {string|null|undefined} path
     * @returns {string|null}
     */
    function validateRelativeRedirectPath(path) {
        if (typeof path !== 'string' || path.length === 0) {
            return null;
        }
        if (!/^\/(?!\/)/.test(path)) {
            return null;
        }
        return path;
    }

    window.sanitizeLogValue = sanitizeLogValue;
    window.escapeHtml = escapeHtml;
    window.decodeEntities = decodeEntities;
    window.stripHtmlForAlert = stripHtmlForAlert;
    window.validateRelativeRedirectPath = validateRelativeRedirectPath;
})();
