import { getApiBase } from '../shared/auth';
import { getAuthHeaders } from './api';
import {
  getSessionId,
  setInterviewPrepData,
} from './state-access';
import { renderInterviewPrep } from './render';
import { showError, showState } from './ui';
import type {
  InterviewPrepLoadResponse,
  WorkflowResultsResponse,
} from './types';

export async function loadJobInfo(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;
  try {
    const response = await fetch(`${getApiBase()}/workflow/results/${sessionId}`, {
      headers: getAuthHeaders(),
    });
    if (response.ok) {
      const data = (await response.json()) as WorkflowResultsResponse;
      if (data.job_analysis) {
        const titleEl = document.getElementById('jobTitle');
        const compEl = document.getElementById('companyName');
        if (titleEl) {
          titleEl.textContent = `Interview Prep: ${data.job_analysis.job_title || 'Position'}`;
        }
        if (compEl) compEl.textContent = data.job_analysis.company_name || '';
      }
    }
  } catch (error) {
    console.error('Error loading job info:', error);
  }
}

export async function loadInterviewPrep(): Promise<void> {
  const sessionId = getSessionId();
  if (!sessionId) return;
  showState('loading');
  try {
    const response = await fetch(`${getApiBase()}/interview-prep/${sessionId}`, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) {
      if (response.status === 404) {
        showError('Session not found');
        return;
      }
      throw new Error('Failed to load interview prep');
    }
    const data = (await response.json()) as InterviewPrepLoadResponse;
    if (data.has_interview_prep && data.interview_prep) {
      setInterviewPrepData(data.interview_prep);
      await loadJobInfo();
      renderInterviewPrep();
      showState('content');
    } else {
      showState('generate');
    }
  } catch (error) {
    const err = error as Error;
    console.error('Error loading interview prep:', err);
    showError(`Failed to load interview prep: ${err.message}`);
  }
}
