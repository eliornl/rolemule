/**
 * @fileoverview ApplyPilot - Authentication Manager
 * Handles login, registration, form validation, and session management.
 * 
 * @description Provides authentication functionality including:
 * - Login/logout with JWT tokens
 * - User registration with validation
 * - Password strength validation
 * - Session management with auto-refresh
 * - Remember me functionality
 * 
 * @version 2.0.0
 */

/// <reference path="./types.js" />

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

/**
 * Authentication manager class.
 * Handles all authentication-related operations.
 * 
 * @class
 */
class AuthManager {
    // =============================================================================
    // CONSTANTS AND CONFIGURATION
    // =============================================================================

    /** Configuration constants */
    static CONFIG = {
        API_BASE_URL: (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1',
        REDIRECT_DELAY: 1000,
        VALIDATION_DELAY: 300,
        SESSION_REFRESH_BUFFER: 5 * 60 * 1000, // 5 minutes before expiry
        MAX_RETRY_ATTEMPTS: 3,
        RETRY_DELAY: 1000
    };

    /** Validation patterns */
    static VALIDATION_PATTERNS = {
        EMAIL: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
        PASSWORD: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/,
        NAME: /^[a-zA-Z\s]{2,50}$/
    };

    /** Password strength requirements */
    static PASSWORD_REQUIREMENTS = {
        MIN_LENGTH: 8,
        MAX_LENGTH: 128,
        REQUIRE_UPPERCASE: true,
        REQUIRE_LOWERCASE: true,
        REQUIRE_NUMBER: true,
        REQUIRE_SPECIAL: true,
        SPECIAL_CHARS: '@$!%*?&'
    };

    /** Storage keys */
    static STORAGE_KEYS = {
        AUTH_TOKEN: 'authToken',
        USER_DATA: 'user',
        REMEMBER_ME: 'rememberMe',
        CSRF_TOKEN: 'csrfToken'
    };

    /** Error messages */
    static ERROR_MESSAGES = {
        NETWORK_ERROR: 'Network error. Please check your connection and try again.',
        INVALID_EMAIL: 'Please enter a valid email address.',
        WEAK_PASSWORD: 'Password must be at least 8 characters with uppercase, lowercase, number, and special character.',
        PASSWORDS_MISMATCH: 'Passwords do not match.',
        REQUIRED_FIELD: 'This field is required.',
        INVALID_NAME: 'Name must be 2-50 characters long and contain only letters and spaces.',
        TERMS_REQUIRED: 'You must accept the terms and conditions.',
        LOGIN_FAILED: 'Login failed. Please check your credentials and try again.',
        REGISTRATION_FAILED: 'Registration failed. Please try again.',
        SESSION_EXPIRED: 'Your session has expired. Please log in again.'
    };

    // =============================================================================
    // CONSTRUCTOR AND INITIALIZATION
    // =============================================================================

    /**
     * Initialize AuthManager instance
     */
    constructor() {
        this.apiBaseUrl = AuthManager.CONFIG.API_BASE_URL;
        this.isInitialized = false;
        this.validationTimeouts = new Map();
        this.requestAbortController = null;
        
        // Initialize the authentication manager
        this.init();
    }

    /**
     * Initialize authentication manager
     * Sets up event listeners, validates session, and handles URL parameters
     */
    init() {
        try {
            // Prevent multiple initializations
            if (this.isInitialized) {
                return;
            }

            // Setup core functionality
        this.setupEventListeners();
            this.handleUrlParameters();
            this.setupFormValidation();
            this.validateExistingSession();
            
            this.isInitialized = true;
        } catch (error) {
            console.error('AuthManager initialization failed:', error);
            this.showNotification('Authentication system initialization failed', 'error');
        }
    }

    // =============================================================================
    // EVENT LISTENERS AND SETUP
    // =============================================================================

    /**
     * Setup event listeners for authentication forms and interactions
     */
    setupEventListeners() {
        // Form submission handlers
        this.setupFormSubmissionHandlers();
        
        // Password visibility toggles
        this.setupPasswordToggles();
        
        // Real-time validation handlers
        this.setupValidationHandlers();
        
        // Page visibility change handler for session management
        this.setupPageVisibilityHandler();
    }

    /**
     * Setup form submission handlers
     */
    setupFormSubmissionHandlers() {
        // Login form handler
        const loginForm = document.querySelector('#loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', (event) => this.handleLogin(event));
        }

        // Registration form handler
        const registerForm = document.querySelector('#registerForm');
        if (registerForm) {
            registerForm.addEventListener('submit', (event) => this.handleRegister(event));
        }


    }

    /**
     * Setup password visibility toggle functionality
     */
    setupPasswordToggles() {
        document.addEventListener('click', (event) => {
            const toggle = event.target.closest('.password-toggle');
            if (toggle) {
                event.preventDefault();
                this.togglePasswordVisibility(toggle);
            }
        });
    }

    /**
     * Setup real-time form validation
     */
    setupValidationHandlers() {
        document.addEventListener('input', (event) => {
            const field = event.target;
            if (field.hasAttribute('data-validate')) {
                this.handleFieldValidation(field);
            }
        });

        document.addEventListener('blur', (event) => {
            const field = event.target;
            if (field.hasAttribute('data-validate')) {
                this.validateField(field);
            }
        });
    }

    /**
     * Setup page visibility handler for session management
     */
    setupPageVisibilityHandler() {
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.isAuthenticated()) {
                this.validateExistingSession();
            }
        });
    }

    /**
     * Setup form validation enhancement
     */
    setupFormValidation() {
        // Add novalidate attribute to prevent browser validation
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.setAttribute('novalidate', '');
        });

        // Setup password strength indicator
        this.setupPasswordStrengthIndicator();
    }

    /**
     * Setup password strength indicator
     */
    setupPasswordStrengthIndicator() {
        const passwordFields = document.querySelectorAll('input[type="password"][data-validate*="password"]');
        passwordFields.forEach(field => {
            if (field.id === 'password' || field.name === 'password') {
                this.createPasswordStrengthIndicator(field);
            }
        });
    }

    // =============================================================================
    // AUTHENTICATION HANDLERS
    // =============================================================================

    /**
     * Handle login form submission
     * @param {Event} event - Form submission event
     */
    async handleLogin(event) {
        event.preventDefault();
        const form = event.target;
        
        try {
            // Clear previous alerts
            this.clearAlerts();
            
            // Validate form
            if (!this.validateForm(form)) {
                this.showNotification('Please fix the validation errors', 'error');
                return;
        }

            // Set loading state
            this.setFormLoading(form, true);

            // Extract form data
            const credentials = {
                email: form.elements.email.value,
                password: form.elements.password.value,
                remember_me: form.elements.remember_me ? form.elements.remember_me.checked : false
            };

            // Perform login
            const result = await this.performLogin(credentials);
            
            // Handle successful login
            this.handleLoginSuccess(result);
            
        } catch (error) {
            this.handleLoginError(error);
        } finally {
            this.setFormLoading(form, false);
        }
    }

    /**
     * Handle registration form submission
     * @param {Event} event - Form submission event
     */
    async handleRegister(event) {
        event.preventDefault();
        const form = event.target;
        
        try {
            // Clear previous alerts
            this.clearAlerts();
            
            // Validate form
            if (!this.validateForm(form)) {
                this.showNotification('Please fix the validation errors', 'error');
                return;
            }

            // Set loading state
            this.setFormLoading(form, true);

            // Extract form data
            const formData = this.extractFormData(form);
            const registrationData = {
                email: formData.email,
                password: formData.password,
                confirm_password: formData.confirm_password,
                full_name: `${formData.first_name} ${formData.last_name}`.trim()
            };

            // Perform registration
            const result = await this.performRegistration(registrationData);
            
            // Handle successful registration
            this.handleRegistrationSuccess(result);
            
        } catch (error) {
            this.handleRegistrationError(error);
        } finally {
            this.setFormLoading(form, false);
        }
    }



    // =============================================================================
    // API COMMUNICATION
    // =============================================================================

    /**
     * Perform login API call
     * @param {Object} credentials - Login credentials
     * @returns {Promise<Object>} Authentication response
     */
    async performLogin(credentials) {
        return this.makeApiCall('/auth/login', 'POST', credentials);
    }

    /**
     * Perform registration API call
     * @param {Object} registrationData - Registration data
     * @returns {Promise<Object>} Authentication response
     */
    async performRegistration(registrationData) {
        return this.makeApiCall('/auth/register', 'POST', registrationData);
    }

    /**
     * Verify current authentication token
     * @returns {Promise<Object>} Verification result
     */
    async verifyToken() {
        return this.makeApiCall('/auth/verify', 'GET');
    }

    /**
     * Make authenticated API call
     * @param {string} endpoint - API endpoint
     * @param {string} method - HTTP method
     * @param {Object} data - Request data
     * @param {Object} options - Additional options
     * @returns {Promise<Object>} API response
     */
    async makeApiCall(endpoint, method = 'GET', data = null, options = {}) {
        try {
            // Abort previous request if still pending
            if (this.requestAbortController) {
                this.requestAbortController.abort();
            }

            // Create new abort controller
            this.requestAbortController = new AbortController();

            const config = {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    ...options.headers
                },
                signal: this.requestAbortController.signal
            };

            // Add request body for non-GET requests
            if (data && method !== 'GET') {
                config.body = JSON.stringify(data);
            }

            // Add authentication token if available
            const token = this.getAuthToken();
            if (token) {
                config.headers.Authorization = `Bearer ${token}`;
            }

            // Note: CSRF tokens not needed - using JWT authentication

            // Make API call
            const response = await fetch(`${this.apiBaseUrl}${endpoint}`, config);
            
            // Handle JSON parsing with error handling
            let result;
            try {
                result = await response.json();
            } catch (parseError) {
                // Handle non-JSON responses
                throw new Error(`Invalid JSON response: ${response.status}`);
            }

            // Handle response
            if (!response.ok) {
                // Format error message in a user-friendly way
                let errorMessage = 'An error occurred';
                
                // Use appropriate user-friendly messages based on status code
                if (response.status === 401) {
                    errorMessage = 'Invalid email or password';
                } else if (response.status === 422) {
                    errorMessage = 'Please enter all required fields';
                } else if (response.status === 500) {
                    errorMessage = 'Server error. Please try again later.';
                } else if (response.status === 404) {
                    errorMessage = 'Resource not found';
                } else if (response.status === 403) {
                    errorMessage = 'You do not have permission to access this resource';
                }
                
                throw new Error(errorMessage);
            }

            return result;
        } catch (error) {
            // Handle abort errors
            if (error.name === 'AbortError') {
                return null;
            }

            // Re-throw other errors
            throw error;
        } finally {
            // Clean up abort controller
            this.requestAbortController = null;
        }
    }

    // =============================================================================
    // SUCCESS AND ERROR HANDLERS
    // =============================================================================

    /**
     * Handle successful login
     * @param {Object} result - Login result from API
     */
    handleLoginSuccess(result) {
        try {
            // Store session data
            this.storeAuthData(result);
            
            // Notify Chrome extension of login (if installed)
            this.notifyChromeExtension(result.access_token, result.user);
            
            // Track login event (if Analytics is loaded)
            if (window.Analytics) {
                window.Analytics.trackLogin('email');
                if (result.user_id) {
                    window.Analytics.identify(result.user_id, { email: result.email });
                }
            }
            
            // Show success message
            this.showNotification('Login successful! Redirecting...', 'success');
            
            // Redirect user
            this.redirectUser(result.profile_completed);
            
        } catch (error) {
            console.error('Login success handling failed:', error);
            this.showNotification('Login succeeded but there was an error. Please refresh the page.', 'warning');
        }
    }

    /**
     * Handle login error
     * @param {Error} error - Login error
     */
    handleLoginError(error) {
        console.error('Login failed:', error);
        
        let message = AuthManager.ERROR_MESSAGES.LOGIN_FAILED;
        
        // Customize error message based on error type
        if (error.message.includes('network') || error.message.includes('fetch')) {
            message = AuthManager.ERROR_MESSAGES.NETWORK_ERROR;
        } else if (error.message.includes('credentials') || error.message.includes('invalid')) {
            message = 'Invalid email or password. Please try again.';
        } else if (error.message) {
            message = error.message;
        }
        
        this.showNotification(message, 'error');
    }

    /**
     * Handle successful registration
     * @param {Object} result - Registration result from API
     */
    handleRegistrationSuccess(result) {
        try {
            // Store session data
            this.storeAuthData(result);
            
            // Notify Chrome extension of login (if installed)
            this.notifyChromeExtension(result.access_token, result.user);
            
            // Track signup event (if Analytics is loaded)
            if (window.Analytics) {
                window.Analytics.trackSignup('email');
                if (result.user_id) {
                    window.Analytics.identify(result.user_id, { email: result.email });
                }
            }
            
            // Show success message
            this.showNotification('Registration successful! Welcome to ApplyPilot!', 'success');
            
            // Redirect to profile setup (new users need to complete profile)
                setTimeout(() => {
                window.location.href = '/profile/setup';
            }, AuthManager.CONFIG.REDIRECT_DELAY);
            
        } catch (error) {
            console.error('Registration success handling failed:', error);
            this.showNotification('Registration succeeded but there was an error. Please refresh the page.', 'warning');
        }
    }

    /**
     * Handle registration error
     * @param {Error} error - Registration error
     */
    handleRegistrationError(error) {
        console.error('Registration failed:', error);
        
        let message = AuthManager.ERROR_MESSAGES.REGISTRATION_FAILED;
        
        // Customize error message based on error type
        if (error.message.includes('network') || error.message.includes('fetch')) {
            message = AuthManager.ERROR_MESSAGES.NETWORK_ERROR;
        } else if (error.message.includes('exists') || error.message.includes('duplicate')) {
            message = 'An account with this email already exists. Please try logging in instead.';
        } else if (error.message) {
            message = error.message;
        }
        
        this.showNotification(message, 'error');
    }




    // =============================================================================
    // FORM VALIDATION
    // =============================================================================

    /**
     * Validate entire form
     * @param {HTMLFormElement} form - Form to validate
     * @returns {boolean} Whether form is valid
     */
    validateForm(form) {
        const fields = form.querySelectorAll('[data-validate]');
        let isValid = true;
        
        fields.forEach(field => {
            if (!this.validateField(field)) {
                isValid = false;
            }
        });
        
        return isValid;
    }

    /**
     * Validate individual field
     * @param {HTMLElement} field - Field to validate
     * @returns {boolean} Whether field is valid
     */
    validateField(field) {
        const value = field.value.trim();
        const validationType = field.getAttribute('data-validate');
        const validationRules = validationType.split(',');
        
        let isValid = true;
        let errorMessage = '';
        
        // Check each validation rule
        for (const rule of validationRules) {
            const ruleResult = this.validateRule(value, rule.trim(), field);
            if (!ruleResult.isValid) {
                isValid = false;
                errorMessage = ruleResult.message;
                break;
            }
        }
        
        // Update field UI
        this.updateFieldValidationState(field, isValid, errorMessage);
        
        // Update password strength indicator if applicable
        if (field.type === 'password' && field.id === 'password') {
            this.updatePasswordStrengthIndicator(field, value);
        }
        
        return isValid;
    }

    /**
     * Validate a specific rule
     * @param {string} value - Field value
     * @param {string} rule - Validation rule
     * @param {HTMLElement} field - Field element
     * @returns {Object} Validation result
     */
    validateRule(value, rule, field) {
        switch (rule) {
            case 'required':
                return {
                    isValid: value.length > 0,
                    message: AuthManager.ERROR_MESSAGES.REQUIRED_FIELD
                };
                
            case 'email':
                return {
                    isValid: AuthManager.VALIDATION_PATTERNS.EMAIL.test(value),
                    message: AuthManager.ERROR_MESSAGES.INVALID_EMAIL
                };
                
            case 'password':
                return {
                    isValid: this.validatePassword(value).isValid,
                    message: AuthManager.ERROR_MESSAGES.WEAK_PASSWORD
                };
                
            case 'password-confirm':
                const passwordField = document.querySelector('#password');
                const passwordValue = passwordField ? passwordField.value : '';
                return {
                    isValid: value === passwordValue,
                    message: AuthManager.ERROR_MESSAGES.PASSWORDS_MISMATCH
                };
                
            case 'name':
                return {
                    isValid: AuthManager.VALIDATION_PATTERNS.NAME.test(value),
                    message: AuthManager.ERROR_MESSAGES.INVALID_NAME
                };
                
            case 'terms':
                return {
                    isValid: field.checked,
                    message: AuthManager.ERROR_MESSAGES.TERMS_REQUIRED
                };
                
            default:
                return { isValid: true, message: '' };
        }
    }

    /**
     * Validate password strength
     * @param {string} password - Password to validate
     * @returns {Object} Validation result with strength details
     */
    validatePassword(password) {
        const requirements = AuthManager.PASSWORD_REQUIREMENTS;
        const checks = {
            length: password.length >= requirements.MIN_LENGTH,
            uppercase: requirements.REQUIRE_UPPERCASE ? /[A-Z]/.test(password) : true,
            lowercase: requirements.REQUIRE_LOWERCASE ? /[a-z]/.test(password) : true,
            number: requirements.REQUIRE_NUMBER ? /\d/.test(password) : true,
            special: requirements.REQUIRE_SPECIAL ? new RegExp(`[${requirements.SPECIAL_CHARS}]`).test(password) : true
        };
        
        const passedChecks = Object.values(checks).filter(check => check).length;
        const totalChecks = Object.keys(checks).length;
        
        return {
            isValid: passedChecks === totalChecks,
            strength: passedChecks / totalChecks,
            checks,
            score: passedChecks
        };
    }

    /**
     * Handle field validation with debouncing
     * @param {HTMLElement} field - Field element
     */
    handleFieldValidation(field) {
        // Clear existing timeout for this field
        if (this.validationTimeouts.has(field)) {
            clearTimeout(this.validationTimeouts.get(field));
        }
        
        // Set new timeout
        const timeout = setTimeout(() => {
            this.validateField(field);
            this.validationTimeouts.delete(field);
        }, AuthManager.CONFIG.VALIDATION_DELAY);
        
        this.validationTimeouts.set(field, timeout);
    }

    // =============================================================================
    // UI UTILITY FUNCTIONS
    // =============================================================================

    /**
     * Update field validation state
     * @param {HTMLElement} field - Field element
     * @param {boolean} isValid - Whether field is valid
     * @param {string} errorMessage - Error message to display
     */
    updateFieldValidationState(field, isValid, errorMessage) {
        const feedbackElement = this.getOrCreateFeedbackElement(field);
        
        // Update field classes
        field.classList.remove('is-valid', 'is-invalid');
        field.classList.add(isValid ? 'is-valid' : 'is-invalid');
        
        // Update feedback
        if (isValid) {
            feedbackElement.textContent = '';
            feedbackElement.classList.remove('show');
        } else {
            feedbackElement.textContent = errorMessage;
            feedbackElement.classList.add('show');
        }
        
        // Update ARIA attributes
        field.setAttribute('aria-invalid', isValid ? 'false' : 'true');
        if (!isValid) {
            field.setAttribute('aria-describedby', feedbackElement.id);
        } else {
            field.removeAttribute('aria-describedby');
        }
    }

    /**
     * Get or create feedback element for field
     * @param {HTMLElement} field - Field element
     * @returns {HTMLElement} Feedback element
     */
    getOrCreateFeedbackElement(field) {
        const fieldContainer = field.closest('.form-floating') || field.parentNode;
        let feedbackElement = fieldContainer.querySelector('.invalid-feedback');
        
        if (!feedbackElement) {
            feedbackElement = document.createElement('div');
            feedbackElement.className = 'invalid-feedback';
            feedbackElement.id = `${field.id || field.name}-feedback`;
            fieldContainer.appendChild(feedbackElement);
        }
        
        return feedbackElement;
    }

    /**
     * Create password strength indicator
     * @param {HTMLElement} passwordField - Password field
     */
    createPasswordStrengthIndicator(passwordField) {
        const container = passwordField.closest('.form-floating') || passwordField.parentNode;
        
        // Check if indicator already exists
        if (container.querySelector('.password-strength-indicator')) {
            return;
        }
        
        const indicator = document.createElement('div');
        indicator.className = 'password-strength-indicator';
        indicator.innerHTML = `
            <div class="strength-bar">
                <div class="strength-fill"></div>
            </div>
            <div class="strength-text">Password strength</div>
        `;
        
        container.appendChild(indicator);
    }

    /**
     * Update password strength indicator
     * @param {HTMLElement} passwordField - Password field
     * @param {string} password - Password value
     */
    updatePasswordStrengthIndicator(passwordField, password) {
        const container = passwordField.closest('.form-floating') || passwordField.parentNode;
        const indicator = container.querySelector('.password-strength-indicator');
        
        if (!indicator) {
            return;
        }
        
        const validation = this.validatePassword(password);
        const strengthFill = indicator.querySelector('.strength-fill');
        const strengthText = indicator.querySelector('.strength-text');
        
        // Update strength bar
        const strengthPercentage = validation.strength * 100;
        strengthFill.style.width = `${strengthPercentage}%`;
        
        // Update strength text and color
        let strengthLevel = 'weak';
        let strengthMessage = 'Weak password';
        
        if (validation.strength >= 0.8) {
            strengthLevel = 'strong';
            strengthMessage = 'Strong password';
        } else if (validation.strength >= 0.6) {
            strengthLevel = 'medium';
            strengthMessage = 'Medium password';
        }
        
        strengthFill.className = `strength-fill ${strengthLevel}`;
        strengthText.textContent = strengthMessage;
        
        // Show/hide indicator based on password length
        indicator.style.display = password.length > 0 ? 'block' : 'none';
    }

    /**
     * Toggle password visibility
     * @param {HTMLElement} toggleButton - Toggle button
     */
    togglePasswordVisibility(toggleButton) {
        const passwordField = toggleButton.parentNode.querySelector('input[type="password"], input[type="text"]');
        const icon = toggleButton.querySelector('i');
        
        if (!passwordField || !icon) {
            return;
        }
        
        if (passwordField.type === 'password') {
            passwordField.type = 'text';
                icon.className = 'fas fa-eye-slash';
            toggleButton.setAttribute('aria-label', 'Hide password');
            } else {
            passwordField.type = 'password';
                icon.className = 'fas fa-eye';
            toggleButton.setAttribute('aria-label', 'Show password');
        }
    }

    /**
     * Set form loading state
     * @param {HTMLFormElement} form - Form element
     * @param {boolean} loading - Whether form is loading
     */
    setFormLoading(form, loading) {
        const submitButton = form.querySelector('button[type="submit"]');
        const inputs = form.querySelectorAll('input, select, textarea, button');

        if (loading) {
            // Disable form
            inputs.forEach(input => {
                input.disabled = true;
            });
            
            // Update submit button
            if (submitButton) {
                const originalText = submitButton.getAttribute('data-original-text') || submitButton.textContent;
                submitButton.setAttribute('data-original-text', originalText);
                submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
                submitButton.setAttribute('aria-busy', 'true');
            }
        } else {
            // Enable form
            inputs.forEach(input => {
                input.disabled = false;
            });
            
            // Restore submit button
            if (submitButton) {
                const originalText = submitButton.getAttribute('data-original-text');
                if (originalText) {
                    submitButton.textContent = originalText;
                }
                submitButton.setAttribute('aria-busy', 'false');
            }
        }
    }

    /**
     * Extract form data
     * @param {HTMLFormElement} form - Form element
     * @returns {Object} Form data object
     */
    extractFormData(form) {
        const formData = new FormData(form);
        const data = {};
        
        for (const [key, value] of formData.entries()) {
            data[key] = value;
        }
        
        return data;
    }

    /**
     * Show notification to user
     * @param {string} message - Notification message
     * @param {string} type - Notification type (success, error, warning, info)
     */
    showNotification(message, type = 'info') {
        try {
            // Try to use global app notification system
        if (window.app && typeof window.app.showNotification === 'function') {
            window.app.showNotification(message, type);
            return;
        }

            // Fallback to alert container
            this.showAlertNotification(message, type);
        } catch (error) {
            console.error('Notification display failed:', error);
        }
    }

    /**
     * Show alert notification as fallback
     * @param {string} message - Notification message
     * @param {string} type - Notification type
     */
    showAlertNotification(message, type) {
        const alertContainer = this.getOrCreateAlertContainer();
        
        const alertTypes = {
            success: { class: 'alert-success', icon: 'fas fa-check-circle' },
            error: { class: 'alert-danger', icon: 'fas fa-exclamation-triangle' },
            warning: { class: 'alert-warning', icon: 'fas fa-exclamation-circle' },
            info: { class: 'alert-info', icon: 'fas fa-info-circle' }
        };
        
        const alertInfo = alertTypes[type] || alertTypes.info;

        const alert = document.createElement('div');
        alert.className = `alert ${alertInfo.class} alert-dismissible fade show`;
        alert.setAttribute('role', 'alert');
        const iconEl = document.createElement('i');
        iconEl.className = `${alertInfo.icon} me-2`;
        const msgNode = document.createTextNode(message);
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'btn-close';
        closeBtn.setAttribute('data-bs-dismiss', 'alert');
        closeBtn.setAttribute('aria-label', 'Close');
        alert.appendChild(iconEl);
        alert.appendChild(msgNode);
        alert.appendChild(closeBtn);

        alertContainer.appendChild(alert);

        // Auto-remove after 5 seconds for non-error messages
        if (type !== 'error') {
        setTimeout(() => {
            if (alert.parentNode) {
                alert.remove();
            }
        }, 5000);
        }
    }

    /**
     * Get or create alert container
     * @returns {HTMLElement} Alert container
     */
    getOrCreateAlertContainer() {
        let container = document.querySelector('.alert-container');
        
        if (!container) {
            container = document.createElement('div');
            container.className = 'alert-container';
            container.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 1060;
                max-width: 400px;
            `;
            document.body.appendChild(container);
        }
        
        return container;
    }

    /**
     * Clear all alerts
     */
    clearAlerts() {
        const alertContainer = document.querySelector('.alert-container');
        if (alertContainer) {
            alertContainer.innerHTML = '';
        }
    }

    // =============================================================================
    // SESSION MANAGEMENT
    // =============================================================================

    /**
     * Notify Chrome extension of successful authentication.
     * Uses postMessage to communicate with the extension's content script,
     * which then relays the token to the extension's service worker.
     * @param {string} token - JWT access token
     * @param {Object} user - User data object
     */
    notifyChromeExtension(token, user) {
        try {
            // Method 1: Broadcast via window message (content script can pick this up)
            window.postMessage({
                type: 'JAA_AUTH_SUCCESS',
                token: token,
                user: user,
                apiUrl: window.location.origin + ((window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1')
            }, window.location.origin);
            
            // Method 2: Try direct extension messaging (if extension ID is known)
            // This works when the extension declares externally_connectable in manifest
            if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
                // This branch runs if we're in a Chrome extension context
                chrome.runtime.sendMessage({
                    type: 'AUTH_SUCCESS',
                    token: token,
                    user: user
                }).catch(() => {}); // Silently fail if extension not available
            }
            
            console.debug('Chrome extension auth notification sent');
        } catch (error) {
            // Silently fail - extension may not be installed
            console.debug('Chrome extension notification skipped:', error.message);
        }
    }

    /**
     * Store authentication data
     * @param {Object} authData - Authentication data
     */
    storeAuthData(authData) {
        try {
            localStorage.setItem(AuthManager.STORAGE_KEYS.AUTH_TOKEN, authData.access_token);
            localStorage.setItem('access_token', authData.access_token); // For backward compatibility
            localStorage.setItem(AuthManager.STORAGE_KEYS.USER_DATA, JSON.stringify(authData.user));
            
            // Store remember me preference
            if (authData.remember_me) {
                localStorage.setItem(AuthManager.STORAGE_KEYS.REMEMBER_ME, 'true');
            }
            
            // Update instance properties
            this.user = authData.user;
            this.token = authData.access_token;
            
            // Integrate with main app if available
            if (window.app && typeof window.app.setSession === 'function') {
                window.app.setSession(authData.access_token, authData.user);
            }
            
        } catch (error) {
            console.error('Failed to store authentication data:', error);
            throw new Error('Failed to save session data');
        }
    }

    /**
     * Check if user is authenticated
     * @returns {boolean} Authentication status
     */
    isAuthenticated() {
        return !!this.getAuthToken();
    }

    /**
     * Get authentication token
     * @returns {string|null} Authentication token
     */
    getAuthToken() {
        return localStorage.getItem(AuthManager.STORAGE_KEYS.AUTH_TOKEN);
    }

    /**
     * Get current user data
     * @returns {Object|null} User data
     */
    getCurrentUser() {
        try {
            const userData = localStorage.getItem(AuthManager.STORAGE_KEYS.USER_DATA);
            return userData ? JSON.parse(userData) : null;
        } catch (error) {
            console.error('Failed to parse user data:', error);
            return null;
        }
    }

    /**
     * Clear session data
     */
    clearSession() {
        localStorage.removeItem(AuthManager.STORAGE_KEYS.AUTH_TOKEN);
        localStorage.removeItem(AuthManager.STORAGE_KEYS.USER_DATA);
        localStorage.removeItem(AuthManager.STORAGE_KEYS.REMEMBER_ME);
        
        this.user = null;
        this.token = null;
    }

    /**
     * Validate existing session
     */
    async validateExistingSession() {
        if (!this.isAuthenticated()) {
            return;
        }
        
        try {
            // Use main app's session validation if available
            if (window.app && typeof window.app.checkAuthStatus === 'function') {
                await window.app.checkAuthStatus();
            }
        } catch (error) {
            console.error('Session validation failed:', error);
            this.clearSession();
        }
    }

    /**
     * Redirect user based on authentication state
     * @param {boolean} profileCompleted - Whether profile is completed
     */
    redirectUser(profileCompleted = false) {
        const defaultDestination = profileCompleted ? '/dashboard' : '/profile/setup';
        let destination = defaultDestination;

        try {
            const urlParams = new URLSearchParams(window.location.search);
            const rawRedirect = urlParams.get('redirect');
            const validatedRedirect = validateRelativeRedirectPath(rawRedirect);
            if (validatedRedirect) {
                destination = validatedRedirect;
            }
        } catch (error) {
            console.error('Redirect validation failed:', error);
        }

        const safeDestination = destination;
        setTimeout(() => {
            window.location.href = safeDestination;
        }, AuthManager.CONFIG.REDIRECT_DELAY);
    }

    /**
     * Redirect if already authenticated
     */
    redirectIfAuthenticated() {
        if (this.isAuthenticated()) {
            window.location.href = '/dashboard';
        }
    }

    // =============================================================================
    // URL PARAMETER HANDLING
    // =============================================================================

    /**
     * Handle URL parameters for authentication feedback
     */
    handleUrlParameters() {
        try {
            const urlParams = new URLSearchParams(window.location.search);
            
            // Handle OAuth success
            if (urlParams.has('oauth_success')) {
                this.showNotification('Account linked successfully!', 'success');
                // Track Google login (if Analytics is loaded)
                if (window.Analytics) {
                    window.Analytics.trackLogin('google');
                }
                this.cleanUrl();
            }
            
            // Handle OAuth errors
            if (urlParams.has('oauth_error')) {
                this.showNotification('OAuth authentication failed. Please try again.', 'error');
                this.cleanUrl();
            }
            
            // Handle email verification
            if (urlParams.has('verified')) {
                this.showNotification('Email verified successfully! You can now log in.', 'success');
                this.cleanUrl();
            }
            
            // Handle registration success
            if (urlParams.has('registered')) {
                this.showNotification('Registration successful! Please log in.', 'success');
                this.cleanUrl();
            }
            
            // Handle password reset
            if (urlParams.has('password_reset')) {
                this.showNotification('Password reset successfully! You can now log in.', 'success');
                this.cleanUrl();
            }
            
        } catch (error) {
            console.error('URL parameter handling failed:', error);
        }
    }

    /**
     * Clean URL parameters
     */
    cleanUrl() {
        try {
            window.history.replaceState({}, document.title, window.location.pathname);
        } catch (error) {
            console.error('URL cleanup failed:', error);
        }
    }

    // =============================================================================
    // UTILITY FUNCTIONS
    // =============================================================================

    /**
     * Get CSRF token
     * Note: Not used - this application uses JWT authentication instead of CSRF tokens
     * @returns {string|null} CSRF token
     */
    getCSRFToken() {
        // Try meta tag first
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }

        // Try cookie
        const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
        if (cookieMatch) {
            return cookieMatch[1];
        }
        
        // Try localStorage
        return localStorage.getItem(AuthManager.STORAGE_KEYS.CSRF_TOKEN);
    }

    /**
     * Cleanup resources
     */
    cleanup() {
        // Clear validation timeouts
        this.validationTimeouts.forEach(timeout => clearTimeout(timeout));
        this.validationTimeouts.clear();
        
        // Abort pending requests
        if (this.requestAbortController) {
            this.requestAbortController.abort();
        }
        
        // Clear session if not remembered
        const rememberMe = localStorage.getItem(AuthManager.STORAGE_KEYS.REMEMBER_ME);
        if (!rememberMe) {
            this.clearSession();
        }
    }

    // =============================================================================
    // PUBLIC API METHODS
    // =============================================================================

    /**
     * Login user programmatically
     * @param {Object} credentials - Login credentials
     * @returns {Promise<Object>} Login result
     */
    async login(credentials) {
        return this.performLogin(credentials);
    }

    /**
     * Register user programmatically
     * @param {Object} registrationData - Registration data
     * @returns {Promise<Object>} Registration result
     */
    async register(registrationData) {
        return this.performRegistration(registrationData);
    }

    /**
     * Logout user
     * @returns {Promise<void>}
     */
    async logout() {
        try {
            // Use main app's logout if available
            if (window.app && typeof window.app.logout === 'function') {
                await window.app.logout();
            } else {
                this.clearSession();
                window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
            }
        } catch (error) {
            console.error('Logout failed:', error);
            this.clearSession();
            window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
        }
    }

    /**
     * Refresh authentication token
     * @returns {Promise<Object>} Refresh result
     */
    async refreshToken() {
        if (window.app && typeof window.app.refreshToken === 'function') {
            return window.app.refreshToken();
        }
        throw new Error('Token refresh not available');
    }
}

// =============================================================================
// INITIALIZATION AND EXPORT
// =============================================================================

/**
 * Initialize AuthManager when DOM is ready
 */
function initializeAuthManager() {
    try {
        // Create global instance
    window.authManager = new AuthManager();

        // Auto-redirect if authenticated on auth pages
    if (window.location.pathname.includes('/auth/')) {
        window.authManager.redirectIfAuthenticated();
        }
        
        console.log('AuthManager initialized successfully');
    } catch (error) {
        console.error('AuthManager initialization failed:', error);
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeAuthManager);
} else {
    initializeAuthManager();
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.authManager) {
        window.authManager.cleanup();
    }
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AuthManager;
}

// Export for ES6 modules
if (typeof window !== 'undefined') {
    window.AuthManager = AuthManager;
}

