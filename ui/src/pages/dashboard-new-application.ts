/**
 * New Application page — paste job text or upload file, start workflow.
 */
import { getApiBase, getAuthToken, requireLogin } from '../shared/auth';
import { errorMessageFromBody } from '../shared/auth-api';
import { notify } from '../shared/notify';
import { syncProfileCompletionFromApi } from '../shared/profile-completion';
import type { WorkflowStartResponse } from '../shared/types';
import { addTrackedSession } from '../shared/workflow-tracking';

type MethodTab = 'manual' | 'file';

const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt'];
const MAX_FILE_BYTES = 5 * 1024 * 1024;
const MAX_DESC_CHARS = 50000;

let currentTab: MethodTab = 'manual';
let uploadedFile: File | null = null;
let submitting = false;

function showAlert(message: string, type: 'success' | 'danger' | 'warning' | 'info'): void {
  notify(message, type, { replace: true });
}

function showApiKeyAlert(): void {
  const container = document.getElementById('alertContainer');
  if (!container) return;
  container.innerHTML = `
    <div class="alert alert-warning alert-dismissible fade show" role="alert">
      <i class="fas fa-key me-2"></i>
      <strong>API key required.</strong>
      To analyze jobs with AI, choose a provider and add your API key in
      <a href="/settings?tab=ai-setup" class="alert-link">Settings &rarr; AI Setup</a>
      (or select Ollama / ask your admin about Vertex AI).
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>`;
}

function clearAlerts(): void {
  const container = document.getElementById('alertContainer');
  if (container) container.innerHTML = '';
  document.querySelectorAll('.is-invalid').forEach((el) => el.classList.remove('is-invalid'));
}

function switchTab(tabName: string): void {
  if (tabName !== 'manual' && tabName !== 'file') return;

  document.querySelectorAll('.method-tab').forEach((t) => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));

  const tabBtn = document.querySelector(`.method-tab[data-tab="${tabName}"]`);
  tabBtn?.classList.add('active');
  document.getElementById(`${tabName}Tab`)?.classList.add('active');

  const subtitle = document.getElementById('headerSubtitle');
  if (subtitle) {
    subtitle.textContent =
      tabName === 'manual'
        ? 'Paste a job description and let AI do the rest'
        : 'Upload a job posting and let AI do the rest';
  }
  currentTab = tabName;
  clearAlerts();
}

function handleFileDrop(event: DragEvent): void {
  event.preventDefault();
  event.stopPropagation();
  document.getElementById('fileUploadArea')?.classList.remove('dragover');
  const files = event.dataTransfer?.files;
  if (files && files.length > 0) handleFileUpload(files[0]);
}

function handleDragOver(event: DragEvent): void {
  event.preventDefault();
  event.stopPropagation();
  document.getElementById('fileUploadArea')?.classList.add('dragover');
}

function handleDragLeave(event: DragEvent): void {
  event.preventDefault();
  event.stopPropagation();
  document.getElementById('fileUploadArea')?.classList.remove('dragover');
}

function handleFileSelect(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) handleFileUpload(file);
}

function handleFileUpload(file: File): void {
  const parts = file.name.split('.');
  const fileExtension =
    parts.length >= 2 ? `.${(parts.pop() || '').toLowerCase()}` : '';
  if (!fileExtension || !ALLOWED_EXTENSIONS.includes(fileExtension)) {
    showAlert('Please upload a PDF, Word (.docx), or TXT file.', 'danger');
    return;
  }
  if (file.size > MAX_FILE_BYTES) {
    showAlert('File size must be less than 5MB.', 'danger');
    return;
  }
  uploadedFile = file;
  showFileInfo(file);
}

function showFileInfo(file: File): void {
  const fileInfo = document.getElementById('fileInfo');
  const fileName = document.getElementById('fileName');
  const fileSize = document.getElementById('fileSize');
  if (fileName) fileName.textContent = file.name;
  if (fileSize) fileSize.textContent = formatFileSize(file.size);
  if (fileInfo) fileInfo.style.display = 'block';
}

function removeFile(): void {
  uploadedFile = null;
  const fileInfo = document.getElementById('fileInfo');
  const fileInput = document.getElementById('fileInput') as HTMLInputElement | null;
  if (fileInfo) fileInfo.style.display = 'none';
  if (fileInput) fileInput.value = '';
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

function updateCharacterCount(
  textareaId: string,
  countId: string,
  maxLength: number,
): void {
  const textarea = document.getElementById(textareaId) as HTMLTextAreaElement | null;
  const count = document.getElementById(countId);
  if (!textarea || !count) return;
  const length = textarea.value.length;
  count.textContent = `${length.toLocaleString()}/${maxLength.toLocaleString()} characters`;
  count.style.color = length > maxLength ? '#dc3545' : '#6c757d';
  textarea.classList.toggle('is-invalid', length > maxLength);
}

function trackWorkflowSession(sessionId: string): void {
  addTrackedSession(sessionId);
  sessionStorage.setItem('new_application_session_id', sessionId);
}

async function processApplication(): Promise<void> {
  if (submitting) return;
  clearAlerts();

  let jobText: string | null = null;

  if (currentTab === 'manual') {
    const textarea = document.getElementById('jobDescription') as HTMLTextAreaElement | null;
    const description = textarea?.value.trim() ?? '';
    if (!description) {
      showAlert('Please enter the job description', 'danger');
      textarea?.classList.add('is-invalid');
      return;
    }
    if (description.length < 100) {
      showAlert(
        'Job description seems too short. Please paste the complete job posting.',
        'danger',
      );
      textarea?.classList.add('is-invalid');
      return;
    }
    jobText = description;
  } else if (currentTab === 'file' && !uploadedFile) {
    showAlert('Please upload a file first.', 'danger');
    return;
  }

  const submitBtn = document.querySelector(
    '[data-action="process-application"]',
  ) as HTMLButtonElement | null;
  const originalBtnHtml = submitBtn?.innerHTML ?? '';

  submitting = true;
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Creating...';
  }

  try {
    const formData = new FormData();
    if (jobText) formData.append('job_text', jobText);
    if (currentTab === 'file' && uploadedFile) formData.append('job_file', uploadedFile);
    if (currentTab === 'manual') {
      const titleInput = document.getElementById('jobTitleInput') as HTMLInputElement | null;
      const companyInput = document.getElementById('companyNameInput') as HTMLInputElement | null;
      const manualTitle = titleInput?.value.trim() ?? '';
      const manualCompany = companyInput?.value.trim() ?? '';
      if (manualTitle) formData.append('detected_title', manualTitle);
      if (manualCompany) formData.append('detected_company', manualCompany);
    }

    const token = getAuthToken();
    if (!token) throw new Error('Authentication failed - please log in again');

    const response = await fetch(`${getApiBase()}/workflow/start`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const responseText = await response.text();

    if (response.ok) {
      try {
        const parsed = JSON.parse(responseText) as WorkflowStartResponse;
        if (parsed.session_id) trackWorkflowSession(parsed.session_id);
      } catch {
        /* response may not be JSON */
      }
      sessionStorage.setItem(
        'new_application_toast',
        'Application submitted! AI agents are analyzing it in the background.',
      );
      window.location.href = '/dashboard';
      return;
    }

    let errorDetail = 'Unknown server error';
    let errorCode = '';
    try {
      const errorJson = JSON.parse(responseText) as {
        error_code?: string;
        message?: string;
        detail?: string;
      };
      errorCode = errorJson.error_code || '';
      errorDetail = errorMessageFromBody(errorJson, errorDetail);
    } catch {
      errorDetail = `HTTP ${response.status}: ${responseText.substring(0, 100)}`;
    }

    submitting = false;
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalBtnHtml;
    }

    if (errorCode === 'CFG_6001') {
      showApiKeyAlert();
    } else if (errorCode === 'RES_3002') {
      notify(
        'You already have this role and company on your applications list. Open that card on your dashboard—you do not need to add the same job twice.',
        'warning',
      );
    } else {
      showAlert(`Error creating application: ${errorDetail}`, 'danger');
    }
  } catch (error) {
    const err = error instanceof Error ? error : new Error(String(error));
    console.error('Error creating application:', err);
    submitting = false;
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalBtnHtml;
    }
    showAlert(`Error creating application: ${err.message}`, 'danger');
  }
}

function initNewApplicationPage(): void {
  document.querySelectorAll('.method-tab[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = (btn as HTMLElement).dataset.tab;
      if (tab) switchTab(tab);
    });
  });

  const jobDescEl = document.getElementById('jobDescription');
  if (jobDescEl) {
    jobDescEl.addEventListener('input', () => {
      updateCharacterCount('jobDescription', 'descriptionCount', MAX_DESC_CHARS);
    });
  }

  const fileUploadArea = document.getElementById('fileUploadArea');
  const fileInput = document.getElementById('fileInput') as HTMLInputElement | null;
  if (fileUploadArea && fileInput) {
    fileUploadArea.addEventListener('click', (e) => {
      if ((e.target as HTMLElement).closest('input')) return;
      fileInput.click();
    });
    fileUploadArea.addEventListener('dragover', (e) => handleDragOver(e as DragEvent));
    fileUploadArea.addEventListener('dragleave', (e) => handleDragLeave(e as DragEvent));
    fileUploadArea.addEventListener('drop', (e) => handleFileDrop(e as DragEvent));
    fileInput.addEventListener('change', handleFileSelect);
  }

  document.addEventListener('click', (e) => {
    const action = (e.target as HTMLElement).closest('[data-action]') as HTMLElement | null;
    if (!action) return;
    const actionName = action.dataset.action;
    if (actionName === 'remove-file') removeFile();
    if (actionName === 'process-application') void processApplication();
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireLogin()) return;
  if (!(await syncProfileCompletionFromApi())) return;
  initNewApplicationPage();
});

// Legacy global exports (e2e / extension compatibility)
window.handleDragLeave = handleDragLeave;
window.handleDragOver = handleDragOver;
window.handleFileDrop = handleFileDrop;
window.handleFileSelect = handleFileSelect;
window.processApplication = processApplication;
window.removeFile = removeFile;
window.switchTab = switchTab;
window.updateCharacterCount = updateCharacterCount;
