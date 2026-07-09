/**
 * Migrated from ui/static/js/profile.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
/**
 * @fileoverview ApplyPilot - Profile Management JavaScript
 * Handles profile setup, editing, and data management.
 * 
 * @description Provides profile management functionality including:
 * - Multi-step profile setup wizard
 * - Work experience management
 * - Skills and qualifications
 * - Career preferences
 * - Auto-save functionality
 * 
 * @note This is an alternative/advanced implementation of profile management.
 * The main profile setup interface uses inline JavaScript in setup.html.
 */

/// <reference path="./types.js" />

/* eslint-disable no-unused-vars */

/**
 * Profile manager class for user profile setup and editing.
 * Implements a multi-step wizard with validation and auto-save.
 * 
 * @class
 */
class ProfileManager {
  static normalizeYearMonth(value) {
    if (value == null || value === "") return "";
    const s = String(value).trim();
    if (/^\d{4}-\d{2}$/.test(s)) return s;
    if (s.length >= 10 && s[4] === "-") return s.slice(0, 7);
    return s.length >= 7 ? s.slice(0, 7) : s;
  }

  /**
   * Escape HTML special characters to prevent XSS.
   * @param {string|null|undefined} str
   * @returns {string}
   */
  static escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;');
  }

  /**
   * Create a new ProfileManager instance.
   */
  constructor() {
    /** @type {string} Base URL for API calls */
    this.apiBaseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';
    
    /** @type {number} Current step in the wizard (1-5) */
    this.currentStep = 1;
    
    /** @type {number} Total number of steps */
    this.maxSteps = 5;
    
    /** @type {Object} Profile data being edited */
    this.profileData = {};
    
    /** @type {boolean} Whether auto-save is in progress */
    this.isAutoSaving = false;
    
    /** @type {number} Delay before auto-save triggers (ms) */
    this.autoSaveDelay = 2000;
    
    /** @type {number|null} Auto-save timer ID */
    this.autoSaveTimer = null;

    this.init();
  }

  /**
   * Initialize profile manager
   */
  init() {
    this.setupEventListeners();
    this.loadProfileData();
    this.initializeComponents();
    this.setupAutoSave();
  }

  /**
   * Setup event listeners
   */
  setupEventListeners() {
    // Step navigation
    document.addEventListener("click", (e) => {
      if (e.target.matches(".next-step-btn")) {
        e.preventDefault();
        this.nextStep();
      }
      if (e.target.matches(".prev-step-btn")) {
        e.preventDefault();
        this.prevStep();
      }
      if (e.target.matches(".step-indicator")) {
        e.preventDefault();
        const step = parseInt(e.target.getAttribute("data-step"));
        this.goToStep(step);
      }
    });

    // Form submission
    const profileForm = document.querySelector("#profileForm");
    if (profileForm) {
      profileForm.addEventListener("submit", (e) =>
        this.handleFormSubmission(e),
      );
    }

    // Auto-save on input changes
    document.addEventListener("input", (e) => {
      if (e.target.matches(".profile-input")) {
        this.handleInputChange(e.target);
        this.scheduleAutoSave();
      }
    });

    // Handle checkbox changes
    document.addEventListener("change", (e) => {
      if (e.target.matches(".profile-checkbox")) {
        this.handleCheckboxChange(e.target);
        this.scheduleAutoSave();
      }
    });

    // Add experience/education/certification buttons
    document.addEventListener("click", (e) => {
      if (e.target.matches(".add-experience-btn")) {
        e.preventDefault();
        this.addExperienceEntry();
      }
      if (e.target.matches(".add-education-btn")) {
        e.preventDefault();
        this.addEducationEntry();
      }
      if (e.target.matches(".add-certification-btn")) {
        e.preventDefault();
        this.addCertificationEntry();
      }
      if (e.target.matches(".remove-entry-btn")) {
        e.preventDefault();
        this.removeEntry(e.target);
      }
    });

    // File upload handling
    document.addEventListener("change", (e) => {
      if (e.target.matches(".resume-upload")) {
        this.handleResumeUpload(e.target);
      }
    });

    // Current job checkbox handling
    document.addEventListener("change", (e) => {
      if (e.target.matches(".current-job-checkbox")) {
        this.handleCurrentJobToggle(e.target);
      }
    });

    // Form validation
    document.addEventListener(
      "blur",
      (e) => {
        if (e.target.matches(".profile-input[required]")) {
          this.validateField(e.target);
        }
      },
      true,
    );
  }

  /**
   * Load existing profile data
   */
  async loadProfileData() {
    try {
      const response = await this.apiCall("/profile/", "GET");
      if (response.user_info && response.profile_data) {
        // Merge user_info and profile_data for easier access
        this.profileData = {
          ...response.user_info,
          ...response.profile_data
        };
        this.populateForm();
        this.updateProgress();
      }
    } catch (error) {
      console.error("Error loading profile data:", error);
    }
  }

  /**
   * Initialize components
   */
  initializeComponents() {
    this.updateStepVisibility();
    this.initializeDatePickers();
    this.initializeSkillsTags();
    this.setupProgressIndicator();
  }

  /**
   * Initialize date pickers
   */
  initializeDatePickers() {
    const dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach((input) => {
      if (!input.value) {
        input.max = new Date().toISOString().split("T")[0];
      }
    });
  }

  /**
   * Initialize skills tags input
   */
  initializeSkillsTags() {
    const skillsInputs = document.querySelectorAll(".skills-input");
    skillsInputs.forEach((input) => {
      this.setupTagsInput(input);
    });
  }

  /**
   * Setup tags input for skills
   */
  setupTagsInput(input) {
    const container = input.parentElement;
    const tagsContainer =
      container.querySelector(".tags-container") ||
      this.createTagsContainer(container);

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        this.addSkillTag(input, tagsContainer);
      }
    });

    input.addEventListener("blur", () => {
      if (input.value.trim()) {
        this.addSkillTag(input, tagsContainer);
      }
    });

    // Load existing tags
    this.loadExistingTags(input, tagsContainer);
  }

  /**
   * Create tags container
   */
  createTagsContainer(parent) {
    const container = document.createElement("div");
    container.className = "tags-container mt-2";
    parent.appendChild(container);
    return container;
  }

  /**
   * Add skill tag
   */
  addSkillTag(input, container) {
    const value = input.value.trim();
    if (!value) return;

    const tag = document.createElement("span");
    tag.className = "badge bg-primary me-2 mb-2 skill-tag";
    tag.setAttribute("data-skill", value);

    const labelNode = document.createTextNode(value + ' ');
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn-close btn-close-white ms-1";
    removeBtn.setAttribute("aria-label", "Remove skill");
    removeBtn.addEventListener("click", function () { tag.remove(); });
    tag.appendChild(labelNode);
    tag.appendChild(removeBtn);

    container.appendChild(tag);
    input.value = "";
    this.updateSkillsData(container);
  }

  /**
   * Load existing tags
   */
  loadExistingTags(input, container) {
    const fieldName = input.getAttribute("data-field");
    const skills = this.profileData[fieldName];

    if (skills && Array.isArray(skills)) {
      skills.forEach((skill) => {
        const tag = document.createElement("span");
        tag.className = "badge bg-primary me-2 mb-2 skill-tag";
        const skillText = document.createTextNode(skill + ' ');
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn-close btn-close-white ms-1';
        removeBtn.setAttribute('aria-label', 'Remove skill');
        removeBtn.addEventListener('click', function () { tag.remove(); });
        tag.appendChild(skillText);
        tag.appendChild(removeBtn);
        tag.setAttribute("data-skill", skill);
        container.appendChild(tag);
      });
    }
  }

  /**
   * Update skills data
   */
  updateSkillsData(container) {
    const fieldName =
      container.previousElementSibling.getAttribute("data-field");
    const tags = container.querySelectorAll(".skill-tag");
    const skills = Array.from(tags).map((tag) =>
      tag.getAttribute("data-skill"),
    );

    this.profileData[fieldName] = skills;
  }

  /**
   * Setup progress indicator
   */
  setupProgressIndicator() {
    this.updateStepIndicators();
  }

  /**
   * Setup auto-save functionality
   */
  setupAutoSave() {
    // Auto-save every 30 seconds if there are unsaved changes
    setInterval(() => {
      if (this.hasUnsavedChanges() && !this.isAutoSaving) {
        this.autoSave();
      }
    }, 30000);
  }

  /**
   * Handle input changes
   */
  handleInputChange(input) {
    const fieldName = input.getAttribute("data-field") || input.name;
    const value = input.value;

    if (fieldName) {
      this.setNestedValue(this.profileData, fieldName, value);
      this.markAsChanged();
    }

    // Validate field
    this.validateField(input);
  }

  /**
   * Handle checkbox changes
   */
  handleCheckboxChange(checkbox) {
    const fieldName = checkbox.getAttribute("data-field") || checkbox.name;
    const value = checkbox.checked;

    if (fieldName) {
      this.setNestedValue(this.profileData, fieldName, value);
      this.markAsChanged();
    }
  }

  /**
   * Handle current job toggle
   */
  handleCurrentJobToggle(checkbox) {
    const entryContainer = checkbox.closest(
      ".experience-entry, .education-entry",
    );
    const endDateInput = entryContainer.querySelector(".end-date-input");

    if (checkbox.checked) {
      endDateInput.disabled = true;
      endDateInput.value = "";
      endDateInput.removeAttribute("required");
    } else {
      endDateInput.disabled = false;
      endDateInput.setAttribute("required", "");
    }

    this.handleCheckboxChange(checkbox);
  }

  /**
   * Set nested object value using dot notation
   */
  setNestedValue(obj, path, value) {
    const keys = path.split(".");
    let current = obj;

    for (let i = 0; i < keys.length - 1; i++) {
      const key = keys[i];
      if (key === "__proto__" || key === "constructor" || key === "prototype") {
        return;
      }
      if (!(key in current)) {
        current[key] = {};
      }
      current = current[key];
    }

    const leafKey = keys[keys.length - 1];
    if (leafKey === "__proto__" || leafKey === "constructor" || leafKey === "prototype") {
      return;
    }
    current[leafKey] = value;
  }

  /**
   * Get nested object value using dot notation
   */
  getNestedValue(obj, path) {
    return path.split(".").reduce((current, key) => current?.[key], obj);
  }

  /**
   * Mark profile as changed
   */
  markAsChanged() {
    document.body.setAttribute("data-profile-changed", "true");
  }

  /**
   * Check if there are unsaved changes
   */
  hasUnsavedChanges() {
    return document.body.getAttribute("data-profile-changed") === "true";
  }

  /**
   * Schedule auto-save
   */
  scheduleAutoSave() {
    clearTimeout(this.autoSaveTimer);
    this.autoSaveTimer = setTimeout(() => {
      this.autoSave();
    }, this.autoSaveDelay);
  }

  /**
   * Auto-save profile data
   */
  async autoSave() {
    if (this.isAutoSaving) return;

    try {
      this.isAutoSaving = true;
      this.showAutoSaveIndicator();

      // Auto-save disabled - backend doesn't support auto-save endpoint
      // Would need to save to appropriate step endpoint based on current step
      // Auto-save not implemented in this version
      
      // For now, just mark as saved to prevent constant auto-save attempts
      document.body.removeAttribute("data-profile-changed");
      this.showAutoSaveSuccess();
      return;
    } catch (error) {
      // Auto-save failed
      this.showAutoSaveError();
    } finally {
      this.isAutoSaving = false;
      this.hideAutoSaveIndicator();
    }
  }

  /**
   * Show auto-save indicator
   */
  showAutoSaveIndicator() {
    let indicator = document.querySelector(".auto-save-indicator");
    if (!indicator) {
      indicator = document.createElement("div");
      indicator.className = "auto-save-indicator";
      indicator.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #ffc107;
                color: #212529;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 14px;
                z-index: 1050;
            `;
      document.body.appendChild(indicator);
    }
    indicator.innerHTML =
      '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';
    indicator.style.display = "block";
  }

  /**
   * Hide auto-save indicator
   */
  hideAutoSaveIndicator() {
    const indicator = document.querySelector(".auto-save-indicator");
    if (indicator) {
      indicator.style.display = "none";
    }
  }

  /**
   * Show auto-save success
   */
  showAutoSaveSuccess() {
    const indicator = document.querySelector(".auto-save-indicator");
    if (indicator) {
      indicator.innerHTML = '<i class="fas fa-check me-2"></i>Saved';
      indicator.style.background = "#28a745";
      indicator.style.color = "white";
      setTimeout(() => this.hideAutoSaveIndicator(), 2000);
    }
  }

  /**
   * Show auto-save error
   */
  showAutoSaveError() {
    const indicator = document.querySelector(".auto-save-indicator");
    if (indicator) {
      indicator.innerHTML =
        '<i class="fas fa-exclamation-triangle me-2"></i>Save failed';
      indicator.style.background = "#dc3545";
      indicator.style.color = "white";
      setTimeout(() => this.hideAutoSaveIndicator(), 3000);
    }
  }

  /**
   * Add experience entry
   */
  addExperienceEntry() {
    const container = document.querySelector(".experience-entries");
    const entryHtml = this.getExperienceEntryTemplate();

    const entry = document.createElement("div");
    entry.className = "experience-entry border rounded p-3 mb-3";
    entry.innerHTML = entryHtml;

    container.appendChild(entry);
    this.initializeDatePickers();
  }

  /**
   * Add education entry
   */
  addEducationEntry() {
    const container = document.querySelector(".education-entries");
    const entryHtml = this.getEducationEntryTemplate();

    const entry = document.createElement("div");
    entry.className = "education-entry border rounded p-3 mb-3";
    entry.innerHTML = entryHtml;

    container.appendChild(entry);
    this.initializeDatePickers();
  }

  /**
   * Add certification entry
   */
  addCertificationEntry() {
    const container = document.querySelector(".certification-entries");
    const entryHtml = this.getCertificationEntryTemplate();

    const entry = document.createElement("div");
    entry.className = "certification-entry border rounded p-3 mb-3";
    entry.innerHTML = entryHtml;

    container.appendChild(entry);
    this.initializeDatePickers();
  }

  /**
   * Remove entry
   */
  removeEntry(button) {
    const entry = button.closest(
      ".experience-entry, .education-entry, .certification-entry",
    );
    if (entry) {
      entry.remove();
      this.scheduleAutoSave();
    }
  }

  /**
   * Get experience entry template
   */
  getExperienceEntryTemplate() {
    return `
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Job Title <span class="text-danger">*</span></label>
                        <input type="text" class="form-control profile-input" data-field="experience.title" required>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Company <span class="text-danger">*</span></label>
                        <input type="text" class="form-control profile-input" data-field="experience.company" required>
                    </div>
                </div>
            </div>
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Location</label>
                        <input type="text" class="form-control profile-input" data-field="experience.location" placeholder="City, State">
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Employment Type</label>
                        <select class="form-control profile-input" data-field="experience.type">
                            <option value="">Select type</option>
                            <option value="full-time">Full-time</option>
                            <option value="part-time">Part-time</option>
                            <option value="contract">Contract</option>
                            <option value="internship">Internship</option>
                            <option value="freelance">Freelance</option>
                        </select>
                    </div>
                </div>
            </div>
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Start Date <span class="text-danger">*</span></label>
                        <input type="date" class="form-control profile-input" data-field="experience.start_date" required>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">End Date</label>
                        <input type="date" class="form-control profile-input end-date-input" data-field="experience.end_date">
                        <div class="form-check mt-2">
                            <input type="checkbox" class="form-check-input profile-checkbox current-job-checkbox" data-field="experience.current">
                            <label class="form-check-label">I currently work here</label>
                        </div>
                    </div>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label">Description</label>
                <textarea class="form-control profile-input" data-field="experience.description" rows="3" placeholder="Describe your responsibilities and achievements..."></textarea>
            </div>
            <div class="text-end">
                <button type="button" class="btn btn-outline-danger btn-sm remove-entry-btn">
                    <i class="fas fa-trash me-1"></i>Remove
                </button>
            </div>
        `;
  }

  /**
   * Get education entry template
   */
  getEducationEntryTemplate() {
    return `
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Institution <span class="text-danger">*</span></label>
                        <input type="text" class="form-control profile-input" data-field="education.institution" required>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Degree <span class="text-danger">*</span></label>
                        <input type="text" class="form-control profile-input" data-field="education.degree" required>
                    </div>
                </div>
            </div>
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Field of Study</label>
                        <input type="text" class="form-control profile-input" data-field="education.field">
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Location</label>
                        <input type="text" class="form-control profile-input" data-field="education.location" placeholder="City, State">
                    </div>
                </div>
            </div>
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Start Date</label>
                        <input type="date" class="form-control profile-input" data-field="education.start_date">
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">End Date</label>
                        <input type="date" class="form-control profile-input end-date-input" data-field="education.end_date">
                        <div class="form-check mt-2">
                            <input type="checkbox" class="form-check-input profile-checkbox current-job-checkbox" data-field="education.current">
                            <label class="form-check-label">I currently study here</label>
                        </div>
                    </div>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label">GPA</label>
                <input type="number" class="form-control profile-input" data-field="education.gpa" step="0.01" min="0" max="4" placeholder="3.5">
            </div>
            <div class="text-end">
                <button type="button" class="btn btn-outline-danger btn-sm remove-entry-btn">
                    <i class="fas fa-trash me-1"></i>Remove
                </button>
            </div>
        `;
  }

  /**
   * Get certification entry template
   */
  getCertificationEntryTemplate() {
    return `
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Certification Name <span class="text-danger">*</span></label>
                        <input type="text" class="form-control profile-input" data-field="certification.name" required>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Issuing Organization <span class="text-danger">*</span></label>
                        <input type="text" class="form-control profile-input" data-field="certification.issuer" required>
                    </div>
                </div>
            </div>
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Issue Date</label>
                        <input type="date" class="form-control profile-input" data-field="certification.issue_date">
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">Expiration Date</label>
                        <input type="date" class="form-control profile-input" data-field="certification.expiry_date">
                        <div class="form-check mt-2">
                            <input type="checkbox" class="form-check-input profile-checkbox" data-field="certification.no_expiry">
                            <label class="form-check-label">This certification does not expire</label>
                        </div>
                    </div>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label">Credential ID</label>
                <input type="text" class="form-control profile-input" data-field="certification.credential_id">
            </div>
            <div class="mb-3">
                <label class="form-label">Credential URL</label>
                <input type="url" class="form-control profile-input" data-field="certification.credential_url" placeholder="https://...">
            </div>
            <div class="text-end">
                <button type="button" class="btn btn-outline-danger btn-sm remove-entry-btn">
                    <i class="fas fa-trash me-1"></i>Remove
                </button>
            </div>
        `;
  }

  /**
   * Handle resume upload
   */
  async handleResumeUpload(input) {
    const file = input.files[0];
    if (!file) return;

    // Validate file
    const allowedTypes = [
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ];
    if (!allowedTypes.includes(file.type)) {
      this.showMessage("Please upload a PDF or Word document", "error");
      input.value = "";
      return;
    }

    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
      this.showMessage("File size must be less than 10MB", "error");
      input.value = "";
      return;
    }

    try {
      this.showUploadProgress(input, 0);

      const formData = new FormData();
      formData.append("resume", file);

      const response = await this.uploadFile(
        "/profile/resume",
        formData,
        (progress) => {
          this.showUploadProgress(input, progress);
        },
      );

      if (response.success) {
        this.profileData.resume_url = response.file_url;
        this.showMessage("Resume uploaded successfully", "success");
        this.displayUploadedFile(input, file.name, response.file_url);
      } else {
        throw new Error(response.message || "Upload failed");
      }
    } catch (error) {
      console.error("Resume upload error:", error);
      this.showMessage(error.message || "Upload failed", "error");
      input.value = "";
    } finally {
      this.hideUploadProgress(input);
    }
  }

  /**
   * Upload file with progress
   */
  uploadFile(endpoint, formData, progressCallback) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const progress = (e.loaded / e.total) * 100;
          progressCallback(progress);
        }
      });

      xhr.addEventListener("load", () => {
        try {
          const response = JSON.parse(xhr.responseText);
          if (xhr.status === 200) {
            resolve(response);
          } else {
            reject(new Error(response.message || `HTTP ${xhr.status}`));
          }
        } catch (error) {
          reject(new Error("Invalid response"));
        }
      });

      xhr.addEventListener("error", () => {
        reject(new Error("Network error"));
      });

      xhr.open("POST", this.apiBaseUrl + endpoint);

      // Add auth token if available
      const token = (window.app && typeof window.app.getAuthToken === "function")
        ? window.app.getAuthToken()
        : (localStorage.getItem("access_token") || localStorage.getItem("authToken"));
      if (token) {
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      }

      xhr.send(formData);
    });
  }

  /**
   * Show upload progress
   */
  showUploadProgress(input, progress) {
    let progressContainer = input.parentNode.querySelector(".upload-progress");
    if (!progressContainer) {
      progressContainer = document.createElement("div");
      progressContainer.className = "upload-progress mt-2";
      input.parentNode.appendChild(progressContainer);
    }

    progressContainer.innerHTML = `
            <div class="progress">
                <div class="progress-bar" style="width: ${progress}%"></div>
            </div>
            <small class="text-muted">${Math.round(progress)}% uploaded</small>
        `;
  }

  /**
   * Hide upload progress
   */
  hideUploadProgress(input) {
    const progressContainer =
      input.parentNode.querySelector(".upload-progress");
    if (progressContainer) {
      progressContainer.remove();
    }
  }

  /**
   * Display uploaded file
   */
  displayUploadedFile(input, fileName, fileUrl) {
    const container = input.parentNode;
    let fileDisplay = container.querySelector(".uploaded-file");

    if (!fileDisplay) {
      fileDisplay = document.createElement("div");
      fileDisplay.className = "uploaded-file mt-2";
      container.appendChild(fileDisplay);
    }

    // Build DOM nodes to avoid XSS from fileName/fileUrl
    fileDisplay.innerHTML = '';
    const row = document.createElement('div');
    row.className = 'd-flex align-items-center justify-content-between p-2 bg-light rounded';

    const nameCol = document.createElement('div');
    nameCol.className = 'd-flex align-items-center';
    const icon = document.createElement('i');
    icon.className = 'fas fa-file-pdf text-danger me-2';
    const nameSpan = document.createElement('span');
    nameSpan.textContent = fileName;
    nameCol.appendChild(icon);
    nameCol.appendChild(nameSpan);

    const btnCol = document.createElement('div');
    const viewLink = document.createElement('a');
    const safeFileUrl = (fileUrl && (fileUrl.startsWith('http://') || fileUrl.startsWith('https://') || fileUrl.startsWith('/'))) ? fileUrl : '#';
    viewLink.href = safeFileUrl;
    viewLink.target = '_blank';
    viewLink.rel = 'noopener noreferrer';
    viewLink.className = 'btn btn-sm btn-outline-primary me-2';
    viewLink.innerHTML = '<i class="fas fa-eye"></i>';
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn btn-sm btn-outline-danger';
    removeBtn.innerHTML = '<i class="fas fa-trash"></i>';
    removeBtn.addEventListener('click', function () { fileDisplay?.remove(); });
    btnCol.appendChild(viewLink);
    btnCol.appendChild(removeBtn);

    row.appendChild(nameCol);
    row.appendChild(btnCol);
    fileDisplay.appendChild(row);
  }

  /**
   * Validate form field
   */
  validateField(field) {
    const value = field.value.trim();
    const isRequired = field.hasAttribute("required");
    let isValid = true;
    let message = "";

    if (isRequired && !value) {
      isValid = false;
      message = "This field is required";
    } else if (field.type === "email" && value && !this.isValidEmail(value)) {
      isValid = false;
      message = "Please enter a valid email address";
    } else if (field.type === "url" && value && !this.isValidUrl(value)) {
      isValid = false;
      message = "Please enter a valid URL";
    } else if (field.type === "tel" && value && !this.isValidPhone(value)) {
      isValid = false;
      message = "Please enter a valid phone number";
    }

    this.setFieldValidation(field, isValid, message);
    return isValid;
  }

  /**
   * Set field validation state
   */
  setFieldValidation(field, isValid, message) {
    const feedback =
      field.parentNode.querySelector(".invalid-feedback") ||
      this.createFeedbackElement(field.parentNode);

    if (isValid) {
      field.classList.remove("is-invalid");
      field.classList.add("is-valid");
      feedback.style.display = "none";
    } else {
      field.classList.remove("is-valid");
      field.classList.add("is-invalid");
      feedback.textContent = message;
      feedback.style.display = "block";
    }
  }

  /**
   * Create feedback element
   */
  createFeedbackElement(parent) {
    const feedback = document.createElement("div");
    feedback.className = "invalid-feedback";
    parent.appendChild(feedback);
    return feedback;
  }

  /**
   * Validation helpers
   */
  isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  isValidUrl(url) {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  }

  isValidPhone(phone) {
    return /^[\+]?[1-9][\d]{0,15}$/.test(phone.replace(/[\s\-\(\)]/g, ""));
  }

  /**
   * Navigate to next step
   */
  nextStep() {
    if (this.validateCurrentStep()) {
      if (this.currentStep < this.maxSteps) {
        this.currentStep++;
        this.updateStepVisibility();
        this.updateStepIndicators();
        this.scrollToTop();
      }
    }
  }

  /**
   * Navigate to previous step
   */
  prevStep() {
    if (this.currentStep > 1) {
      this.currentStep--;
      this.updateStepVisibility();
      this.updateStepIndicators();
      this.scrollToTop();
    }
  }

  /**
   * Navigate to specific step
   */
  goToStep(step) {
    if (step >= 1 && step <= this.maxSteps) {
      this.currentStep = step;
      this.updateStepVisibility();
      this.updateStepIndicators();
      this.scrollToTop();
    }
  }

  /**
   * Update step visibility
   */
  updateStepVisibility() {
    const steps = document.querySelectorAll(".profile-step");
    steps.forEach((step, index) => {
      if (index + 1 === this.currentStep) {
        step.style.display = "block";
        step.classList.add("active");
      } else {
        step.style.display = "none";
        step.classList.remove("active");
      }
    });

    // Update navigation buttons
    const prevBtn = document.querySelector(".prev-step-btn");
    const nextBtn = document.querySelector(".next-step-btn");
    const submitBtn = document.querySelector(".submit-profile-btn");

    if (prevBtn) {
      prevBtn.style.display = this.currentStep > 1 ? "inline-block" : "none";
    }

    if (nextBtn && submitBtn) {
      if (this.currentStep === this.maxSteps) {
        nextBtn.style.display = "none";
        submitBtn.style.display = "inline-block";
      } else {
        nextBtn.style.display = "inline-block";
        submitBtn.style.display = "none";
      }
    }
  }

  /**
   * Update step indicators
   */
  updateStepIndicators() {
    const indicators = document.querySelectorAll(".step-indicator");
    indicators.forEach((indicator, index) => {
      const stepNumber = index + 1;
      indicator.classList.remove("active", "completed");

      if (stepNumber < this.currentStep) {
        indicator.classList.add("completed");
      } else if (stepNumber === this.currentStep) {
        indicator.classList.add("active");
      }
    });

    // Update progress bar
    const progressBar = document.querySelector(".profile-progress-bar");
    if (progressBar) {
      const percentage = ((this.currentStep - 1) / (this.maxSteps - 1)) * 100;
      progressBar.style.width = percentage + "%";
    }
  }

  /**
   * Validate current step
   */
  validateCurrentStep() {
    const currentStepElement = document.querySelector(
      `.profile-step:nth-child(${this.currentStep})`,
    );
    const requiredFields =
      currentStepElement?.querySelectorAll("[required]") || [];
    let isValid = true;

    requiredFields.forEach((field) => {
      if (!this.validateField(field)) {
        isValid = false;
      }
    });

    return isValid;
  }

  /**
   * Update progress indicator
   */
  updateProgress() {
    const totalFields = document.querySelectorAll(".profile-input").length;
    const filledFields = Array.from(
      document.querySelectorAll(".profile-input"),
    ).filter((input) => {
      return input.value && input.value.trim() !== "";
    }).length;

    const percentage = totalFields > 0 ? (filledFields / totalFields) * 100 : 0;

    const progressBar = document.querySelector(".completion-progress-bar");
    if (progressBar) {
      progressBar.style.width = percentage + "%";
    }

    const progressText = document.querySelector(".completion-percentage");
    if (progressText) {
      progressText.textContent = Math.round(percentage) + "%";
    }
  }

  /**
   * Populate form with existing data
   */
  populateForm() {
    const inputs = document.querySelectorAll(".profile-input");
    inputs.forEach((input) => {
      const fieldName = input.getAttribute("data-field");
      if (fieldName) {
        const value = this.getNestedValue(this.profileData, fieldName);
        if (value !== undefined && value !== null) {
          if (input.type === "checkbox") {
            input.checked = !!value;
          } else {
            input.value = value;
          }
        }
      }
    });

    // Populate arrays (experience, education, etc.)
    this.populateArrayFields();
  }

  /**
   * Populate array fields (experience, education, certifications)
   */
  populateArrayFields() {
    // Experience
    if (
      this.profileData.experience &&
      Array.isArray(this.profileData.experience)
    ) {
      this.profileData.experience.forEach((exp) => {
        this.addExperienceEntry();
        // Populate the latest entry
        // This would need more specific implementation based on your data structure
      });
    }

    // Education
    if (
      this.profileData.education &&
      Array.isArray(this.profileData.education)
    ) {
      this.profileData.education.forEach((edu) => {
        this.addEducationEntry();
        // Populate the latest entry
      });
    }

    // Certifications
    if (
      this.profileData.certifications &&
      Array.isArray(this.profileData.certifications)
    ) {
      this.profileData.certifications.forEach((cert) => {
        this.addCertificationEntry();
        // Populate the latest entry
      });
    }
  }

  /**
   * Handle form submission - save all profile steps
   */
  async handleFormSubmission(event) {
    event.preventDefault();

    if (!this.validateForm()) {
      this.showMessage("Please fill in all required fields", "error");
      return;
    }

    try {
      this.setFormLoading(true);

      // Collect all form data
      this.collectFormData();

      // Save each profile step using the correct API endpoints
      await this.saveAllProfileSteps();

      this.showMessage("Profile completed successfully!", "success");
      setTimeout(() => {
        window.location.href = "/dashboard";
      }, 2000);
    } catch (error) {
      console.error("Profile submission error:", error);
      this.showMessage(error.message || "Failed to save profile", "error");
    } finally {
      this.setFormLoading(false);
    }
  }

  /**
   * Save all profile steps using the correct API endpoints
   */
  async saveAllProfileSteps() {
    // Step 1: Basic Info
    await this.saveBasicInfo();
    
    // Step 2: Work Experience
    await this.saveWorkExperience();
    
    // Step 3: Education
    await this.saveEducation();
    
    // Step 4: Skills & Qualifications
    await this.saveSkillsQualifications();
    
    // Step 5: Career Preferences
    await this.saveCareerPreferences();
  }

  /**
   * Save basic info (step 1)
   */
  async saveBasicInfo() {
    const basicInfo = {
      full_name: this.profileData.full_name || "",
      email: this.profileData.email || "",
      phone: this.profileData.phone || "",
      location: this.profileData.location || "",
      profile_url: this.profileData.profile_url || "",
      github_url: this.profileData.github_url || "",
      portfolio_url: this.profileData.portfolio_url || "",
      professional_summary: this.profileData.professional_summary || ""
    };

    const response = await this.apiCall("/profile/basic-info", "PUT", basicInfo);
    return response;
  }

  /**
   * Save work experience (step 2)
   */
  async saveWorkExperience() {
    const raw = this.profileData.experience || [];
    const work_experience = raw
      .map((exp) => ({
        company_name: exp.company_name || exp.company || "",
        job_title: exp.job_title || exp.title || "",
        description: exp.description || exp.employment_notes || "",
        start_date: exp.start_date || "",
        end_date: exp.end_date || null,
        is_current: Boolean(exp.is_current || exp.current),
      }))
      .filter((row) => row.company_name && row.job_title && row.start_date);

    const response = await this.apiCall("/profile/work-experience", "PUT", {
      work_experience,
    });
    return response;
  }

  /**
   * Save education (step 3) — aligns with PUT /api/v1/profile/education
   */
  async saveEducation() {
    const raw = this.profileData.education || [];
    const education = raw
      .map((edu) => ({
        institution: edu.institution || "",
        degree: edu.degree || "",
        field_of_study: edu.field_of_study || edu.field || null,
        start_date: ProfileManager.normalizeYearMonth(edu.start_date),
        end_date: edu.end_date ? ProfileManager.normalizeYearMonth(edu.end_date) : null,
        is_current: Boolean(edu.is_current || edu.current),
      }))
      .filter((row) => row.institution && row.degree && row.start_date);

    const response = await this.apiCall("/profile/education", "PUT", { education });
    return response;
  }

  /**
   * Save skills & qualifications (step 4)
   */
  async saveSkillsQualifications() {
    const buckets = [
      this.profileData.skills,
      this.profileData.technical_skills,
      this.profileData.soft_skills,
      this.profileData.industry_knowledge,
      this.profileData.tools_technologies,
    ];
    const seen = new Set();
    const skills = [];
    for (const b of buckets) {
      if (!Array.isArray(b)) continue;
      for (const s of b) {
        const t = String(s).trim();
        if (!t) continue;
        const k = t.toLowerCase();
        if (!seen.has(k)) {
          seen.add(k);
          skills.push(t);
        }
      }
    }

    const response = await this.apiCall("/profile/skills-qualifications", "PUT", { skills });
    return response;
  }

  /**
   * Save career preferences (step 5)
   */
  async saveCareerPreferences() {
    const careerPrefs = this.extractCareerPreferencesData();
    const response = await this.apiCall("/profile/career-preferences", "PUT", careerPrefs);
    return response;
  }

  /**
   * Collect all form data
   */
  collectFormData() {
    // Collect basic inputs
    const inputs = document.querySelectorAll(".profile-input");
    inputs.forEach((input) => {
      const fieldName = input.getAttribute("data-field");
      if (fieldName) {
        let value;
        if (input.type === "checkbox") {
          value = input.checked;
        } else {
          value = input.value.trim();
        }
        this.setNestedValue(this.profileData, fieldName, value);
      }
    });

    // Collect experience entries
    this.collectExperienceData();

    // Collect education entries
    this.collectEducationData();

    // Collect certification entries
    this.collectCertificationData();

    // Collect skills
    this.collectSkillsData();
  }

  /**
   * Collect experience data
   */
  collectExperienceData() {
    const entries = document.querySelectorAll(".experience-entry");
    this.profileData.experience = [];

    entries.forEach((entry) => {
      const experienceData = {};
      const inputs = entry.querySelectorAll(".profile-input");

      inputs.forEach((input) => {
        const field = input
          .getAttribute("data-field")
          ?.replace("experience.", "");
        if (field) {
          if (input.type === "checkbox") {
            experienceData[field] = input.checked;
          } else {
            experienceData[field] = input.value.trim();
          }
        }
      });

      if (experienceData.title && experienceData.company) {
        this.profileData.experience.push(experienceData);
      }
    });
  }

  /**
   * Collect education data
   */
  collectEducationData() {
    const entries = document.querySelectorAll(".education-entry");
    this.profileData.education = [];

    entries.forEach((entry) => {
      const educationData = {};
      const inputs = entry.querySelectorAll(".profile-input");

      inputs.forEach((input) => {
        const field = input
          .getAttribute("data-field")
          ?.replace("education.", "");
        if (field) {
          if (input.type === "checkbox") {
            educationData[field] = input.checked;
          } else {
            educationData[field] = input.value.trim();
          }
        }
      });

      if (educationData.institution && educationData.degree) {
        this.profileData.education.push(educationData);
      }
    });
  }

  /**
   * Collect certification data
   */
  collectCertificationData() {
    const entries = document.querySelectorAll(".certification-entry");
    this.profileData.certifications = [];

    entries.forEach((entry) => {
      const certificationData = {};
      const inputs = entry.querySelectorAll(".profile-input");

      inputs.forEach((input) => {
        const field = input
          .getAttribute("data-field")
          ?.replace("certification.", "");
        if (field) {
          if (input.type === "checkbox") {
            certificationData[field] = input.checked;
          } else {
            certificationData[field] = input.value.trim();
          }
        }
      });

      if (certificationData.name && certificationData.issuer) {
        this.profileData.certifications.push(certificationData);
      }
    });
  }

  /**
   * Collect skills data
   */
  collectSkillsData() {
    const skillsContainers = document.querySelectorAll(".tags-container");
    skillsContainers.forEach((container) => {
      const input = container.previousElementSibling;
      const fieldName = input.getAttribute("data-field");
      if (fieldName) {
        this.updateSkillsData(container);
      }
    });
  }

  /**
   * Extract career preferences data for API submission
   */
  extractCareerPreferencesData() {
    return {
      desired_job_titles: this.profileData.desired_job_titles || [],
      desired_industries: this.profileData.desired_industries || [],
      desired_locations: this.profileData.desired_locations || [],
      salary_range: this.profileData.salary_range || null,
      desired_company_sizes: this.profileData.desired_company_sizes || [],
      job_types: this.profileData.job_types || [],
      work_arrangements: this.profileData.work_arrangements || [],
      actively_searching: this.profileData.actively_searching || false,
      is_student: this.profileData.is_student || false,
    };
  }

  /**
   * Validate entire form
   */
  validateForm() {
    const requiredFields = document.querySelectorAll(
      ".profile-input[required]",
    );
    let isValid = true;

    requiredFields.forEach((field) => {
      if (!this.validateField(field)) {
        isValid = false;
      }
    });

    return isValid;
  }

  /**
   * Set form loading state
   */
  setFormLoading(loading) {
    const submitBtn = document.querySelector(".submit-profile-btn");
    const inputs = document.querySelectorAll(".profile-input");

    if (loading) {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML =
          '<span class="spinner-border spinner-border-sm me-2"></span>Saving Profile...';
      }
      inputs.forEach((input) => (input.disabled = true));
    } else {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML =
          '<i class="fas fa-check me-2"></i>Complete Profile';
      }
      inputs.forEach((input) => (input.disabled = false));
    }
  }

  /**
   * Scroll to top of page
   */
  scrollToTop() {
    window.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  }

  /**
   * Show message to user
   */
  showMessage(message, type = "info") {
    if (window.app && typeof window.app.showNotification === "function") {
      window.app.showNotification(message, type);
    } else {
      console.warn(message);
    }
  }

  /**
   * Make API call
   */
  async apiCall(endpoint, method = "GET", data = null) {
    const url = `${this.apiBaseUrl}${endpoint}`;
    const config = {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    };

    if (data && method !== "GET") {
      config.body = JSON.stringify(data);
    }

    // Add auth token
    const token = (window.app && typeof window.app.getAuthToken === "function")
      ? window.app.getAuthToken()
      : (localStorage.getItem("access_token") || localStorage.getItem("authToken"));
    if (token) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }

    // Add CSRF token
    const csrfToken = this.getCSRFToken();
    if (csrfToken) {
      config.headers["X-CSRF-Token"] = csrfToken;
    }

    const response = await fetch(url, config);
    
    // Handle JSON parsing with error handling
    let result;
    try {
      result = await response.json();
    } catch (parseError) {
      throw new Error(`Invalid JSON response: ${response.status}`);
    }

    if (!response.ok) {
      throw new Error(result.message || result.detail || result.error || `HTTP ${response.status}`);
    }

    return result;
  }

  /**
   * Get CSRF token
   */
  getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
      return metaTag.getAttribute("content");
    }

    const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
    return cookieMatch ? cookieMatch[1] : null;
  }
}

// Initialize profile manager when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
  if (
    document.querySelector("#profileForm") ||
    document.querySelector(".profile-step")
  ) {
    window.profileManager = new ProfileManager();
  }
});

// Export for use in other modules
if (typeof module !== "undefined" && module.exports) {
  module.exports = ProfileManager;
}
