import { getApiBase, getAuthToken, getLoginUrl } from '../shared/auth';
import { renderHeader } from './render-header';
import { renderCoverLetter } from './render-cover-letter';
import { renderInterviewPrep } from './render-interview';
import { renderMainContent } from './render-overview';
import { renderResumeTips } from './render-resume';
import {
  getApplicationData,
  getCurrentSessionId,
  getProcessingRefreshTimer,
  setApplicationData,
  setProcessingRefreshTimer,
  setWorkflowStatus,
} from './state';
import type {
  CompanyResearch,
  CoverLetter,
  JobAnalysis,
  ProfileMatching,
  ResumeRecommendations,
  WorkflowResults,
} from './types';

function buildJobView(data: WorkflowResults): JobAnalysis {
  const job: JobAnalysis = { ...((data.job_analysis as JobAnalysis | undefined) ?? {}) };
  job.application_company_name = data.application_company_name;
  job.detected_company = data.detected_company;
  return job;
}

const API_BASE = getApiBase();

const PROCESSING_STATUSES = new Set(['in_progress', 'initialized', 'pending']);

interface WorkflowStatusResponse {
  status?: string;
  current_agent?: string | null;
  [key: string]: unknown;
}

const AGENT_STEPS = [
  { id: 'job_analyzer', label: 'Analyzing job requirements', icon: 'fa-search' },
  { id: 'profile_matching', label: 'Matching your profile', icon: 'fa-user-check' },
  { id: 'company_research', label: 'Researching the company', icon: 'fa-building' },
  { id: 'cover_letter_writer', label: 'Writing cover letter', icon: 'fa-envelope' },
  { id: 'resume_advisor', label: 'Generating resume tips', icon: 'fa-file-alt' },
] as const;

export function showError(message: string): void {
  const ls = document.getElementById('loadingState');
  const es = document.getElementById('errorState');
  const em = document.getElementById('errorMessage');
  if (ls) ls.style.display = 'none';
  if (es) es.style.display = 'block';
  if (em) em.textContent = message;
}

export function showProcessing(currentAgent: string | null = null): void {
  const ls = document.getElementById('loadingState');
  if (!ls) return;

  const stepOrder = AGENT_STEPS.map((s) => s.id);
  const currentIdx = currentAgent ? stepOrder.indexOf(currentAgent as (typeof stepOrder)[number]) : 0;
  const safeIdx = currentIdx >= 0 ? currentIdx : 0;

  const stepsHtml = AGENT_STEPS.map((step, idx) => {
    let stateClass: string;
    let iconHtml: string;
    if (idx < safeIdx) {
      stateClass = 'done';
      iconHtml = '<i class="fas fa-check"></i>';
    } else if (idx === safeIdx) {
      stateClass = 'active';
      iconHtml = '<div class="agent-step-spinner"></div>';
    } else {
      stateClass = '';
      iconHtml = `<i class="fas ${step.icon}"></i>`;
    }
    return `<div class="agent-step ${stateClass}">
                <div class="agent-step-icon">${iconHtml}</div>
                <span class="agent-step-label">${step.label}</span>
            </div>`;
  }).join('');

  ls.innerHTML = `
            <div class="agent-progress-card">
                <div class="agent-progress-header">
                    <i class="fas fa-robot agent-progress-icon"></i>
                    <h3 class="agent-progress-title">AI Agents Working</h3>
                    <p class="agent-progress-subtitle">This takes about 30 seconds — you don't need to wait here</p>
                </div>
                <div class="agent-steps">${stepsHtml}</div>
                <div class="agent-progress-footer">
                    <a href="/dashboard" class="btn btn-secondary btn-sm">
                        <i class="fas fa-arrow-left me-2"></i>Back to Dashboard
                    </a>
                    <span class="agent-progress-footer-note">This page updates automatically</span>
                </div>
            </div>
        `;

  if (getProcessingRefreshTimer() !== null) {
    clearTimeout(getProcessingRefreshTimer()!);
  }
  setProcessingRefreshTimer(
    window.setTimeout(() => {
      setProcessingRefreshTimer(null);
      void loadApplicationData();
    }, 3000),
  );
}

export function renderApplication(): void {
  const ls = document.getElementById('loadingState');
  const mc = document.getElementById('mainContent');
  if (ls) ls.style.display = 'none';
  if (mc) mc.style.display = 'block';

  const data = getApplicationData();
  if (!data) return;

  const job = buildJobView(data);
  const match = (data.profile_matching as ProfileMatching | undefined) ?? {};
  const company = (data.company_research as CompanyResearch | undefined) ?? {};
  const resume = (data.resume_recommendations as ResumeRecommendations | undefined) ?? {};
  const cover = (data.cover_letter as CoverLetter | undefined) ?? {};

  const jobUrl = typeof data.job_url === 'string' ? data.job_url : '';
  const jobUrlMeta = document.getElementById('jobUrlMeta');
  const jobUrlLink = document.getElementById('jobUrlLink') as HTMLAnchorElement | null;
  if (jobUrlMeta && jobUrlLink && /^https?:\/\//.test(jobUrl)) {
    jobUrlLink.href = jobUrl;
    jobUrlMeta.classList.remove('is-hidden');
  }

  renderHeader(job, match);
  renderMainContent(job, company, match);
  renderCoverLetter(cover, job);
  renderResumeTips(resume);
  renderInterviewPrep(company, job);
}

export async function loadApplicationData(): Promise<void> {
  const sessionId = getCurrentSessionId();
  if (!sessionId) {
    showError('No application ID provided');
    return;
  }

  try {
    const statusRes = await fetch(`${API_BASE}/workflow/status/${sessionId}`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });

    if (statusRes.status === 404) {
      showError('Application not found');
      return;
    }
    if (statusRes.status === 401) {
      window.location.href = getLoginUrl();
      return;
    }
    if (!statusRes.ok) throw new Error('Failed to load status');

    const statusData = (await statusRes.json()) as WorkflowStatusResponse;
    setWorkflowStatus(statusData.status ?? null);

    if (statusData.status && PROCESSING_STATUSES.has(statusData.status)) {
      setApplicationData(statusData as WorkflowResults);
      showProcessing(statusData.current_agent ?? null);
      return;
    }

    const resultsRes = await fetch(`${API_BASE}/workflow/results/${sessionId}`, {
      headers: { Authorization: `Bearer ${getAuthToken()}` },
    });

    if (resultsRes.ok) {
      setApplicationData((await resultsRes.json()) as WorkflowResults);
    } else {
      setApplicationData(statusData as WorkflowResults);
    }

    renderApplication();
  } catch (error) {
    const err = error instanceof Error ? error : new Error('Failed to load application');
    console.error('Error loading application:', err);
    showError(err.message);
  }
}
