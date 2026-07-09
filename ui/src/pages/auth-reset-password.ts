/**
 * Migrated from ui/static/js/auth-reset-password.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
(function () {
    'use strict';

    const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';

    /** @param {string|null|undefined} str */
    function escapeHtml(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#x27;');
    }

    document.addEventListener('DOMContentLoaded', function () {
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('token');

        if (token) {
            document.getElementById('forgotPasswordSection')?.classList.add('d-none');
            document.getElementById('resetPasswordSection')?.classList.remove('d-none');
            const resetTokenInput = /** @type {HTMLInputElement|null} */ (document.getElementById('resetToken'));
            if (resetTokenInput) resetTokenInput.value = token;
        }

        const emailInput = /** @type {HTMLInputElement|null} */ (document.getElementById('email'));
        if (emailInput) {
            emailInput.addEventListener('input', function () {
                const container = emailInput.closest('.email-validation-container');
                if (!container) return;
                const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailInput.value);
                container.classList.remove('email-validation-valid', 'email-validation-invalid');
                if (emailInput.value.length > 0) {
                    container.classList.add(isValid ? 'email-validation-valid' : 'email-validation-invalid');
                }
            });
        }

        // Wire password toggle buttons (replaces inline onclick="togglePassword('...')")
        document.querySelectorAll('.password-toggle[data-field]').forEach(btn => {
            btn.addEventListener('click', function () {
                togglePassword(/** @type {HTMLElement} */ (this).dataset['field'] ?? '');
            });
        });

        const newPasswordInput = document.getElementById('newPassword');
        if (newPasswordInput) {
            newPasswordInput.addEventListener('input', updatePasswordUI);
        }

        const confirmPasswordInput = document.getElementById('confirmPassword');
        if (confirmPasswordInput) {
            confirmPasswordInput.addEventListener('input', updateConfirmPasswordUI);
        }
    });

    /** @param {string} password */
    function validatePassword(password) {
        if (!password || password.length < 8) return false;
        return /[A-Z]/.test(password) &&
               /[a-z]/.test(password) &&
               /[0-9]/.test(password) &&
               /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password);
    }

    function updatePasswordUI() {
        const input = /** @type {HTMLInputElement|null} */ (document.getElementById('newPassword'));
        const checkIcon   = document.getElementById('newPasswordCheck');
        const requirements = document.getElementById('newPasswordReq');
        if (!input) return;

        if (validatePassword(input.value)) {
            if (checkIcon)    checkIcon.style.display = 'block';
            if (requirements) requirements.classList.add('hidden');
        } else {
            if (checkIcon)    checkIcon.style.display = 'none';
            if (requirements) requirements.classList.remove('hidden');
        }
        updateConfirmPasswordUI();
    }

    function updateConfirmPasswordUI() {
        const newPassInput  = /** @type {HTMLInputElement|null} */ (document.getElementById('newPassword'));
        const confPassInput = /** @type {HTMLInputElement|null} */ (document.getElementById('confirmPassword'));
        const checkIcon     = document.getElementById('confirmPasswordCheck');
        if (!newPassInput || !confPassInput || !checkIcon) return;

        const matches = confPassInput.value.length > 0 &&
                        newPassInput.value === confPassInput.value &&
                        validatePassword(newPassInput.value);
        checkIcon.style.display = matches ? 'block' : 'none';
    }

    /** @param {string} inputId */
    function togglePassword(inputId) {
        const input = /** @type {HTMLInputElement|null} */ (document.getElementById(inputId));
        const icon  = document.getElementById(inputId + 'Icon');
        if (!input || !icon) return;

        if (input.type === 'password') {
            input.type = 'text';
            icon.classList.replace('fa-eye', 'fa-eye-slash');
        } else {
            input.type = 'password';
            icon.classList.replace('fa-eye-slash', 'fa-eye');
        }
    }

    /**
     * @param {string} elementId
     * @param {string} message
     * @param {string} type
     */
    function showAlert(elementId, message, type) {
        const alertEl = document.getElementById(elementId);
        if (!alertEl) return;
        /** @type {Record<string,string>} */
        const icons = { success: 'check-circle', danger: 'exclamation-triangle', warning: 'exclamation-circle', info: 'info-circle' };
        alertEl.className = `alert alert-${type}`;
        alertEl.innerHTML = `<i class="fas fa-${icons[type] ?? 'info-circle'} me-2"></i>${escapeHtml(message)}`;
        alertEl.classList.remove('d-none');
    }

    /** @param {string} elementId */
    function hideAlert(elementId) {
        document.getElementById(elementId)?.classList.add('d-none');
    }

    /**
     * @param {HTMLButtonElement} btn
     * @param {boolean} loading
     */
    function setButtonLoading(btn, loading) {
        const text    = btn.querySelector('.btn-text');
        const spinner = btn.querySelector('.btn-spinner');
        if (loading) {
            text?.classList.add('d-none');
            spinner?.classList.remove('d-none');
            btn.disabled = true;
        } else {
            text?.classList.remove('d-none');
            spinner?.classList.add('d-none');
            btn.disabled = false;
        }
    }

    const forgotForm = document.getElementById('forgotPasswordForm');
    if (forgotForm) {
        forgotForm.addEventListener('submit', async function (e) {
            e.preventDefault();
            const btn   = /** @type {HTMLButtonElement|null} */ (document.getElementById('forgotBtn'));
            const email = /** @type {HTMLInputElement|null} */ (document.getElementById('email'));
            if (!btn || !email) return;

            hideAlert('forgotAlert');
            setButtonLoading(btn, true);

            try {
                const response = await fetch(`${API_BASE}/auth/forgot-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: email.value })
                });
                const data = await response.json();

                if (response.ok) {
                    if (data.reset_url) {
                        // SMTP not configured — show the reset button directly on the page
                        const resetBtn = /** @type {HTMLAnchorElement|null} */ (document.getElementById('noEmailResetBtn'));
                        if (resetBtn) {
                            // Only allow safe relative paths
                            const url = String(data.reset_url);
                            resetBtn.href = /^\/(?!\/)/.test(url) ? url : '/auth/reset-password';
                        }
                        document.getElementById('forgotPasswordSection')?.classList.add('d-none');
                        document.getElementById('noEmailSection')?.classList.remove('d-none');
                    } else {
                        showAlert('forgotAlert', data.message || 'If an account exists, you will receive a reset link shortly.', 'success');
                    }
                } else {
                    showAlert('forgotAlert', data.detail || data.message || 'An error occurred. Please try again.', 'danger');
                }
            } catch (error) {
                console.error('Forgot password error:', error);
                showAlert('forgotAlert', 'Network error. Please try again.', 'danger');
            } finally {
                setButtonLoading(btn, false);
            }
        });
    }

    const resetForm = document.getElementById('resetPasswordForm');
    if (resetForm) {
        resetForm.addEventListener('submit', async function (e) {
            e.preventDefault();
            const btn         = /** @type {HTMLButtonElement|null} */ (document.getElementById('resetBtn'));
            const tokenInput  = /** @type {HTMLInputElement|null} */ (document.getElementById('resetToken'));
            const newPassEl   = /** @type {HTMLInputElement|null} */ (document.getElementById('newPassword'));
            const confPassEl  = /** @type {HTMLInputElement|null} */ (document.getElementById('confirmPassword'));
            if (!btn || !tokenInput || !newPassEl || !confPassEl) return;

            const token       = tokenInput.value;
            const newPassword = newPassEl.value;
            const confirmPassword = confPassEl.value;

            hideAlert('resetAlert');

            if (!validatePassword(newPassword)) {
                showAlert('resetAlert', 'Password must be at least 8 characters with uppercase, lowercase, number, and special character.', 'danger');
                return;
            }
            if (newPassword !== confirmPassword) {
                showAlert('resetAlert', 'Passwords do not match.', 'danger');
                return;
            }

            setButtonLoading(btn, true);

            try {
                const response = await fetch(`${API_BASE}/auth/reset-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token, new_password: newPassword, confirm_password: confirmPassword })
                });
                const data = await response.json();

                if (response.ok) {
                    document.getElementById('resetPasswordSection')?.classList.add('d-none');
                    document.getElementById('successSection')?.classList.remove('d-none');
                } else {
                    showAlert('resetAlert', data.detail || 'Failed to reset password. Please try again.', 'danger');
                }
            } catch (error) {
                console.error('Reset password error:', error);
                showAlert('resetAlert', 'Network error. Please try again.', 'danger');
            } finally {
                setButtonLoading(btn, false);
            }
        });
    }

    // Public API
    // @ts-ignore
    window.togglePassword = togglePassword;

}());
