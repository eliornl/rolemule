(function () {
    'use strict';

    // ================================================================
    // APPLYPILOT - PROFILE SETUP
    // ================================================================
    // 5-Step Profile Setup (plus optional Step 0 resume upload)
    // Step 1: Basic Information + Professional Summary
    // Step 2: Work Experience (or explicit "no experience")
    // Step 3: Education (or explicit "no formal education")
    // Step 4: Skills
    // Step 5: Career Preferences (job types, company sizes, arrangements)
    //
    // Features:
    // - Form validation with detailed error messages
    // - Dynamic form sections (add/remove entries)
    // - Progress tracking and completion summary
    // - API integration with backend profile endpoints
    // - Enum-based dropdowns for consistent data entry
    // ================================================================

    // ================================================================
    // GLOBAL VARIABLES AND CONFIGURATION
    // ================================================================

    const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';

    /** @param {string} str */
    function escapeHtml(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    }

    let currentStep = 0;  // Start at step 0 (resume upload)
    const totalSteps = 5; // Form steps 1–5: Basic, Experience, Education, Skills, Preferences (step 0 = resume)

    // Data collections for dynamic form sections
    let skills = [];
    let workExperience = [];
    /** @type {Array<{institution: string, degree: string, field_of_study: string, start_date: string, end_date: string, is_current: boolean}>} */
    let educationHistory = [];

    // In-flight request tracker — aborted on page unload
    let _pageAbortController = new AbortController();

    // Constants and global variables
    const STORAGE_KEYS = {
        ACCESS_TOKEN: "access_token",
        TOKEN_TYPE: "token_type",
        USER_DATA: "user_data",
        PROFILE_COMPLETED: "profile_completed"
    };

    /**
     * Get authentication token from URL parameters or localStorage
     * Checks both 'access_token' and legacy 'authToken' keys for backward compatibility
     */
    function getAuthToken() {
        const urlParams = new URLSearchParams(window.location.search);
        const tokenFromUrl = urlParams.get('token') || urlParams.get('access_token');
        if (tokenFromUrl) return tokenFromUrl;
        return localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN) || localStorage.getItem('authToken');
    }

    /**
     * Set authentication token in localStorage under both keys for backward compatibility
     */
    function setAuthToken(token) {
        if (!token) return;
        localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, token);
        localStorage.setItem('authToken', token);
    }

    /**
     * Returns a debounced version of fn that delays invocation until after
     * wait milliseconds have elapsed since the last call.
     * @template {(...args: any[]) => void} T
     * @param {T} fn
     * @param {number} wait
     * @returns {T}
     */
    function debounce(fn, wait) {
        let timer = 0;
        return /** @type {T} */ (function (...args) {
            clearTimeout(timer);
            timer = window.setTimeout(() => fn.apply(this, args), wait);
        });
    }

    /**
     * Parse salary from text — strips commas/spaces so "220,000" → 220000.
     * Avoids type="number" step/wheel changing 220000 → 218000 before save.
     * @param {string|number|null|undefined} value
     * @returns {number}
     */
    function parseSalaryDigits(value) {
        const digits = String(value ?? '').replace(/[^\d]/g, '');
        if (!digits) return 0;
        const n = Number(digits);
        return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
    }

    /**
     * @param {HTMLInputElement|null|undefined} el
     * @returns {number}
     */
    function readSalaryField(el) {
        if (!el) return 0;
        return parseSalaryDigits(el.value);
    }

    // Validation rules and constants
    const VALIDATION_RULES = {
        MIN_EXPERIENCE_ENTRIES: 1,
        MIN_SKILLS: 1,
        MIN_JOB_TYPES: 1,
        MIN_COMPANY_SIZES: 1,
        MIN_WORK_ARRANGEMENTS: 1
    };

    // Cached DOM elements — resolved once at module load to avoid repeated getElementById calls
    const progressBar   = document.getElementById("progress-bar");
    const prevBtn       = document.getElementById("prev-btn");
    const nextBtn       = document.getElementById("next-btn");
    const completeBtn   = document.getElementById("complete-btn");
    const errorAlert    = document.getElementById("error-alert");
    const successAlert  = document.getElementById("success-alert");
    const errorMessage  = document.getElementById("error-message");
    const successMessage = document.getElementById("success-message");
    const skillsContainer = document.getElementById("skills-container");
    const experienceContainer = document.getElementById("experience-container");
    const educationContainer = document.getElementById("education-container");

    /**
     * If the URL contains ?code= from an OAuth callback, exchange it for a JWT
     * and store it in localStorage before the auth check runs.
     * @returns {Promise<boolean>}
     */
    async function exchangeOAuthCodeIfPresent() {
        const urlParams = new URLSearchParams(window.location.search);
        const code = urlParams.get('code');
        if (!code) return false;

        // Remove ?code= from the URL immediately so a refresh doesn't replay it.
        urlParams.delete('code');
        const newSearch = urlParams.toString();
        history.replaceState(null, '', window.location.pathname + (newSearch ? '?' + newSearch : ''));

        try {
            const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';
            const response = await fetch(`${API_BASE}/auth/oauth/exchange-code`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
            });
            if (!response.ok) return false;
            const data = await response.json();
            const token = /** @type {string|undefined} */ (data.access_token);
            if (!token) return false;
            setAuthToken(token);
            return true;
        } catch (err) {
            const error = /** @type {Error} */ (err);
            console.error('OAuth code exchange failed:', error.message);
            return false;
        }
    }

    // Initialize page
    document.addEventListener("DOMContentLoaded", async function () {
        await exchangeOAuthCodeIfPresent();
        checkAuthentication();

        // Handle edit mode and fromResume parameters
        const urlParams = new URLSearchParams(window.location.search);
        const isEditMode = urlParams.get('edit') === 'true';
        const fromResume = urlParams.get('fromResume') === 'true';

        // If profile is already complete and this isn't an intentional edit, redirect to dashboard
        // immediately — prevents the wizard from flashing for users who have finished setup.
        if (!isEditMode && !fromResume && localStorage.getItem('profile_completed') === 'true') {
            window.location.href = '/dashboard';
            return;
        }

        // Must finish loading saved profile before applying parsed resume from sessionStorage.
        // Otherwise populateFormData() can resolve after autoFillProfile() and overwrite parsed data.
        const profilePayload = await loadUserData();
        const completionStatus = profilePayload?.completion_status;

        initializeEventListeners();
        updateStepDisplay();

        // Button event listeners for navigation
        nextBtn.addEventListener("click", goToNextStep);
        prevBtn.addEventListener("click", goToPrevStep);
        completeBtn.addEventListener("click", completeProfile);
        document.getElementById("logout-btn").addEventListener("click", logout);

        // Skip resume button - go directly to basic info
        const skipResumeBtn = document.getElementById("skip-resume-btn");
        if (skipResumeBtn) {
            skipResumeBtn.addEventListener("click", function() {
                changeStep(1); // Go to Basic Info step
            });
        }

        // Silently check key status on load so we know before the user interacts.
        // The prompt card only appears when they actually try to upload.
        checkApiKeyStatus();
        setupInlineApiKey();

        if (fromResume) {
            const parsedData = sessionStorage.getItem('parsedResumeData');
            if (parsedData) {
                try {
                    const resumeData = JSON.parse(parsedData);
                    autoFillProfile(resumeData);
                    sessionStorage.removeItem('parsedResumeData');
                } catch (e) {
                    console.error('Failed to parse resume data:', e);
                }
            }
        }

        const returningUser =
            isEditMode ||
            (completionStatus && !completionStatus.profile_completed &&
                (completionStatus.completion_percentage ?? 0) > 0);

        if (returningUser) {
            const targetStep = onlyCareerPreferencesMissing(completionStatus) ? 5 : 1;
            requestAnimationFrame(() => changeStep(targetStep));

            const headerTitle = document.querySelector('.sidebar h2');
            if (headerTitle) {
                headerTitle.textContent = 'Edit Your Profile';
            }
        }

        // Update UI
        updateStepIndicators();
        updateProgressBar();
        checkPreferencesStep();
        updateStepDisplay();
    });

    // Abort any in-flight requests when the user navigates away
    window.addEventListener('beforeunload', function () {
        _pageAbortController.abort();
    });

    // Authentication check
    function checkAuthentication() {
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

    /**
     * Make an authenticated API call via window.app.apiCall.
     * Falls back to a direct fetch if window.app is not yet available.
     * @param {string} endpoint - API endpoint (e.g. "/profile/basic-info")
     * @param {string} [method] - HTTP method (default: 'GET')
     * @param {Object|null} [body] - Request body object (will be JSON-stringified)
     * @returns {Promise<Object>} Parsed JSON response
     */
    async function makeAuthenticatedApiCall(endpoint, method = 'GET', body = null) {
        // @ts-ignore
        const app = window.app;
        if (app && typeof app.apiCall === 'function') {
            return app.apiCall(endpoint, method, body);
        }
        // Fallback: direct fetch (should not normally be needed)
        const token = getAuthToken();
        if (!token) { window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login'; throw new Error('Authentication required'); }
        const fetchOptions = /** @type {RequestInit} */ ({
            method,
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        });
        if (body && method !== 'GET') fetchOptions.body = JSON.stringify(body);
        const response = await fetch(`${API_BASE}${endpoint}`, fetchOptions);
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            if (response.status === 401) { window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login'; }
            throw new Error(err.message || err.detail || `API error: ${response.status}`);
        }
        return response.json();
    }

    /**
     * Returning user who only needs Step 5 (e.g. new work_authorization column after migrate).
     * @param {object|null|undefined} completionStatus
     * @returns {boolean}
     */
    function onlyCareerPreferencesMissing(completionStatus) {
        const cs = completionStatus;
        if (!cs || cs.profile_completed) return false;
        return (
            cs.career_preferences === false &&
            cs.basic_info !== false &&
            cs.work_experience !== false &&
            cs.education !== false &&
            cs.skills_qualifications !== false
        );
    }

    // Load existing user data
    /** @returns {Promise<object|null>} */
    async function loadUserData() {
        try {
            const data = await makeAuthenticatedApiCall("/profile/");
            populateFormData(data);
            return data;
        } catch (error) {
            // For new users, this error is expected and will be silently ignored
            return null;
        }
    }

    // Populate form with existing data
    function populateFormData(data) {
        const userInfo = data.user_info;
        const profileData = data.profile_data;

        // Populate location fields
        if (profileData.city)
            document.getElementById("city").value = profileData.city;
        if (profileData.state)
            document.getElementById("state").value = profileData.state;
        if (profileData.country)
            document.getElementById("country").value = profileData.country;

        // Populate professional details
        if (profileData.professional_title)
            document.getElementById("professional-title").value = profileData.professional_title;
        if (profileData.years_experience !== undefined && profileData.years_experience !== null)
            document.getElementById("years-experience").value = String(profileData.years_experience);
        if (profileData.summary)
            document.getElementById("summary").value = profileData.summary;

        const phoneEl = document.getElementById("phone");
        if (phoneEl && profileData.phone) phoneEl.value = profileData.phone;
        const liEl = document.getElementById("linkedin-url");
        if (liEl && profileData.linkedin_url) liEl.value = profileData.linkedin_url;
        const ghEl = document.getElementById("github-url");
        if (ghEl && profileData.github_url) ghEl.value = profileData.github_url;
        const pfEl = document.getElementById("portfolio-url");
        if (pfEl && profileData.portfolio_url) pfEl.value = profileData.portfolio_url;

        // Student status field has been removed

        // Work experience — empty array is truthy in JS; sync "no experience" checkbox
        workExperience = Array.isArray(profileData.work_experience)
            ? profileData.work_experience
            : [];
        workExperience.forEach((exp) => {
            if (String(exp.end_date || "").trim()) {
                exp.is_current = false;
            }
        });
        renderWorkExperience();
        const noExpOnLoad = /** @type {HTMLInputElement|null} */ (document.getElementById("no-experience"));
        if (noExpOnLoad) {
            noExpOnLoad.checked = workExperience.length === 0;
            if (noExpOnLoad.checked) {
                noExpOnLoad.dispatchEvent(new Event("change"));
            }
        }

        // Skills
        if (profileData.skills) {
            skills = profileData.skills;
            renderSkills();
        }

        educationHistory = Array.isArray(profileData.education) ? profileData.education : [];
        educationHistory.forEach((edu) => {
            const endLike = edu.end_date || edu.graduation_date;
            if (String(endLike || "").trim()) {
                edu.is_current = false;
            }
        });
        renderEducation();
        const noEdOnLoad = /** @type {HTMLInputElement|null} */ (document.getElementById("no-education"));
        if (noEdOnLoad) {
            noEdOnLoad.checked = educationHistory.length === 0;
            if (noEdOnLoad.checked) {
                noEdOnLoad.dispatchEvent(new Event("change"));
            }
        }

        if (profileData.is_student !== undefined && document.getElementById("is-student")) {
            /** @type {HTMLInputElement} */ (document.getElementById("is-student")).checked = !!profileData.is_student;
        }

        // Job preferences
        if (profileData.desired_salary_range) {
            const minSalaryEl = /** @type {HTMLInputElement|null} */ (document.getElementById("min-salary"));
            const maxSalaryEl = /** @type {HTMLInputElement|null} */ (document.getElementById("max-salary"));
            const parsedMin = parseSalaryDigits(profileData.desired_salary_range.min);
            const parsedMax = parseSalaryDigits(profileData.desired_salary_range.max);
            if (minSalaryEl) minSalaryEl.value = parsedMin > 0 ? String(parsedMin) : "";
            if (maxSalaryEl) maxSalaryEl.value = parsedMax > 0 ? String(parsedMax) : "";
        }

        // Company sizes
        if (profileData.desired_company_sizes) {
            profileData.desired_company_sizes.forEach((size) => {
                // Extract the lowercase first word for matching
                const sizeKey = size.split(' ')[0].toLowerCase();
                const checkbox = document.querySelector(
                    `input[value="${sizeKey}"][id^="company-size-"]`,
                );
                if (checkbox) {
                    checkbox.checked = true;
                } else {
                }
            });
        }

        // Job types
        if (profileData.job_types) {
            profileData.job_types.forEach((type) => {
                // Convert "Full-time" to "full-time", etc.
                const typeKey = type.toLowerCase().replace(' ', '-');
                const checkbox = document.querySelector(
                    `input[value="${typeKey}"][id^="job-type-"]`,
                );
                if (checkbox) {
                    checkbox.checked = true;
                } else {
                }
            });
        }

        // Work arrangements
        if (profileData.work_arrangements) {
            profileData.work_arrangements.forEach((arrangement) => {
                // Convert "Onsite" to "onsite", etc.
                const arrangementKey = arrangement.toLowerCase();
                const checkbox = document.querySelector(`input[value="${arrangementKey}"][id^="work-arrangement-"]`);
                if (checkbox) {
                    checkbox.checked = true;
                } else {
                }
            });
        }

        // Populate additional career options
        if (profileData.willing_to_relocate) {
            document.getElementById("willing-to-relocate").checked = true;
        }

        // Work authorization (career step)
        const validWorkAuth = new Set([
            "no_work_authorization",
            "has_work_authorization",
            "us_lawful_permanent_resident",
            "us_citizen",
        ]);
        let workAuth = profileData.work_authorization;
        if (workAuth && validWorkAuth.has(workAuth)) {
            document.querySelectorAll('input[name="work-authorization"]').forEach((/** @type {Element} */ el) => {
                const inp = /** @type {HTMLInputElement} */ (el);
                inp.checked = inp.value === workAuth;
            });
        }

        if (profileData.requires_visa_sponsorship === true) {
            const visaEl = document.getElementById("requires-visa-sponsorship");
            if (visaEl) visaEl.checked = true;
        }

        if (profileData.has_security_clearance) {
            document.getElementById("has-security-clearance").checked = true;
        }

        // Handle student status checkbox
        if (profileData.is_student === true) {
            document.getElementById("is-student").checked = true;
        }

        // Set travel preference
        if (profileData.max_travel_preference) {

            // Map percentage values to enum values
            const travelPreferenceMap = {
                "0": "NONE",
                "25": "MINIMAL",
                "50": "MODERATE",
                "75": "FREQUENT",
                "100": "EXTENSIVE"
            };

            // Try direct match first
            let travelRadio = document.querySelector(`input[name="travel-preference"][value="${profileData.max_travel_preference}"]`);

            // If not found, try mapping from percentage to enum value
            if (!travelRadio && travelPreferenceMap[profileData.max_travel_preference]) {
                const mappedValue = travelPreferenceMap[profileData.max_travel_preference];
                travelRadio = document.querySelector(`input[name="travel-preference"][value="${mappedValue}"]`);
            }

            if (travelRadio) {
                travelRadio.checked = true;
            } else {
            }
        }
    }

    // Function to check if we need to show the preferences step
    function checkPreferencesStep() {
        // Logic to determine if preferences step should be shown
        // This would typically check if previous steps are completed
    }

    /**
     * Display an error message to the user
     * @param {string} message - Error message to display
     */
    function showErrorMessage(message) {
        if (errorAlert && errorMessage) {
            errorMessage.textContent = message;
            errorAlert.classList.remove("d-none");
            window.scrollTo({ top: 0, behavior: 'smooth' });
        } else {
            alert(message);
        }
    }

    // Function to handle next button click
    function goToNextStep() {

        try {
            // Hide any previous error messages
            hideAlerts();

            // Validate the current step before proceeding
            let isValid = false;

            // Step-specific validation
            switch(currentStep) {
                case 1: // Basic Info
                    isValid = validateBasicInfo();
                    break;
                case 2: // Work Experience
                    isValid = validateWorkExperience();
                    break;
                case 3: // Education
                    isValid = validateEducation();
                    break;
                case 4: // Skills
                    isValid = validateSkillsQualifications();
                    break;
                case 5: // Career Preferences
                    isValid = validateCareerPreferences();
                    break;
                default:
                    isValid = true;
            }

            // Only proceed if validation passes
            if (isValid) {
                changeStep(currentStep + 1);
            } else {
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }
        } catch (error) {
            console.error("Error in goToNextStep:", error);
            showError("Error moving to next step: " + error.message);
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    }

    // Function to handle previous button click
    function goToPrevStep() {
        changeStep(currentStep - 1);
    }

    function initializeEventListeners() {

        // Resume upload functionality
        initializeResumeUpload();

        // Skills input — debounced to avoid processing partial words
        const skillsInput = document.getElementById("skills-input");
        skillsInput.addEventListener("keypress", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                addSkill(this.value.trim());
                this.value = "";
            }
        });

        // Salary inputs — debounced validation (300 ms) to avoid on-every-keystroke work
        const debouncedSalaryValidate = debounce(() => {
            const minEl = /** @type {HTMLInputElement|null} */ (document.getElementById('min-salary'));
            const maxEl = /** @type {HTMLInputElement|null} */ (document.getElementById('max-salary'));
            const min = readSalaryField(minEl);
            const max = readSalaryField(maxEl);
            if (maxEl && max > 0 && min > 0 && max <= min) {
                maxEl.setCustomValidity('Maximum salary must be greater than minimum salary.');
            } else if (maxEl) {
                maxEl.setCustomValidity('');
            }
        }, 300);
        ['min-salary', 'max-salary'].forEach((id) => {
            const salaryInput = /** @type {HTMLInputElement|null} */ (document.getElementById(id));
            salaryInput?.addEventListener('input', debouncedSalaryValidate);
            salaryInput?.addEventListener('blur', () => {
                const n = readSalaryField(salaryInput);
                salaryInput.value = n > 0 ? String(n) : '';
                debouncedSalaryValidate();
            });
        });

        // Add experience button (wired here; also used below for no-experience toggle)
        document
            .getElementById("add-experience-btn")
            ?.addEventListener("click", addWorkExperience);

        // No experience checkbox — uses cached container reference
        const noExperienceCheckbox = document.getElementById("no-experience");
        const addExperienceBtn = /** @type {HTMLElement|null} */ (document.getElementById("add-experience-btn"));
        if (noExperienceCheckbox) {
            noExperienceCheckbox.addEventListener("change", function() {
                const container = experienceContainer || document.getElementById("experience-container");
                if (this.checked) {
                    if (addExperienceBtn) { addExperienceBtn.style.opacity = "0.5"; addExperienceBtn.style.pointerEvents = "none"; }
                    if (container) container.style.opacity = "0.5";
                } else {
                    if (addExperienceBtn) { addExperienceBtn.style.opacity = "1"; addExperienceBtn.style.pointerEvents = "auto"; }
                    if (container) container.style.opacity = "1";
                }
            });
        }

        document.getElementById("add-education-btn")?.addEventListener("click", addEducation);
        const noEducationCheckbox = /** @type {HTMLInputElement|null} */ (document.getElementById("no-education"));
        const addEducationBtn = /** @type {HTMLElement|null} */ (document.getElementById("add-education-btn"));
        if (noEducationCheckbox) {
            noEducationCheckbox.addEventListener("change", function() {
                const ec = educationContainer || document.getElementById("education-container");
                if (this.checked) {
                    if (addEducationBtn) { addEducationBtn.style.opacity = "0.5"; addEducationBtn.style.pointerEvents = "none"; }
                    if (ec) ec.style.opacity = "0.5";
                } else {
                    if (addEducationBtn) { addEducationBtn.style.opacity = "1"; addEducationBtn.style.pointerEvents = "auto"; }
                    if (ec) ec.style.opacity = "1";
                }
            });
        }
    }

    // =============================================================================
    // RESUME UPLOAD AND PARSING
    // =============================================================================

    /**
     * Initialize resume upload functionality
     */
    function initializeResumeUpload() {
        const dropZone = document.getElementById("resume-drop-zone");
        const fileInput = document.getElementById("resume-file-input");

        if (!dropZone || !fileInput) return;

        // Click to upload — show API key prompt first if no key is configured
        dropZone.addEventListener("click", () => {
            if (!_hasApiKey) {
                showApiKeyPrompt();
                return;
            }
            fileInput.click();
        });

        // File input change (triggered after click passes the key check)
        fileInput.addEventListener("change", (e) => {
            const target = /** @type {HTMLInputElement} */ (e.target);
            if (target.files && target.files.length > 0) {
                handleResumeUpload(target.files[0]);
            }
        });

        // Drag visual feedback
        dropZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            dropZone.classList.add("dragover");
        });

        dropZone.addEventListener("dragleave", (e) => {
            e.preventDefault();
            dropZone.classList.remove("dragover");
        });

        // Drop — show API key prompt if no key, otherwise upload
        dropZone.addEventListener("drop", (e) => {
            e.preventDefault();
            dropZone.classList.remove("dragover");

            if (!_hasApiKey) {
                showApiKeyPrompt();
                return;
            }

            const files = e.dataTransfer ? e.dataTransfer.files : null;
            if (files && files.length > 0) {
                handleResumeUpload(files[0]);
            }
        });
    }

    /**
     * Module-level flag: true when the user or server already has a key.
     * Populated silently on load — never mutates the DOM directly.
     * @type {boolean}
     */
    let _hasApiKey = true; // optimistic default; corrected by checkApiKeyStatus()

    /**
     * Silently fetch key status and store the result in _hasApiKey.
     * Does NOT touch the DOM — the prompt card appears only when the user
     * actually tries to interact with the upload zone.
     */
    async function checkApiKeyStatus() {
        try {
            const token = getAuthToken();
            if (!token) return;
            const res = await fetch(`${API_BASE}/profile/api-key/status`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (!res.ok) return;
            const data = await res.json();
            _hasApiKey = !!(data.has_user_key || data.server_has_key || data.use_vertex_ai);
        } catch (_e) {
            // Non-fatal — assume key available so we never block upload incorrectly
        }
    }

    /**
     * Show the API key prompt card and focus the input.
     */
    function showApiKeyPrompt() {
        const prompt = document.getElementById('api-key-prompt');
        if (!prompt) return;
        prompt.style.display = 'flex';
        const input = /** @type {HTMLInputElement|null} */ (document.getElementById('setup-api-key-input'));
        if (input) input.focus();
        prompt.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    /**
     * Wire up the inline API key save button on step 0.
     * On success: marks _hasApiKey = true, shows confirmation briefly,
     * then collapses the card so the upload zone is the focus.
     */
    function setupInlineApiKey() {
        const saveBtn   = document.getElementById('setup-save-key-btn');
        const input     = /** @type {HTMLInputElement|null} */ (document.getElementById('setup-api-key-input'));
        const spinner   = document.getElementById('setup-save-key-spinner');
        const btnText   = document.getElementById('setup-save-key-text');
        const successEl = document.getElementById('setup-key-success');
        const errorEl   = document.getElementById('setup-key-error');
        const prompt    = document.getElementById('api-key-prompt');

        if (!saveBtn || !input) return;

        saveBtn.addEventListener('click', async function () {
            const key = input.value.trim();

            if (!key) {
                if (errorEl) { errorEl.textContent = 'Please paste your API key.'; errorEl.style.display = 'block'; }
                input.focus();
                return;
            }
            if (errorEl) errorEl.style.display = 'none';

            saveBtn.disabled = true;
            if (spinner) spinner.style.display = 'inline-block';
            if (btnText) btnText.textContent = 'Saving…';

            try {
                const token = getAuthToken();
                const res = await fetch(`${API_BASE}/profile/api-key`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ api_key: key })
                });

                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.message || data.detail || 'Failed to save key.');

                // Mark key as available so next interaction goes straight to upload
                _hasApiKey = true;
                input.value = '';

                // Swap input row for success message
                const inputRow = document.getElementById('api-key-input-row');
                if (inputRow) inputRow.style.display = 'none';
                if (successEl) successEl.style.display = 'flex';

                // Collapse the card after a moment so the upload zone takes focus
                setTimeout(() => {
                    if (prompt) prompt.style.display = 'none';
                    // Re-show input row for the edge case where they open it again
                    if (inputRow) inputRow.style.display = 'flex';
                    if (successEl) successEl.style.display = 'none';
                }, 2000);

            } catch (err) {
                const e = /** @type {Error} */ (err);
                if (errorEl) { errorEl.textContent = e.message || 'Could not save key — please try again.'; errorEl.style.display = 'block'; }
            } finally {
                saveBtn.disabled = false;
                if (spinner) spinner.style.display = 'none';
                if (btnText) btnText.textContent = 'Save & Continue';
            }
        });

        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') saveBtn.click();
        });
    }

    /**
     * The template has a Bootstrap spinner next to #upload-status-text; toggle it so it
     * does not keep animating after success or failure.
     * @param {boolean} visible
     */
    function setResumeUploadSpinnerVisible(visible) {
        const spin = document.querySelector("#upload-status .spinner-border");
        if (spin) spin.classList.toggle("d-none", !visible);
    }

    /**
     * Handle resume file upload and parsing
     * @param {File} file - The resume file to upload
     */
    async function handleResumeUpload(file) {
        const dropZone = document.getElementById("resume-drop-zone");
        const progressContainer = document.getElementById("upload-progress");
        const progressBar = document.getElementById("upload-progress-bar");
        const progressTrack = progressContainer?.querySelector(".progress");
        const statusText = document.getElementById("upload-status-text");
        const statusContainer = document.getElementById("upload-status");

        // Validate file
        const allowedExtensions = [".pdf", ".docx", ".txt"];
        const fileExtension = "." + file.name.split(".").pop().toLowerCase();

        if (fileExtension === ".doc") {
            showError(
                "Older Word (.doc) files are not supported. Save as .docx or PDF, then upload again.",
            );
            return;
        }
        if (!allowedExtensions.includes(fileExtension)) {
            showError("Please upload a PDF, Word (.docx), or TXT file.");
            return;
        }

        if (file.size > 10 * 1024 * 1024) {
            showError("File size must be less than 10MB.");
            return;
        }

        try {
            hideAlerts();
            // Show progress with indeterminate animation
            dropZone.classList.add("uploading");
            progressContainer.classList.remove("d-none");
            if (progressTrack) progressTrack.classList.remove("d-none");
            progressBar.classList.remove("d-none", "success");
            progressBar.classList.add("indeterminate");
            setResumeUploadSpinnerVisible(true);
            statusText.textContent = "Parsing your resume...";
            statusContainer.className = "upload-status";

            // Prepare form data
            const formData = new FormData();
            formData.append("resume", file);

            // Get auth token
            const token = getAuthToken();
            if (!token) {
                throw new Error("Authentication required");
            }

            // Call the parse-resume API
            const response = await fetch(`${API_BASE}/profile/parse-resume`, {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${token}`
                },
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                // No API key — update flag and surface the prompt
                if (errorData.error_code === 'CFG_6001') {
                    _hasApiKey = false;
                    showApiKeyPrompt();
                    throw new Error('Resume parsing requires a Gemini API key. Add your key above, or use "Fill in manually".');
                }
                throw new Error(errorData.message || errorData.detail || "Failed to parse resume");
            }

            const result = await response.json();

            if (!result.success) {
                throw new Error(result.message || "Failed to parse resume");
            }

            statusText.textContent = "Auto-filling profile...";

            // Auto-fill the profile with parsed data
            await autoFillProfile(result.data);

            // Show success - switch from indeterminate to success state
            setResumeUploadSpinnerVisible(false);
            progressBar.classList.remove("indeterminate");
            progressBar.classList.remove("d-none");
            progressBar.classList.add("success");
            statusContainer.className = "upload-status success";
            statusText.innerHTML = '<i class="fas fa-check-circle me-1"></i> Resume parsed successfully!';

            showSuccess(`Resume parsed with ${result.confidence || 'MEDIUM'} confidence. Please review the auto-filled data.`);

            // Navigate to Basic Info step — let the success message render first
            requestAnimationFrame(() => changeStep(1));

        } catch (error) {
            console.error("Resume upload error:", error);
            const err = /** @type {Error} */ (error);
            const msg = err.message || "Failed to parse resume. Please try again or enter your information manually.";
            setResumeUploadSpinnerVisible(false);
            progressBar.classList.remove("indeterminate", "success");
            progressBar.classList.add("d-none");
            if (progressTrack) progressTrack.classList.add("d-none");
            statusContainer.className = "upload-status error";
            statusText.innerHTML = `<i class="fas fa-exclamation-circle me-1"></i> ${escapeHtml(msg)}`;
            // Inline status only — avoid duplicating the same text in #error-alert
            errorAlert?.classList.add("d-none");
            successAlert?.classList.add("d-none");
        } finally {
            dropZone.classList.remove("uploading");
        }
    }

    /**
     * Auto-fill profile fields with parsed resume data
     * @param {Object} data - Parsed resume data
     */
    async function autoFillProfile(data) {

        // Step 1: Basic Information
        if (data.city) document.getElementById("city").value = data.city;
        if (data.state) document.getElementById("state").value = data.state;
        if (data.country) document.getElementById("country").value = data.country;
        if (data.professional_title) document.getElementById("professional-title").value = data.professional_title;
        if (data.years_experience !== undefined) document.getElementById("years-experience").value = data.years_experience;
        if (data.summary) document.getElementById("summary").value = data.summary;
        if (data.is_student !== undefined) document.getElementById("is-student").checked = data.is_student;
        if (data.phone) {
            const pe = document.getElementById("phone");
            if (pe) pe.value = data.phone;
        }
        if (data.linkedin_url) {
            const e = document.getElementById("linkedin-url");
            if (e) e.value = data.linkedin_url;
        }
        if (data.github_url) {
            const e = document.getElementById("github-url");
            if (e) e.value = data.github_url;
        }
        if (data.portfolio_url) {
            const e = document.getElementById("portfolio-url");
            if (e) e.value = data.portfolio_url;
        }

        // Step 2: Work Experience
        if (data.work_experience && data.work_experience.length > 0) {
            // Clear existing work experience
            workExperience = [];

            // Add each work experience (matching existing data structure)
            for (const exp of data.work_experience) {
                const endYm = formatDateForInput(exp.end_date);
                const hasEnd = !!String(endYm).trim();
                const isCurrent = !!(exp.is_current && !hasEnd);
                workExperience.push({
                    company: exp.company || "",
                    job_title: exp.title || exp.job_title || "",
                    start_date: formatDateForInput(exp.start_date),
                    end_date: hasEnd ? endYm : "",
                    description: exp.description || "",
                    is_current: isCurrent,
                });
            }

            // Use existing render function
            renderWorkExperience();

            const noExpEl = /** @type {HTMLInputElement|null} */ (document.getElementById("no-experience"));
            if (noExpEl && noExpEl.checked) {
                noExpEl.checked = false;
                noExpEl.dispatchEvent(new Event("change"));
            }
        }

        // Step 3: Education (parsed resume)
        if (data.education && data.education.length > 0) {
            educationHistory = [];
            for (const edu of data.education) {
                const endYm = formatDateForInput(edu.graduation_date || edu.end_date || "");
                const hasEnd = !!String(endYm).trim();
                const isCurrent = !!(edu.is_current && !hasEnd);
                let startYm = formatDateForInput(edu.start_date || "");
                if (!startYm && endYm) {
                    const parts = endYm.split("-");
                    const y = parseInt(parts[0], 10);
                    const m = parseInt(parts[1], 10) || 9;
                    if (!Number.isNaN(y)) {
                        startYm = `${Math.max(1900, y - 4)}-${String(m).padStart(2, "0")}`;
                    }
                }
                educationHistory.push({
                    institution: edu.institution || "",
                    degree: edu.degree || "",
                    field_of_study: edu.field_of_study || edu.field || "",
                    start_date: startYm,
                    end_date: hasEnd ? endYm : "",
                    is_current: isCurrent,
                });
            }
            renderEducation();
            const noEdEl = /** @type {HTMLInputElement|null} */ (document.getElementById("no-education"));
            if (noEdEl && noEdEl.checked) {
                noEdEl.checked = false;
                noEdEl.dispatchEvent(new Event("change"));
            }
        }

        // Step 4: Skills
        if (data.skills && data.skills.length > 0) {
            // Clear existing skills
            skills = [];
            const skillsContainer = document.getElementById("skills-container");
            skillsContainer.innerHTML = "";

            // Add each skill
            for (const skill of data.skills) {
                if (skill && typeof skill === "string") {
                    addSkill(skill);
                }
            }
        }

    }

    /**
     * Format date string for input (YYYY-MM format)
     * @param {string} dateStr - Date string from parsed data
     * @returns {string} Formatted date for input
     */
    function formatDateForInput(dateStr) {
        if (!dateStr) return "";

        // Handle "present" or similar
        if (typeof dateStr === "string" && dateStr.toLowerCase() === "present") return "";

        // If already in YYYY-MM format
        if (/^\d{4}-\d{2}$/.test(dateStr)) return dateStr;

        // If just year (YYYY)
        if (/^\d{4}$/.test(dateStr)) return `${dateStr}-01`;

        // Try to parse other formats
        try {
            const date = new Date(dateStr);
            if (!isNaN(date.getTime())) {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, "0");
                return `${year}-${month}`;
            }
        } catch (e) {
            console.warn("Could not parse date:", dateStr);
        }

        return "";
    }

    // Step navigation
    function changeStep(newStep) {
        if (newStep < 1 || newStep > totalSteps) return;

        // Update step
        currentStep = newStep;
        updateStepDisplay();

        // Update UI elements
        updateStepIndicators();
        updateProgressBar();

    }

    /**
     * Updates the step indicators in the UI based on current step
     */
    function updateStepIndicators() {
        // Step indicators are for steps 1-4 (Basic Info to Preferences)
        // Step 0 (resume upload) doesn't have an indicator
        document
            .querySelectorAll(".step-indicator")
            .forEach((indicator, index) => {
                const stepNum = index + 1; // Indicators are 1-indexed (1, 2, 3, 4)
                indicator.classList.remove("active", "completed");

                if (currentStep === 0) {
                    // On step 0, no indicator is active yet
                    return;
                }

                if (stepNum === currentStep) {
                    indicator.classList.add("active");
                } else if (stepNum < currentStep) {
                    indicator.classList.add("completed");
                }
            });
    }

    /**
     * Updates the progress bar based on current step
     * Step 0 (resume upload) doesn't count in progress - progress is for steps 1-4
     */
    function updateProgressBar() {
        // Progress is calculated based on steps 1–5 (Basic Info through Preferences)
        const mainSteps = 5;
        const adjustedStep = Math.max(0, currentStep); // Current position in main flow
        const progress = currentStep === 0 ? 0 : (adjustedStep / mainSteps) * 100;
        progressBar.style.width = `${progress}%`;
    }

    function updateStepDisplay() {
        // Show/hide step forms based on current step
        document.querySelectorAll(".step-form").forEach((form) => {
            const formId = form.id;
            const stepNum = parseInt(formId.replace("step-", ""), 10);
            form.classList.remove("active");
            if (stepNum === currentStep) {
                form.classList.add("active");
            }
        });

        // Update navigation buttons
        // Step 0: No prev/next buttons (handled by skip button)
        // Step 1: No prev (or prev goes to step 0), has next
        // Step 2-3: Has prev and next
        // Step 4: Has prev and complete
        // Show/hide progress container based on step
        const progressContainer = document.querySelector(".progress-container");
        if (progressContainer) {
            if (currentStep === 0) {
                progressContainer.classList.add("hidden");
            } else {
                progressContainer.classList.remove("hidden");
            }
        }

        if (currentStep === 0) {
            prevBtn.style.display = "none";
            nextBtn.style.display = "none";
            completeBtn.style.display = "none";
        } else {
            prevBtn.style.display = currentStep > 1 ? "block" : "none";
            nextBtn.style.display = currentStep < 5 ? "block" : "none";
            completeBtn.style.display = currentStep === 5 ? "block" : "none";
        }

        // Update completion summary on final step
        if (currentStep === totalSteps) {
            updateCompletionSummary();
        }
    }

    // Validation
    function validateCurrentStep() {
        switch (currentStep) {
            case 1:
                return validateBasicInfo();
            case 2:
                return validateWorkExperience();
            case 3:
                return validateEducation();
            case 4:
                return validateSkillsQualifications();
            case 5:
                return validateCareerPreferences();
            default:
                return true;
        }
    }

    /**
     * Validate basic information step (Step 1)
     * Ensures all required fields are completed with proper validation
     */
    function validateBasicInfo() {
        const requiredFields = [
            { id: "full-name", name: "Full Name" },
            { id: "city", name: "City" },
            { id: "state", name: "State" },
            { id: "country", name: "Country" },
            { id: "professional-title", name: "Professional Title" },
            { id: "years-experience", name: "Years of Experience" },
            { id: "summary", name: "Professional Summary" }
        ];

        // Optional URL fields (no validation required)
        const optionalUrlFields = [
            { id: "linkedin-url", name: "LinkedIn URL" },
            { id: "github-url", name: "GitHub URL" },
            { id: "portfolio-url", name: "Portfolio URL" },
        ];

        let isValid = true;
        let missingFields = [];

        // Check each required field
        requiredFields.forEach(fieldInfo => {
            const field = document.getElementById(fieldInfo.id);
            if (!field) return; // Skip if field doesn't exist

            const value = field.value.trim();
            if (value === "") {
                field.classList.add("is-invalid");
                isValid = false;
                missingFields.push(fieldInfo.name);
            } else {
                field.classList.remove("is-invalid");

                // Additional validation for specific fields
                if (fieldInfo.id === "years-experience") {
                    const years = parseInt(value);
                    if (isNaN(years) || years < 0 || years > 50) {
                        field.classList.add("is-invalid");
                        showError("Years of experience must be between 0 and 50");
                        return false;
                    }
                }
            }
        });

        // Validate optional URL fields if they're not empty
        optionalUrlFields.forEach(fieldInfo => {
            const field = document.getElementById(fieldInfo.id);
            if (!field) return; // Skip if field doesn't exist

            const value = field.value.trim();
            if (value !== "" && !isValidUrl(value)) {
                field.classList.add("is-invalid");
                isValid = false;
                showError(`Please enter a valid URL for ${fieldInfo.name}`);
            } else {
                field.classList.remove("is-invalid");
            }
        });

        if (!isValid && missingFields.length > 0) {
            showError(`Please fill in the following required fields: ${missingFields.join(", ")}`);
        }

        return isValid;
    }

    // Helper function to validate URLs
    function isValidUrl(url) {
        try {
            new URL(url);
            return true;
        } catch (e) {
            return false;
        }
    }

    /**
     * Validate work experience step (Step 2)
     * Ensures at least one work experience entry with required fields
     * or the no experience checkbox is checked
     */
    function validateWorkExperience() {
        // Check if the "no experience" checkbox is checked
        const noExperienceCheckbox = document.getElementById("no-experience");
        if (noExperienceCheckbox && noExperienceCheckbox.checked) {
            // If user has no experience, we don't need to validate further
            return true;
        }

        // Otherwise, require at least one work experience entry
        if (workExperience.length < VALIDATION_RULES.MIN_EXPERIENCE_ENTRIES) {
            showError(`Please add at least ${VALIDATION_RULES.MIN_EXPERIENCE_ENTRIES} work experience entry or check the "I don't have any relevant work experience yet" box`);
            return false;
        }

        // Validate each work experience entry has required fields
        for (let i = 0; i < workExperience.length; i++) {
            const exp = workExperience[i];
            if (!exp.company?.trim() || !exp.job_title?.trim() || !exp.start_date?.trim()) {
                showError(`Work experience entry ${i + 1}: Please fill in Company, Job Title, and Start Date`);
                return false;
            }

            // Validate date logic for completed positions
            if (!exp.is_current && !exp.end_date?.trim()) {
                showError(`Work experience entry ${i + 1}: Please provide an end date or mark as current position`);
                return false;
            }

        }

        return true;
    }

    /**
     * Validate education step (Step 3): at least one entry or "no formal education" checked.
     */
    function validateEducation() {
        const noEd = /** @type {HTMLInputElement|null} */ (document.getElementById("no-education"));
        if (noEd && noEd.checked) {
            return true;
        }
        if (!educationHistory || educationHistory.length < 1) {
            showError('Please add at least one education entry or check "I don\'t have formal education to add".');
            return false;
        }
        for (let i = 0; i < educationHistory.length; i++) {
            const edu = educationHistory[i];
            if (!edu.institution?.trim() || !edu.degree?.trim() || !edu.field_of_study?.trim()) {
                showError(`Education entry ${i + 1}: Please fill in Institution, Degree, and Field of study`);
                return false;
            }
            if (!edu.start_date?.trim()) {
                showError(`Education entry ${i + 1}: Please fill in Start month and year`);
                return false;
            }
            if (!edu.is_current && !edu.end_date?.trim()) {
                showError(
                    `Education entry ${i + 1}: Please fill in End month and year, or check Currently enrolled`,
                );
                return false;
            }
        }
        return true;
    }

    /**
     * Validate skills step (Step 4)
     * Ensures minimum requirements for skills (at least one skill required)
     */
    function validateSkillsQualifications() {

        // Check if skills array has at least one entry
        if (skills.length < 1) {
            // If skills array is empty, check if there are any skill badges in the DOM
            // (in case the skills array wasn't properly updated)
            const skillsContainer = document.getElementById("skills-container");
            if (skillsContainer) {
                const skillElements = skillsContainer.querySelectorAll(".skill-badge");
                if (skillElements.length > 0) {
                    return true;
                }
            }

            showError("Please add at least one skill");
            return false;
        }

        return true;
    }

    /**
     * Validate career preferences step (Step 5)
     * Ensures all required fields are completed according to requirements:
     * - Minimum & Maximum Salary: Required
     * - Job Types: At least one required
     * - Company Sizes: At least one required
     * - Work Arrangements: At least one required
     * - Travel Preference: One option required
     * - Additional Options: Optional
     */
    function validateCareerPreferences() {
        let isValid = true;
        let errorMessages = [];

        // Validate Salary (both optional, but if both provided min must be less than max)
        const minSalary = document.getElementById('min-salary').value;
        const maxSalary = document.getElementById('max-salary').value;

        if (minSalary && maxSalary && parseSalaryDigits(minSalary) >= parseSalaryDigits(maxSalary)) {
            isValid = false;
            errorMessages.push('Minimum salary must be less than maximum salary');
        }

        // Validate Job Types (at least one required)
        const jobTypeElements = document.querySelectorAll('input[id^="job-type-"]:checked');
        if (!jobTypeElements || jobTypeElements.length === 0) {
            isValid = false;
            errorMessages.push('At least one job type must be selected');
        }

        // Validate Company Sizes (at least one required)
        const companySizeElements = document.querySelectorAll('input[id^="company-size-"]:checked');
        if (!companySizeElements || companySizeElements.length === 0) {
            isValid = false;
            errorMessages.push('At least one preferred company size must be selected');
        }

        // Validate Work Arrangements (at least one required)
        const workArrangementElements = document.querySelectorAll('input[id^="work-arrangement-"]:checked');
        if (!workArrangementElements || workArrangementElements.length === 0) {
            isValid = false;
            errorMessages.push('At least one work arrangement must be selected');
        }

        // Validate Travel Preference (one option required)
        const travelPreferenceElement = document.querySelector('input[name="travel-preference"]:checked');
        if (!travelPreferenceElement) {
            isValid = false;
            errorMessages.push('Maximum travel preference must be selected');
        }

        const workAuthElement = document.querySelector('input[name="work-authorization"]:checked');
        if (!workAuthElement) {
            isValid = false;
            errorMessages.push('Work authorization status must be selected');
        }

        // Show validation errors if any
        if (!isValid) {
            showErrorMessage('Please correct the following issues: ' + errorMessages.join(', '));
        } else {
        }

        return isValid;
    }

    // Data saving
    /**
     * Save current step data to backend
     * Handles step-specific data saving with proper error handling
     */
    async function saveCurrentStepData() {
        try {

            // Get token using the same consistent approach as other functions
            // First check URL parameters for token
            const urlParams = new URLSearchParams(window.location.search);
            let token = urlParams.get('token');


            // If token is in URL, store it in localStorage with consistent key
            if (token) {
                localStorage.setItem("access_token", token);
                // Also save with alternate key for backward compatibility
                localStorage.setItem("authToken", token);
            } else {
                // Otherwise check localStorage with both possible keys
                token = localStorage.getItem("access_token") || localStorage.getItem("authToken");

                // Ensure token is stored with consistent key
                if (token) {
                    localStorage.setItem("access_token", token);
                }
            }

            if (!token) {
                console.error("Authentication token not found in URL or localStorage");
                showError("Authentication token not found. Please log in again.");
                window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || "/auth/login";
                return false;
            }


            let success = false;
            switch (currentStep) {
                case 1:
                    success = await saveBasicInfo();
                    break;
                case 2:
                    success = await saveWorkExperience();
                    break;
                case 3:
                    success = await saveEducation();
                    break;
                case 4:
                    // For skills step, make sure we have at least one skill
                    if (skills.length === 0) {
                        const skillsContainer = document.getElementById("skills-container");
                        const skillElements = skillsContainer.querySelectorAll(".skill-badge");
                        if (skillElements.length > 0) {
                            // Update skills array from UI
                            skills = [];
                            skillElements.forEach(element => {
                                skills.push(element.textContent.trim());
                            });
                        }
                    }
                    success = await saveSkillsQualifications();
                    break;
                case 5:
                    success = await saveCareerPreferences();
                    break;
                default:
                    console.warn(`Unknown step: ${currentStep}`);
                    return false;
            }

            if (success) {
                return true;
            } else {
                console.error(`Failed to save data for step ${currentStep}`);
                return false;
            }
        } catch (error) {
            console.error(`Error saving step ${currentStep} data:`, error);
            showError(`Error saving data: ${error.message}`);
            return false;
        }
    }

    /**
     * Save basic information to backend API
     * Handles form data collection and API communication
     */
    async function saveBasicInfo() {
        try {
            const formData = new FormData(document.getElementById("basic-info-form"));
            const data = Object.fromEntries(formData.entries());

            // Convert years_experience to integer (0 is valid — do not use truthiness)
            const rawYears = data["years_experience"];
            data.years_experience =
                rawYears === undefined || rawYears === null || rawYears === ""
                    ? NaN
                    : parseInt(String(rawYears), 10);

            // Convert is_student checkbox to boolean
            data.is_student = data.is_student === "on";

            // Ensure all required fields are present (years_experience checked separately — 0 is valid)
            const requiredFields = ["city", "state", "country", "professional_title", "summary"];
            for (const field of requiredFields) {
                if (!data[field]) {
                    throw new Error(`Missing required field: ${field}`);
                }
            }
            if (Number.isNaN(data.years_experience)) {
                throw new Error("Missing required field: years_experience");
            }


            await makeAuthenticatedApiCall("/profile/basic-info", "PUT", data);

            console.log("Basic info saved successfully");
            return true; // Ensure we return true for success
        } catch (error) {
            console.error("Error saving basic info:", error);
            throw new Error(`Failed to save basic information: ${error.message}`);
        }
    }

    /**
     * Save work experience information to backend API
     * Formats data according to API requirements and handles API communication
     */
    async function saveWorkExperience() {
        try {
            const noExpCheckbox = /** @type {HTMLInputElement|null} */ (document.getElementById("no-experience"));
            // If "no experience" is checked, persist [] so the server can mark step 2 complete
            if (noExpCheckbox && noExpCheckbox.checked) {
                workExperience = [];
                await makeAuthenticatedApiCall("/profile/work-experience", "PUT", {
                    work_experience: [],
                });
                return true;
            }

            if (!workExperience || !Array.isArray(workExperience) || workExperience.length === 0) {
                console.error("saveWorkExperience: empty work experience without no-experience option");
                showError(
                    'Please add at least one work experience entry or check "I don\'t have any relevant work experience yet".',
                );
                return false;
            }

            // Create a deep copy of work experience to avoid modifying the original
            const workExperienceToSave = JSON.parse(JSON.stringify(workExperience));

            /**
             * Sanitize text content by removing special characters
             * that may cause validation errors
             */
            function sanitizeText(text) {
                if (!text) return text;

                // Strip ASCII control characters only (preserve all printable ASCII + all Unicode)
                // This keeps •, ■, ▪, ▸, –, — and any other Unicode bullet/symbol characters
                return text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
            }
            // Clean and validate each work experience entry to ensure it meets API requirements
            for (let i = 0; i < workExperienceToSave.length; i++) {
                const exp = workExperienceToSave[i];
                // Sanitize description field to avoid validation errors
                if (exp.description) {
                    exp.description = sanitizeText(exp.description);
                }
                // Check required fields
                if (!exp.company || !exp.job_title || !exp.start_date) {
                    console.warn(`Work experience entry ${i+1} is missing required fields:`, exp);
                    // Remove this entry rather than failing the whole save
                    workExperienceToSave.splice(i, 1);
                    i--; // Adjust index since we removed an item
                    continue;
                }

                // Make sure start_date is in YYYY-MM format as required by the API
                if (exp.start_date) {
                    // Convert to YYYY-MM format if not already in that format
                    if (!exp.start_date.match(/^\d{4}-\d{2}$/)) {
                        try {
                            const date = new Date(exp.start_date);
                            if (!isNaN(date.getTime())) {
                                exp.start_date = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
                            } else {
                                // If date parsing failed, remove this entry
                                console.warn(`Invalid start_date format for entry ${i+1}:`, exp.start_date);
                                workExperienceToSave.splice(i, 1);
                                i--; // Adjust index
                                continue;
                            }
                        } catch (e) {
                            console.warn(`Error formatting start_date for entry ${i+1}:`, e);
                            workExperienceToSave.splice(i, 1);
                            i--; // Adjust index
                            continue;
                        }
                    }
                }

                // Handle end_date for current position and ensure proper format
                if (exp.is_current) {
                    // Clear end_date for current positions as required by API
                    exp.end_date = null;
                } else if (exp.end_date) {
                    // For non-current positions, ensure end_date is in YYYY-MM format
                    if (!exp.end_date.match(/^\d{4}-\d{2}$/)) {
                        try {
                            const date = new Date(exp.end_date);
                            if (!isNaN(date.getTime())) {
                                exp.end_date = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
                            } else {
                                // If we can't parse the end_date, set to null
                                console.warn(`Invalid end_date format for entry ${i+1}:`, exp.end_date);
                                exp.end_date = null;
                            }
                        } catch (e) {
                            console.warn(`Error formatting end_date for entry ${i+1}:`, e);
                            exp.end_date = null;
                        }
                    }
                }
            }

            // Check if we have any entries left after validation
            if (workExperienceToSave.length === 0) {
                console.warn("All work experience entries were invalid and removed");
                // Return true since an empty array is valid
                const requestData = { work_experience: [] };
                await makeAuthenticatedApiCall("/profile/work-experience", "PUT", requestData);
                return true;
            }


            // Format data according to backend API expectations
            const requestData = { work_experience: workExperienceToSave };

            const response = await makeAuthenticatedApiCall("/profile/work-experience", "PUT", requestData);

            console.log("Work experience saved successfully with", workExperienceToSave.length, "entries");
            return true; // Ensure we return true for success
        } catch (error) {
            console.error("Error saving work experience:", error);
            showError("Failed to save work experience: " + error.message);
            return false; // Return false on error
        }
    }

    /**
     * Persist education (Step 3)
     * @returns {Promise<boolean>}
     */
    async function saveEducation() {
        try {
            const noEd = /** @type {HTMLInputElement|null} */ (document.getElementById("no-education"));
            if (noEd && noEd.checked) {
                educationHistory = [];
                await makeAuthenticatedApiCall("/profile/education", "PUT", {
                    education: [],
                });
                return true;
            }
            if (!educationHistory || educationHistory.length === 0) {
                showError(
                    'Please add at least one education entry or check "I don\'t have formal education to add".',
                );
                return false;
            }
            const toSave = JSON.parse(JSON.stringify(educationHistory));
            for (let i = 0; i < toSave.length; i++) {
                const edu = toSave[i];
                if (!edu.institution?.trim() || !edu.degree?.trim() || !edu.field_of_study?.trim()) {
                    toSave.splice(i, 1);
                    i--;
                    continue;
                }
                if (!edu.start_date?.trim()) {
                    showError(`Education entry ${i + 1}: Please fill in Start month and year`);
                    return false;
                }
                if (!edu.is_current && !edu.end_date?.trim()) {
                    showError(
                        `Education entry ${i + 1}: Please fill in End month and year, or check Currently enrolled`,
                    );
                    return false;
                }
                if (edu.is_current) {
                    edu.end_date = null;
                }
                if (edu.start_date && !/^\d{4}-\d{2}$/.test(edu.start_date)) {
                    edu.start_date = formatDateForInput(edu.start_date);
                }
                if (edu.end_date && !/^\d{4}-\d{2}$/.test(edu.end_date)) {
                    edu.end_date = formatDateForInput(edu.end_date);
                }
                if (edu.field_of_study !== undefined && edu.field_of_study !== null) {
                    edu.field_of_study = String(edu.field_of_study).trim();
                }
            }
            if (toSave.length === 0) {
                await makeAuthenticatedApiCall("/profile/education", "PUT", { education: [] });
                return true;
            }
            await makeAuthenticatedApiCall("/profile/education", "PUT", { education: toSave });
            return true;
        } catch (error) {
            console.error("Error saving education:", error);
            showError("Failed to save education: " + error.message);
            return false;
        }
    }

    async function saveSkillsQualifications() {
        try {

            // Backend expects just "skills" field
            const data = {
                skills: skills
            };

            await makeAuthenticatedApiCall("/profile/skills-qualifications", "PUT", data);

            return true;
        } catch (error) {
            console.error("Error saving skills:", error);
            showError("Failed to save skills: " + error.message);
            return false;
        }
    }

    /**
     * Save career preferences to backend API
     * Maps form values to API enum values and handles API communication
     */
    async function saveCareerPreferences() {
        try {

            // Initialize empty arrays for collections
            let jobTypes = [];
            let companySizes = [];
            let workArrangements = [];
            let travelPreference = "NONE";

            // Maps form values to API enum values
            const jobTypeMapping = {
                "full-time": "FULL_TIME",
                "part-time": "PART_TIME",
                "contract": "CONTRACT",
                "freelance": "FREELANCE",
                "internship": "INTERNSHIP"
            };

            const companySizeMapping = {
                "startup": "STARTUP",
                "small": "SMALL", 
                "medium": "MEDIUM",
                "large": "LARGE",
                "enterprise": "ENTERPRISE"
            };

            const workArrangementMapping = {
                "onsite": "ONSITE",
                "remote": "REMOTE",
                "hybrid": "HYBRID"
            };

            // Collect job types
            try {
                const jobTypeElements = document.querySelectorAll('input[id^="job-type-"]:checked');
                if (jobTypeElements && jobTypeElements.length > 0) {
                    jobTypes = Array.from(jobTypeElements)
                        .map(input => {
                            const mappedValue = jobTypeMapping[input.value];
                            return mappedValue || "FULL_TIME";
                        })
                        .filter(Boolean);
                }

                // API requires at least one job type
                if (jobTypes.length === 0) {
                    jobTypes = ["FULL_TIME"];
                }

            } catch (error) {
                console.error("Error mapping job types:", error);
                jobTypes = ["FULL_TIME"];
            }

            // Collect company sizes
            try {
                const companySizeElements = document.querySelectorAll('input[id^="company-size-"]:checked');
                if (companySizeElements && companySizeElements.length > 0) {
                    companySizes = Array.from(companySizeElements)
                        .map(input => {
                            const mappedValue = companySizeMapping[input.value];
                            return mappedValue || "MEDIUM";
                        })
                        .filter(Boolean);
                }

                // API requires at least one company size
                if (companySizes.length === 0) {
                    companySizes = ["MEDIUM"];
                }

            } catch (error) {
                console.error("Error mapping company sizes:", error);
                companySizes = ["MEDIUM"];
            }

            // Collect work arrangements
            try {
                const workArrangementElements = document.querySelectorAll('input[id^="work-arrangement-"]:checked');
                if (workArrangementElements && workArrangementElements.length > 0) {
                    workArrangements = Array.from(workArrangementElements)
                        .map(input => {
                            const mappedValue = workArrangementMapping[input.value];
                            return mappedValue || "REMOTE";
                        })
                        .filter(Boolean);
                }

                // API requires at least one work arrangement
                if (workArrangements.length === 0) {
                    workArrangements = ["REMOTE"];
                }

            } catch (error) {
                console.error("Error mapping work arrangements:", error);
                workArrangements = ["REMOTE"];
            }

            // Get travel preference
            try {
                const travelPreferenceElement = document.querySelector('input[name="travel-preference"]:checked');
                if (travelPreferenceElement && travelPreferenceElement.value) {
                    travelPreference = travelPreferenceElement.value.toUpperCase();
                }
            } catch (error) {
                console.error("Error mapping travel preference:", error);
                travelPreference = "NONE";
            }

            const waEl = document.querySelector('input[name="work-authorization"]:checked');
            if (!waEl) {
                showError("Work authorization status must be selected");
                return false;
            }
            const workAuthorization = String(/** @type {HTMLInputElement} */ (waEl).value);

            const relocateChecked = document.getElementById('willing-to-relocate')?.checked || false;
            const visaSponsorshipChecked =
                document.getElementById('requires-visa-sponsorship')?.checked || false;
            const securityClearanceChecked = document.getElementById('has-security-clearance')?.checked || false;

            const minSalaryVal = readSalaryField(
                /** @type {HTMLInputElement|null} */ (document.getElementById('min-salary'))
            );
            const maxSalaryVal = readSalaryField(
                /** @type {HTMLInputElement|null} */ (document.getElementById('max-salary'))
            );
            const desiredSalaryRange = {};
            if (minSalaryVal > 0) desiredSalaryRange.min = minSalaryVal;
            if (maxSalaryVal > 0) desiredSalaryRange.max = maxSalaryVal;

            const data = {
                job_types: jobTypes,
                desired_company_sizes: companySizes,
                work_arrangements: workArrangements,
                max_travel_preference: travelPreference,
                desired_salary_range: Object.keys(desiredSalaryRange).length > 0 ? desiredSalaryRange : null,
                willing_to_relocate: relocateChecked,
                requires_visa_sponsorship: visaSponsorshipChecked,
                work_authorization: workAuthorization,
                has_security_clearance: securityClearanceChecked
            };


            const response = await makeAuthenticatedApiCall("/profile/career-preferences", "PUT", data);


            if (response && response.message === "Career preferences updated successfully") {
                return true;
            } else {
                console.error("Career preferences API returned unexpected response", response);
                showError("Failed to save career preferences: API validation failed");
                return false;
            }
        } catch (error) {
            console.error("Error saving career preferences:", error);
            showError("Failed to save career preferences: " + error.message);
            return false;
        }
    }
    /**
     * Complete user profile by saving all sections in sequence
     * and redirecting to dashboard upon successful completion
     */
    async function completeProfile() {
        try {
            // Validate ALL steps upfront before making any API calls.
            // Run each validator first — it shows its own error message via showErrorMessage().
            // If it fails, navigate to that step (changeStep no longer clears the error).
            const stepValidations = [
                { step: 1, fn: validateBasicInfo },
                { step: 2, fn: validateWorkExperience },
                { step: 3, fn: validateEducation },
                { step: 4, fn: validateSkillsQualifications },
                { step: 5, fn: validateCareerPreferences },
            ];

            for (const { step, fn } of stepValidations) {
                if (!fn()) {
                    changeStep(step);
                    window.scrollTo({ top: 0, behavior: "smooth" });
                    return;
                }
            }

            hideAlerts();
            setLoading(true);

            // Get token from URL or localStorage with consistent approach
            const urlParams = new URLSearchParams(window.location.search);
            let token = urlParams.get('token');


            if (token) {
                // Save token to localStorage for consistent access
                localStorage.setItem("access_token", token);
                // Also save with alternate key for backward compatibility
                localStorage.setItem("authToken", token);
            } else {
                // Get token from localStorage if not in URL
                token = localStorage.getItem("access_token") || localStorage.getItem("authToken");
            }

            if (!token) {
                console.error("No authentication token found");
                showError("Authentication token not found. Please log in again.");
                setLoading(false);
                return;
            }


            // Save basic info first
            try {
                if (validateBasicInfo()) {
                    const basicInfoResult = await saveBasicInfo();
                    if (basicInfoResult) {
                    } else {
                        console.error("Basic info save returned false");
                        showError("Failed to save basic information. Please try again.");
                        setLoading(false);
                        return false;
                    }
                } else {
                    console.error("Basic info validation failed");
                    showError("Please complete all required basic information fields before proceeding.");
                    setLoading(false);
                    return false;
                }
            } catch (error) {
                console.error("Error saving basic info:", error);
                showError("Error saving basic information: " + (error.message || "Unknown error"));
                setLoading(false);
                return false;
            }

            // Save work experience
            try {
                if (validateWorkExperience()) {
                    const workExpResult = await saveWorkExperience();
                    if (workExpResult) {
                    } else {
                        console.error("Work experience save returned false");
                        showError("Failed to save work experience. Please try again.");
                        setLoading(false);
                        return false;
                    }
                } else {
                    console.error("Work experience validation failed");
                    showError("Please add at least one work experience entry or check the 'I don't have any relevant work experience yet' box.");
                    setLoading(false);
                    return false;
                }
            } catch (error) {
                console.error("Error saving work experience:", error);
                showError("Error saving work experience: " + (error.message || "Unknown error"));
                setLoading(false);
                return false;
            }

            // Save education
            try {
                if (validateEducation()) {
                    const eduResult = await saveEducation();
                    if (!eduResult) {
                        console.error("Education save returned false");
                        showError("Failed to save education. Please try again.");
                        setLoading(false);
                        return false;
                    }
                } else {
                    console.error("Education validation failed");
                    showError(
                        'Please add at least one education entry or check "I don\'t have formal education to add".',
                    );
                    setLoading(false);
                    return false;
                }
            } catch (error) {
                console.error("Error saving education:", error);
                showError("Error saving education: " + (error.message || "Unknown error"));
                setLoading(false);
                return false;
            }

            // Save skills
            try {
                // Make sure skills array is populated from UI if empty
                if (skills.length === 0) {
                    const skillsContainer = document.getElementById("skills-container");
                    if (skillsContainer) {
                        const skillElements = skillsContainer.querySelectorAll(".skill-badge");
                        if (skillElements.length > 0) {
                            skillElements.forEach(element => {
                                const skillText = element.textContent.trim().replace("×", "").trim();
                                if (skillText && !skills.includes(skillText)) {
                                    skills.push(skillText);
                                }
                            });
                        }
                    }
                }

                if (validateSkillsQualifications()) {
                    const skillsResult = await saveSkillsQualifications();
                    if (skillsResult) {
                    } else {
                        console.error("Skills save returned false");
                        showError("Failed to save skills. Please try again.");
                        setLoading(false);
                        return false;
                    }
                } else {
                    console.error("Skills validation failed");
                    showError("Please add at least one skill before proceeding.");
                    setLoading(false);
                    return false;
                }
            } catch (error) {
                console.error("Error saving skills:", error);
                showError("Error saving skills: " + (error.message || "Unknown error"));
                setLoading(false);
                return false;
            }

            // Step 4: Save Career Preferences
            try {
                if (validateCareerPreferences()) {
                    await saveCareerPreferences();
                } else {
                    console.error("Career preferences validation failed");
                    showError("Please complete all required career preference fields before proceeding.");
                    setLoading(false);
                    return false; // Stop the profile completion process if validation fails
                }
            } catch (error) {
                console.error("Failed to save career preferences:", error);
                showError("Error saving career preferences: " + (error.message || "Unknown error"));
                setLoading(false);
                return false; // Stop the profile completion process if saving fails
            }

            // All sections have been successfully saved, mark profile as complete

            try {
                // Make API call to mark profile as complete
                const token = getAuthToken();
                const completeResponse = await fetch(`${API_BASE}/profile/complete`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${token}`
                    }
                });

                if (!completeResponse.ok) {
                    const errorData = await completeResponse.json().catch(() => ({}));
                    throw new Error(errorData.message || errorData.detail || `Server error: ${completeResponse.status}`);
                }

                // Set profile completed flag in localStorage
                localStorage.setItem("profile_completed", "true");

                // Show success message
                showSuccess("Profile completed successfully! Redirecting to dashboard...");

                // Redirect to dashboard — token is already in localStorage.
                // Use a short delay so the success message is visible before navigation.
                const successEl = document.getElementById('success-alert');
                if (successEl && typeof successEl.ontransitionend !== 'undefined') {
                    successEl.addEventListener('transitionend', () => { window.location.href = '/dashboard'; }, { once: true });
                    // Fallback in case transitionend never fires
                    setTimeout(() => { window.location.href = '/dashboard'; }, 1200);
                } else {
                    setTimeout(() => { window.location.href = '/dashboard'; }, 1200);
                }
            } catch (error) {
                console.error("Error marking profile as complete:", error);
                showError("Error completing profile: " + (error.message || "Unknown error"));
                setLoading(false);
                return false;
            }
        } catch (error) {
            console.error("Error completing profile:", error);
            showError("Failed to complete profile: " + error.message);
        } finally {
            setLoading(false);
        }
    }

    // Function to check if we need to show the preferences step
    function checkPreferencesStep() {
        // If we're on step 4, make sure the complete button is visible
        if (currentStep === totalSteps) {
            nextBtn.style.display = "none";
            completeBtn.style.display = "inline-block";
        }
    }

    // Duplicate function removed - using the more complete version above

    // Skills management
    function addSkill(skill) {
        if (skill && !skills.includes(skill)) {
            skills.push(skill);
            renderSkills();
        }
    }

    function removeSkill(skill) {
        skills = skills.filter((s) => s !== skill);
        renderSkills();
    }

    function renderSkills() {
        const container = skillsContainer || document.getElementById("skills-container");
        container.innerHTML = "";

        skills.forEach((skill) => {
            const tag = document.createElement("div");
            tag.className = "skill-tag";
            const span = document.createElement("span");
            span.textContent = skill;
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "skill-remove";
            btn.setAttribute("aria-label", `Remove skill: ${skill}`);
            btn.innerHTML = '<i class="fas fa-times"></i>';
            btn.addEventListener("click", () => removeSkill(skill));
            tag.appendChild(span);
            tag.appendChild(btn);
            container.appendChild(tag);
        });
    }



    // Work experience management
    function addWorkExperience() {
        workExperience.push({
            company: "",
            job_title: "",
            start_date: "",
            end_date: "",
            description: "",
            is_current: false,
        });
        renderWorkExperience();
    }

    function removeWorkExperience(index) {
        workExperience.splice(index, 1);
        renderWorkExperience();
    }

    /** @type {null | (() => void)} */
    let _profileMonthDdCloser = null;

    function closeOpenProfileMonthDropdown() {
        if (typeof _profileMonthDdCloser === "function") {
            try {
                _profileMonthDdCloser();
            } catch (_e) {
                /* ignore */
            }
            _profileMonthDdCloser = null;
        }
    }

    /**
     * Place the date quartet beside an invisible trash column so total width matches the text rows
     * (col + col + delete button).
     * @param {HTMLDivElement} shell
     * @param {HTMLDivElement} quartet
     */
    function appendProfileDatesMainWithTrashSlot(shell, quartet) {
        const main = document.createElement("div");
        main.className = "profile-exp-dates-main";
        main.appendChild(quartet);
        const dateTrashSlot = document.createElement("div");
        dateTrashSlot.className = "profile-exp-date-trash-slot";
        const dateTrashPh = document.createElement("button");
        dateTrashPh.type = "button";
        dateTrashPh.className = "remove-experience profile-exp-trash-slot-placeholder";
        dateTrashPh.tabIndex = -1;
        dateTrashPh.disabled = true;
        dateTrashPh.setAttribute("aria-hidden", "true");
        dateTrashPh.innerHTML = '<i class="fas fa-trash"></i>';
        dateTrashSlot.appendChild(dateTrashPh);
        main.appendChild(dateTrashSlot);
        shell.appendChild(main);
    }

    /**
     * Custom dropdown (not native select) so the open menu uses app theme CSS.
     * @param {Array<{value: string, label: string}>} options
     * @param {string} selectedValue
     * @param {string} placeholder
     * @param {boolean} disabled
     * @param {(s: string) => void} onPick
     * @param {string} ariaLabel
     * @param {string} [toggleId]
     * @param {boolean} [suppressEmptyOptionLabel] when true, empty value shows a blank toggle (floating label only) — avoids overlapping “Month”/“Year” with optional date labels
     * @returns {HTMLDivElement}
     */
    function createProfileStyledDropdown(
        options,
        selectedValue,
        placeholder,
        disabled,
        onPick,
        ariaLabel,
        toggleId,
        suppressEmptyOptionLabel,
    ) {
        const root = document.createElement("div");
        root.className = "profile-dd";

        let value = selectedValue || "";

        const suppressEmpty = suppressEmptyOptionLabel === true;

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "profile-dd-toggle profile-month-field-select";
        if (toggleId) {
            toggle.id = toggleId;
        }
        toggle.disabled = disabled;
        toggle.setAttribute("aria-haspopup", "listbox");
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", ariaLabel);

        const labelSpan = document.createElement("span");
        labelSpan.className = "profile-dd-toggle-text";

        function labelFor(v) {
            const hit = options.find(function (o) {
                return o.value === v;
            });
            if (hit) {
                if (suppressEmpty && hit.value === "") {
                    return "\u00a0";
                }
                return hit.label;
            }
            return placeholder;
        }

        function syncToggleText() {
            labelSpan.textContent = labelFor(value);
        }
        syncToggleText();

        const chev = document.createElement("span");
        chev.className = "profile-dd-chevron";
        chev.setAttribute("aria-hidden", "true");
        chev.innerHTML = '<i class="fas fa-chevron-down"></i>';

        toggle.appendChild(labelSpan);
        toggle.appendChild(chev);

        const panel = document.createElement("div");
        panel.className = "profile-dd-panel";
        panel.hidden = true;
        panel.setAttribute("role", "listbox");

        let myCloser = null;

        function closePanel() {
            panel.hidden = true;
            toggle.setAttribute("aria-expanded", "false");
            root.classList.remove("profile-dd-open");
            if (_profileMonthDdCloser === myCloser) {
                _profileMonthDdCloser = null;
            }
            document.removeEventListener("click", onDocClick, true);
            document.removeEventListener("keydown", onEsc, true);
        }

        function onDocClick(ev) {
            const t = ev.target;
            if (!(t instanceof Node) || !root.contains(t)) {
                closePanel();
            }
        }

        function onEsc(ev) {
            if (ev.key === "Escape") {
                closePanel();
            }
        }

        function openPanel() {
            closeOpenProfileMonthDropdown();
            panel.hidden = false;
            toggle.setAttribute("aria-expanded", "true");
            root.classList.add("profile-dd-open");
            myCloser = closePanel;
            _profileMonthDdCloser = closePanel;
            document.addEventListener("click", onDocClick, true);
            document.addEventListener("keydown", onEsc, true);
        }

        toggle.addEventListener("click", function (ev) {
            ev.stopPropagation();
            if (disabled) return;
            if (panel.hidden) {
                openPanel();
            } else {
                closePanel();
            }
        });

        function refreshSelectedMarks() {
            panel.querySelectorAll('[role="option"]').forEach(function (el) {
                const v = el.getAttribute("data-value") || "";
                el.setAttribute("aria-selected", v === value ? "true" : "false");
            });
        }

        options.forEach(function (opt) {
            const optBtn = document.createElement("button");
            optBtn.type = "button";
            optBtn.className = "profile-dd-option";
            optBtn.setAttribute("role", "option");
            optBtn.setAttribute("data-value", opt.value);
            optBtn.setAttribute("aria-selected", opt.value === value ? "true" : "false");

            const inner = document.createElement("span");
            inner.className = "profile-dd-option-inner";
            const chk = document.createElement("span");
            chk.className = "profile-dd-check";
            chk.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i>';
            const txt = document.createElement("span");
            txt.className = "profile-dd-option-label";
            txt.textContent = opt.label;
            inner.appendChild(chk);
            inner.appendChild(txt);
            optBtn.appendChild(inner);

            optBtn.addEventListener("click", function (ev) {
                ev.stopPropagation();
                value = opt.value;
                syncToggleText();
                refreshSelectedMarks();
                closePanel();
                onPick(value);
            });
            panel.appendChild(optBtn);
        });

        root.appendChild(toggle);
        root.appendChild(panel);
        return root;
    }

    /**
     * Append month + year cells (YYYY-MM) to a Bootstrap row — one flat row so all boxes share width.
     * @param {HTMLDivElement} parentRow
     * @param {string} cellColClass Bootstrap col classes for each cell (e.g. col-6 col-lg-2)
     * @param {string} [firstCellExtraClass] optional extra class on the month column (e.g. pair divider)
     * @param {string} initialValue
     * @param {boolean} disabled
     * @param {(s: string) => void} commit
     * @param {string} idPrefix
     * @param {'start'|'end'} whichHalf
     * @param {{ endPresentLocked?: boolean, showLabelStar?: boolean, suppressEmptyToggleLabel?: boolean }} [opts]
     *   end dates: `endPresentLocked` — show “Present” in both cells, disabled.
     *   Default: same chrome as work experience (cyan `*` labels, `Month`/`Year` when empty). Set
     *   `suppressEmptyToggleLabel: true` to hide empty value text (rare).
     */
    function appendProfileMonthYearPair(
        parentRow,
        cellColClass,
        firstCellExtraClass,
        initialValue,
        disabled,
        commit,
        idPrefix,
        whichHalf,
        opts,
    ) {
        const o = opts || {};
        const endPresentLocked =
            !!(o.endPresentLocked && whichHalf === "end");
        const showLabelStar = o.showLabelStar !== false;
        const suppressEmptyToggleLabel = o.suppressEmptyToggleLabel === true;

        const half = whichHalf === "end" ? "end" : "start";
        const labelMonth = half === "end" ? "End month" : "Start month";
        const labelYear = half === "end" ? "End year" : "Start year";
        let emptyMonthOption = "Month";
        let emptyYearOption = "Year";

        let monthOptions;
        let yearOptions;
        let yearVal = "";
        let monthVal = "";

        if (endPresentLocked) {
            monthOptions = [{ value: "present", label: "Present" }];
            yearOptions = [{ value: "present", label: "Present" }];
            monthVal = "present";
            yearVal = "present";
        } else {
            const parsed = /^(\d{4})-(\d{2})$/.exec(String(initialValue || "").trim());
            yearVal = parsed ? parsed[1] : "";
            monthVal = parsed ? parsed[2] : "";
            const MONTHS = [
                ["01", "Jan"],
                ["02", "Feb"],
                ["03", "Mar"],
                ["04", "Apr"],
                ["05", "May"],
                ["06", "Jun"],
                ["07", "Jul"],
                ["08", "Aug"],
                ["09", "Sep"],
                ["10", "Oct"],
                ["11", "Nov"],
                ["12", "Dec"],
            ];
            monthOptions = [{ value: "", label: emptyMonthOption }].concat(
                MONTHS.map(function (pair) {
                    return { value: pair[0], label: pair[1] };
                }),
            );

            yearOptions = [{ value: "", label: emptyYearOption }];
            const yNow = new Date().getFullYear();
            for (let yy = yNow; yy >= 1950; yy--) {
                yearOptions.push({ value: String(yy), label: String(yy) });
            }
        }

        const star = showLabelStar ? " *" : "";

        const ddDisabled = disabled || endPresentLocked;

        function emit() {
            if (endPresentLocked) {
                commit("");
                return;
            }
            if (yearVal && monthVal) {
                commit(yearVal + "-" + monthVal);
                return;
            }
            if (!yearVal && !monthVal) {
                commit("");
                return;
            }
            /* Partial month/year only: do not commit. Calling commit("") used to run renderEducation /
             * renderWorkExperience on every pick and remount the pair before YYYY-MM was complete. */
        }

        const toggleIdM = idPrefix + "-month-toggle";
        const toggleIdY = idPrefix + "-year-toggle";

        const floatWrapM = document.createElement("div");
        floatWrapM.className =
            "form-floating profile-dd-floating mb-0" + (endPresentLocked ? " profile-dd-end-present-locked" : "");
        const floatWrapY = document.createElement("div");
        floatWrapY.className =
            "form-floating profile-dd-floating mb-0" + (endPresentLocked ? " profile-dd-end-present-locked" : "");

        function refreshFloatStates() {
            if (endPresentLocked || monthVal) {
                floatWrapM.classList.add("has-value");
            } else {
                floatWrapM.classList.remove("has-value");
            }
            if (endPresentLocked || yearVal) {
                floatWrapY.classList.add("has-value");
            } else {
                floatWrapY.classList.remove("has-value");
            }
        }
        refreshFloatStates();

        const ddMonth = createProfileStyledDropdown(
            monthOptions,
            monthVal,
            emptyMonthOption,
            ddDisabled,
            function (v) {
                monthVal = v;
                refreshFloatStates();
                emit();
            },
            labelMonth + ", " + idPrefix,
            toggleIdM,
            suppressEmptyToggleLabel,
        );

        const ddYear = createProfileStyledDropdown(
            yearOptions,
            yearVal,
            emptyYearOption,
            ddDisabled,
            function (v) {
                yearVal = v;
                refreshFloatStates();
                emit();
            },
            labelYear + ", " + idPrefix,
            toggleIdY,
            suppressEmptyToggleLabel,
        );

        floatWrapM.appendChild(ddMonth);
        const labM = document.createElement("label");
        labM.htmlFor = toggleIdM;
        labM.textContent = labelMonth + star;
        floatWrapM.appendChild(labM);

        floatWrapY.appendChild(ddYear);
        const labY = document.createElement("label");
        labY.htmlFor = toggleIdY;
        labY.textContent = labelYear + star;
        floatWrapY.appendChild(labY);

        const colM = document.createElement("div");
        colM.className = firstCellExtraClass ? cellColClass + " " + firstCellExtraClass : cellColClass;
        colM.appendChild(floatWrapM);
        const colY = document.createElement("div");
        colY.className = cellColClass;
        colY.appendChild(floatWrapY);
        parentRow.appendChild(colM);
        parentRow.appendChild(colY);
    }

    /**
     * Hide the floating label while the job-description textarea is scrolled away from the top;
     * show again when scrolled back to top. Label position/transform unchanged — visibility only.
     * @param {HTMLDivElement} wrapper
     * @param {HTMLTextAreaElement} textarea
     */
    function bindProfileExpJobDescScrollLabel(wrapper, textarea) {
        function sync() {
            const scrolled = textarea.scrollTop > 2;
            wrapper.classList.toggle("profile-exp-job-desc-scrolled", scrolled);
        }
        textarea.addEventListener("scroll", sync, { passive: true });
        sync();
    }

    function renderWorkExperience() {
        const container = experienceContainer || document.getElementById("experience-container");
        container.innerHTML = "";

        workExperience.forEach((exp, index) => {
            const div = document.createElement("div");
            div.className = "experience-item";

            /**
             * Create a labeled form-floating input row.
             * @param {string} type
             * @param {string} initialValue
             * @param {string} labelText
             * @param {string} field
             * @param {boolean} [disabled]
             * @returns {HTMLDivElement}
             */
            function makeFloatingInput(type, initialValue, labelText, field, disabled = false) {
                const wrapper = document.createElement("div");
                wrapper.className = "form-floating mb-3";
                const input = document.createElement("input");
                input.type = type;
                input.className = "form-control";
                input.placeholder = " ";
                input.id = `ws-${index}-${field}`;
                input.value = initialValue;
                if (disabled) input.disabled = true;
                input.required = true;
                input.addEventListener("change", function () {
                    updateWorkExperience(index, field, this.value);
                });
                const label = document.createElement("label");
                label.htmlFor = input.id;
                label.textContent = labelText;
                wrapper.appendChild(input);
                wrapper.appendChild(label);
                return wrapper;
            }

            // Row 1: company | job title | trash button
            const row1 = document.createElement("div");
            row1.className = "row align-items-center profile-exp-company-job-row";
            const col1 = document.createElement("div"); col1.className = "col";
            col1.appendChild(makeFloatingInput("text", exp.company, "Company Name *", "company"));
            const col2 = document.createElement("div"); col2.className = "col";
            col2.appendChild(makeFloatingInput("text", exp.job_title, "Job Title *", "job_title"));
            const colTrash = document.createElement("div"); colTrash.className = "col-auto mb-3";
            const removeBtn = document.createElement("button");
            removeBtn.type = "button";
            removeBtn.className = "remove-experience";
            removeBtn.setAttribute("aria-label", `Remove experience ${index + 1}`);
            removeBtn.innerHTML = '<i class="fas fa-trash"></i>';
            removeBtn.addEventListener("click", () => removeWorkExperience(index));
            colTrash.appendChild(removeBtn);
            row1.appendChild(col1); row1.appendChild(col2); row1.appendChild(colTrash);
            div.appendChild(row1);

            const DATE_CELL = "profile-exp-date-cell";

            const shell = document.createElement("div");
            shell.className = "profile-exp-dates-shell mb-3";

            const quartet = document.createElement("div");
            quartet.className =
                "profile-exp-date-quartet" + (exp.is_current ? " profile-exp-date-quartet--start-only" : "");

            appendProfileMonthYearPair(
                quartet,
                DATE_CELL,
                "",
                exp.start_date,
                false,
                function (ym) {
                    updateWorkExperience(index, "start_date", ym);
                },
                `ws-${index}-start_date`,
                "start",
            );

            if (!exp.is_current) {
                appendProfileMonthYearPair(
                    quartet,
                    DATE_CELL,
                    "",
                    exp.end_date || "",
                    false,
                    function (ym) {
                        updateWorkExperience(index, "end_date", ym);
                    },
                    `ws-${index}-end_date`,
                    "end",
                );
            }

            appendProfileDatesMainWithTrashSlot(shell, quartet);

            const showWorkCurrentToggle = !String(exp.end_date || "").trim();
            if (showWorkCurrentToggle) {
                const checkWrap = document.createElement("div");
                checkWrap.className = "profile-exp-date-check-wrap";
                const checkWrapper = document.createElement("div");
                checkWrapper.className = "form-check mb-0 profile-exp-current-toggle";
                const wbId = `work-exp-is-current-${index}`;
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.className = "form-check-input";
                checkbox.id = wbId;
                checkbox.checked = !!exp.is_current;
                checkbox.addEventListener("change", function () {
                    updateWorkExperience(index, "is_current", this.checked);
                });
                const checkLabel = document.createElement("label");
                checkLabel.className = "form-check-label";
                checkLabel.setAttribute("for", wbId);
                checkLabel.textContent = "Currently work here";
                checkWrapper.appendChild(checkbox);
                checkWrapper.appendChild(checkLabel);
                checkWrap.appendChild(checkWrapper);
                shell.appendChild(checkWrap);
            }

            div.appendChild(shell);

            const descWrapper = document.createElement("div");
            descWrapper.className = "form-floating profile-exp-job-desc-float";
            const textarea = document.createElement("textarea");
            textarea.className = "form-control"; textarea.style.height = "150px"; textarea.style.minHeight = "150px";
            textarea.placeholder = " ";
            textarea.textContent = exp.description || "";
            textarea.addEventListener("change", function () {
                updateWorkExperience(index, "description", this.value);
            });
            const descLabel = document.createElement("label"); descLabel.textContent = "Job Description";
            descWrapper.appendChild(textarea); descWrapper.appendChild(descLabel);
            bindProfileExpJobDescScrollLabel(descWrapper, textarea);
            div.appendChild(descWrapper);

            container.appendChild(div);
        });
    }

    function updateWorkExperience(index, field, value) {
        workExperience[index][field] = value;

        if (field === "end_date") {
            if (String(value).trim()) {
                workExperience[index]["is_current"] = false;
            }
            renderWorkExperience();
            return;
        }

        if (field === "is_current") {
            if (value) {
                workExperience[index]["end_date"] = "";
            }
            renderWorkExperience();
        }
    }

    // =============================================================================
    // Education management (profile setup Step 3)
    // =============================================================================

    function addEducation() {
        educationHistory.push({
            institution: "",
            degree: "",
            field_of_study: "",
            start_date: "",
            end_date: "",
            is_current: false,
        });
        renderEducation();
    }

    function removeEducation(index) {
        educationHistory.splice(index, 1);
        renderEducation();
    }

    /**
     * @param {number} index
     * @param {string} field
     * @param {string|boolean} value
     */
    function updateEducation(index, field, value) {
        if (!educationHistory[index]) return;
        educationHistory[index][field] = value;
        if (field === "end_date") {
            if (String(value).trim()) {
                educationHistory[index]["is_current"] = false;
            }
            renderEducation();
            return;
        }
        if (field === "is_current") {
            if (value) {
                educationHistory[index]["end_date"] = "";
            }
            renderEducation();
        }
    }

    function renderEducation() {
        const container = educationContainer || document.getElementById("education-container");
        if (!container) return;
        container.innerHTML = "";

        educationHistory.forEach((edu, index) => {
            const div = document.createElement("div");
            div.className = "experience-item";

            /**
             * @param {string} type
             * @param {string} initialValue
             * @param {string} labelText
             * @param {string} field
             * @param {boolean} [disabled]
             * @param {boolean} [required]
             */
            function makeFloatingInput(type, initialValue, labelText, field, disabled = false, required = true) {
                const wrapper = document.createElement("div");
                wrapper.className = "form-floating mb-3";
                const input = document.createElement("input");
                input.type = type;
                input.className = "form-control";
                input.placeholder = " ";
                input.id = `ed-${index}-${field}`;
                input.value = initialValue;
                if (disabled) input.disabled = true;
                input.required = required;
                input.addEventListener("change", function () {
                    updateEducation(index, field, this.value);
                });
                const label = document.createElement("label");
                label.htmlFor = input.id;
                label.textContent = labelText;
                wrapper.appendChild(input);
                wrapper.appendChild(label);
                return wrapper;
            }

            const row1 = document.createElement("div");
            row1.className = "row align-items-center profile-exp-company-job-row";
            const col1 = document.createElement("div");
            col1.className = "col";
            col1.appendChild(makeFloatingInput("text", edu.institution, "Institution *", "institution"));
            const col2 = document.createElement("div");
            col2.className = "col";
            col2.appendChild(makeFloatingInput("text", edu.degree, "Degree *", "degree"));
            const colTrash = document.createElement("div");
            colTrash.className = "col-auto mb-3";
            const removeBtn = document.createElement("button");
            removeBtn.type = "button";
            removeBtn.className = "remove-experience";
            removeBtn.setAttribute("aria-label", `Remove education ${index + 1}`);
            removeBtn.innerHTML = '<i class="fas fa-trash"></i>';
            removeBtn.addEventListener("click", () => removeEducation(index));
            colTrash.appendChild(removeBtn);
            row1.appendChild(col1);
            row1.appendChild(col2);
            row1.appendChild(colTrash);
            div.appendChild(row1);

            const fieldRow = document.createElement("div");
            fieldRow.className = "row align-items-center profile-exp-company-job-row";
            const fieldCol = document.createElement("div");
            fieldCol.className = "col profile-exp-education-field-col";
            const fieldWrap = document.createElement("div");
            fieldWrap.className = "form-floating mb-3 w-100";
            const fieldInput = document.createElement("input");
            fieldInput.id = `ed-${index}-field_of_study`;
            fieldInput.className = "form-control";
            fieldInput.placeholder = " ";
            fieldInput.value = edu.field_of_study || "";
            fieldInput.addEventListener("change", function () {
                updateEducation(index, "field_of_study", this.value);
            });
            const fieldLabel = document.createElement("label");
            fieldLabel.textContent = "Field of study *";
            fieldLabel.htmlFor = fieldInput.id;
            fieldInput.required = true;
            fieldWrap.appendChild(fieldInput);
            fieldWrap.appendChild(fieldLabel);
            fieldCol.appendChild(fieldWrap);
            const fieldTrashSlot = document.createElement("div");
            fieldTrashSlot.className = "col-auto mb-3 d-flex align-items-center justify-content-center";
            const trashSlotPh = document.createElement("button");
            trashSlotPh.type = "button";
            trashSlotPh.className = "remove-experience profile-exp-trash-slot-placeholder";
            trashSlotPh.tabIndex = -1;
            trashSlotPh.disabled = true;
            trashSlotPh.setAttribute("aria-hidden", "true");
            trashSlotPh.innerHTML = '<i class="fas fa-trash"></i>';
            fieldTrashSlot.appendChild(trashSlotPh);
            fieldRow.appendChild(fieldCol);
            fieldRow.appendChild(fieldTrashSlot);
            div.appendChild(fieldRow);

            const DATE_CELL = "profile-exp-date-cell";

            const shell = document.createElement("div");
            shell.className = "profile-exp-dates-shell mb-3";

            const quartet = document.createElement("div");
            quartet.className =
                "profile-exp-date-quartet" + (edu.is_current ? " profile-exp-date-quartet--start-only" : "");

            appendProfileMonthYearPair(
                quartet,
                DATE_CELL,
                "",
                edu.start_date || "",
                false,
                function (ym) {
                    updateEducation(index, "start_date", ym);
                },
                `ed-${index}-start_date`,
                "start",
            );

            if (!edu.is_current) {
                appendProfileMonthYearPair(
                    quartet,
                    DATE_CELL,
                    "",
                    edu.end_date || "",
                    false,
                    function (ym) {
                        updateEducation(index, "end_date", ym);
                    },
                    `ed-${index}-end_date`,
                    "end",
                );
            }

            appendProfileDatesMainWithTrashSlot(shell, quartet);

            const showEduCurrentToggle = !String(edu.end_date || "").trim();
            if (showEduCurrentToggle) {
                const checkWrap = document.createElement("div");
                checkWrap.className = "profile-exp-date-check-wrap";
                const checkWrapper = document.createElement("div");
                checkWrapper.className = "form-check mb-0 profile-exp-current-toggle";
                const cbId = `education-is-current-${index}`;
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.className = "form-check-input";
                checkbox.id = cbId;
                checkbox.checked = !!edu.is_current;
                checkbox.addEventListener("change", function () {
                    updateEducation(index, "is_current", this.checked);
                });
                const checkLabel = document.createElement("label");
                checkLabel.className = "form-check-label";
                checkLabel.setAttribute("for", cbId);
                checkLabel.textContent = "Currently enrolled";
                checkWrapper.appendChild(checkbox);
                checkWrapper.appendChild(checkLabel);
                checkWrap.appendChild(checkWrapper);
                shell.appendChild(checkWrap);
            }

            div.appendChild(shell);

            container.appendChild(div);
        });
    }

    // File upload functionality removed - no longer needed in 4-step profile setup

    // Completion summary
    function updateCompletionSummary() {
        const container = document.getElementById("completion-items");

        // Check if container exists before manipulating it
        if (!container) {
            return;
        }

        container.innerHTML = "";

        const items = [
            {
                name: "Basic Information",
                completed: validateBasicInfo(),
            },
            {
                name: "Work Experience",
                completed: validateWorkExperience(),
            },
            {
                name: "Education",
                completed: validateEducation(),
            },
            {
                name: "Skills",
                completed: skills.length >= VALIDATION_RULES.MIN_SKILLS,
            },
            {
                name: "Career Preferences",
                completed: validateCareerPreferences(),
            },
        ];

        items.forEach((item) => {
            const div = document.createElement("div");
            div.className = "completion-item";
            div.innerHTML = `
            <span>${escapeHtml(item.name)}</span>
            <span class="completion-status">
                ${item.completed ? '<i class="fas fa-check text-success"></i> Complete' : '<i class="fas fa-times text-danger"></i> Incomplete'}
            </span>
        `;
            container.appendChild(div);
        });
    }

    // Utility functions
    function showError(message) {
        showErrorMessage(message);
        successAlert?.classList.add("d-none");
    }

    function showSuccess(message) {
        if (successMessage) successMessage.textContent = message;
        successAlert?.classList.remove("d-none");
        errorAlert?.classList.add("d-none");
    }

    function hideAlerts() {
        if (errorAlert) {
            errorAlert.classList.add("d-none");
        }
        if (successAlert) {
            successAlert.classList.add("d-none");
        }
    }

    function setLoading(loading) {
        if (nextBtn) {
            nextBtn.disabled = loading;
            if (loading) {
                nextBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processing...';
            } else {
                nextBtn.innerHTML = 'Next<i class="fas fa-arrow-right ms-2"></i>';
            }
        }

        if (completeBtn) {
            completeBtn.disabled = loading;
            if (loading) {
                completeBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Completing...';
            } else {
                completeBtn.innerHTML = 'Complete Profile<i class="fas fa-check ms-2"></i>';
            }
        }
    }

    function logout() {
        // @ts-ignore
        if (window.app && typeof window.app.logout === 'function') { window.app.logout(); return; }
        localStorage.removeItem('access_token');
        localStorage.removeItem('authToken');
        window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';
    }

    // Make functions globally available
    window.removeSkill = removeSkill;
    window.removeWorkExperience = removeWorkExperience;
    window.updateWorkExperience = updateWorkExperience;

    // ---- Public API: functions accessible from inline HTML handlers ----
    window.logout = logout;

}());
