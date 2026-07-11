/**
 * Standalone interview prep page entry.
 */
import { requireLogin } from '../shared/auth';
import { attachEventListeners } from '../interview-prep/listeners';
import { loadInterviewPrep } from '../interview-prep/load';
import {
  generateInterviewPrep,
  regenerateInterviewPrep,
} from '../interview-prep/generate';
import { setSessionId } from '../interview-prep/state-access';
import { showError } from '../interview-prep/ui';

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireLogin()) return;
  if (
    typeof window.syncProfileCompletionFromApi !== 'function' ||
    !(await window.syncProfileCompletionFromApi())
  ) {
    return;
  }

  const pathParts = window.location.pathname.split('/');
  const id = pathParts[pathParts.length - 1] || null;
  setSessionId(id);

  attachEventListeners();

  if (id) {
    void loadInterviewPrep();
  } else {
    showError('No session ID provided');
  }
});

window.generateInterviewPrep = () => {
  void generateInterviewPrep();
};
window.regenerateInterviewPrep = () => {
  void regenerateInterviewPrep();
};
