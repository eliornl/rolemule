/**
 * Migrated from ui/static/js/auth-verify-email.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
(function () {
    'use strict';

    const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';
    let userEmail = '';

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
    let resendCooldown = 0;

    document.addEventListener('DOMContentLoaded', function () {
        const urlParams = new URLSearchParams(window.location.search);
        userEmail = urlParams.get('email') || localStorage.getItem('pendingVerificationEmail') || '';

        if (userEmail) {
            const emailEl = document.getElementById('userEmail');
            if (emailEl) emailEl.textContent = userEmail;
            document.getElementById('codeSection')?.classList.remove('d-none');
            document.getElementById('noEmailSection')?.classList.add('d-none');
            /** @type {HTMLElement|null} */ (document.querySelector('.code-input'))?.focus();
        } else {
            document.getElementById('codeSection')?.classList.add('d-none');
            document.getElementById('noEmailSection')?.classList.remove('d-none');
        }

        setupCodeInputs();

        // Wire resend link (replaces inline onclick="resendCode()")
        const resendLink = document.getElementById('resendLink');
        if (resendLink) {
            resendLink.addEventListener('click', (e) => { e.preventDefault(); resendCode(); });
            resendLink.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); resendCode(); }
            });
        }
    });

    function setupCodeInputs() {
        const inputs = /** @type {NodeListOf<HTMLInputElement>} */ (document.querySelectorAll('.code-input'));

        inputs.forEach((input, index) => {
            input.addEventListener('input', function () {
                const value = this.value.replace(/[^0-9]/g, '');
                this.value = value;

                if (value) {
                    this.classList.add('filled');
                    if (index < inputs.length - 1) {
                        inputs[index + 1].focus();
                    }
                } else {
                    this.classList.remove('filled');
                }
                checkCodeComplete();
            });

            input.addEventListener('keydown', function (e) {
                const ke = /** @type {KeyboardEvent} */ (e);
                if (ke.key === 'Backspace' && !this.value && index > 0) {
                    inputs[index - 1].focus();
                    inputs[index - 1].value = '';
                    inputs[index - 1].classList.remove('filled');
                }
                inputs.forEach(inp => inp.classList.remove('error'));
            });

            input.addEventListener('paste', function (e) {
                e.preventDefault();
                const pe = /** @type {ClipboardEvent} */ (e);
                const pastedData = (pe.clipboardData?.getData('text') ?? '').replace(/[^0-9]/g, '').slice(0, 6);

                pastedData.split('').forEach((char, i) => {
                    if (inputs[i]) {
                        inputs[i].value = char;
                        inputs[i].classList.add('filled');
                    }
                });

                if (pastedData.length === 6) {
                    inputs[5].focus();
                } else if (pastedData.length > 0) {
                    inputs[Math.min(pastedData.length, 5)].focus();
                }
                checkCodeComplete();
            });
        });
    }

    function checkCodeComplete() {
        const inputs = /** @type {NodeListOf<HTMLInputElement>} */ (document.querySelectorAll('.code-input'));
        const code = Array.from(inputs).map(i => i.value).join('');
        const btn = /** @type {HTMLButtonElement|null} */ (document.getElementById('verifyBtn'));
        if (btn) btn.disabled = code.length !== 6;
    }

    function getCode() {
        const inputs = /** @type {NodeListOf<HTMLInputElement>} */ (document.querySelectorAll('.code-input'));
        return Array.from(inputs).map(i => i.value).join('');
    }

    /**
     * @param {string} message
     * @param {string} type
     */
    function showAlert(message, type) {
        const container = document.getElementById('alertContainer');
        if (!container) return;
        container.innerHTML = `
            <div class="alert alert-${type}" role="alert">
                <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-triangle'} me-2"></i>
                ${escapeHtml(message)}
            </div>
        `;
    }

    function clearAlert() {
        const container = document.getElementById('alertContainer');
        if (container) container.innerHTML = '';
    }

    const verifyForm = document.getElementById('verifyForm');
    if (verifyForm) {
        verifyForm.addEventListener('submit', async function (e) {
            e.preventDefault();
            clearAlert();

            const code = getCode();
            if (code.length !== 6) return;

            const btn = /** @type {HTMLButtonElement|null} */ (document.getElementById('verifyBtn'));
            if (!btn) return;
            btn.querySelector('.btn-text')?.classList.add('d-none');
            btn.querySelector('.btn-loader')?.classList.remove('d-none');
            btn.disabled = true;

            try {
                const response = await fetch(`${API_BASE}/auth/verify-code`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: userEmail, code })
                });

                const data = await response.json();

                if (response.ok) {
                    localStorage.removeItem('pendingVerificationEmail');

                    if (data.access_token) {
                        localStorage.setItem('authToken', data.access_token);
                        localStorage.setItem('access_token', data.access_token);
                        if (data.user) {
                            localStorage.setItem('user_data', JSON.stringify(data.user));
                        }
                        if (data.profile_completed !== undefined) {
                            localStorage.setItem('profile_completed', String(data.profile_completed));
                        }
                        // New users (profile not yet completed) should always see the onboarding tour.
                        // Returning users who re-verify (e.g. after lockout) must keep their tour status.
                        if (!data.profile_completed) {
                            localStorage.removeItem('onboarding_completed');
                        }
                    }

                    const successMsg = document.getElementById('successMessage');
                    if (successMsg) successMsg.textContent = data.message;
                    const continueBtn = /** @type {HTMLAnchorElement|null} */ (document.getElementById('continueBtn'));
                    if (continueBtn) {
                        const rawRedirect = data.redirect || '/profile/setup';
                        const safeRedirect = /^\/(?!\/)/.test(rawRedirect) ? rawRedirect : '/profile/setup';
                        continueBtn.href = safeRedirect;
                        if (safeRedirect.includes('dashboard')) {
                            continueBtn.innerHTML = '<i class="fas fa-tachometer-alt me-2"></i> Go to Dashboard';
                        }
                    }

                    document.getElementById('codeSection')?.classList.add('d-none');
                    document.getElementById('successSection')?.classList.remove('d-none');
                } else {
                    showAlert(data.detail || 'Invalid verification code. Please try again.', 'danger');
                    /** @type {NodeListOf<HTMLInputElement>} */ (document.querySelectorAll('.code-input')).forEach(input => {
                        input.classList.add('error');
                        input.value = '';
                        input.classList.remove('filled');
                    });
                    /** @type {HTMLElement|null} */ (document.querySelector('.code-input'))?.focus();
                }
            } catch (error) {
                console.error('Verification error:', error);
                showAlert('An error occurred. Please try again.', 'danger');
            } finally {
                btn.querySelector('.btn-text')?.classList.remove('d-none');
                btn.querySelector('.btn-loader')?.classList.add('d-none');
                btn.disabled = false;
                checkCodeComplete();
            }
        });
    }

    async function resendCode() {
        if (resendCooldown > 0) return;

        const link = document.getElementById('resendLink');
        const timer = document.getElementById('resendTimer');
        if (!link || !timer) return;

        link.classList.add('disabled');

        try {
            const response = await fetch(`${API_BASE}/auth/resend-verification`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: userEmail })
            });

            const data = await response.json();

            if (response.ok) {
                showAlert('New verification code sent! Check your email.', 'success');
            } else if (data.message && data.message.includes('already verified')) {
                showAlert('Your email is already verified! You can log in.', 'success');
            } else {
                showAlert('Failed to send code. Please try again.', 'danger');
            }

            if (response.ok) {
                resendCooldown = 60;
                link.classList.add('d-none');
                timer.classList.remove('d-none');

                const interval = setInterval(() => {
                    resendCooldown--;
                    timer.textContent = `Resend in ${resendCooldown}s`;
                    if (resendCooldown <= 0) {
                        clearInterval(interval);
                        link.classList.remove('d-none', 'disabled');
                        timer.classList.add('d-none');
                    }
                }, 1000);
            }
        } catch (error) {
            console.error('Resend error:', error);
            showAlert('Failed to resend code. Please try again.', 'danger');
            link.classList.remove('disabled');
        }
    }

    const emailForm = document.getElementById('emailForm');
    if (emailForm) {
        emailForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            const emailInput = /** @type {HTMLInputElement|null} */ (document.getElementById('emailInput'));
            if (!emailInput) return;
            userEmail = emailInput.value.trim();

            const btn = /** @type {HTMLButtonElement|null} */ (this.querySelector('button'));
            if (!btn) return;
            btn.querySelector('.btn-text')?.classList.add('d-none');
            btn.querySelector('.btn-loader')?.classList.remove('d-none');
            btn.disabled = true;

            try {
                const response = await fetch(`${API_BASE}/auth/resend-verification`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: userEmail })
                });

                if (response.ok) {
                    localStorage.setItem('pendingVerificationEmail', userEmail);
                    const emailEl = document.getElementById('userEmail');
                    if (emailEl) emailEl.textContent = userEmail;
                    document.getElementById('noEmailSection')?.classList.add('d-none');
                    document.getElementById('codeSection')?.classList.remove('d-none');
                    /** @type {HTMLElement|null} */ (document.querySelector('.code-input'))?.focus();
                    showAlert('Verification code sent! Check your email.', 'success');
                } else {
                    const data = await response.json();
                    showAlert(data.detail || 'Failed to send code.', 'danger');
                }
            } catch (error) {
                console.error('Error:', error);
                showAlert('An error occurred. Please try again.', 'danger');
            } finally {
                btn.querySelector('.btn-text')?.classList.remove('d-none');
                btn.querySelector('.btn-loader')?.classList.add('d-none');
                btn.disabled = false;
            }
        });
    }

    // Public API
    // @ts-ignore
    window.resendCode = resendCode;

}());
