/**
 * @fileoverview ApplyPilot - Dashboard JavaScript
 * Handles workflow management, AI processing, and dashboard interactions.
 * 
 * @description Manages the dashboard view including:
 * - Workflow creation and monitoring
 * - Real-time WebSocket updates
 * - Status polling fallback
 * - Document downloads
 */

/// <reference path="./types.js" />

/** @param {unknown} value */
function sanitizeLogValue(value) {
  return window.sanitizeLogValue(value);
}

/** @param {string|null|undefined} str */
function escapeHtml(str) {
  return window.escapeHtml(str);
}

/**
 * Dashboard manager class for workflow and application management.
 * Handles real-time updates via WebSocket with polling fallback.
 * 
 * @class
 */
class DashboardManager {
  /**
   * Create a new DashboardManager instance.
   */
  constructor() {
    /** @type {string} Base URL for API calls */
    this.apiBaseUrl = (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';
    
    /** @type {import('./types.js').WorkflowSession[]} List of workflow sessions */
    this.workflows = [];
    
    /** @type {import('./types.js').WorkflowSession|null} Currently selected workflow */
    this.currentWorkflow = null;
    
    /** @type {Set<string>} Set of session IDs currently being processed */
    this.processingQueue = new Set();
    
    /** @type {number|null} Polling interval ID */
    this.pollingInterval = null;
    
    /** @type {number} Status polling interval in milliseconds */
    this.statusUpdateInterval = 5000;
    
    /** @type {WebSocket|null} WebSocket connection */
    this.ws = null;
    
    /** @type {string|null} Currently subscribed session ID */
    this.wsSessionId = null;
    
    /** @type {number} WebSocket reconnection attempts */
    this.wsReconnectAttempts = 0;
    
    /** @type {number|null} WebSocket ping interval ID */
    this.wsPingInterval = null;
    
    /** @type {any} Status chart instance */
    this.statusChart = null;
    
    /** @type {any} Activity chart instance */
    this.activityChart = null;

    this.init();
  }

  /**
   * Initialize dashboard manager
   */
  init() {
    this.setupEventListeners();
    this.loadDashboardData();
    this.initializeComponents();
    this.startStatusPolling();
  }

  /**
   * Setup event listeners
   */
  setupEventListeners() {
    // New application button
    document.addEventListener("click", (/** @type {any} */ e) => {
      if (e.target.matches(".new-application-btn, .new-application-btn *")) {
        e.preventDefault();
        this.showNewApplicationModal();
      }
    });

    // Job input form submission
    const jobInputForm = document.querySelector("#jobInputForm");
    if (jobInputForm) {
      jobInputForm.addEventListener("submit", (/** @type {any} */ e) =>
        this.handleJobInputSubmission(e),
      );
    }

    // Workflow actions
    document.addEventListener("click", (/** @type {any} */ e) => {
      if (e.target.matches(".view-application-btn")) {
        const sessionId = e.target.getAttribute("data-session-id");
        this.viewWorkflowResults(sessionId);
      }
      if (e.target.matches(".edit-application-btn")) {
        const sessionId = e.target.getAttribute("data-session-id");
        this.editWorkflow(sessionId);
      }
      if (e.target.matches(".delete-application-btn")) {
        const sessionId = e.target.getAttribute("data-session-id");
        this.deleteWorkflow(sessionId);
      }
      if (e.target.matches(".download-documents-btn")) {
        const sessionId = e.target.getAttribute("data-session-id");
        this.downloadDocuments(sessionId);
      }
      if (e.target.matches(".interview-prep-btn")) {
        const sessionId = e.target.getAttribute("data-session-id");
        this.openInterviewPrep(sessionId);
      }
    });

    // Job input method selection
    document.addEventListener("change", (/** @type {any} */ e) => {
      if (e.target.matches('input[name="job_input_method"]')) {
        this.handleJobInputMethodChange(e.target.value);
      }
    });

    // File upload handling
    document.addEventListener("change", (/** @type {any} */ e) => {
      if (e.target.matches(".job-file-upload")) {
        this.handleJobFileUpload(e.target);
      }
    });

    // URL validation
    document.addEventListener("input", (/** @type {any} */ e) => {
      if (e.target.matches("#jobUrl")) {
        this.validateJobUrl(e.target);
      }
    });

    // Search and filter — debounced to avoid filtering on every keystroke
    let searchDebounceTimer = 0;
    const searchInput = document.querySelector("#applicationSearch");
    if (searchInput) {
      searchInput.addEventListener("input", (/** @type {any} */ e) => {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = window.setTimeout(() => { this.filterWorkflows(e.target.value); }, 300);
      });
    }

    const statusFilter = document.querySelector("#statusFilter");
    if (statusFilter) {
      statusFilter.addEventListener("change", (/** @type {any} */ e) => {
        this.filterByStatus(e.target.value);
      });
    }

    // Pagination
    document.addEventListener("click", (/** @type {any} */ e) => {
      if (e.target.matches(".pagination-btn")) {
        const page = e.target.getAttribute("data-page");
        this.loadWorkflowsPage(page);
      }
    });

    // Document preview
    document.addEventListener("click", (/** @type {any} */ e) => {
      if (e.target.matches(".preview-document-btn")) {
        const docType = e.target.getAttribute("data-doc-type");
        const sessionId = e.target.getAttribute("data-session-id");
        this.previewDocument(sessionId, docType);
      }
    });

    // Copy to clipboard
    document.addEventListener("click", (/** @type {any} */ e) => {
      if (e.target.matches(".copy-content-btn")) {
        const content =
          e.target.getAttribute("data-content") ||
          e.target
            .closest(".document-container")
            ?.querySelector(".document-content")?.textContent;
        this.copyToClipboard(content);
      }
    });
  }

  /**
   * Load dashboard data using correct workflow API
   */
  async loadDashboardData() {
    try {
      // Load workflow list using the correct endpoint
      // Use /workflow/list as the endpoint for retrieving all job applications
      const response = await this.apiCall("/workflow/list", "GET");
      
      if (response.sessions) {
        this.workflows = response.sessions || [];
        this.renderWorkflowsList();
        this.updateDashboardStats();
        
        // Load recent applications for dashboard homepage
        if (document.querySelector('#recentApplications')) {
          this.renderRecentApplications(this.workflows.slice(0, 5)); // Show top 5 most recent
        }
      }
    } catch (error) {
      console.error("Error loading dashboard data:", sanitizeLogValue(error instanceof Error ? error.message : String(error)));
      this.showMessage("Failed to load dashboard data", "error");
    }
  }

  /**
   * Initialize components
   */
  initializeComponents() {
    this.initializeCharts();
    this.initializeTooltips();
    this.setupRealtimeUpdates();
  }

  /**
   * Initialize charts
   */
  initializeCharts() {
    // Application status chart
    const statusChartCanvas = document.querySelector("#statusChart");
    const _wChart = /** @type {any} */ (window);
    if (statusChartCanvas && typeof _wChart.Chart !== "undefined") {
      this.createStatusChart(statusChartCanvas);
    }

    // Weekly activity chart
    const activityChartCanvas = document.querySelector("#activityChart");
    if (activityChartCanvas && typeof _wChart.Chart !== "undefined") {
      this.createActivityChart(activityChartCanvas);
    }
  }

  /**
   * Create status chart
   * @param {any} canvas
   */
  createStatusChart(canvas) {
    const ctx = canvas.getContext("2d");
    const ChartCtor = /** @type {any} */ ((/** @type {any} */ (window)).Chart);
    this.statusChart = new ChartCtor(ctx, {
      type: "doughnut",
      data: {
        labels: ["Draft", "Processing", "Completed", "Applied"],
        datasets: [
          {
            data: [0, 0, 0, 0],
            backgroundColor: ["#6c757d", "#ffc107", "#28a745", "#667eea"],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
          },
        },
      },
    });
  }

  /**
   * Create activity chart
   * @param {any} canvas
   */
  createActivityChart(canvas) {
    const ctx = canvas.getContext("2d");
    const ChartCtor2 = /** @type {any} */ ((/** @type {any} */ (window)).Chart);
    this.activityChart = new ChartCtor2(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Applications",
            data: [],
            borderColor: "#667eea",
            backgroundColor: "rgba(102, 126, 234, 0.1)",
            tension: 0.4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            beginAtZero: true,
          },
        },
      },
    });
  }

  /**
   * Initialize tooltips
   */
  initializeTooltips() {
    // @ts-ignore
    const bs = /** @type {any} */ (typeof bootstrap !== "undefined" ? bootstrap : null);
    if (bs) {
      const tooltipTriggerList = /** @type {any[]} */ ([].slice.call(
        document.querySelectorAll('[data-bs-toggle="tooltip"]'),
      ));
      tooltipTriggerList.map((el) => new bs.Tooltip(el));
    }
  }

  /**
   * Setup realtime updates
   */
  setupRealtimeUpdates() {
    // WebSocket connection for real-time updates
    if (typeof WebSocket !== "undefined") {
      this.connectWebSocket();
    }
  }

  /**
   * Connect WebSocket for real-time updates
   * @param {string|null} [sessionId] - Optional workflow session ID to subscribe to specific updates
   */
  connectWebSocket(sessionId = null) {
    const token = localStorage.getItem("authToken") || localStorage.getItem("access_token");
    if (!token) {
      console.warn("No auth token available for WebSocket connection");
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const endpoint = sessionId 
      ? `/api/ws/workflow/${sessionId}?token=${encodeURIComponent(token)}`
      : `/api/ws/user?token=${encodeURIComponent(token)}`;
    const wsUrl = `${protocol}//${window.location.host}${endpoint}`;

    try {
      // Close existing connection if any
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.close();
      }

      this.ws = new WebSocket(wsUrl);
      this.wsSessionId = sessionId;

      this.ws.onopen = () => {
        console.log(
          "WebSocket connected" +
            (sessionId ? ` for session ${sanitizeLogValue(sessionId)}` : " for all user updates"),
        );
        this.wsReconnectAttempts = 0;
        this.wsReconnecting = false;

        // Start ping interval to keep connection alive
        this.startWsPing();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleWebSocketMessage(data);
        } catch (e) {
          console.error("Failed to parse WebSocket message:", sanitizeLogValue(e instanceof Error ? e.message : String(e)));
        }
      };

      this.ws.onclose = (event) => {
        console.log(
          "WebSocket disconnected:",
          sanitizeLogValue(event.code),
          sanitizeLogValue(event.reason),
        );
        this.stopWsPing();

        // Guard: only schedule one reconnect timer at a time.
        // Without this, rapid close events can queue multiple timers that all
        // fire and each open a separate WebSocket connection.
        if (this.wsReconnecting) return;
        this.wsReconnecting = true;

        // Reconnect with exponential backoff (max 30 seconds)
        this.wsReconnectAttempts = (this.wsReconnectAttempts || 0) + 1;
        const delay = Math.min(1000 * Math.pow(2, this.wsReconnectAttempts), 30000);
        console.log(`Reconnecting WebSocket in ${sanitizeLogValue(delay)}ms...`);
        setTimeout(() => {
          this.wsReconnecting = false;
          this.connectWebSocket(this.wsSessionId);
        }, delay);
      };

      this.ws.onerror = (error) => {
        console.error("WebSocket error:", sanitizeLogValue(String(error)));
      };
    } catch (error) {
      console.error(
        "Failed to connect WebSocket:",
        sanitizeLogValue(error instanceof Error ? error.message : String(error)),
      );
    }
  }

  /**
   * Start WebSocket ping interval
   */
  startWsPing() {
    this.stopWsPing();
    this.wsPingInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000); // Ping every 30 seconds
  }

  /**
   * Stop WebSocket ping interval
   */
  stopWsPing() {
    if (this.wsPingInterval) {
      clearInterval(this.wsPingInterval);
      this.wsPingInterval = null;
    }
  }

  /**
   * Subscribe to a specific workflow's updates
   */
  /** @param {string} sessionId */
  subscribeToWorkflow(sessionId) {
    this.connectWebSocket(sessionId);
  }

  /** @param {any} data */
  handleWebSocketMessage(data) {
    console.debug("WebSocket message type:", sanitizeLogValue(data.type));
    
    switch (data.type) {
      case "connected":
        // Connection confirmed
        console.log("WebSocket subscription confirmed:", sanitizeLogValue(data.message));
        break;
        
      case "pong":
        // Ping response, connection is alive
        break;
        
      case "agent_update":
        // Agent status changed (running, completed, failed)
        this.handleAgentUpdate(data.session_id, data.data);
        break;
        
      case "phase_change":
        // Workflow phase changed
        this.handlePhaseChange(data.session_id, data.data);
        break;
        
      case "workflow_complete":
        // Workflow finished successfully
        this.handleWorkflowComplete(data.session_id, data.data);
        break;
        
      case "workflow_error":
        // Workflow failed
        this.handleWorkflowError(data.session_id, data.data);
        break;
        
      case "gate_decision":
        // Profile matching gate triggered - needs user confirmation
        this.handleGateDecision(data.session_id, data.data);
        break;
        
      // Legacy event types for backwards compatibility
      case "application_status_update":
        (/** @type {any} */ (this)).updateApplicationStatus(data.application_id, data.status, data.progress);
        break;
      case "document_generated":
        this.handleDocumentGenerated(data.application_id, data.document_type);
        break;
      case "processing_error":
        this.handleProcessingError(data.application_id, data.error);
        break;
        
      default:
        console.debug("Unknown WebSocket message type:", sanitizeLogValue(data.type));
    }
  }

  /**
   * Handle agent status update
   * @param {string} sessionId
   * @param {any} data
   */
  handleAgentUpdate(sessionId, data) {
    const { agent, status, message } = data;
    
    // Update UI to show agent progress
    /** @type {Record<string,{running:number,completed:number}>} */
    const progressMap = {
      "job_analyzer": { running: 10, completed: 20 },
      "profile_matching": { running: 25, completed: 35 },
      "company_research": { running: 45, completed: 60 },
      "resume_advisor": { running: 70, completed: 85 },
      "cover_letter_writer": { running: 80, completed: 95 },
    };
    
    const agentProgress = progressMap[agent] || { running: 50, completed: 50 };
    const progress = status === "completed" ? agentProgress.completed : 
                     status === "running" ? agentProgress.running : 0;
    
    this.updateWorkflowStatus(sessionId, "running", progress);
    
    // Show notification for completed agents
    if (status === "completed") {
      this.showMessage(`${this.formatAgentName(agent)} completed`, "success");
    } else if (status === "failed") {
      this.showMessage(`${this.formatAgentName(agent)} failed: ${message}`, "error");
    }
  }

  /**
   * @param {string} sessionId
   * @param {any} data
   */
  handlePhaseChange(sessionId, data) {
    const { progress } = data;
    this.updateWorkflowStatus(sessionId, "running", progress);
  }

  /**
   * @param {string} sessionId
   * @param {any} data
   */
  handleWorkflowComplete(sessionId, data) {
    this.processingQueue.delete(sessionId);
    this.updateWorkflowStatus(sessionId, "completed", 100);
    
    const matchScore = data.match_score ? `${Math.round(data.match_score * 100)}%` : "";
    this.showMessage(
      `Workflow completed! ${matchScore ? `Match score: ${matchScore}` : ""}`,
      "success"
    );
    
    // Track workflow completion (if Analytics is loaded)
    // @ts-ignore
    if (window.Analytics) {
      // @ts-ignore
      window.Analytics.trackWorkflowCompleted({
        sessionId: sessionId,
        matchScore: data.match_score || null,
        agentsCompleted: data.agents_completed || 5,
      });
    }
    
    // Refresh the dashboard to show updated results
    this.loadDashboardData();
  }

  /**
   * @param {string} sessionId
   * @param {any} data
   */
  handleWorkflowError(sessionId, data) {
    this.processingQueue.delete(sessionId);
    this.updateWorkflowStatus(sessionId, "failed", 0);
    this.showMessage(`Workflow failed: ${data.error}`, "error");
    
    // Track workflow failure (if Analytics is loaded)
    // @ts-ignore
    if (window.Analytics) {
      // @ts-ignore
      window.Analytics.trackWorkflowFailed(data.error, data.failed_agent || "unknown");
    }
  }

  /**
   * @param {string} sessionId
   * @param {any} data
   */
  handleGateDecision(sessionId, data) {
    const { match_score, recommendation } = data;
    const scorePercent = Math.round(match_score * 100);
    
    // Show modal asking user if they want to continue
    this.showGateDecisionModal(sessionId, scorePercent, recommendation);
  }

  /**
   * @param {string} sessionId
   * @param {number} matchScore
   * @param {string} recommendation
   */
  showGateDecisionModal(sessionId, matchScore, recommendation) {
    const modal = document.createElement("div");
    modal.className = "modal fade";
    modal.id = "gateDecisionModal";
    modal.innerHTML = `
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header bg-warning text-dark">
            <h5 class="modal-title">
              <i class="fas fa-exclamation-triangle me-2"></i>Low Match Score
            </h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <p>The AI analysis indicates a low match for this position:</p>
            <div class="alert alert-warning">
              <strong>Match Score:</strong> <span class="gate-score"></span>%<br>
              <strong>Recommendation:</strong> <span class="gate-recommendation"></span>
            </div>
            <p>Do you want to continue generating application materials anyway?</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" data-action="cancel-workflow">
              <i class="fas fa-times me-1"></i>Stop Workflow
            </button>
            <button type="button" class="btn btn-primary" data-bs-dismiss="modal" data-action="continue-workflow">
              <i class="fas fa-arrow-right me-1"></i>Continue Anyway
            </button>
          </div>
        </div>
      </div>
    `;

    const scoreEl = modal.querySelector('.gate-score');
    const recEl = modal.querySelector('.gate-recommendation');
    if (scoreEl) scoreEl.textContent = String(matchScore);
    if (recEl) recEl.textContent = recommendation;

    const cancelBtn = modal.querySelector('[data-action="cancel-workflow"]');
    const continueBtn = modal.querySelector('[data-action="continue-workflow"]');
    if (cancelBtn) cancelBtn.addEventListener('click', () => window.dashboardManager.cancelWorkflow(sessionId));
    if (continueBtn) continueBtn.addEventListener('click', () => window.dashboardManager.continueWorkflow(sessionId));

    document.body.appendChild(modal);
    
    // @ts-ignore
    const bsGate = /** @type {any} */ (typeof bootstrap !== "undefined" ? bootstrap : null);
    if (bsGate) {
      const bsModal = new bsGate.Modal(modal);
      bsModal.show();
      modal.addEventListener("hidden.bs.modal", () => modal.remove());
    }
  }

  /** @param {string} sessionId */
  async continueWorkflow(sessionId) {
    try {
      await this.apiCall(`/workflow/sessions/${sessionId}/continue`, "POST");
      this.showMessage("Continuing workflow...", "info");
      this.processingQueue.add(sessionId);
    } catch (error) {
      const err = /** @type {Error} */ (error);
      this.showMessage(`Failed to continue workflow: ${err.message}`, "error");
    }
  }

  /** @param {string} sessionId */
  async cancelWorkflow(sessionId) {
    try {
      await this.apiCall(`/workflow/sessions/${sessionId}/cancel`, "POST");
      this.showMessage("Workflow cancelled", "info");
      this.processingQueue.delete(sessionId);
      this.loadDashboardData();
    } catch (error) {
      const err = /** @type {Error} */ (error);
      this.showMessage(`Failed to cancel workflow: ${err.message}`, "error");
    }
  }

  /**
   * Format agent name for display
   * @param {string} agentKey
   */
  formatAgentName(agentKey) {
    /** @type {Record<string,string>} */
    const names = {
      "job_analyzer": "Job Analysis",
      "profile_matching": "Profile Matching",
      "company_research": "Company Research",
      "resume_advisor": "Resume Advisor",
      "cover_letter_writer": "Cover Letter Writer",
    };
    return names[agentKey] || agentKey;
  }

  /**
   * Start status polling for applications
   */
  startStatusPolling() {
    this.pollingInterval = setInterval(async () => {
      if (this.processingQueue.size > 0) {
        await this.checkProcessingStatus();
      }
    }, this.statusUpdateInterval);
  }

  /**
   * Check workflow processing status
   */
  async checkProcessingStatus() {
    try {
      const sessionIds = Array.from(this.processingQueue);
      
      // Check each workflow individually
      for (const sessionId of sessionIds) {
        try {
          const status = await this.getWorkflowStatus(sessionId);
          this.updateWorkflowStatus(sessionId, status.workflow_status, status.progress_percentage);
          
          if (status.workflow_status === "completed" || status.workflow_status === "failed") {
            this.processingQueue.delete(sessionId);
          }
        } catch (error) {
          // Don't remove from queue on temporary errors
        }
      }
    } catch (error) {
      this.showMessage("Error checking workflow status", "error");
    }
  }

  /**
   * Show new application modal
   */
  showNewApplicationModal() {
    const modal = document.querySelector("#newApplicationModal");
    if (modal) {
      // @ts-ignore
      const bsModal2 = /** @type {any} */ (typeof bootstrap !== "undefined" ? bootstrap : null);
      if (bsModal2) {
        const inst = new bsModal2.Modal(modal);
        inst.show();
      } else {
        /** @type {HTMLElement} */ (modal).style.display = "block";
      }
    } else {
      // Fallback: navigate to new application page
      window.location.href = "/dashboard/new-application";
    }
  }

  /** @param {string} method */
  handleJobInputMethodChange(method) {
    const urlInput = document.querySelector("#jobUrlInput");
    const manualInput = document.querySelector("#jobManualInput");
    const fileInput = document.querySelector("#jobFileInput");

    // Hide all inputs
    [urlInput, manualInput, fileInput].forEach((input) => {
      if (input) /** @type {HTMLElement} */ (input).style.display = "none";
    });

    // Show selected input
    switch (method) {
      case "url":
        if (urlInput) /** @type {HTMLElement} */ (urlInput).style.display = "block";
        break;
      case "manual":
        if (manualInput) /** @type {HTMLElement} */ (manualInput).style.display = "block";
        break;
      case "file":
        if (fileInput) /** @type {HTMLElement} */ (fileInput).style.display = "block";
        break;
    }
  }

  /**
   * Handle job input form submission
   * @param {any} event
   */
  async handleJobInputSubmission(event) {
    event.preventDefault();
    const form = /** @type {HTMLFormElement} */ (event.target);
    const formData = new FormData(form);

    const method = formData.get("job_input_method");
    /** @type {Record<string,any>} */
    let jobData = { method };

    try {
      this.setFormLoading(form, true);

      switch (method) {
        case "url":
          jobData.url = formData.get("job_url");
          if (!this.isValidUrl(jobData.url)) {
            throw new Error("Please enter a valid job posting URL");
          }
          break;
        case "manual":
          jobData.title = formData.get("job_title");
          jobData.company = formData.get("company_name");
          jobData.description = formData.get("job_description");
          if (!jobData.title || !jobData.company || !jobData.description) {
            throw new Error("Please fill in all required fields");
          }
          break;
        case "file": {
          const file = /** @type {File|null} */ (formData.get("job_file"));
          if (!file || /** @type {File} */ (file).size === 0) {
            throw new Error("Please select a job posting file");
          }
          jobData['file'] = file;
          break;
        }
        default:
          throw new Error("Please select a job input method");
      }

      const response = await this.createWorkflow(jobData);

      if (response.session_id) {
        this.showMessage("Workflow started successfully! Processing will begin automatically.", "success");

        // Close modal if it exists
        const modal = document.querySelector("#newApplicationModal");
        // @ts-ignore
        const bsInst = /** @type {any} */ (typeof bootstrap !== "undefined" ? bootstrap : null);
        if (modal && bsInst) {
          const bsModal = bsInst.Modal.getInstance(modal);
          if (bsModal) bsModal.hide();
        }

        // Add to processing queue for status monitoring
        this.processingQueue.add(response.session_id);

        // Subscribe to this workflow's WebSocket updates for real-time progress
        this.subscribeToWorkflow(response.session_id);

        // Refresh workflows list
        await this.loadDashboardData();
      } else {
        throw new Error(response.message || "Failed to start workflow");
      }
    } catch (error) {
      const err = /** @type {Error & { errorCode?: string }} */ (error);
      const isDup = err.errorCode === "RES_3002";
      this.showMessage(
        err.message || "Failed to create application",
        isDup ? "warning" : "error",
      );
    } finally {
      this.setFormLoading(form, false);
    }
  }

  /** @param {Record<string,any>} jobData */
  async createWorkflow(jobData) {
    const endpoint = "/workflow/start";
    const method = "POST";

    // Always use FormData to match backend expectations
    const formData = new FormData();
    
    // Handle different input methods
    // Note: job_title and company_name will be extracted by the AI from the job content
    if (jobData.method === "url" && jobData.url) {
      formData.append("job_url", jobData.url);
    } else if (jobData.method === "manual" && jobData.description) {
      // Prepend the job title and company name to help with extraction if provided
      let jobText = jobData.description;
      if (jobData.title || jobData.company) {
        jobText = `Job Title: ${jobData.title || 'Not specified'}\nCompany: ${jobData.company || 'Not specified'}\n\n${jobData.description}`;
      }
      formData.append("job_text", jobText);
    } else if (jobData.method === "file" && jobData.file) {
      formData.append("job_file", jobData.file);
    }

    return await this.apiCall(endpoint, method, formData, {
      headers: {}, // Remove Content-Type to let browser set it for FormData
    });
  }

  /**
   * Get workflow status from the API.
   * 
   * @param {string} sessionId - Workflow session ID
   * @returns {Promise<import('./types.js').WorkflowStatusResponse>} Status response
   * @throws {Error} If the request fails
   */
  async getWorkflowStatus(sessionId) {
    try {
      const response = await this.apiCall(`/workflow/sessions/${sessionId}/status`, "GET");
      return response;
    } catch (error) {
      console.error(
        'Error getting workflow status:',
        sanitizeLogValue(error instanceof Error ? error.message : String(error)),
      );
      throw error;
    }
  }

  /**
   * Update workflow status display in the UI.
   * 
   * @param {string} sessionId - Workflow session ID
   * @param {import('./types.js').WorkflowStatus | string} status - New status
   * @param {number} [progress=0] - Progress percentage (0-100)
   * @returns {void}
   */
  updateWorkflowStatus(sessionId, status, progress = 0) {
    const workflowCard = document.querySelector(
      `[data-session-id="${sessionId}"]`,
    );
    if (!workflowCard) return;
    
    console.debug(
      `Updating workflow status: ${sanitizeLogValue(sessionId)} to ${sanitizeLogValue(status)} with progress ${sanitizeLogValue(progress)}%`,
    );
    
    // Normalize status for UI consistency (backend may send varied formats)
    const normalizedStatus = typeof status === 'string' ? status.toLowerCase() : status;
    console.debug(`Normalized status: ${sanitizeLogValue(normalizedStatus)}`);
    
    // Map backend workflow statuses to UI status values
    let uiStatus = normalizedStatus;
    if (normalizedStatus === "in_progress" || normalizedStatus === "processing") {
      uiStatus = "running";
    } else if (normalizedStatus === "initialized") {
      uiStatus = "draft";
    } else if (normalizedStatus === "completed") {
      uiStatus = "completed";
      // When workflow completes, force progress to 100%
      progress = 100;
    }
    
    console.debug(
      `Mapped to UI status: ${sanitizeLogValue(uiStatus)} with ${sanitizeLogValue(progress)}% progress`,
    );

    // Update status badge
    const statusBadge = workflowCard.querySelector(".status-badge");
    if (statusBadge) {
      statusBadge.className = `status-badge status-${uiStatus}`;
      statusBadge.textContent = this.formatStatus(uiStatus);
      console.debug(`Updated badge to: ${sanitizeLogValue(this.formatStatus(uiStatus))}`);
    }

    // Update progress bar
    const progressBar = /** @type {HTMLElement|null} */ (workflowCard.querySelector(".progress-bar"));
    if (progressBar) {
      progressBar.style.width = progress + "%";
      progressBar.setAttribute("aria-valuenow", String(progress));
      console.debug(`Updated progress bar to: ${sanitizeLogValue(progress)}%`);
    }

    // Update progress text
    const progressText = workflowCard.querySelector(".progress-text");
    if (progressText) {
      if (uiStatus === "running") {
        progressText.textContent = `${Math.round(progress)}% complete`;
      } else {
        progressText.textContent = this.getStatusMessage(uiStatus);
      }
      console.debug(`Updated progress text to: ${sanitizeLogValue(progressText.textContent)}`);
    }

    // Update action buttons
    const viewBtn = workflowCard.querySelector(".view-application-btn");
    const downloadBtn = workflowCard.querySelector(".download-documents-btn");

    if (viewBtn) {
      /** @type {HTMLElement} */ (viewBtn).style.display = uiStatus === "completed" ? "inline-block" : "none";
    }
    if (downloadBtn) {
      /** @type {HTMLElement} */ (downloadBtn).style.display = uiStatus === "completed" ? "inline-block" : "none";
    }

    // Show processing animation
    if (uiStatus === "running") {
      workflowCard.classList.add("processing");
    } else {
      workflowCard.classList.remove("processing");
    }
  }

  /**
   * @param {string} sessionId
   * @param {string} documentType
   */
  handleDocumentGenerated(sessionId, documentType) {
    this.showMessage(`${documentType} generated successfully!`, "success");

    // Update the workflow card to show new document
    const workflowCard = document.querySelector(
      `[data-session-id="${sessionId}"]`,
    );
    if (workflowCard) {
      const documentsSection = workflowCard.querySelector(".documents-list");
      if (documentsSection) {
        this.addDocumentToList(documentsSection, documentType, sessionId);
      }
    }
  }

  /**
   * @param {string} sessionId
   * @param {any} error
   */
  handleProcessingError(sessionId, error) {
    this.processingQueue.delete(sessionId);
    this.updateWorkflowStatus(sessionId, "failed", 0);
    this.showMessage(`Processing failed: ${error}`, "error");
  }

  /** @param {string} sessionId */
  viewWorkflowResults(sessionId) {
    window.location.href = `/dashboard/results/${encodeURIComponent(sessionId)}`;
  }

  /**
   * Open interview preparation page
   * @param {string} sessionId - Workflow session ID
   */
  openInterviewPrep(sessionId) {
    window.location.href = `/dashboard/interview-prep/${encodeURIComponent(sessionId)}`;
  }

  /** @param {string} sessionId */
  editWorkflow(sessionId) {
    window.location.href = `/dashboard/new-application?copy=${encodeURIComponent(sessionId)}`;
  }

  /** @param {string} sessionId */
  async deleteWorkflow(sessionId) {
    const confirmed = await this.confirm(
      "Are you sure you want to delete this workflow? This action cannot be undone.",
      "Delete Workflow",
    );

    if (confirmed) {
      try {
        await this.apiCall(
          `/workflow/${sessionId}`,
          "DELETE",
        );

        // DELETE returns 204 No Content on success
        this.showMessage("Workflow deleted successfully", "success");
        await this.loadDashboardData();
      } catch (error) {
        const err = /** @type {Error} */ (error);
        this.showMessage(err.message || "Failed to delete workflow", "error");
      }
    }
  }

  /** @param {string} sessionId */
  async downloadDocuments(sessionId) {
    try {
      // Get workflow results first
      const results = await this.apiCall(`/workflow/results/${sessionId}`, "GET");
      
      if (results.cover_letter || results.resume_recommendations) {
        // Create downloadable content
        let content = "";
        
        if (results.cover_letter && results.cover_letter.content) {
          content += "COVER LETTER\n";
          content += "=============\n\n";
          content += results.cover_letter.content;
          content += "\n\n";
        }
        
        if (results.resume_recommendations && results.resume_recommendations.content) {
          content += "RESUME RECOMMENDATIONS\n";
          content += "======================\n\n";
          content += results.resume_recommendations.content;
          content += "\n\n";
        }
        
        // Create and download file
        const blob = new Blob([content], { type: 'text/plain' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `workflow-${sessionId}-documents.txt`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        this.showMessage("Documents downloaded successfully", "success");
      } else {
        throw new Error("No documents available to download");
      }
    } catch (error) {
      this.showMessage("Failed to download documents", "error");
    }
  }

  /** @param {HTMLInputElement} input */
  handleJobFileUpload(input) {
    const file = input.files?.[0];
    if (!file) return;

    // Validate file type
    const allowedTypes = [
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain",
    ];
    if (!allowedTypes.includes(file.type)) {
      this.showMessage(
        "Please upload a PDF, Word document, or text file",
        "error",
      );
      input.value = "";
      return;
    }

    // Validate file size (10MB max)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
      this.showMessage("File size must be less than 10MB", "error");
      input.value = "";
      return;
    }

    // Show file info
    this.displayFileInfo(input, file);
  }

  /**
   * @param {HTMLInputElement} input
   * @param {File} file
   */
  displayFileInfo(input, file) {
    const container = input.closest(".file-upload-container");
    let fileInfo = container?.querySelector(".file-info");

    if (!fileInfo) {
      fileInfo = document.createElement("div");
      fileInfo.className = "file-info mt-2";
      container?.appendChild(fileInfo);
    }

    fileInfo.innerHTML = `
            <div class="d-flex align-items-center justify-content-between p-2 bg-light rounded">
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

    const nameEl = fileInfo.querySelector('.fw-bold');
    const sizeEl = fileInfo.querySelector('small.text-muted');
    if (nameEl) nameEl.textContent = file.name;
    if (sizeEl) sizeEl.textContent = this.formatFileSize(file.size);

    const removeBtn = fileInfo.querySelector('.remove-file-btn');
    if (removeBtn) {
      removeBtn.addEventListener('click', () => {
        fileInfo.remove();
        input.value = '';
      });
    }
  }

  /** @param {HTMLInputElement} input */
  validateJobUrl(input) {
    const url = input.value.trim();
    const feedback = /** @type {HTMLElement} */ (
      input.parentNode?.querySelector(".invalid-feedback") ||
      this.createFeedbackElement(/** @type {HTMLElement} */ (input.parentNode)));

    if (url && !this.isValidUrl(url)) {
      input.classList.add("is-invalid");
      feedback.textContent = "Please enter a valid URL";
      feedback.style.display = "block";
    } else {
      input.classList.remove("is-invalid");
      feedback.style.display = "none";
    }
  }

  /** @param {string} searchTerm */
  filterWorkflows(searchTerm) {
    const workflowCards = document.querySelectorAll(".workflow-card");
    const term = searchTerm.toLowerCase();

    workflowCards.forEach((cardEl) => {
      const card = /** @type {HTMLElement} */ (cardEl);
      const title   = card.querySelector(".job-title")?.textContent?.toLowerCase() || "";
      const company = card.querySelector(".company-name")?.textContent?.toLowerCase() || "";
      const description = card.querySelector(".job-description")?.textContent?.toLowerCase() || "";
      const matches = title.includes(term) || company.includes(term) || description.includes(term);
      card.style.display = matches ? "block" : "none";
    });
  }

  /** @param {string} status */
  filterByStatus(status) {
    const workflowCards = document.querySelectorAll(".workflow-card");
    workflowCards.forEach((cardEl) => {
      const card = /** @type {HTMLElement} */ (cardEl);
      if (status === "" || status === "all") {
        card.style.display = "block";
      } else {
        const cardStatus = card.querySelector(".status-badge")?.className.includes(`status-${status}`);
        card.style.display = cardStatus ? "block" : "none";
      }
    });
  }

  /** @param {string|null} page */
  async loadWorkflowsPage(page) {
    try {
      const response = /** @type {Record<string,any>} */ (await this.apiCall(`/workflow/list?page=${page}`, "GET"));
      if (response['sessions']) {
        this.workflows = response['sessions'];
        this.renderWorkflowsList();
        this.updatePagination({
          current: response['page'],
          total: response['total_pages'],
          per_page: response['per_page']
        });
      }
    } catch (error) {
      this.showMessage("Failed to load workflows", "error");
    }
  }

  /**
   * @param {string} applicationId
   * @param {string} documentType
   */
  async previewDocument(applicationId, documentType) {
    try {
      const response = await this.apiCall(
        `/applications/${applicationId}/documents/${documentType}`,
        "GET",
      );

      const res = /** @type {Record<string,any>} */ (response);
      if (res['success']) {
        this.showDocumentPreview(res['content'], documentType);
      } else {
        throw new Error(res['message'] || "Failed to load document");
      }
    } catch (error) {
      this.showMessage("Failed to load document preview", "error");
    }
  }

  /**
   * @param {string} content
   * @param {string} documentType
   */
  showDocumentPreview(content, documentType) {
    const modal = this.createDocumentPreviewModal(content, documentType);
    document.body.appendChild(modal);

    // @ts-ignore
    if (typeof bootstrap !== "undefined") {
      // @ts-ignore
      const bsModal = new (/** @type {any} */ (bootstrap)).Modal(modal);
      bsModal.show();

      modal.addEventListener("hidden.bs.modal", () => {
        modal.remove();
      });
    }
  }

  /**
   * @param {string} content
   * @param {string} documentType
   * @returns {HTMLElement}
   */
  createDocumentPreviewModal(content, documentType) {
    const modal = document.createElement("div");
    modal.className = "modal fade";
    modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"></h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="document-preview" style="white-space: pre-wrap; font-family: inherit;"></div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        <button type="button" class="btn btn-primary copy-content-btn">
                            <i class="fas fa-copy me-2"></i>Copy Content
                        </button>
                    </div>
                </div>
            </div>
        `;

    const titleEl = modal.querySelector('.modal-title');
    if (titleEl) titleEl.textContent = `${this.formatDocumentType(documentType)} Preview`;

    const previewEl = modal.querySelector('.document-preview');
    if (previewEl) previewEl.textContent = content;

    const copyBtn = modal.querySelector('.copy-content-btn');
    if (copyBtn) copyBtn.addEventListener('click', () => this.copyToClipboard(content));

    return modal;
  }

  /** @param {Record<string,any>|null} [stats] */
  updateDashboardStats(stats) {
    // Calculate stats from workflows if not provided
    if (!stats && this.workflows) {
      stats = this.calculateStatsFromWorkflows();
    }

    // Update stat numbers
    if (stats) {
      const statsObj = /** @type {Record<string,any>} */ (stats);
      Object.keys(statsObj).forEach((key) => {
        const element = document.querySelector(`[data-stat="${key}"]`);
        if (element) {
          this.animateCounter(element, 0, statsObj[key]);
        }
      });

      // Update charts if they exist
      if (this.statusChart && statsObj['by_status']) {
        this.statusChart.data.datasets[0].data = [
          statsObj['by_status']['initialized'] || 0,
          statsObj['by_status']['running'] || 0,
          statsObj['by_status']['completed'] || 0,
          statsObj['by_status']['failed'] || 0,
        ];
        this.statusChart.update();
      }
    }
  }
  
  /**
   * Render recent applications on the dashboard homepage
   * @param {Array<Record<string,any>>} recentApplications - Array of recent application data
   */
  renderRecentApplications(recentApplications) {
    const container = document.querySelector('#recentApplications');
    if (!container) return;
    
    if (recentApplications.length === 0) {
      container.innerHTML = `
        <div class="empty-state text-center py-4">
          <p class="text-muted">No recent applications</p>
          <button class="btn btn-sm btn-outline-primary new-application-btn">
            <i class="fas fa-plus-circle me-2"></i>Start New Application
          </button>
        </div>
      `;
      return;
    }
    
    const html = recentApplications.map((app) => {
      const a = /** @type {Record<string,any>} */ (app);
      const date = new Date(a['created_at']);
      const formattedDate = date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric',
        year: 'numeric'
      });
      
      let statusClass = 'status-active';
      if (a['status'] === 'completed') statusClass = 'status-completed';
      else if (a['status'] === 'failed') statusClass = 'status-failed';
      else if (a['status'] === 'cancelled') statusClass = 'status-cancelled';
      
      return `
        <div class="application-card">
          <div class="application-header">
            <div>
              <h5 class="application-title">${this.escapeHtml(a['job_title'] || 'Untitled Position')}</h5>
              <div class="company-name">${this.escapeHtml(a['company_name'] || 'Unknown')}</div>
            </div>
            <span class="status-badge ${statusClass}">${this.escapeHtml(a['status'])}</span>
          </div>
          <div class="application-meta">
            <div class="meta-item">
              <i class="far fa-calendar"></i>
              <span>${formattedDate}</span>
            </div>
            <div class="meta-item">
              <i class="fas fa-tasks"></i>
              <span>${this.escapeHtml(a['current_phase'] || 'processing')}</span>
            </div>
          </div>
          <div class="application-actions mt-3">
            <a href="/dashboard/application.html?session_id=${encodeURIComponent(a['session_id'])}" class="btn btn-sm btn-outline-primary">
              <i class="fas fa-eye me-1"></i> View
            </a>
          </div>
        </div>
      `;
    }).join('');
    
    container.innerHTML = html;
  }

  calculateStatsFromWorkflows() {
    const byStatus = /** @type {Record<string,number>} */ ({
      initialized: 0,
      running: 0,
      completed: 0,
      failed: 0
    });
    const stats = { total: this.workflows.length, by_status: byStatus };

    this.workflows.forEach(workflow => {
      const status = /** @type {string} */ ((/** @type {any} */ (workflow))['status'] || 'initialized');
      if (byStatus[status] !== undefined) {
        byStatus[status]++;
      }
    });

    return stats;
  }

  /**
   * Render workflows list
   */
  renderWorkflowsList() {
    const container = document.querySelector("#workflowsList") || document.querySelector("#applicationsList");
    if (!container) return;

    if (this.workflows.length === 0) {
      container.innerHTML = this.getEmptyStateHtml();
      return;
    }

    container.innerHTML = this.workflows
      .map((workflow) => this.getWorkflowCardHtml(workflow))
      .join("");
  }

  /** @param {Record<string,any>} workflow */
  getWorkflowCardHtml(workflow) {
    return `
            <div class="col-md-6 col-lg-4 mb-4">
                <div class="card workflow-card h-100" data-session-id="${workflow.session_id}">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-3">
                            <h5 class="card-title job-title mb-1">${this.escapeHtml(workflow.job_title || 'Untitled Job')}</h5>
                            <span class="status-badge status-${escapeHtml(String(workflow.status))}">${escapeHtml(this.formatStatus(workflow.status))}</span>
                        </div>
                        <p class="company-name text-muted mb-2">
                            <i class="fas fa-building me-1"></i>
                            ${this.escapeHtml(workflow.company_name || 'Unknown')}
                        </p>
                        <p class="card-text job-description">${this.escapeHtml(this.truncateText(workflow.job_description || 'No description', 100))}</p>

                        ${
                          workflow.status === "running"
                            ? `
                            <div class="progress mb-3">
                                <div class="progress-bar" style="width: ${workflow.progress || 0}%" aria-valuenow="${workflow.progress || 0}" aria-valuemin="0" aria-valuemax="100"></div>
                            </div>
                            <small class="text-muted progress-text">${Math.round(workflow.progress || 0)}% complete</small>
                        `
                            : ""
                        }

                        <div class="mt-3">
                            <small class="text-muted">
                                <i class="fas fa-calendar me-1"></i>
                                Created ${this.formatDate(workflow.created_at)}
                            </small>
                        </div>
                    </div>
                    <div class="card-footer bg-transparent">
                        <div class="btn-group w-100" role="group">
                            ${
                              workflow.status === "completed"
                                ? `
                                <button type="button" class="btn btn-success btn-sm view-application-btn" data-session-id="${workflow.session_id}">
                                    <i class="fas fa-eye me-1"></i>View
                                </button>
                                <button type="button" class="btn btn-primary btn-sm interview-prep-btn" data-session-id="${workflow.session_id}" title="Prepare for Interview">
                                    <i class="fas fa-microphone-alt me-1"></i>Interview Prep
                                </button>
                                <button type="button" class="btn btn-info btn-sm download-documents-btn" data-session-id="${workflow.session_id}">
                                    <i class="fas fa-download me-1"></i>Download
                                </button>
                            `
                                : ""
                            }
                            <button type="button" class="btn btn-outline-danger btn-sm delete-application-btn" data-session-id="${workflow.session_id}">
                                <i class="fas fa-trash me-1"></i>Delete
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
  }

  /**
   * Get empty state HTML
   */
  getEmptyStateHtml() {
    return `
            <div class="text-center py-5">
                <div class="mb-4">
                    <i class="fas fa-briefcase fa-4x text-muted"></i>
                </div>
                <h3>No Applications Yet</h3>
                <p class="text-muted mb-4">Get started by creating your first job application</p>
                <button type="button" class="btn btn-primary new-application-btn">
                    <i class="fas fa-plus me-2"></i>Create New Application
                </button>
            </div>
        `;
  }

  /** @param {Array<Record<string,any>>} activities */
  updateRecentActivity(activities) {
    const container = document.querySelector("#recentActivity");
    if (!container || !activities) return;

    if (activities.length === 0) {
      container.innerHTML =
        '<p class="text-muted text-center">No recent activity</p>';
      return;
    }

    container.innerHTML = activities
      .map(
        (activity) => `
            <div class="d-flex align-items-center mb-3">
                <div class="activity-icon me-3">
                    <i class="${(/** @type {any} */ (this)).getActivityIcon(activity.type)} text-primary"></i>
                </div>
                <div class="flex-grow-1">
                    <div class="fw-bold">${this.escapeHtml(activity.title)}</div>
                    <small class="text-muted">${this.formatDate(activity.created_at)}</small>
                </div>
            </div>
        `,
      )
      .join("");
  }

  /** @param {Record<string,any>|null} [pagination] */
  updatePagination(pagination) {
    const container = document.querySelector("#pagination");
    if (!container || !pagination) return;

    const p = /** @type {Record<string,any>} */ (pagination);
    const current_page = p['current_page'], total_pages = p['total_pages'], has_prev = p['has_prev'], has_next = p['has_next'];

    container.innerHTML = `
            <nav aria-label="Applications pagination">
                <ul class="pagination justify-content-center">
                    <li class="page-item ${!has_prev ? "disabled" : ""}">
                        <button class="page-link pagination-btn" data-page="${current_page - 1}" ${!has_prev ? "disabled" : ""}>
                            Previous
                        </button>
                    </li>
                    ${this.generatePageNumbers(current_page, total_pages)}
                    <li class="page-item ${!has_next ? "disabled" : ""}">
                        <button class="page-link pagination-btn" data-page="${current_page + 1}" ${!has_next ? "disabled" : ""}>
                            Next
                        </button>
                    </li>
                </ul>
            </nav>
        `;
  }

  /**
   * @param {number} current
   * @param {number} total
   * @returns {string}
   */
  generatePageNumbers(current, total) {
    let pages = "";
    const maxVisible = 5;
    let start = Math.max(1, current - Math.floor(maxVisible / 2));
    let end = Math.min(total, start + maxVisible - 1);

    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1);
    }

    for (let i = start; i <= end; i++) {
      pages += `
                <li class="page-item ${i === current ? "active" : ""}">
                    <button class="page-link pagination-btn" data-page="${i}">${i}</button>
                </li>
            `;
    }

    return pages;
  }

  /**
   * @param {Element} container
   * @param {string} documentType
   * @param {string} applicationId
   */
  addDocumentToList(container, documentType, applicationId) {
    const safeDocType = escapeHtml(String(documentType));
    const safeAppId = escapeHtml(String(applicationId));
    const documentHtml = `
            <div class="document-item d-flex align-items-center justify-content-between mb-2">
                <div class="d-flex align-items-center">
                    <i class="${escapeHtml(this.getDocumentIcon(documentType))} me-2"></i>
                    <span>${escapeHtml(this.formatDocumentType(documentType))}</span>
                </div>
                <button type="button" class="btn btn-sm btn-outline-primary preview-document-btn"
                        data-app-id="${safeAppId}" data-doc-type="${safeDocType}">
                    <i class="fas fa-eye"></i>
                </button>
            </div>
        `;
    container.insertAdjacentHTML("beforeend", documentHtml);
  }

  /**
   * @param {HTMLFormElement} form
   * @param {boolean} loading
   */
  setFormLoading(form, loading) {
    const submitBtn = /** @type {HTMLButtonElement|null} */ (form.querySelector('[type="submit"]'));
    const inputs = form.querySelectorAll("input, select, textarea");

    if (loading) {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
      }
      inputs.forEach((input) => { /** @type {HTMLInputElement} */ (input).disabled = true; });
    } else {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent =
          submitBtn.getAttribute("data-original-text") || "Create Application";
      }
      inputs.forEach((input) => { /** @type {HTMLInputElement} */ (input).disabled = false; });
    }
  }

  /** @param {number} bytes */
  formatFileSize(bytes) {
    // @ts-ignore
    const app = window.app;
    if (app && typeof app.formatFileSize === 'function') return app.formatFileSize(bytes);
    if (bytes === 0) return "0 Bytes";
    const k = 1024, sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  /** @param {string} status */
  formatStatus(status) {
    const statusMap = /** @type {Record<string,string>} */ ({
      draft: "Draft",
      processing: "Processing",
      completed: "Completed",
      failed: "Failed",
      applied: "Applied",
      interview: "Interview",
      rejected: "Rejected",
      accepted: "Accepted",
      error: "Error",
    });
    const normalizedStatus = typeof status === 'string' ? status.toLowerCase() : status;
    return statusMap[normalizedStatus] || status;
  }

  /** @param {string} status */
  getStatusMessage(status) {
    const messages = /** @type {Record<string,string>} */ ({
      draft: "Ready to process",
      processing: "AI is working...",
      completed: "Documents ready",
      failed: "Processing failed",
      applied: "Application submitted",
      interview: "Interview scheduled",
      rejected: "Application rejected",
      accepted: "Offer accepted",
      error: "Processing failed"
    });
    const normalizedStatus = typeof status === 'string' ? status.toLowerCase() : status;
    return messages[normalizedStatus] || status;
  }

  /** @param {string} type */
  formatDocumentType(type) {
    const typeMap = /** @type {Record<string,string>} */ ({
      resume: "Resume",
      cover_letter: "Cover Letter",
      interview_prep: "Interview Preparation"
    });
    return typeMap[type] || type;
  }

  /** @param {string} type */
  getDocumentIcon(type) {
    const icons = /** @type {Record<string,string>} */ ({
      resume: "fas fa-file-user",
      cover_letter: "fas fa-file-alt",
      interview_prep: "fas fa-question-circle",
    });
    return icons[type] || "fas fa-file";
  }

  /**
   * @param {string} text
   * @param {number} maxLength
   */
  truncateText(text, maxLength) {
    if (!text) return "";
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + "...";
  }

  /** @param {string} dateString */
  formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffInSeconds < 60) return "just now";
    if (diffInSeconds < 3600)
      return `${Math.floor(diffInSeconds / 60)} minutes ago`;
    if (diffInSeconds < 86400)
      return `${Math.floor(diffInSeconds / 3600)} hours ago`;
    if (diffInSeconds < 604800)
      return `${Math.floor(diffInSeconds / 86400)} days ago`;

    return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  /**
   * @param {Element} element
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

  /** @param {string} url */
  isValidUrl(url) {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  }

  /** @param {HTMLElement} parent */
  createFeedbackElement(parent) {
    const feedback = document.createElement("div");
    feedback.className = "invalid-feedback";
    parent.appendChild(feedback);
    return feedback;
  }

  /** @param {string} text */
  escapeHtml(text) {
    // @ts-ignore
    const app = window.app;
    if (app && typeof app.escapeHtml === 'function') return app.escapeHtml(String(text ?? ''));
    return window.escapeHtml(String(text ?? ''));
  }

  /** @param {string} text */
  async copyToClipboard(text) {
    // @ts-ignore
    const app = window.app;
    if (app && typeof app.copyToClipboard === 'function') {
      return app.copyToClipboard(text);
    }
    try {
      await navigator.clipboard.writeText(text);
      this.showMessage("Copied to clipboard!", "success");
    } catch {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      this.showMessage("Copied to clipboard!", "success");
    }
  }

  /**
   * @param {string} message
   * @param {string} [title]
   * @returns {Promise<boolean>}
   */
  confirm(message, title = "Confirm") {
    return new Promise((resolve) => {
      // @ts-ignore
      if (window.app && typeof window.app.confirm === "function") {
        // @ts-ignore
        window.app.confirm(message, title).then(resolve);
      } else if (typeof window.showConfirm === "function") {
        window.showConfirm({ title: title, message: message }).then(resolve);
      } else {
        resolve(false);
      }
    });
  }

  /**
   * @param {string} message
   * @param {string} [type]
   */
  showMessage(message, type = "info") {
    // @ts-ignore
    if (window.app && typeof window.app.showNotification === "function") {
      // @ts-ignore
      window.app.showNotification(message, type);
    }
    // No fallback needed
  }

  /**
   * @param {string} endpoint
   * @param {string} [method]
   * @param {any} [data]
   * @param {Record<string,any>} [options]
   * @returns {Promise<any>}
   */
  async apiCall(endpoint, method = "GET", data = null, options = {}) {
    // @ts-ignore
    const app = window.app;
    if (app && typeof app.apiCall === 'function') {
      return app.apiCall(endpoint, method, data, options);
    }
    // Fallback if app.js not yet initialized
    const url = `${this.apiBaseUrl}${endpoint}`;
    const config = /** @type {Record<string,any>} */ ({
      method,
      headers: /** @type {Record<string,string>} */ ({
        "Content-Type": "application/json",
        ...(options['headers'] || {}),
      }),
      ...options,
    });
    if (data && method !== "GET") {
      if (data instanceof FormData) { delete config['headers']['Content-Type']; config['body'] = data; }
      else config['body'] = JSON.stringify(data);
    }
    const token = localStorage.getItem("authToken") || localStorage.getItem("access_token");
    if (token) config['headers']['Authorization'] = `Bearer ${token}`;
    const response = await fetch(url, config);
    if (response.status === 401) { localStorage.removeItem("authToken"); window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || "/auth/login"; throw new Error("Authentication failed"); }
    let result;
    try { result = await response.json(); } catch { throw new Error(`Invalid JSON response: ${response.status}`); }
    const res = /** @type {Record<string,any>} */ (result);
    if (!response.ok) {
      const fallbackErr = new Error(res['message'] || res['detail'] || res['error'] || `HTTP ${response.status}`);
      if (res['error_code']) {
        /** @type {any} */ (fallbackErr).errorCode = res['error_code'];
      }
      throw fallbackErr;
    }
    return result;
  }

  /**
   * Cleanup on page unload
   */
  cleanup() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
    }
    this.stopWsPing();
    if (this.ws) {
      this.ws.close();
    }
  }
}

// Initialize dashboard manager when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
  if (
    document.querySelector(".dashboard") ||
    document.querySelector("#applicationsList")
  ) {
    // @ts-ignore
    window.dashboardManager = new DashboardManager();
  }
});

// Cleanup on page unload
window.addEventListener("beforeunload", () => {
  // @ts-ignore
  if (window.dashboardManager) {
    // @ts-ignore
    window.dashboardManager.cleanup();
  }
});

// Export for use in other modules
if (typeof module !== "undefined" && module.exports) {
  module.exports = DashboardManager;
}
