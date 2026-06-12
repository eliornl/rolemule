/**
 * @fileoverview ApplyPilot - Main Application JavaScript
 * Handles core functionality, API communication, and UI interactions.
 * 
 * @description This is the main entry point for the frontend application.
 * It provides authentication, API communication, notifications, and UI utilities.
 */

/// <reference path="./types.js" />

/**
 * Main application class for the ApplyPilot.
 * Provides core functionality including authentication, API calls, notifications, and UI utilities.
 * 
 * @class
 * @example
 * // Access the global instance
 * window.app.showNotification('Hello!', 'success');
 * 
 * // Make an API call
 * const data = await window.app.apiCall('/workflow/list', 'GET');
 */
class JobApplicationAssistant {
    /**
     * Create a new JobApplicationAssistant instance.
     * Automatically initializes on DOMContentLoaded.
     */
    constructor() {
        /** @type {string} Base URL for API calls */
        this.apiBaseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';
        
        /** @type {string|null} JWT authentication token */
        this.token = localStorage.getItem('access_token') || localStorage.getItem('authToken');
        
        /** @type {import('./types.js').User} Current user data */
        this.user = JSON.parse(localStorage.getItem('user') || '{}');
        
        /** @type {string|null} CSRF token (not used with JWT auth) */
        this.csrfToken = this.getCSRFToken();
        
        /** @type {Promise<any>|null} Tracks ongoing token refresh to prevent duplicates */
        this.refreshPromise = null;
        
        /** @type {number|null} Timer ID for auto-refresh */
        this.refreshTimer = null;

        this.init();
    }

    /**
     * Initialize the application
     */
    init() {
        this.setupEventListeners();
        this.setupAjaxDefaults();
        this.checkAuthStatus();
        this.initializeComponents();
        this.setupAutoRefresh();
    }

    /**
     * Setup global event listeners
     */
    setupEventListeners() {
        // Global error handling
        window.addEventListener('error', (event) => {
            console.error('Global error:', event.error);
            this.showNotification('An unexpected error occurred', 'error');
        });

        // Handle unhandled promise rejections
        window.addEventListener('unhandledrejection', (event) => {
            console.error('Unhandled promise rejection:', event.reason);
            this.showNotification('Network request failed', 'error');
        });

        // Handle form submissions
        document.addEventListener('submit', (event) => {
            const target = /** @type {Element|null} */ (event.target);
            if (target?.matches('.ajax-form')) {
                event.preventDefault();
                this.handleFormSubmission(/** @type {HTMLFormElement} */ (target));
            }
        });

        // Handle file uploads
        document.addEventListener('change', (event) => {
            const target = /** @type {Element|null} */ (event.target);
            if (target?.matches('.file-upload-input')) {
                this.handleFileUpload(/** @type {HTMLInputElement} */ (target));
            }
        });

        // Handle drag and drop
        document.addEventListener('dragover', (event) => {
            const target = /** @type {Element|null} */ (event.target);
            if (target?.closest('.file-upload-area')) {
                event.preventDefault();
                target.closest('.file-upload-area')?.classList.add('drag-over');
            }
        });

        document.addEventListener('dragleave', (event) => {
            const target = /** @type {Element|null} */ (event.target);
            if (target?.closest('.file-upload-area')) {
                target.closest('.file-upload-area')?.classList.remove('drag-over');
            }
        });

        document.addEventListener('drop', (event) => {
            const target = /** @type {Element|null} */ (event.target);
            const uploadArea = target?.closest('.file-upload-area');
            if (uploadArea) {
                event.preventDefault();
                uploadArea.classList.remove('drag-over');
                const fileInput = /** @type {HTMLInputElement|null} */ (uploadArea.querySelector('.file-upload-input'));
                if (fileInput && (event.dataTransfer?.files?.length ?? 0) > 0) {
                    fileInput.files = /** @type {DataTransfer} */ (event.dataTransfer).files;
                    this.handleFileUpload(fileInput);
                }
            }
        });

        // Handle logout via class or data-action
        document.addEventListener('click', (event) => {
            const target = /** @type {Element|null} */ (event.target);
            const actionEl = /** @type {HTMLElement|null} */ (target?.closest('[data-action]'));
            if (target?.matches('.logout-btn, .logout-btn *') || actionEl?.dataset['action'] === 'logout') {
                event.preventDefault();
                this.logout();
            }
        });
    }

    /**
     * Setup AJAX defaults - removed global fetch override for better compatibility
     */
    setupAjaxDefaults() {
        // Headers are now applied in the apiCall method only
        // This avoids interfering with third-party requests
    }

    /**
     * Get CSRF token from meta tag or cookie
     * Note: This app uses JWT authentication, not CSRF tokens
     */
    getCSRFToken() {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }

        // Fallback to cookie
        const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
        return cookieMatch ? cookieMatch[1] : null;
    }

    /**
     * Check authentication status
     */
    async checkAuthStatus() {
        if (!this.token) {
            return;
        }

        try {
            const response = /** @type {Record<string,any>} */ (await this.apiCall('/auth/verify', 'GET'));
            if (!response['success']) {
                this.logout();
            }
        } catch (error) {
            console.error('Auth verification failed:', error);
            this.logout();
        }
    }

    /**
     * Initialize UI components
     */
    initializeComponents() {
        this.initializeTooltips();
        this.initializeProgressBars();
        this.initializeModals();
        this.initializeFormValidation();
    }

    /**
     * Setup automatic token refresh before expiration
     */
    setupAutoRefresh() {
        if (!this.token) {
            return;
        }

        // Clear any existing refresh timer
        if (this.refreshTimer) {
            clearTimeout(this.refreshTimer);
        }

        // Set up proactive refresh 5 minutes before expiration
        // Token expires in 1 hour (3600 seconds), so refresh after 55 minutes
        const refreshDelay = 55 * 60 * 1000; // 55 minutes in milliseconds

        this.refreshTimer = setTimeout(async () => {
            try {
                // Proactively refresh token
                await this.refreshToken();
                this.setupAutoRefresh(); // Set up next refresh
            } catch (error) {
                console.error('Proactive token refresh failed:', error);
                // Don't logout on proactive refresh failure, let regular request handle it
            }
        }, refreshDelay);
    }

    /**
     * Initialize Bootstrap tooltips
     */
    initializeTooltips() {
        // @ts-ignore
        const bs = typeof bootstrap !== 'undefined' ? /** @type {any} */ (bootstrap) : null;
        if (bs) {
            const tooltipTriggerList = /** @type {any[]} */ ([].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]')));
            tooltipTriggerList.map(/** @param {any} el */ el => new bs.Tooltip(el));
        }
    }

    /**
     * Initialize progress bars with animation
     */
    initializeProgressBars() {
        const progressBars = document.querySelectorAll('.progress-bar');
        progressBars.forEach(barEl => {
            const bar = /** @type {HTMLElement} */ (barEl);
            const width = bar.getAttribute('data-width') || bar.style.width;
            if (width) {
                bar.style.width = '0%';
                setTimeout(() => { bar.style.width = width; }, 100);
            }
        });
    }

    /**
     * Initialize modal components
     */
    initializeModals() {
        const modals = document.querySelectorAll('.modal');
        modals.forEach(modal => {
            modal.addEventListener('show.bs.modal', () => {
                document.body.classList.add('modal-open');
            });

            modal.addEventListener('hidden.bs.modal', () => {
                document.body.classList.remove('modal-open');
            });
        });
    }

    /**
     * Initialize form validation
     */
    initializeFormValidation() {
        const forms = document.querySelectorAll('.needs-validation');
        forms.forEach(formEl => {
            const form = /** @type {HTMLFormElement} */ (formEl);
            form.addEventListener('submit', (event) => {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                form.classList.add('was-validated');
            });
        });
    }

    /**
     * Refresh JWT token to extend session
     */
    async refreshToken() {
        // If there's already a refresh in progress, wait for it
        if (this.refreshPromise) {
            return this.refreshPromise;
        }

        // Start refresh process
        this.refreshPromise = this._performTokenRefresh();
        
        try {
            const result = await this.refreshPromise;
            this.refreshPromise = null;
            return result;
        } catch (error) {
            this.refreshPromise = null;
            throw error;
        }
    }

    /**
     * Perform the actual token refresh
     */
    async _performTokenRefresh() {
        if (!this.token) {
            throw new Error('No token to refresh');
        }

        try {
            const response = await fetch(`${this.apiBaseUrl}/auth/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (!response.ok) {
                throw new Error(`Refresh failed: ${response.status}`);
            }

            const result = await response.json();
            
            // Update stored token
            this.token = result.access_token;
            localStorage.setItem('authToken', result.access_token);
            
            // Set up auto-refresh for the new token
            this.setupAutoRefresh();
            
            // Token refreshed successfully
            this.showNotification('Session extended successfully', 'success');
            return result;
        } catch (error) {
            console.error('Token refresh failed:', error);
            throw error;
        }
    }

    /**
     * Make API calls with automatic token refresh.
     * Handles authentication, JSON serialization, and error handling.
     * 
     * @param {string} endpoint - API endpoint (e.g., '/workflow/list')
     * @param {'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'} [method='GET'] - HTTP method
     * @param {Object|FormData|null} [data=null] - Request body data
     * @param {import('./types.js').ApiCallOptions} [options={}] - Additional options
     * @returns {Promise<Object>} Response data
     * @throws {Error} If the request fails or returns an error
     * 
     * @example
     * // GET request
     * const sessions = await app.apiCall('/workflow/list');
     * 
     * // POST request with JSON
     * const result = await app.apiCall('/auth/login', 'POST', { email, password });
     * 
     * // POST with FormData
     * const formData = new FormData();
     * formData.append('file', file);
     * const uploaded = await app.apiCall('/upload', 'POST', formData);
     */
    async apiCall(endpoint, method = 'GET', data = null, options = {}) {
        const url = `${this.apiBaseUrl}${endpoint}`;
        /** @type {Record<string,any>} */
        const config = {
            method,
            headers: {
                'Content-Type': 'application/json',
                ...(/** @type {any} */ (options)).headers
            },
            ...(/** @type {any} */ (options))
        };

        if (data && method !== 'GET') {
            if (data instanceof FormData) {
                delete config['headers']['Content-Type']; // Let browser set it for FormData
                config['body'] = data;
            } else {
                config['body'] = JSON.stringify(data);
            }
        }

        if (this.token) {
            config.headers['Authorization'] = `Bearer ${this.token}`;
        }

        try {
            const response = await fetch(url, config);

            // Handle token expiration with automatic refresh
            if (response.status === 401 && !options.skipTokenRefresh && !endpoint.includes('/auth/refresh')) {
                try {
                    // Token expired, attempting refresh
                    await this.refreshToken();
                    
                    // Retry the original request with the new token
                    config.headers['Authorization'] = `Bearer ${this.token}`;
                    const retryResponse = await fetch(url, config);
                    
                    let retryResult;
                    try {
                        retryResult = await retryResponse.json();
                    } catch (parseError) {
                        throw new Error(`Invalid JSON response on retry: ${retryResponse.status}`);
                    }
                    
                    if (!retryResponse.ok) {
                        const retryErr = new Error(
                            retryResult.message || retryResult.error || `HTTP ${retryResponse.status}`,
                        );
                        if (retryResult.error_code) {
                            /** @type {any} */ (retryErr).errorCode = retryResult.error_code;
                        }
                        throw retryErr;
                    }
                    
                    return retryResult;
                } catch (refreshError) {
                    console.error('Token refresh failed, logging out:', refreshError);
                    this.logout();
                    throw new Error('Authentication failed');
                }
            }

            let result;
            try {
                result = await response.json();
            } catch (parseError) {
                // Handle non-JSON responses
                throw new Error(`Invalid JSON response: ${response.status}`);
            }

            if (!response.ok) {
                const apiErr = new Error(
                    result.message || result.detail || result.error || `HTTP ${response.status}`,
                );
                if (result.error_code) {
                    /** @type {any} */ (apiErr).errorCode = result.error_code;
                }
                if (result.details) {
                    /** @type {any} */ (apiErr).details = result.details;
                }
                throw apiErr;
            }

            return result;
        } catch (error) {
            console.error('API call failed:', error);
            throw error;
        }
    }

    /**
     * Handle form submissions
     * @param {HTMLFormElement} form
     */
    async handleFormSubmission(form) {
        const submitBtn = form.querySelector('[type="submit"]');
        const originalText = submitBtn ? submitBtn.innerHTML : '';

        try {
            // Show loading state
            if (submitBtn) {
                this.setButtonLoading(/** @type {HTMLElement} */ (submitBtn), true);
            }

            const formData = new FormData(form);
            let endpoint = form.getAttribute('data-endpoint') || form.action;
            const method = form.getAttribute('data-method') || form.method || 'POST';

            // Ensure endpoint is API-relative (starts with /)
            if (endpoint && !endpoint.startsWith('/')) {
                endpoint = '/' + endpoint;
            }
            
            // If no endpoint specified, throw error
            if (!endpoint) {
                throw new Error('No endpoint specified for form submission');
            }

            // Convert FormData to JSON if needed
            /** @type {any} */
            let data = formData;
            if (form.getAttribute('data-json')) {
                /** @type {Record<string,any>} */
                const jsonData = {};
                for (let [key, value] of formData.entries()) {
                    jsonData[key] = value;
                }
                data = jsonData;
            }

            const response = /** @type {Record<string,any>} */ (await this.apiCall(endpoint, /** @type {any} */ (method), data));

            if (response['success']) {
                this.showNotification(response['message'] || 'Success!', 'success');

                // Handle redirect — only allow relative paths (prevents open redirect)
                const rawRedirect = response['redirect'];
                if (rawRedirect && /^\/(?!\/)/.test(rawRedirect)) {
                    setTimeout(() => {
                        window.location.href = rawRedirect;
                    }, 1000);
                }

                // Trigger custom event
                const event = new CustomEvent('formSuccess', {
                    detail: { response, form }
                });
                form.dispatchEvent(event);
            } else {
                this.showNotification(response['message'] || 'Something went wrong', 'error');
            }

        } catch (error) {
            const err = /** @type {Error} */ (error);
            this.showNotification(err.message || 'Network error occurred', 'error');
        } finally {
            if (submitBtn) {
                this.setButtonLoading(/** @type {HTMLElement} */ (submitBtn), false, originalText);
            }
        }
    }

    /**
     * Handle file uploads
     * @param {HTMLInputElement} input
     */
    async handleFileUpload(input) {
        const files = input.files;
        if (!files || files.length === 0) return;

        const allowedTypes = input.getAttribute('data-allowed-types')?.split(',') || [];
        const maxSize = parseInt(input.getAttribute('data-max-size') ?? '0') || 10 * 1024 * 1024; // 10MB default

        for (let file of files) {
            // Validate file type
            if (allowedTypes.length > 0 && !allowedTypes.includes(file.type)) {
                this.showNotification(`Invalid file type: ${file.type}`, 'error');
                continue;
            }

            // Validate file size
            if (file.size > maxSize) {
                this.showNotification(`File too large: ${file.name}`, 'error');
                continue;
            }

            // Show file info
            this.displayFileInfo(input, file);
        }
    }

    /**
     * Display file information
     * @param {HTMLInputElement} input
     * @param {File} file
     */
    displayFileInfo(input, file) {
        const container = input.closest('.file-upload-area');
        const info = /** @type {HTMLElement} */ (container?.querySelector('.file-info') || document.createElement('div'));
        info.className = 'file-info mt-3';

        info.innerHTML = `
            <div class="d-flex align-items-center justify-content-between p-3 bg-light rounded">
                <div class="d-flex align-items-center">
                    <i class="fas fa-file me-2"></i>
                    <div>
                        <div class="fw-bold"></div>
                        <small class="text-muted"></small>
                    </div>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger remove-file-btn" aria-label="Remove file">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

        const nameEl = info.querySelector('.fw-bold');
        const sizeEl = info.querySelector('small.text-muted');
        if (nameEl) nameEl.textContent = file.name;
        if (sizeEl) sizeEl.textContent = this.formatFileSize(file.size);

        const removeBtn = info.querySelector('.remove-file-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', () => {
                info.remove();
                input.value = '';
            });
        }

        if (container && !container.querySelector('.file-info')) {
            container.appendChild(info);
        }
    }

    /**
     * Format file size for display
     * @param {number} bytes
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Set button loading state
     * @param {HTMLElement} button
     * @param {boolean} loading
     * @param {string|null} [originalText]
     */
    setButtonLoading(button, loading, originalText = null) {
        const btn = /** @type {HTMLButtonElement} */ (button);
        if (loading) {
            btn.disabled = true;
            btn.classList.add('btn-loading');
            if (originalText) {
                btn.setAttribute('data-original-text', originalText);
            }
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Loading...';
        } else {
            btn.disabled = false;
            btn.classList.remove('btn-loading');
            btn.innerHTML = originalText || btn.getAttribute('data-original-text') || 'Submit';
        }
    }

    /**
     * Show a notification toast message.
     * 
     * @param {string} message - Message to display
     * @param {import('./types.js').NotificationType} [type='info'] - Notification type
     * @param {number} [duration=5000] - Duration in milliseconds before auto-dismiss
     * @returns {void}
     * 
     * @example
     * app.showNotification('Profile saved!', 'success');
     * app.showNotification('Please check your input', 'warning', 8000);
     */
    showNotification(message, type = 'info', duration = 5000) {
        const toastContainer = this.getToastContainer();
        const toastId = 'toast-' + Date.now();

        const iconMap = {
            success: 'fas fa-check-circle text-success',
            error: 'fas fa-exclamation-circle text-danger',
            warning: 'fas fa-exclamation-triangle text-warning',
            info: 'fas fa-info-circle text-info'
        };

        const toast = document.createElement('div');
        toast.className = `toast fade show`;
        toast.id = toastId;
        toast.innerHTML = `
            <div class="toast-header">
                <i class="${iconMap[type]} me-2"></i>
                <strong class="me-auto">Notification</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${this.escapeHtml(message)}
            </div>
        `;

        toastContainer.appendChild(toast);

        // Auto remove after duration
        setTimeout(() => {
            if (document.getElementById(toastId)) {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);

        // Handle manual close
        toast.querySelector('.btn-close')?.addEventListener('click', () => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        });
    }

    /**
     * Get or create toast container
     */
    getToastContainer() {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            /** @type {HTMLElement} */ (container).style.zIndex = '1055';
            document.body.appendChild(container);
        }
        return container;
    }

    /**
     * Show a modal dialog.
     * SECURITY: `content` is inserted as raw innerHTML. Callers MUST pass only
     * static developer-controlled HTML — never raw user input. Use escapeHtml()
     * on any user-supplied strings before passing them here.
     * 
     * @param {string} title - Modal title (set via textContent, safe)
     * @param {string} content - Trusted HTML content for the modal body
     * @param {import('./types.js').ModalOptions} [options={}] - Modal options
     * @returns {any|undefined} Bootstrap modal instance
     * 
     * @example
     * app.showModal('Confirm', '<p>Are you sure?</p>', { 
     *   size: 'lg',
     *   footer: '<button class="btn btn-primary">OK</button>'
     * });
     */
    showModal(title, content, options = {}) {
        const modalId = 'modal-' + Date.now();
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = modalId;
        modal.innerHTML = `
            <div class="modal-dialog ${options.size ? 'modal-' + options.size : ''}">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"></h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        ${content}
                    </div>
                    ${options.footer ? `<div class="modal-footer">${options.footer}</div>` : ''}
                </div>
            </div>
        `;
        const titleEl = modal.querySelector('.modal-title');
        if (titleEl) titleEl.textContent = title;

        document.body.appendChild(modal);

        // @ts-ignore
        const bs2 = typeof bootstrap !== 'undefined' ? /** @type {any} */ (bootstrap) : null;
        if (bs2) {
            const bsModal = new bs2.Modal(modal);
            bsModal.show();

            modal.addEventListener('hidden.bs.modal', () => {
                modal.remove();
            });

            return bsModal;
        }
    }

    /**
     * Show a confirmation dialog and wait for user response.
     * 
     * @param {string} message - Confirmation message
     * @param {string} [title='Confirm'] - Dialog title
     * @param {import('./types.js').ModalOptions} [options={}] - Modal options
     * @returns {Promise<boolean>} True if confirmed, false if cancelled
     * 
     * @example
     * const confirmed = await app.confirm('Delete this item?', 'Confirm Delete');
     * if (confirmed) {
     *   await deleteItem();
     * }
     */
    confirm(message, title = 'Confirm', options = {}) {
        return new Promise((resolve) => {
            const footer = `
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button type="button" class="btn btn-primary confirm-btn">Confirm</button>
            `;

            const modal = this.showModal(title, message, { footer });

            if (modal) {
                const confirmBtn = modal._element?.querySelector('.confirm-btn');
                confirmBtn?.addEventListener('click', () => {
                    modal.hide();
                    resolve(true);
                });

                modal._element?.addEventListener('hidden.bs.modal', () => {
                    resolve(false);
                });
            }
        });
    }

    /**
     * Update progress bar
     * @param {string} selector
     * @param {number} percentage
     */
    updateProgress(selector, percentage) {
        const progressBar = /** @type {HTMLElement|null} */ (document.querySelector(selector));
        if (progressBar) {
            progressBar.style.width = percentage + '%';
            progressBar.setAttribute('aria-valuenow', String(percentage));

            const label = progressBar.querySelector('.progress-label');
            if (label) {
                label.textContent = Math.round(percentage) + '%';
            }
        }
    }

    /**
     * Animate counter
     * @param {HTMLElement} element
     * @param {number} start
     * @param {number} end
     * @param {number} [duration]
     */
    animateCounter(element, start, end, duration = 2000) {
        const range = end - start;
        const increment = end > start ? 1 : -1;
        const stepTime = Math.abs(Math.floor(duration / range));
        let current = start;

        const timer = setInterval(() => {
            current += increment;
            element.textContent = String(current);
            if (current === end) {
                clearInterval(timer);
            }
        }, stepTime);
    }

    /**
     * Format date for display
     * @param {string} dateString
     * @param {Intl.DateTimeFormatOptions} [options]
     */
    formatDate(dateString, options = {}) {
        const date = new Date(dateString);
        /** @type {Intl.DateTimeFormatOptions} */
        const defaultOptions = {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            ...options
        };
        return date.toLocaleDateString('en-US', defaultOptions);
    }

    /**
     * Format time ago
     * @param {string} dateString
     */
    timeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

        const intervals = {
            year: 31536000,
            month: 2592000,
            week: 604800,
            day: 86400,
            hour: 3600,
            minute: 60
        };

        for (let interval in intervals) {
            const count = Math.floor(diffInSeconds / intervals[/** @type {keyof typeof intervals} */ (interval)]);
            if (count >= 1) {
                return `${count} ${interval}${count !== 1 ? 's' : ''} ago`;
            }
        }

        return 'just now';
    }

    /**
     * Debounce function
     * @param {(...args: any[]) => any} func
     * @param {number} wait
     * @param {boolean} [immediate]
     */
    debounce(func, wait, immediate = false) {
        /** @type {ReturnType<typeof setTimeout>|undefined} */
        let timeout = undefined;
        return function executedFunction(/** @type {any[]} */ ...args) {
            const later = () => {
                timeout = undefined;
                if (!immediate) func(...args);
            };
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func(...args);
        };
    }

    /**
     * Throttle function
     * @param {(...args: any[]) => any} func
     * @param {number} limit
     */
    throttle(func, limit) {
        /** @type {boolean} */
        let inThrottle = false;
        return (/** @type {any[]} */ ...args) => {
            if (!inThrottle) {
                func(...args);
                inThrottle = true;
                setTimeout(() => { inThrottle = false; }, limit);
            }
        };
    }

    /**
     * Store user session data in localStorage.
     * 
     * @param {string} token - JWT access token
     * @param {import('./types.js').User} user - User data
     * @returns {void}
     */
    setSession(token, user) {
        this.token = token;
        this.user = user;
        localStorage.setItem('access_token', token);
        localStorage.setItem('authToken', token); // For backward compatibility
        localStorage.setItem('user', JSON.stringify(user));
        this.setupAutoRefresh(); // Set up auto-refresh for new token
        // @ts-ignore
        window.eventBus?.emit(window.BusEvents?.AUTH_SESSION_SET, { userId: user?.id, email: user?.email });
    }

    /**
     * Clear user session
     */
    clearSession() {
        this.token = null;
        this.user = /** @type {any} */ ({});
        localStorage.removeItem('access_token');
        localStorage.removeItem('authToken');
        localStorage.removeItem('user');
        
        // Clear auto-refresh timer
        if (this.refreshTimer) {
            clearTimeout(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    /**
     * Logout user
     */
    async logout() {
        try {
            // Track logout event before clearing session
            // @ts-ignore
            if (window.Analytics) {
                // @ts-ignore
                window.Analytics.trackLogout();
            }
            // @ts-ignore
            window.eventBus?.emit(window.BusEvents?.AUTH_LOGOUT, { reason: 'user_initiated' });
            await this.apiCall('/auth/logout', 'POST');
        } catch (error) {
            console.error('Logout error:', error);
        } finally {
            this.clearSession();
            window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
        }
    }

    /**
     * Get current user
     */
    getCurrentUser() {
        return this.user;
    }

    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        return !!this.token;
    }

    /**
     * Copy text to clipboard
     * @param {string} text
     */
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            this.showNotification('Copied to clipboard!', 'success');
        } catch (error) {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            this.showNotification('Copied to clipboard!', 'success');
        }
    }

    /**
     * Scroll to element
     * @param {string|HTMLElement} element
     * @param {number} [offset]
     */
    scrollTo(element, offset = 0) {
        const targetElement = typeof element === 'string' ? document.querySelector(element) : element;
        if (targetElement) {
            const targetPosition = (/** @type {HTMLElement} */ (targetElement)).offsetTop - offset;
            window.scrollTo({
                top: targetPosition,
                behavior: 'smooth'
            });
        }
    }

    /**
     * Get URL parameters
     */
    getUrlParams() {
        const params = new URLSearchParams(window.location.search);
        /** @type {Record<string,string>} */
        const result = {};
        for (let [key, value] of params.entries()) {
            result[key] = value;
        }
        return result;
    }

    /**
     * Get the current authentication token
     * @returns {string|null}
     */
    getAuthToken() {
        return this.token;
    }

    /**
     * Escape HTML special characters to prevent XSS
     * @param {string} text
     * @returns {string}
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Format application status string for display
     * @param {string} status
     * @returns {string}
     */
    formatStatus(status) {
        /** @type {Record<string,string>} */
        const map = {
            draft: 'Draft', processing: 'Processing', completed: 'Completed',
            failed: 'Failed', applied: 'Applied', interview: 'Interview',
            rejected: 'Rejected', accepted: 'Accepted', initialized: 'Initialized',
            running: 'Running', in_progress: 'In Progress', error: 'Error',
        };
        const normalized = typeof status === 'string' ? status.toLowerCase() : String(status);
        return map[normalized] || status;
    }

    /**
     * Update URL without reload
     * @param {Record<string, string|null|undefined>} params
     * @param {boolean} [replaceState]
     */
    updateUrl(params, replaceState = false) {
        const url = new URL(window.location.href);
        Object.keys(params).forEach(key => {
            if (params[key] === null || params[key] === undefined) {
                url.searchParams.delete(key);
            } else {
                url.searchParams.set(key, params[key]);
            }
        });

        if (replaceState) {
            window.history.replaceState({}, '', url);
        } else {
            window.history.pushState({}, '', url);
        }
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // @ts-ignore
    window.app = new JobApplicationAssistant();
    // Wire notification helpers through event bus so any module can trigger UI alerts
    // @ts-ignore
    if (window.eventBus && window.app) {
        // @ts-ignore
        window.eventBus.on(window.BusEvents.NOTIFY_SUCCESS, (/** @type {any} */ e) => /** @type {any} */ (window.app).showNotification(e.data?.message, 'success'));
        // @ts-ignore
        window.eventBus.on(window.BusEvents.NOTIFY_ERROR,   (/** @type {any} */ e) => /** @type {any} */ (window.app).showNotification(e.data?.message, 'error'));
        // @ts-ignore
        window.eventBus.on(window.BusEvents.NOTIFY_WARNING, (/** @type {any} */ e) => /** @type {any} */ (window.app).showNotification(e.data?.message, 'warning'));
        // @ts-ignore
        window.eventBus.on(window.BusEvents.NOTIFY_INFO,    (/** @type {any} */ e) => /** @type {any} */ (window.app).showNotification(e.data?.message, 'info'));
    }
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = JobApplicationAssistant;
}
