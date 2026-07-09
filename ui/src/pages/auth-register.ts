/**
 * Migrated from ui/static/js/auth-register.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
(function () {
    'use strict';

    // =============================================================================
    // CONSTANTS
    // =============================================================================

    const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';
    const REDIRECT_DELAY = 2000;

    const PASSWORD_REQUIREMENTS = {
        MIN_LENGTH: 8,
        UPPERCASE_REGEX: /[A-Z]/,
        LOWERCASE_REGEX: /[a-z]/,
        NUMBER_REGEX:    /\d/,
        SPECIAL_REGEX:   /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/
    };

    const STORAGE_KEYS = {
        ACCESS_TOKEN:      'access_token',
        TOKEN_TYPE:        'token_type',
        USER_DATA:         'user_data',
        PROFILE_COMPLETED: 'profile_completed'
    };

    /** @param {string} text */
    function stripHtmlForAlert(text) {
        return window.stripHtmlForAlert(text);
    }

    // =============================================================================
    // DOM CACHE
    // =============================================================================

    const DOM = {
        registerForm:           /** @type {HTMLFormElement|null} */   (document.getElementById('registerForm')),
        registerBtn:            /** @type {HTMLButtonElement|null} */ (document.getElementById('register-btn')),
        registerText:           /** @type {HTMLElement|null} */       (document.querySelector('.register-text')),
        loadingSpinner:         /** @type {HTMLElement|null} */       (document.querySelector('.loading-spinner')),
        errorAlert:             /** @type {HTMLElement|null} */       (document.getElementById('error-alert')),
        successAlert:           /** @type {HTMLElement|null} */       (document.getElementById('success-alert')),
        errorMessage:           /** @type {HTMLElement|null} */       (document.getElementById('error-message')),
        successMessage:         /** @type {HTMLElement|null} */       (document.getElementById('success-message')),
        fullNameField:          /** @type {HTMLInputElement|null} */  (document.getElementById('full-name')),
        emailField:             /** @type {HTMLInputElement|null} */  (document.getElementById('email')),
        passwordField:          /** @type {HTMLInputElement|null} */  (document.getElementById('password')),
        confirmPasswordField:   /** @type {HTMLInputElement|null} */  (document.getElementById('confirm-password')),
        termsCheckbox:          /** @type {HTMLInputElement|null} */  (document.getElementById('terms-agreement')),
        passwordToggle:         /** @type {HTMLElement|null} */       (document.getElementById('password-toggle')),
        confirmPasswordToggle:  /** @type {HTMLElement|null} */       (document.getElementById('confirm-password-toggle')),
        reqLength:              /** @type {HTMLElement|null} */       (document.getElementById('req-length')),
        reqUppercase:           /** @type {HTMLElement|null} */       (document.getElementById('req-uppercase')),
        reqLowercase:           /** @type {HTMLElement|null} */       (document.getElementById('req-lowercase')),
        reqNumber:              /** @type {HTMLElement|null} */       (document.getElementById('req-number')),
        reqSpecial:             /** @type {HTMLElement|null} */       (document.getElementById('req-special'))
    };

    // =============================================================================
    // UI UTILITIES
    // =============================================================================

    /** @param {string} message */
    function showError(message) {
        if (!DOM.errorMessage || !DOM.errorAlert || !DOM.successAlert) return;
        DOM.errorMessage.textContent = message;
        DOM.errorAlert.classList.remove('d-none');
        DOM.successAlert.classList.add('d-none');
        DOM.errorAlert.setAttribute('aria-live', 'polite');
    }

    /** @param {string} message */
    function showSuccess(message) {
        if (!DOM.successMessage || !DOM.successAlert || !DOM.errorAlert) return;
        DOM.successMessage.textContent = message;
        DOM.successAlert.classList.remove('d-none');
        DOM.errorAlert.classList.add('d-none');
        DOM.successAlert.setAttribute('aria-live', 'polite');
    }

    /** @param {string} message */
    function showInfo(message) {
        if (!DOM.successMessage || !DOM.successAlert || !DOM.errorAlert) return;
        DOM.successMessage.textContent = message;
        DOM.successAlert.classList.remove('d-none', 'alert-success');
        DOM.successAlert.classList.add('alert-info');
        DOM.errorAlert.classList.add('d-none');
        DOM.successAlert.setAttribute('aria-live', 'polite');
        setTimeout(() => {
            DOM.successAlert?.classList.remove('alert-info');
            DOM.successAlert?.classList.add('alert-success');
        }, 5000);
    }

    function hideAlerts() {
        DOM.errorAlert?.classList.add('d-none');
        DOM.successAlert?.classList.add('d-none');
    }

    /** @param {boolean} loading */
    function setLoading(loading) {
        if (!DOM.registerText || !DOM.loadingSpinner || !DOM.registerBtn) return;
        if (loading) {
            DOM.registerText.style.display = 'none';
            DOM.loadingSpinner.style.display = 'inline';
            DOM.registerBtn.disabled = true;
            DOM.registerBtn.setAttribute('aria-busy', 'true');
        } else {
            DOM.registerText.style.display = 'inline';
            DOM.loadingSpinner.style.display = 'none';
            DOM.registerBtn.setAttribute('aria-busy', 'false');
            updateSubmitButton();
        }
    }

    // =============================================================================
    // AUTH HELPERS
    // =============================================================================

    /** @param {string} token */
    function setAuthToken(token) {
        if (!token) return;
        localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, token);
        localStorage.setItem('authToken', token);
    }

    /** @param {Record<string,unknown>} response */
    function storeAuthData(response) {
        try {
            setAuthToken(/** @type {string} */ (response['access_token']));
            localStorage.setItem(STORAGE_KEYS.TOKEN_TYPE,        String(response['token_type'] ?? ''));
            localStorage.setItem(STORAGE_KEYS.USER_DATA,         JSON.stringify(response['user']));
            localStorage.setItem(STORAGE_KEYS.PROFILE_COMPLETED, String(response['profile_completed']));
        } catch (error) {
            console.error('Failed to store authentication data:', error);
            showError('Failed to save registration data. Please try again.');
        }
    }

    function getAuthToken() {
        const urlParams  = new URLSearchParams(window.location.search);
        const urlToken   = urlParams.get('token') || urlParams.get('access_token');
        if (urlToken) return urlToken;
        return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN) || localStorage.getItem('authToken') || null;
    }

    function isAuthenticated() { return getAuthToken() !== null; }

    // =============================================================================
    // VALIDATION
    // =============================================================================

    /** @param {string} name */
    function validateFullName(name) {
        const isValid   = name.trim().length >= 2;
        const container = document.getElementById('fullname-container');
        if (!DOM.fullNameField || !container) return isValid;

        if (name.length > 0) {
            DOM.fullNameField.classList.toggle('is-valid', isValid);
            DOM.fullNameField.classList.toggle('is-invalid', !isValid);
            container.classList.toggle('email-validation-valid', isValid);
            container.classList.remove('email-validation-invalid');
        } else {
            DOM.fullNameField.classList.remove('is-valid', 'is-invalid');
            container.classList.remove('email-validation-valid', 'email-validation-invalid');
        }
        return isValid;
    }

    /** @param {string} password */
    function validatePassword(password) {
        const req = {
            length:    password.length >= PASSWORD_REQUIREMENTS.MIN_LENGTH,
            uppercase: PASSWORD_REQUIREMENTS.UPPERCASE_REGEX.test(password),
            lowercase: PASSWORD_REQUIREMENTS.LOWERCASE_REGEX.test(password),
            number:    PASSWORD_REQUIREMENTS.NUMBER_REGEX.test(password),
            special:   PASSWORD_REQUIREMENTS.SPECIAL_REGEX.test(password)
        };
        if (DOM.reqLength)    DOM.reqLength.className    = req.length    ? 'valid' : 'invalid';
        if (DOM.reqUppercase) DOM.reqUppercase.className = req.uppercase ? 'valid' : 'invalid';
        if (DOM.reqLowercase) DOM.reqLowercase.className = req.lowercase ? 'valid' : 'invalid';
        if (DOM.reqNumber)    DOM.reqNumber.className    = req.number    ? 'valid' : 'invalid';
        if (DOM.reqSpecial)   DOM.reqSpecial.className   = req.special   ? 'valid' : 'invalid';

        const isValid   = Object.values(req).every(v => v);
        const container = document.getElementById('password-container');
        if (!DOM.passwordField || !container) return isValid;

        if (password.length > 0) {
            DOM.passwordField.classList.toggle('is-valid', isValid);
            DOM.passwordField.classList.toggle('is-invalid', !isValid);
            container.classList.toggle('email-validation-valid', isValid);
            container.classList.remove('email-validation-invalid');
        } else {
            DOM.passwordField.classList.remove('is-valid', 'is-invalid');
            container.classList.remove('email-validation-valid', 'email-validation-invalid');
        }
        return isValid;
    }

    function validatePasswordMatch() {
        if (!DOM.passwordField || !DOM.confirmPasswordField) return false;
        const password        = DOM.passwordField.value;
        const confirmPassword = DOM.confirmPasswordField.value;
        const container       = document.getElementById('confirm-password-container');
        if (!container) return false;

        if (confirmPassword.length > 0) {
            const matches = password === confirmPassword;
            DOM.confirmPasswordField.classList.toggle('is-valid', matches);
            DOM.confirmPasswordField.classList.toggle('is-invalid', !matches);
            container.classList.toggle('email-validation-valid', matches);
            container.classList.remove('email-validation-invalid');
            return matches;
        } else {
            DOM.confirmPasswordField.classList.remove('is-valid', 'is-invalid');
            container.classList.remove('email-validation-valid', 'email-validation-invalid');
        }
        return false;
    }

    function updateSubmitButton() {
        if (!DOM.passwordField || !DOM.confirmPasswordField || !DOM.fullNameField ||
            !DOM.emailField || !DOM.termsCheckbox || !DOM.registerBtn) return;
        const pw   = DOM.passwordField.value;
        const cpw  = DOM.confirmPasswordField.value;
        DOM.registerBtn.disabled = !(
            validatePassword(pw) &&
            pw === cpw && cpw.length > 0 &&
            DOM.termsCheckbox.checked &&
            DOM.fullNameField.value.length > 0 &&
            DOM.emailField.value.length > 0
        );
    }

    /**
     * @param {string} email
     * @returns {{ isValid: boolean, message: string, suggestion?: string }}
     */
    function validateEmail(email) {
        if (!email || email.length === 0) return { isValid: false, message: 'Email address is required' };
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return { isValid: false, message: 'Please enter a valid email address (e.g., name@example.com)' };

        const domainPart = email.split('@')[1];
        if (!domainPart || !domainPart.includes('.')) return { isValid: false, message: 'Invalid domain format. Domain must include a TLD (e.g., .com)' };

        for (const domain of ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'icloud.com']) {
            const distance = levenshteinDistance(domainPart, domain);
            if (distance > 0 && distance <= 2 && domainPart !== domain) {
                const correctedEmail = email.split('@')[0] + '@' + domain;
                return { isValid: false, message: 'Did you mean', suggestion: correctedEmail };
            }
        }
        return { isValid: true, message: '' };
    }

    /**
     * @param {string} a
     * @param {string} b
     */
    function levenshteinDistance(a, b) {
        /** @type {number[][]} */
        const matrix = [];
        for (let i = 0; i <= b.length; i++) matrix[i] = [i];
        for (let j = 0; j <= a.length; j++) matrix[0][j] = j;
        for (let i = 1; i <= b.length; i++) {
            for (let j = 1; j <= a.length; j++) {
                matrix[i][j] = b[i - 1] === a[j - 1]
                    ? matrix[i - 1][j - 1]
                    : Math.min(matrix[i - 1][j - 1] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j] + 1);
            }
        }
        return matrix[b.length][a.length];
    }

    // =============================================================================
    // UI INTERACTIONS
    // =============================================================================

    /**
     * @param {HTMLInputElement} field
     * @param {HTMLElement} toggle
     */
    function togglePasswordVisibility(field, toggle) {
        const icon = toggle.querySelector('i');
        if (!icon) return;
        if (field.type === 'password') {
            field.type = 'text';
            icon.classList.replace('fa-eye', 'fa-eye-slash');
            toggle.setAttribute('aria-label', 'Hide password');
        } else {
            field.type = 'password';
            icon.classList.replace('fa-eye-slash', 'fa-eye');
            toggle.setAttribute('aria-label', 'Show password');
        }
    }

    // =============================================================================
    // EVENT HANDLERS
    // =============================================================================

    // Module-level timer IDs so beforeunload can clear them
    let _passwordTimer = 0;
    let _emailTimer = 0;
    let _nameTimer = 0;

    function setupEventListeners() {
        if (!DOM.passwordField || !DOM.confirmPasswordField || !DOM.termsCheckbox ||
            !DOM.fullNameField || !DOM.emailField || !DOM.passwordToggle ||
            !DOM.confirmPasswordToggle || !DOM.registerForm) return;

        DOM.passwordField.addEventListener('input', () => {
            clearTimeout(_passwordTimer);
            _passwordTimer = window.setTimeout(() => {
                validatePassword(/** @type {HTMLInputElement} */ (DOM.passwordField).value);
                if (DOM.confirmPasswordField && DOM.confirmPasswordField.value.length > 0) validatePasswordMatch();
                updateSubmitButton();
            }, 300);
        });
        DOM.confirmPasswordField.addEventListener('input', () => { validatePasswordMatch(); updateSubmitButton(); });
        DOM.termsCheckbox.addEventListener('change', updateSubmitButton);
        DOM.fullNameField.addEventListener('input', () => {
            clearTimeout(_nameTimer);
            _nameTimer = window.setTimeout(() => {
                validateFullName(/** @type {HTMLInputElement} */ (DOM.fullNameField).value);
                updateSubmitButton();
            }, 300);
        });

        DOM.emailField.addEventListener('input', function () {
            clearTimeout(_emailTimer);
            const self = this;
            _emailTimer = window.setTimeout(function () {
            const email          = self.value.trim();
            const emailResult    = validateEmail(email);
            const feedbackEl     = /** @type {HTMLElement|null} */ (document.querySelector('#email-feedback'));
            const container      = /** @type {HTMLElement|null} */ (self.closest('.email-validation-container'));
            if (!container) return;
            container.classList.remove('email-validation-valid', 'email-validation-invalid');

            if (email.length > 0) {
                if (emailResult.isValid) {
                    self.classList.replace('is-invalid', 'is-valid') || self.classList.add('is-valid');
                    container.classList.add('email-validation-valid');
                    if (feedbackEl) { feedbackEl.innerHTML = ''; feedbackEl.classList.remove('d-block'); }
                } else {
                    self.classList.replace('is-valid', 'is-invalid') || self.classList.add('is-invalid');
                    container.classList.add('email-validation-invalid');
                    if (feedbackEl) {
                        feedbackEl.innerHTML = '';
                        if (emailResult.suggestion) {
                            // Build suggestion link safely without innerHTML injection
                            feedbackEl.appendChild(document.createTextNode(emailResult.message + ' '));
                            const link = document.createElement('a');
                            link.className = 'suggestion-link';
                            link.href = '#';
                            link.textContent = emailResult.suggestion;
                            link.addEventListener('click', function (e) {
                                e.preventDefault();
                                if (DOM.emailField) {
                                    DOM.emailField.value = emailResult.suggestion ?? '';
                                    DOM.emailField.dispatchEvent(new Event('input'));
                                }
                            });
                            feedbackEl.appendChild(link);
                            feedbackEl.appendChild(document.createTextNode('?'));
                        } else {
                            feedbackEl.textContent = emailResult.message;
                        }
                        feedbackEl.classList.add('d-block');
                    }
                }
            } else {
                self.classList.remove('is-valid', 'is-invalid');
                feedbackEl?.classList.remove('d-block');
            }
            updateSubmitButton();
            }, 300);
        });

        DOM.passwordToggle.addEventListener('click', () => {
            if (DOM.passwordField && DOM.passwordToggle) togglePasswordVisibility(DOM.passwordField, DOM.passwordToggle);
        });
        DOM.confirmPasswordToggle.addEventListener('click', () => {
            if (DOM.confirmPasswordField && DOM.confirmPasswordToggle) togglePasswordVisibility(DOM.confirmPasswordField, DOM.confirmPasswordToggle);
        });
        DOM.registerForm.addEventListener('submit', handleRegistrationSubmit);
    }

    /** @param {Event} e */
    async function handleRegistrationSubmit(e) {
        e.preventDefault();
        hideAlerts();
        setLoading(true);
        if (!DOM.emailField || !DOM.registerForm) { setLoading(false); return; }

        const emailValue  = DOM.emailField.value.trim();
        const emailResult = validateEmail(emailValue);
        if (!emailResult.isValid) {
            showError(stripHtmlForAlert(emailResult.message));
            DOM.emailField.classList.add('is-invalid');
            setLoading(false);
            return;
        }

        const formData   = new FormData(DOM.registerForm);
        const registerData = {
            full_name:        formData.get('full_name'),
            email:            formData.get('email'),
            password:         formData.get('password'),
            confirm_password: formData.get('confirm_password')
        };

        try {
            const response = await fetch(`${API_BASE}/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(registerData)
            });

            let result;
            try { result = await response.json(); } catch { throw new Error('Invalid response from server'); }

            if (response.ok) {
                if (result.user && result.user.email_verified) {
                    // DISABLE_EMAIL_VERIFICATION=true — user is already verified.
                    // Safe to store the token and go straight to profile setup.
                    storeAuthData(result);
                    showSuccess('Account created! Redirecting...');
                    setTimeout(() => {
                        window.location.href = '/profile/setup';
                    }, REDIRECT_DELAY);
                } else {
                // Do NOT store the token here — the user is not verified yet.
                // The verify-code endpoint issues a fresh token after verification succeeds.
                localStorage.setItem('pendingVerificationEmail', DOM.emailField.value.trim().toLowerCase());
                showSuccess('Account created! Check your email for the verification code...');
                setTimeout(() => {
                    window.location.href = `/auth/verify-email?email=${encodeURIComponent(/** @type {HTMLInputElement} */ (DOM.emailField).value.trim().toLowerCase())}`;
                }, REDIRECT_DELAY);
                }
            } else {
                let errorMessage = 'Registration failed. Please try again.';
                if (result) {
                    if (typeof result === 'object') {
                        errorMessage = result.detail || result.message || result.error ||
                                      (Array.isArray(result.errors) ? result.errors[0] : null) ||
                                      JSON.stringify(result);
                    } else if (typeof result === 'string') {
                        errorMessage = result;
                    }
                }
                showError(errorMessage);
            }
        } catch (error) {
            console.error('Registration error:', error);
            showError('Connection error. Please check your internet connection and try again.');
        } finally {
            setLoading(false);
        }
    }

    // =============================================================================
    // INITIALIZATION
    // =============================================================================

    function initializeRegistrationPage() {
        try {
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.has('error')) {
                if (urlParams.get('error') === 'user_not_found') {
                    ['authToken', 'access_token', 'token_type', 'user_data', 'profile_completed'].forEach(k => localStorage.removeItem(k));
                    showInfo('Your account was not found in the database. Please register again.');
                }
            }
            if (isAuthenticated()) {
                const profileCompleted = localStorage.getItem(STORAGE_KEYS.PROFILE_COMPLETED) === 'true';
                window.location.href = profileCompleted ? '/dashboard' : '/profile/setup';
                return;
            }
            DOM.fullNameField?.focus();
            setupEventListeners();
            DOM.passwordToggle?.setAttribute('aria-label', 'Show password');
            DOM.confirmPasswordToggle?.setAttribute('aria-label', 'Show password');
        } catch (error) {
            console.error('Registration page initialization failed:', error);
        }
    }

    window.addEventListener('load', initializeRegistrationPage);

    // =============================================================================
    // GOOGLE OAUTH
    // =============================================================================

    async function checkGoogleOAuthStatus() {
        try {
            const response = await fetch(`${API_BASE}/auth/oauth/status`);
            if (response.ok) {
                const data = await response.json();
                if (data.google_oauth_enabled) {
                    const divider   = document.getElementById('oauth-divider');
                    const googleBtn = document.getElementById('google-signup-btn');
                    if (divider)   divider.style.display   = 'flex';
                    if (googleBtn) googleBtn.style.display = 'flex';
                }
            }
        } catch (error) {
            console.debug('Could not check OAuth status:', error);
        }
    }

    function handleGoogleSignup() {
        window.location.href = `${API_BASE}/auth/google?redirect_url=/profile/setup`;
    }

    function checkOAuthErrors() {
        const urlParams = new URLSearchParams(window.location.search);
        const error     = urlParams.get('error');
        const message   = urlParams.get('message');
        if (!error) return;

        /** @type {Record<string,string>} */
        const messages = {
            oauth_failed:          message ? `OAuth error: ${message}` : 'Google authentication failed.',
            oauth_not_configured:  'Google sign-up is not available at the moment.',
            token_exchange_failed: 'Failed to complete authentication. Please try again.',
            no_access_token:       'Authentication incomplete. Please try again.',
            userinfo_failed:       'Could not retrieve your account information.',
            missing_user_info:     'Required account information is missing.',
            oauth_error:           message ? `Error: ${message}` : 'An error occurred during authentication.'
        };
        showError(messages[error] ?? 'Authentication failed. Please try again.');
        window.history.replaceState({}, document.title, window.location.pathname);
    }

    document.addEventListener('DOMContentLoaded', function () {
        checkOAuthErrors();
        checkGoogleOAuthStatus();

        // Wire Google signup button (replaces inline onclick="handleGoogleSignup()")
        document.getElementById('google-signup-btn')?.addEventListener('click', handleGoogleSignup);

        // Clear pending validation timers on navigation to avoid memory leaks
        window.addEventListener('beforeunload', () => {
            clearTimeout(_passwordTimer);
            clearTimeout(_emailTimer);
            clearTimeout(_nameTimer);
        });
    });

    // Public API
    // @ts-ignore
    window.handleGoogleSignup = handleGoogleSignup;

}());
