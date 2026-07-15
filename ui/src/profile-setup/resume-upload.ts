import type { ParsedResumeData } from './types';
import { escapeHtml } from '../shared/dom-security';
import { API_BASE } from './state';
import {
  getEducationHistory,
  getHasApiKey,
  getWorkExperience,
  setEducationHistory,
  setHasApiKey,
  setSkills,
  setWorkExperience,
} from './state-access';
import { getAuthToken } from './api';
import { errorAlert, successAlert } from './dom';
import { changeStep } from './navigation';
import { formatDateForInput } from './utils';
import { hideAlerts, showError, showSuccess } from './alerts';
import { addSkill } from './skills';
import { renderEducation } from './education';
import { renderWorkExperience } from './work-experience';
import { inputEl } from './dom-helpers';

export function initializeResumeUpload() {
    const dropZone = document.getElementById("resume-drop-zone");
    const fileInput = document.getElementById("resume-file-input");

    if (!dropZone || !fileInput) return;

    // Click to upload — show API key prompt first if no key is configured
    dropZone.addEventListener("click", () => {
        if (!getHasApiKey()) {
            showApiKeyPrompt();
            return;
        }
        fileInput.click();
    });

    // File input change (triggered after click passes the key check)
    fileInput.addEventListener("change", (e) => {
        const target = e.target as HTMLInputElement | null;
        if (target?.files && target.files.length > 0) {
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

        if (!getHasApiKey()) {
            showApiKeyPrompt();
            return;
        }

        const files = e.dataTransfer ? e.dataTransfer.files : null;
        if (files && files.length > 0) {
            handleResumeUpload(files[0]);
        }
    });
}

export async function checkApiKeyStatus() {
    try {
        const token = getAuthToken();
        if (!token) return;
        const res = await fetch(`${API_BASE}/profile/api-key/status`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        setHasApiKey(!!(data.has_credentials || data.has_user_key || data.use_vertex_ai));
    } catch (_e) {
        // Non-fatal — assume key available so we never block upload incorrectly
    }
}

export function showApiKeyPrompt() {
    const prompt = document.getElementById('api-key-prompt');
    if (!prompt) return;
    prompt.style.display = 'flex';
    const input = (document.getElementById('setup-api-key-input'));
    if (input) input.focus();
    prompt.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

export function setupInlineApiKey() {
    const saveBtn   = document.getElementById('setup-save-key-btn');
    const input = document.getElementById('setup-api-key-input') as HTMLInputElement | null;
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

        (saveBtn as HTMLButtonElement).disabled = true;
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
                body: JSON.stringify({ api_key: key, provider: 'gemini' })
            });

            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.message || data.detail || 'Failed to save key.');

            await fetch(`${API_BASE}/profile/preferences`, {
                method: 'PATCH',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ preferred_provider: 'gemini' })
            });

            // Mark key as available so next interaction goes straight to upload
            setHasApiKey(true);
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
            const e = err instanceof Error ? err : new Error(String(err));
            if (errorEl) { errorEl.textContent = e.message || 'Could not save key — please try again.'; errorEl.style.display = 'block'; }
        } finally {
            (saveBtn as HTMLButtonElement).disabled = false;
            if (spinner) spinner.style.display = 'none';
            if (btnText) btnText.textContent = 'Save & Continue';
        }
    });

    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') saveBtn.click();
    });
}

export function setResumeUploadSpinnerVisible(visible: boolean): void {
    const spin = document.querySelector("#upload-status .spinner-border");
    if (spin) spin.classList.toggle("d-none", !visible);
}

export async function handleResumeUpload(file: File): Promise<void> {
    const dropZone = document.getElementById("resume-drop-zone");
    const progressContainer = document.getElementById("upload-progress");
    const progressBar = document.getElementById("upload-progress-bar");
    const progressTrack = progressContainer?.querySelector(".progress");
    const statusText = document.getElementById("upload-status-text");
    const statusContainer = document.getElementById("upload-status");

    // Validate file
    const allowedExtensions = [".pdf", ".docx", ".txt"];
    const fileExtension =
        '.' + (file.name.split('.').pop()?.toLowerCase() ?? '');

    if (
        !dropZone ||
        !progressContainer ||
        !progressBar ||
        !statusText ||
        !statusContainer
    ) {
        return;
    }

    if (fileExtension === '.doc') {
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
                setHasApiKey(false);
                showApiKeyPrompt();
                throw new Error('Resume parsing requires AI credentials. Configure a provider in Settings → AI Setup, or use "Fill in manually".');
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
        const err = error instanceof Error ? error : new Error(String(error));
        const msg =
            err.message ||
            'Failed to parse resume. Please try again or enter your information manually.';
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

export async function autoFillProfile(
    raw: ParsedResumeData | Record<string, unknown>,
): Promise<void> {
    const data = raw as ParsedResumeData;

    if (data.city) {
        const el = inputEl('city');
        if (el) el.value = String(data.city);
    }
    if (data.state) {
        const el = inputEl('state');
        if (el) el.value = String(data.state);
    }
    if (data.country) {
        const el = inputEl('country');
        if (el) el.value = String(data.country);
    }
    if (data.professional_title) {
        const el = inputEl('professional-title');
        if (el) el.value = String(data.professional_title);
    }
    if (data.years_experience !== undefined) {
        const el = inputEl('years-experience');
        if (el) el.value = String(data.years_experience);
    }
    if (data.summary) {
        const el = document.getElementById('summary') as HTMLTextAreaElement | null;
        if (el) el.value = String(data.summary);
    }
    if (data.is_student !== undefined) {
        const el = document.getElementById('is-student') as HTMLInputElement | null;
        if (el) el.checked = Boolean(data.is_student);
    }
    if (data.phone) {
        const pe = inputEl('phone');
        if (pe) pe.value = String(data.phone);
    }
    if (data.linkedin_url) {
        const e = inputEl('linkedin-url');
        if (e) e.value = String(data.linkedin_url);
    }
    if (data.github_url) {
        const e = inputEl('github-url');
        if (e) e.value = String(data.github_url);
    }
    if (data.portfolio_url) {
        const e = inputEl('portfolio-url');
        if (e) e.value = String(data.portfolio_url);
    }

    const workExp = Array.isArray(data.work_experience) ? data.work_experience : [];
    if (workExp.length > 0) {
        // Clear existing work experience
        setWorkExperience([]);

        // Add each work experience (matching existing data structure)
        for (const exp of workExp) {
            const row = exp as Record<string, unknown>;
            const endYm = formatDateForInput(String(row.end_date ?? ''));
            const hasEnd = !!String(endYm).trim();
            const isCurrent = !!(row.is_current && !hasEnd);
            getWorkExperience().push({
                company: String(row.company ?? ''),
                job_title: String(row.title ?? row.job_title ?? ''),
                start_date: formatDateForInput(String(row.start_date ?? '')),
                end_date: hasEnd ? endYm : '',
                description: String(row.description ?? ''),
                is_current: isCurrent,
            });
        }

        renderWorkExperience();

        const noExpEl = document.getElementById(
            'no-experience',
        ) as HTMLInputElement | null;
        if (noExpEl?.checked) {
            noExpEl.checked = false;
            noExpEl.dispatchEvent(new Event("change"));
        }
    }

    const eduRows = Array.isArray(data.education) ? data.education : [];
    if (eduRows.length > 0) {
        setEducationHistory([]);
        for (const edu of eduRows) {
            const row = edu as Record<string, unknown>;
            const endYm = formatDateForInput(
                String(row.graduation_date ?? row.end_date ?? ''),
            );
            const hasEnd = !!String(endYm).trim();
            const isCurrent = !!(row.is_current && !hasEnd);
            let startYm = formatDateForInput(String(row.start_date ?? ''));
            if (!startYm && endYm) {
                const parts = endYm.split("-");
                const y = parseInt(parts[0], 10);
                const m = parseInt(parts[1], 10) || 9;
                if (!Number.isNaN(y)) {
                    startYm = `${Math.max(1900, y - 4)}-${String(m).padStart(2, "0")}`;
                }
            }
            getEducationHistory().push({
                institution: String(row.institution ?? ''),
                degree: String(row.degree ?? ''),
                field_of_study: String(row.field_of_study ?? row.field ?? ''),
                start_date: startYm,
                end_date: hasEnd ? endYm : '',
                is_current: isCurrent,
            });
        }
        renderEducation();
        const noEdEl = document.getElementById(
            'no-education',
        ) as HTMLInputElement | null;
        if (noEdEl?.checked) {
            noEdEl.checked = false;
            noEdEl.dispatchEvent(new Event("change"));
        }
    }

    const skillRows = Array.isArray(data.skills) ? data.skills : [];
    if (skillRows.length > 0) {
        setSkills([]);
        const skillsEl = document.getElementById('skills-container');
        if (skillsEl) skillsEl.innerHTML = '';

        for (const skill of skillRows) {
            if (skill && typeof skill === "string") {
                addSkill(skill);
            }
        }
    }

}
