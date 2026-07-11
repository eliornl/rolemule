import { getApiBase, getAuthToken } from '../shared/auth';
import {
  apiErrorMessage,
  formatWorkflowFailureDetailForPage,
  workflowFailureMessage,
} from './errors';
import { loadApplicationData } from './load';
import { renderCoverLetter } from './render-cover-letter';
import { renderRichInterviewPrep } from './render-interview';
import { renderResumeTips, renderResumeTipsEmptyState } from './render-resume';
import {
  getApplicationData,
  getCurrentSessionId,
  getProcessingRefreshTimer,
  isContinuingWorkflow,
  isGeneratingInterviewPrep,
  isRegeneratingCoverLetter,
  isRegeneratingResume,
  patchApplicationData,
  setContinuingWorkflow,
  setGeneratingInterviewPrep,
  setProcessingRefreshTimer,
  setRegeneratingCoverLetter,
  setRegeneratingResume,
  setWorkflowStatus,
} from './state';
import { showApplicationToast } from './toast';
import type {
  CompanyResearch,
  CoverLetter,
  GenerateDocKind,
  InterviewPrep,
  JobAnalysis,
  ResumeRecommendations,
} from './types';

const API_BASE = getApiBase();
const showToast = showApplicationToast;

function jobAnalysisFromState(): JobAnalysis {
  return (getApplicationData()?.job_analysis as JobAnalysis | undefined) ?? {};
}

export async function generateSingle(
  which: GenerateDocKind,
  btn: HTMLButtonElement,
): Promise<void> {
  const sessionId = getCurrentSessionId();
  if (!sessionId) return;

  btn.disabled = true;
  btn.classList.add('loading');
  const endpoint =
    which === 'cover'
      ? `${API_BASE}/workflow/regenerate-cover-letter/${sessionId}`
      : `${API_BASE}/workflow/regenerate-resume/${sessionId}`;
  const job = jobAnalysisFromState();

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
    });

    if (res.status === 429) {
      const errData = await res.json().catch(() => ({}));
      showToast(apiErrorMessage(errData, 'Rate limit reached. Try again in a few minutes.'), 'error');
      if (which === 'resume') {
        patchApplicationData({ resume_recommendations: undefined });
        renderResumeTipsEmptyState();
      } else {
        patchApplicationData({ cover_letter: undefined });
        renderCoverLetter({}, job);
      }
      return;
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(apiErrorMessage(errData, 'Generation failed'));
    }

    showToast(which === 'cover' ? 'Cover letter generated!' : 'Resume tips generated!');
    await loadApplicationData();
  } catch (error) {
    const err = error instanceof Error ? error : new Error('Generation failed');
    const toastMsg =
      formatWorkflowFailureDetailForPage(err.message) || err.message || 'Generation failed';
    showToast(toastMsg, 'error');
    if (which === 'resume') {
      patchApplicationData({ resume_recommendations: undefined });
      renderResumeTipsEmptyState();
    } else {
      patchApplicationData({ cover_letter: undefined });
      renderCoverLetter({}, job);
    }
  } finally {
    btn.disabled = false;
    btn.classList.remove('loading');
  }
}

export async function continueWorkflow(): Promise<void> {
  const sessionId = getCurrentSessionId();
  if (!sessionId || isContinuingWorkflow()) return;

  setContinuingWorkflow(true);

  const btn = document.getElementById('continueWorkflowBtn') as HTMLButtonElement | null;
  if (btn) {
    btn.disabled = true;
    btn.classList.add('loading');
  }

  showToast('Running full analysis — this may take a minute…');

  try {
    const res = await fetch(`${API_BASE}/workflow/continue/${sessionId}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
    });

    if (res.status === 429) {
      showToast('Rate limit reached. Please try again later.', 'error');
      return;
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(apiErrorMessage(errData, 'Failed to continue workflow'));
    }

    let attempts = 0;
    const maxAttempts = 40;

    const poll = async (): Promise<void> => {
      if (attempts >= maxAttempts) {
        showToast(
          'Analysis is taking longer than expected. Refresh the page to check progress.',
          'error',
        );
        setContinuingWorkflow(false);
        return;
      }
      attempts++;

      try {
        const sr = await fetch(`${API_BASE}/workflow/status/${sessionId}`, {
          headers: { Authorization: `Bearer ${getAuthToken()}` },
        });
        if (sr.ok) {
          const sd = (await sr.json()) as { status?: string; error_messages?: string[] };
          if (sd.status === 'completed' || sd.status === 'analysis_complete') {
            showToast('Analysis complete!');
            setContinuingWorkflow(false);
            setWorkflowStatus(sd.status ?? null);
            await loadApplicationData();
            return;
          }
          if (sd.status === 'failed') {
            showToast(
              workflowFailureMessage(sd.error_messages, 'Analysis failed. Please try again.'),
              'error',
            );
            setContinuingWorkflow(false);
            if (btn) {
              btn.disabled = false;
              btn.classList.remove('loading');
            }
            return;
          }
        }
      } catch (pollErr) {
        console.debug('Workflow poll error', pollErr);
      }

      if (getProcessingRefreshTimer() !== null) {
        clearTimeout(getProcessingRefreshTimer()!);
      }
      setProcessingRefreshTimer(window.setTimeout(() => {
        void poll();
      }, 3000));
    };

    if (getProcessingRefreshTimer() !== null) {
      clearTimeout(getProcessingRefreshTimer()!);
    }
    setProcessingRefreshTimer(
      window.setTimeout(() => {
        void poll();
      }, 3000),
    );
  } catch (error) {
    const err = error instanceof Error ? error : new Error('Failed to continue workflow');
    showToast(err.message || 'Failed to continue workflow', 'error');
    setContinuingWorkflow(false);
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('loading');
    }
  }
}

export async function regenerateCoverLetter(btn: HTMLButtonElement): Promise<void> {
  const sessionId = getCurrentSessionId();
  if (!sessionId || isRegeneratingCoverLetter()) return;

  setRegeneratingCoverLetter(true);
  btn.classList.add('loading');
  btn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/workflow/regenerate-cover-letter/${sessionId}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
    });

    if (res.status === 429) {
      const errData = await res.json().catch(() => ({}));
      showToast(apiErrorMessage(errData, 'Rate limit reached. Try again in a few minutes.'), 'error');
      return;
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(apiErrorMessage(errData, 'Failed to regenerate cover letter'));
    }

    const data = (await res.json()) as { cover_letter?: CoverLetter };
    const letter =
      data.cover_letter?.content ||
      data.cover_letter?.cover_letter_text ||
      '';

    if (letter) {
      const cltEl = document.getElementById('coverLetterText');
      if (cltEl) cltEl.textContent = letter;
      patchApplicationData({ cover_letter: data.cover_letter });
      showToast('Cover letter regenerated!');
    } else {
      showToast('Regeneration returned empty result', 'error');
    }
  } catch (error) {
    console.error('Error regenerating:', error);
    const err = error instanceof Error ? error : new Error('Failed to regenerate cover letter');
    showToast(err.message || 'Failed to regenerate cover letter', 'error');
  } finally {
    btn.classList.remove('loading');
    btn.disabled = false;
    setRegeneratingCoverLetter(false);
  }
}

export async function regenerateResume(btn: HTMLButtonElement): Promise<void> {
  const sessionId = getCurrentSessionId();
  if (!sessionId || isRegeneratingResume()) return;

  setRegeneratingResume(true);
  btn.classList.add('loading');
  btn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/workflow/regenerate-resume/${sessionId}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
    });

    if (res.status === 429) {
      const errData = await res.json().catch(() => ({}));
      showToast(apiErrorMessage(errData, 'Rate limit reached. Try again in a few minutes.'), 'error');
      patchApplicationData({ resume_recommendations: undefined });
      renderResumeTipsEmptyState();
      return;
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(apiErrorMessage(errData, 'Failed to regenerate resume advice'));
    }

    const data = (await res.json()) as { result?: ResumeRecommendations };
    patchApplicationData({ resume_recommendations: data.result });
    if (data.result) {
      renderResumeTips(data.result);
    } else {
      renderResumeTipsEmptyState();
    }
    showToast('Resume advice regenerated!');
  } catch (error) {
    console.error('Error regenerating resume:', error);
    const err = error instanceof Error ? error : new Error('Failed to regenerate resume advice');
    const toastMsg =
      formatWorkflowFailureDetailForPage(err.message) ||
      err.message ||
      'Failed to regenerate resume advice';
    showToast(toastMsg, 'error');
    patchApplicationData({ resume_recommendations: undefined });
    renderResumeTipsEmptyState();
  } finally {
    btn.classList.remove('loading');
    btn.disabled = false;
    setRegeneratingResume(false);
  }
}

export async function generateInterviewPrep(btn?: HTMLButtonElement): Promise<void> {
  const sessionId = getCurrentSessionId();
  if (!sessionId || isGeneratingInterviewPrep()) return;

  setGeneratingInterviewPrep(true);
  if (btn) {
    btn.classList.add('loading');
    btn.disabled = true;
  }

  try {
    const res = await fetch(`${API_BASE}/workflow/generate-interview-prep/${sessionId}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json',
      },
    });

    if (res.status === 429) {
      const errData = await res.json().catch(() => ({}));
      showToast(apiErrorMessage(errData, 'Rate limit reached. Try again in a few minutes.'), 'error');
      return;
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(apiErrorMessage(errData, 'Failed to generate interview preparation'));
    }

    const data = (await res.json()) as { result?: InterviewPrep };
    const appData = getApplicationData();
    if (appData && data.result) {
      const existing = (appData.company_research as CompanyResearch | undefined) ?? {};
      patchApplicationData({
        company_research: {
          ...existing,
          interview_preparation: data.result,
        },
      });
    }
    if (data.result) {
      renderRichInterviewPrep(data.result);
    }
    showToast('Interview preparation generated!');
  } catch (error) {
    console.error('Error generating interview prep:', error);
    const err =
      error instanceof Error ? error : new Error('Failed to generate interview preparation');
    showToast(err.message || 'Failed to generate interview preparation', 'error');
  } finally {
    if (btn) {
      btn.classList.remove('loading');
      btn.disabled = false;
    }
    setGeneratingInterviewPrep(false);
  }
}
