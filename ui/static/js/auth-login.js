(function () {
    'use strict';

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

    /** @param {string} text */
    function stripHtmlForAlert(text) {
        return String(text)
            .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
            .replace(/<[^>]*>/g, '');
    }

    // =============================================================================
    // CONSTANTS AND CONFIGURATION
    // =============================================================================

    const CONFIG = {
        API_BASE: (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1',
        LOGIN_URL: (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login',
        REDIRECT_DELAY: 1000,
        VALIDATION_DELAY: 500
    };

    /** @type {Record<string, string[]>} */
    const EMAIL_TYPO_DOMAINS = {
        'gmail.com':   ['gmail.co', 'gamil.com', 'gmial.com', 'gmail.comm', 'gmail.con', 'gmail.om'],
        'yahoo.com':   ['yahoo.co', 'yaho.com', 'yahooo.com', 'yahoo.con', 'yahoo.comm'],
        'outlook.com': ['outlook.co', 'outllok.com', 'outlook.con', 'outlook.comm'],
        'hotmail.com': ['hotmai.com', 'hotmial.com', 'hotmail.co', 'hotmail.con'],
        'aol.com':     ['aol.co', 'aol.con', 'aol.comm'],
        'icloud.com':  ['icloud.co', 'icloud.con', 'icloud.comm']
    };

    const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    const STORAGE_KEYS = {
        AUTH_TOKEN:        'access_token',
        AUTH_TOKEN_LEGACY: 'authToken',
        USER_DATA:         'user'
    };

    // =============================================================================
    // DOM ELEMENTS CACHE
    // =============================================================================

    const DOM = {
        form:           /** @type {HTMLFormElement|null} */      (document.getElementById('loginForm')),
        submitBtn:      /** @type {HTMLButtonElement|null} */    (document.getElementById('login-btn')),
        loginText:      /** @type {HTMLElement|null} */          (document.querySelector('.login-text')),
        loginSpinner:   /** @type {HTMLElement|null} */          (document.querySelector('.login-spinner')),
        emailField:     /** @type {HTMLInputElement|null} */     (document.getElementById('email')),
        passwordField:  /** @type {HTMLInputElement|null} */     (document.getElementById('password')),
        rememberMeField:/** @type {HTMLInputElement|null} */     (document.getElementById('remember-me')),
        alertContainer: /** @type {HTMLElement|null} */          (document.getElementById('alert-container')),
        passwordToggle: /** @type {HTMLElement|null} */          (document.querySelector('.password-toggle'))
    };

    // =============================================================================
    // UI UTILITY FUNCTIONS
    // =============================================================================

    /**
     * @param {string} message
     * @param {string} [type]
     * @param {boolean} [persist] - if true, never auto-clears (user must interact)
     */
    function showAlert(message, type = 'info', persist = false) {
        if (!DOM.alertContainer) return;
        /** @type {Record<string,{class:string,icon:string}>} */
        const alertTypes = {
            success: { class: 'alert-success', icon: 'fas fa-check-circle' },
            error:   { class: 'alert-danger',  icon: 'fas fa-exclamation-triangle' },
            info:    { class: 'alert-info',    icon: 'fas fa-info-circle' }
        };
        const alertInfo = alertTypes[type] ?? alertTypes['info'];
        DOM.alertContainer.innerHTML = `
            <div class="alert ${alertInfo.class} alert-dismissible" role="alert">
                <i class="${alertInfo.icon} me-2"></i>${escapeHtml(message)}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>`;
        if (!persist && type !== 'error') {
            setTimeout(() => { if (DOM.alertContainer) DOM.alertContainer.innerHTML = ''; }, 5000);
        }
    }

    function hideAllAlerts() {
        if (DOM.alertContainer) DOM.alertContainer.innerHTML = '';
    }

    /** @param {boolean} loading */
    function setFormLoading(loading) {
        if (!DOM.submitBtn || !DOM.loginText || !DOM.loginSpinner ||
            !DOM.emailField || !DOM.passwordField || !DOM.rememberMeField) return;
        if (loading) {
            DOM.submitBtn.disabled = true;
            DOM.loginText.classList.add('d-none');
            DOM.loginSpinner.classList.remove('d-none');
            DOM.submitBtn.setAttribute('aria-busy', 'true');
            DOM.emailField.disabled = true;
            DOM.passwordField.disabled = true;
            DOM.rememberMeField.disabled = true;
        } else {
            DOM.submitBtn.disabled = false;
            DOM.loginText.classList.remove('d-none');
            DOM.loginSpinner.classList.add('d-none');
            DOM.submitBtn.setAttribute('aria-busy', 'false');
            DOM.emailField.disabled = false;
            DOM.passwordField.disabled = false;
            DOM.rememberMeField.disabled = false;
        }
    }

    // =============================================================================
    // VALIDATION FUNCTIONS
    // =============================================================================

    /**
     * @param {string} email
     * @returns {{ valid: boolean, message?: string, suggestion?: string }}
     */
    function validateEmail(email) {
        if (!EMAIL_REGEX.test(email)) {
            return { valid: false, message: 'Please enter a valid email address' };
        }
        const parts = email.split('@');
        if (parts.length === 2) {
            const domain = parts[1].toLowerCase();
            for (const [correct, typos] of Object.entries(EMAIL_TYPO_DOMAINS)) {
                if (typos.includes(domain)) {
                    return { valid: false, message: `Did you mean ${parts[0]}@${correct}?`, suggestion: `${parts[0]}@${correct}` };
                }
            }
            if (!domain.includes('.')) {
                return { valid: false, message: 'Your email domain appears to be missing a TLD (e.g. .com, .org)' };
            }
            const tld = domain.split('.').pop();
            if (tld && tld.length < 2) {
                return { valid: false, message: 'Your email domain appears to have an invalid TLD' };
            }
        }
        return { valid: true };
    }

    /** @param {string} password */
    function validatePassword(password) {
        if (!password || password.length < 8) return false;
        return /[A-Z]/.test(password) && /[a-z]/.test(password) &&
               /[0-9]/.test(password) && /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password);
    }

    /** @param {string} password */
    function updatePasswordUI(password) {
        const passwordInput  = /** @type {HTMLInputElement|null} */  (document.getElementById('password'));
        const container      = document.getElementById('password-container');
        const requirements   = document.getElementById('password-requirements');
        if (!passwordInput || !container) return;

        if (password.length > 0 && validatePassword(password)) {
            passwordInput.classList.add('is-valid');
            passwordInput.classList.remove('is-invalid');
            container.classList.add('email-validation-valid');
            container.classList.remove('email-validation-invalid');
            requirements?.classList.add('hidden');
        } else if (password.length > 0) {
            passwordInput.classList.remove('is-valid', 'is-invalid');
            container.classList.remove('email-validation-valid', 'email-validation-invalid');
            requirements?.classList.remove('hidden');
        } else {
            passwordInput.classList.remove('is-valid', 'is-invalid');
            container.classList.remove('email-validation-valid', 'email-validation-invalid');
            requirements?.classList.add('hidden');
        }
    }

    /** @param {HTMLInputElement} field */
    function validateField(field) {
        const fieldValue  = field.value.trim();
        const fieldType   = field.dataset['validate'];
        const feedbackEl  = document.getElementById(`${field.id}-feedback`);
        /** @type {{ valid: boolean, message?: string, suggestion?: string }} */
        let validationResult = { valid: false };

        const container = /** @type {HTMLElement|null} */ (
            field.closest('.email-validation-container') || field.parentNode
        );
        if (!container) return false;
        container.classList.remove('email-validation-pending', 'email-validation-valid', 'email-validation-invalid');

        switch (fieldType) {
            case 'email':
                validationResult = validateEmail(fieldValue);
                if (validationResult.valid) {
                    container.classList.add('email-validation-valid');
                } else if (fieldValue.length > 0) {
                    container.classList.add('email-validation-invalid');
                    if (feedbackEl) {
                        feedbackEl.innerHTML = escapeHtml(validationResult.message ?? 'Please enter a valid email address');
                        if (validationResult.suggestion) {
                            const link = document.createElement('a');
                            link.href = '#';
                            link.classList.add('suggestion-link');
                            link.textContent = ' Use this instead';
                            link.addEventListener('click', function (e) {
                                e.preventDefault();
                                field.value = /** @type {string} */ (validationResult.suggestion);
                                setTimeout(() => validateField(field), 10);
                            });
                            feedbackEl.appendChild(link);
                        }
                    }
                }
                break;
            case 'password':
                validationResult = { valid: validatePassword(fieldValue) };
                if (validationResult.valid) {
                    container.classList.add('email-validation-valid');
                    container.classList.remove('email-validation-invalid');
                } else if (fieldValue.length > 0) {
                    container.classList.add('email-validation-invalid');
                    container.classList.remove('email-validation-valid');
                    if (feedbackEl) feedbackEl.textContent = 'Please enter your password';
                }
                break;
        }

        if (validationResult.valid) {
            field.classList.add('is-valid');
            field.classList.remove('is-invalid');
            container.classList.add('email-validation-valid');
            container.classList.remove('email-validation-invalid');
            feedbackEl?.classList.remove('show');
        } else {
            field.classList.remove('is-valid');
            field.classList.add('is-invalid');
            feedbackEl?.classList.add('show');
        }
        return validationResult.valid;
    }

    // =============================================================================
    // AUTHENTICATION FUNCTIONS
    // =============================================================================

    /** @param {string|null} token */
    function setAuthToken(token) {
        if (token) {
            localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, token);
            localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN_LEGACY, token);
        } else {
            localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN);
            localStorage.removeItem(STORAGE_KEYS.AUTH_TOKEN_LEGACY);
        }
    }

    /** @param {Record<string,unknown>} authData */
    function storeAuthData(authData) {
        try {
            if (!authData['access_token']) {
                console.error('Missing access_token in auth data');
                return false;
            }
            setAuthToken(/** @type {string} */ (authData['access_token']));
            localStorage.setItem(STORAGE_KEYS.USER_DATA, JSON.stringify(authData['user']));
            localStorage.setItem('profile_completed', String(authData['profile_completed']));
            return true;
        } catch (error) {
            console.error('Failed to store authentication data:', error);
            showAlert('Failed to save login data. Please try again.', 'error');
            return false;
        }
    }

    /** @param {boolean} profileCompleted */
    function redirectUser(profileCompleted) {
        try {
            const urlParams = new URLSearchParams(window.location.search);
            let redirectUrl = urlParams.get('redirect');
            if (!redirectUrl) {
                redirectUrl = profileCompleted ? '/dashboard' : '/profile/setup';
            } else {
                if (redirectUrl.startsWith('/ui/')) {
                    redirectUrl = redirectUrl
                        .replace('/ui/dashboard/index.html', '/dashboard')
                        .replace('/ui/profile/setup.html', '/profile/setup');
                }
                // Only allow relative paths to prevent open redirect
                if (!redirectUrl.startsWith('/') || redirectUrl.startsWith('//')) {
                    redirectUrl = profileCompleted ? '/dashboard' : '/profile/setup';
                }
            }
            // JWT is stored in localStorage and retrieved by each page on load.
            // Never append it to redirect URLs (leaks into server logs and browser history).
            setTimeout(() => { window.location.href = window.location.origin + redirectUrl; }, CONFIG.REDIRECT_DELAY);
        } catch (error) {
            console.error('Redirect failed:', error);
            window.location.href = '/dashboard';
        }
    }

    // =============================================================================
    // API FUNCTIONS
    // =============================================================================

    /**
     * @param {{ email: string, password: string, remember_me?: boolean }} credentials
     */
    async function performLogin(credentials) {
        if (!credentials.email || !credentials.password) {
            throw new Error('Email and password are required');
        }
        /** @type {Record<string,unknown>} */
        const payload = { email: credentials.email, password: credentials.password };
        if (Object.prototype.hasOwnProperty.call(credentials, 'remember_me')) {
            payload['remember_me'] = credentials.remember_me;
        }

        const response = await fetch(`${CONFIG.API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();

        if (!response.ok) {
            if (response.status === 403) {
                localStorage.setItem('pendingVerificationEmail', credentials.email.toLowerCase());
                window.location.href = `/auth/verify-email?email=${encodeURIComponent(credentials.email.toLowerCase())}`;
                throw new Error('VERIFICATION_REQUIRED');
            }
            let errorMessage = 'Invalid email or password';
            if (response.status === 423) errorMessage = result.detail || 'Account temporarily locked. Please try again later.';
            else if (response.status === 422 || response.status === 400) errorMessage = 'Please enter both email and password';
            else if (response.status === 500) errorMessage = 'Server error. Please try again later.';
            throw new Error(errorMessage);
        }
        return result;
    }

    // =============================================================================
    // EVENT HANDLERS
    // =============================================================================

    document.addEventListener('DOMContentLoaded', function () {
        const passwordInput = /** @type {HTMLInputElement|null} */ (document.getElementById('password'));
        if (passwordInput) {
            passwordInput.addEventListener('input', function () { updatePasswordUI(this.value); });
        }

        const emailInput = /** @type {HTMLInputElement|null} */ (document.getElementById('email'));
        if (emailInput) {
            let emailValidationTimeout = 0;
            const emailContainer = emailInput.closest('.email-validation-container');

            emailInput.addEventListener('input', function () {
                clearTimeout(emailValidationTimeout);
                emailContainer?.classList.remove('email-validation-valid', 'email-validation-invalid');

                emailValidationTimeout = window.setTimeout(() => {
                    const result = validateEmail(emailInput.value.trim());
                    if (result.valid) {
                        emailContainer?.classList.add('email-validation-valid');
                        emailContainer?.classList.remove('email-validation-invalid');
                        document.getElementById('email-feedback')?.classList.remove('show');
                    } else if (emailInput.value.trim().length > 0) {
                        emailContainer?.classList.add('email-validation-invalid');
                        emailContainer?.classList.remove('email-validation-valid');
                        const feedbackEl = document.getElementById('email-feedback');
                        if (feedbackEl) {
                            feedbackEl.innerHTML = escapeHtml(result.message ?? 'Please enter a valid email address');
                            feedbackEl.classList.add('show');
                            if (result.suggestion) {
                                const link = document.createElement('a');
                                link.href = '#';
                                link.classList.add('suggestion-link');
                                link.textContent = ' Use this instead';
                                link.addEventListener('click', function (e) {
                                    e.preventDefault();
                                    emailInput.value = /** @type {string} */ (result.suggestion);
                                    emailInput.dispatchEvent(new Event('input'));
                                });
                                feedbackEl.appendChild(link);
                            }
                        }
                    }
                }, CONFIG.VALIDATION_DELAY);
            });
        }

        if (DOM.form) {
            DOM.form.addEventListener('submit', async function (e) {
                e.preventDefault();
                hideAllAlerts();
                if (!DOM.emailField || !DOM.passwordField || !DOM.rememberMeField) return;

                const email    = DOM.emailField.value.trim();
                const password = DOM.passwordField.value;

                if (!email) { DOM.emailField.classList.add('is-invalid'); showAlert('Please enter your email address', 'error'); return; }
                if (!password) { DOM.passwordField.classList.add('is-invalid'); showAlert('Please enter your password', 'error'); return; }

                const emailResult = validateEmail(email);
                if (!emailResult.valid) {
                    DOM.emailField.classList.add('is-invalid');
                    showAlert(stripHtmlForAlert(emailResult.message ?? 'Invalid email'), 'error');
                    return;
                }

                try {
                    setFormLoading(true);
                    const authData = await performLogin({
                        email, password, remember_me: DOM.rememberMeField.checked
                    });
                    // Clear password from DOM before redirecting
                    if (DOM.passwordField) DOM.passwordField.value = '';
                    if (storeAuthData(authData)) {
                        showAlert('Login successful! Redirecting...', 'success');
                        redirectUser(authData.profile_completed);
                    }
                } catch (error) {
                    // Clear password on failure to prevent resubmission with stale value
                    if (DOM.passwordField) DOM.passwordField.value = '';
                    const err = /** @type {Error} */ (error);
                    if (err.message === 'VERIFICATION_REQUIRED') return;
                    let msg = err.message || 'Login failed. Please check your credentials.';
                    if (msg.includes('401') || msg.includes('unauthorized')) {
                        msg = 'Invalid email or password. Please try again.';
                        DOM.passwordField?.classList.add('is-invalid');
                    } else if (msg.includes('500')) {
                        msg = 'Server error. Please try again later or contact support.';
                    } else if (msg.includes('Failed to fetch') || msg.includes('network')) {
                        msg = 'Network error. Please check your internet connection.';
                    }
                    showAlert(msg, 'error');
                    setFormLoading(false);
                }
            });
        }

        if (DOM.passwordToggle) {
            DOM.passwordToggle.addEventListener('click', function () {
                if (!DOM.passwordField) return;
                const isPassword = DOM.passwordField.getAttribute('type') === 'password';
                DOM.passwordField.setAttribute('type', isPassword ? 'text' : 'password');
                /** @type {HTMLElement} */ (DOM.passwordToggle).innerHTML = isPassword
                    ? '<i class="fas fa-eye-slash"></i>'
                    : '<i class="fas fa-eye"></i>';
            });
        }

        // Redirect already-authenticated users straight to the dashboard
        const existingToken = localStorage.getItem('access_token') || localStorage.getItem('authToken');
        if (existingToken) {
            window.location.href = '/dashboard';
            return;
        }

        checkOAuthErrors();
        checkUrlMessages();
        checkGoogleOAuthStatus();

        // Clear pending validation timers on navigation to avoid memory leaks
        window.addEventListener('beforeunload', () => {
            clearTimeout(emailValidationTimeout);
        });
    });

    // =============================================================================
    // GOOGLE OAUTH
    // =============================================================================

    async function checkGoogleOAuthStatus() {
        try {
            const response = await fetch(`${CONFIG.API_BASE}/auth/oauth/status`);
            if (response.ok) {
                const data = await response.json();
                if (data.google_oauth_enabled) {
                    const divider   = document.getElementById('oauth-divider');
                    const googleBtn = document.getElementById('google-login-btn');
                    if (divider)   divider.style.display   = 'flex';
                    if (googleBtn) googleBtn.style.display = 'flex';
                }
            }
        } catch (error) {
            console.debug('Could not check OAuth status:', error);
        }
    }

    function handleGoogleLogin() {
        const redirectUrl = new URLSearchParams(window.location.search).get('redirect') || '/dashboard';
        window.location.href = `/api/v1/auth/google?redirect_url=${encodeURIComponent(redirectUrl)}`;
    }

    function checkUrlMessages() {
        const params = new URLSearchParams(window.location.search);
        /** @type {Record<string, {msg: string, type: 'success'|'error'|'info'}>} */
        const knownParams = {
            verified:        { msg: 'Email verified successfully! You can now sign in.', type: 'success' },
            registered:      { msg: 'Account created! Please sign in.', type: 'success' },
            password_reset:  { msg: 'Password reset successfully. Please sign in with your new password.', type: 'success' },
            account_deleted: { msg: 'Your account has been deleted. Sorry to see you go.', type: 'info' },
        };
        for (const [key, { msg, type }] of Object.entries(knownParams)) {
            if (params.has(key)) {
                showAlert(msg, type, true); // persist — URL-param messages stay until dismissed
                window.history.replaceState({}, document.title, window.location.pathname);
                return;
            }
        }
    }

    function checkOAuthErrors() {
        const urlParams = new URLSearchParams(window.location.search);
        const error     = urlParams.get('error');
        const message   = urlParams.get('message');
        if (!error) return;

        /** @type {Record<string,string>} */
        const messages = {
            oauth_failed:           message ? `OAuth error: ${message}` : 'Google authentication failed.',
            oauth_not_configured:   'Google sign-in is not available at the moment.',
            token_exchange_failed:  'Failed to complete authentication. Please try again.',
            no_access_token:        'Authentication incomplete. Please try again.',
            userinfo_failed:        'Could not retrieve your account information.',
            missing_user_info:      'Required account information is missing.',
            oauth_error:            message ? `Error: ${message}` : 'An error occurred during authentication.'
        };
        showAlert(messages[error] ?? 'Authentication failed. Please try again.', 'error');
        window.history.replaceState({}, document.title, window.location.pathname);
    }

    // Wire Google login button (replaces inline onclick="handleGoogleLogin()")
    document.addEventListener('DOMContentLoaded', function () {
        document.getElementById('google-login-btn')?.addEventListener('click', handleGoogleLogin);
    });

    // Public API
    // @ts-ignore
    window.handleGoogleLogin = handleGoogleLogin;

}());
