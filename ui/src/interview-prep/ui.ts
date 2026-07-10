import { escapeHtml } from '../shared/dom-security';
import { el, setVisible } from './dom';

export type InterviewPrepUiState = 'loading' | 'generate' | 'generating' | 'content';

export function showState(state: InterviewPrepUiState): void {
  setVisible('loadingState', state === 'loading');
  setVisible('generateState', state === 'generate');
  setVisible('generatingState', state === 'generating');
  setVisible('mainContent', state === 'content');
}

export function showError(message: string): void {
  showState('generate');
  const container = el('generateState')?.querySelector('.section-card');
  if (container) {
    container.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-exclamation-triangle fa-4x text-danger mb-4"></i>
                    <h3>Error</h3>
                    <p class="text-muted mb-4">${escapeHtml(message)}</p>
                    <a href="/dashboard" class="btn btn-primary"><i class="fas fa-arrow-left me-2"></i>Back to Dashboard</a>
                </div>`;
  }
}
