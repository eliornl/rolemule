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

    /**
     * Show a notification via window.app; falls back to alertContainer HTML.
     * @param {string} message
     * @param {string} [type] - 'success' | 'danger' | 'warning' | 'info'
     */
    function notify(message, type = 'info') {
        const notifType = type === 'danger' ? 'error' : type;
        // @ts-ignore
        const bus = window.eventBus; const busEvents = window.BusEvents;
        if (bus && busEvents) {
            /** @type {Record<string,string>} */ const evtMap = { success: busEvents.NOTIFY_SUCCESS, error: busEvents.NOTIFY_ERROR, warning: busEvents.NOTIFY_WARNING, info: busEvents.NOTIFY_INFO };
            bus.emit(evtMap[notifType] ?? busEvents.NOTIFY_INFO, { message });
        }
        // @ts-ignore
        const app = window.app;
        if (app && typeof app.showNotification === 'function') { app.showNotification(message, notifType); return; }
        const container = document.getElementById('alertContainer');
        if (container) container.innerHTML = `<div class="alert alert-${type} alert-dismissible fade show" role="alert"><i class="fas fa-${type === 'danger' ? 'exclamation-triangle' : type === 'success' ? 'check-circle' : 'info-circle'} me-2"></i>${escapeHtml(message)}<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>`;
    }

    let currentTab = 'manual';
    let uploadedFile = /** @type {File|null} */ (null);
    let _submitting = false;

    function getAuthToken() {
        // @ts-ignore
        if (window.app && typeof window.app.getAuthToken === 'function') return window.app.getAuthToken();
        const urlParams = new URLSearchParams(window.location.search);
        const urlToken  = urlParams.get('token');
        if (urlToken) return urlToken;
        return localStorage.getItem('access_token') || localStorage.getItem('authToken');
    }

    /** @returns {boolean} */
    function requireLogin() {
        // @ts-ignore
        const authenticated = window.app ? window.app.isAuthenticated() : !!getAuthToken();
        if (!authenticated) {
            window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
            return false;
        }
        return true;
    }

    document.addEventListener('DOMContentLoaded', async function () {
        if (!requireLogin()) return;
        if (typeof window.syncProfileCompletionFromApi !== 'function' || !(await window.syncProfileCompletionFromApi())) return;

        // Method tab switching (replaces inline onclick="switchTab('...')")
        document.querySelectorAll('.method-tab[data-tab]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const tab = /** @type {HTMLElement} */ (btn).dataset['tab'];
                if (tab) switchTab(tab);
            });
        });

        // Character count for textarea (replaces inline oninput)
        const jobDescEl = document.getElementById('jobDescription');
        if (jobDescEl) {
            jobDescEl.addEventListener('input', function () {
                updateCharacterCount('jobDescription', 'descriptionCount', 50000);
            });
        }

        // File upload area: drag-and-drop + click-to-browse (replaces inline ondrop/etc.)
        const fileUploadArea = document.getElementById('fileUploadArea');
        const fileInput = /** @type {HTMLInputElement|null} */ (document.getElementById('fileInput'));
        if (fileUploadArea && fileInput) {
            fileUploadArea.addEventListener('click', function (e) {
                if (/** @type {HTMLElement} */ (e.target).closest('input')) return;
                fileInput.click();
            });
            fileUploadArea.addEventListener('dragover', function (e) {
                handleDragOver(/** @type {DragEvent} */ (e));
            });
            fileUploadArea.addEventListener('dragleave', function (e) {
                handleDragLeave(/** @type {DragEvent} */ (e));
            });
            fileUploadArea.addEventListener('drop', function (e) {
                handleFileDrop(/** @type {DragEvent} */ (e));
            });
            fileInput.addEventListener('change', function (e) {
                handleFileSelect(/** @type {Event} */ (e));
            });
        }

        // Remove file button (replaces inline onclick="removeFile()")
        document.addEventListener('click', function (e) {
            const el = /** @type {HTMLElement} */ (e.target);
            const action = el.closest('[data-action]');
            if (!action) return;
            const actionName = /** @type {HTMLElement} */ (action).dataset['action'];
            if (actionName === 'remove-file') removeFile();
            if (actionName === 'process-application') processApplication();
        });
    });

    /** @param {string} tabName */
    function switchTab(tabName) {
        document.querySelectorAll('.method-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        if (document.activeElement instanceof HTMLElement) {
            document.activeElement.classList.add('active');
        }
        document.getElementById(tabName + 'Tab')?.classList.add('active');

        const subtitle = document.getElementById('headerSubtitle');
        if (subtitle) {
            subtitle.textContent = tabName === 'manual'
                ? 'Paste a job description and let AI do the rest'
                : 'Upload a job posting and let AI do the rest';
        }
        currentTab = tabName;
        clearAlerts();
    }

    /** @param {DragEvent} event */
    function handleFileDrop(event) {
        event.preventDefault();
        event.stopPropagation();
        document.getElementById('fileUploadArea')?.classList.remove('dragover');
        const files = event.dataTransfer?.files;
        if (files && files.length > 0) handleFileUpload(files[0]);
    }

    /** @param {DragEvent} event */
    function handleDragOver(event) {
        event.preventDefault();
        event.stopPropagation();
        document.getElementById('fileUploadArea')?.classList.add('dragover');
    }

    /** @param {DragEvent} event */
    function handleDragLeave(event) {
        event.preventDefault();
        event.stopPropagation();
        document.getElementById('fileUploadArea')?.classList.remove('dragover');
    }

    /** @param {Event} event */
    function handleFileSelect(event) {
        const input = /** @type {HTMLInputElement} */ (event.target);
        const file  = input.files?.[0];
        if (file) handleFileUpload(file);
    }

    /** @param {File} file */
    function handleFileUpload(file) {
        const allowedExtensions = ['.pdf', '.docx', '.txt'];
        const parts = file.name.split('.');
        const fileExtension = parts.length >= 2 ? '.' + (parts.pop() || '').toLowerCase() : '';
        if (!fileExtension || !allowedExtensions.includes(fileExtension)) {
            showAlert('Please upload a PDF, Word (.docx), or TXT file.', 'danger'); return;
        }
        if (file.size > 5 * 1024 * 1024) {
            showAlert('File size must be less than 5MB.', 'danger'); return;
        }
        uploadedFile = file;
        showFileInfo(file);
    }

    /** @param {File} file */
    function showFileInfo(file) {
        const fileInfo = document.getElementById('fileInfo');
        const fileName = document.getElementById('fileName');
        const fileSize = document.getElementById('fileSize');
        if (fileName) fileName.textContent = file.name;
        if (fileSize) fileSize.textContent = formatFileSize(file.size);
        if (fileInfo) fileInfo.style.display = 'block';
    }

    function removeFile() {
        uploadedFile = null;
        const fileInfo  = document.getElementById('fileInfo');
        const fileInput = /** @type {HTMLInputElement|null} */ (document.getElementById('fileInput'));
        if (fileInfo)  fileInfo.style.display = 'none';
        if (fileInput) fileInput.value = '';
    }

    /** @param {number} bytes */
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * @param {string} textareaId
     * @param {string} countId
     * @param {number} maxLength
     */
    function updateCharacterCount(textareaId, countId, maxLength) {
        const textarea = /** @type {HTMLTextAreaElement|null} */ (document.getElementById(textareaId));
        const count    = document.getElementById(countId);
        if (!textarea || !count) return;
        const length = textarea.value.length;
        count.textContent = `${length}/50,000 characters`;
        count.style.color = length > maxLength ? '#dc3545' : '#6c757d';
        textarea.classList.toggle('is-invalid', length > maxLength);
    }

    async function processApplication() {
        if (_submitting) return;
        clearAlerts();
        /** @type {string|null} */
        let jobText = null;

        if (currentTab === 'manual') {
            const textarea = /** @type {HTMLTextAreaElement|null} */ (document.getElementById('jobDescription'));
            const description = textarea?.value.trim() ?? '';
            if (!description) { showAlert('Please enter the job description', 'danger'); textarea?.classList.add('is-invalid'); return; }
            if (description.length < 100) { showAlert('Job description seems too short. Please paste the complete job posting.', 'danger'); textarea?.classList.add('is-invalid'); return; }
            jobText = description;
        } else if (currentTab === 'file' && !uploadedFile) {
            showAlert('Please upload a file first.', 'danger'); return;
        }

        const submitBtn = /** @type {HTMLButtonElement|null} */ (document.querySelector('[data-action="process-application"]'));
        const originalBtnHtml = submitBtn ? submitBtn.innerHTML : '';

        _submitting = true;
        if (submitBtn) { submitBtn.disabled = true; submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Creating...'; }

        try {
            const formData = new FormData();
            if (jobText) formData.append('job_text', jobText);
            if (currentTab === 'file' && uploadedFile) formData.append('job_file', uploadedFile);

            const token = getAuthToken();
            if (!token) throw new Error('Authentication failed - please log in again');

            const response = await fetch(`${API_BASE}/workflow/start`, {
                method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: formData
            });
            const responseText = await response.text();

            if (response.ok) {
                // Store session_id so navbar-notifications.js can poll for completion on other pages
                try {
                    const parsed = JSON.parse(responseText);
                    const sessionId = parsed && parsed.session_id;
                    if (sessionId) {
                        const raw = localStorage.getItem('applypilot_tracked_sessions') || '[]';
                        const tracked = JSON.parse(raw);
                        tracked.push({ sessionId });
                        if (tracked.length > 20) tracked.splice(0, tracked.length - 20);
                        localStorage.setItem('applypilot_tracked_sessions', JSON.stringify(tracked));
                        sessionStorage.setItem('new_application_session_id', sessionId);
                    }
                } catch (_e) {}
                sessionStorage.setItem('new_application_toast', 'Application submitted! AI agents are analyzing it in the background.');
                window.location.href = '/dashboard';
            } else {
                let errorDetail;
                let errorCode = '';
                try {
                    const errorJson = JSON.parse(responseText);
                    errorCode  = errorJson.error_code || '';
                    errorDetail = errorJson.message || errorJson.detail || 'Unknown server error';
                } catch { errorDetail = `HTTP ${response.status}: ${responseText.substring(0, 100)}`; }
                _submitting = false;
                if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = originalBtnHtml; }
                if (errorCode === 'CFG_6001') {
                    showApiKeyAlert();
                } else if (errorCode === 'RES_3002') {
                    const dupMsg =
                        'You already have this role and company on your applications list. Open that card on your dashboard—you do not need to add the same job twice.';
                    notify(dupMsg, 'warning');
                } else {
                    showAlert(`Error creating application: ${errorDetail}`, 'danger');
                }
            }
        } catch (error) {
            const err = /** @type {Error} */ (error);
            console.error('Error creating application:', err);
            _submitting = false;
            if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = originalBtnHtml; }
            showAlert(`Error creating application: ${err.message}`, 'danger');
        }
    }

    /**
     * @param {string} message
     * @param {string} type
     */
    function showAlert(message, type) { notify(message, type); }

    function showApiKeyAlert() {
        const container = document.getElementById('alertContainer');
        if (container) {
            container.innerHTML = `
                <div class="alert alert-warning alert-dismissible fade show" role="alert">
                    <i class="fas fa-key me-2"></i>
                    <strong>API key required.</strong>
                    To analyze jobs with AI, add your Gemini API key in
                    <a href="/settings?tab=ai-setup" class="alert-link">Settings &rarr; AI Setup</a>.
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>`;
        }
    }

    function clearAlerts() {
        const container = document.getElementById('alertContainer');
        if (container) container.innerHTML = '';
        document.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
    }


    // Public API
    // @ts-ignore
    window.handleDragLeave      = handleDragLeave;
    // @ts-ignore
    window.handleDragOver       = handleDragOver;
    // @ts-ignore
    window.handleFileDrop       = handleFileDrop;
    // @ts-ignore
    window.handleFileSelect     = handleFileSelect;
    // @ts-ignore
    window.processApplication   = processApplication;
    // @ts-ignore
    window.removeFile           = removeFile;
    // @ts-ignore
    window.switchTab            = switchTab;
    // @ts-ignore
    window.updateCharacterCount = updateCharacterCount;

}());
