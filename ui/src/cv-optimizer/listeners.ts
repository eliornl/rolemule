import {
  getEventListenersAttached,
  getCoverLetter,
  getOptimizedCv,
  setEventListenersAttached,
} from './state-access';
import { el } from './dom';
import { clipboardWrite } from './clipboard';
import { handleClear, handleDownloadOdt, handleStart } from './api';

export function attachEventListeners(): void {
  if (getEventListenersAttached()) return;
  const pane = el('cvOptimizeContent');
  if (!pane) return;

  pane.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    const actionEl = target.closest('[data-action]') as HTMLElement | null;
    if (!actionEl) return;

    const action = actionEl.getAttribute('data-action');
    if (action === 'startCvOptimization') void handleStart();
    else if (action === 'clearCvOptimization') void handleClear();
    else if (action === 'copyOptimizedCv') {
      clipboardWrite(getOptimizedCv(), 'Optimized CV copied!');
    } else if (action === 'copyCvoCoverLetter') {
      clipboardWrite(getCoverLetter(), 'Cover letter copied!');
    } else if (action === 'downloadOptimizedCvOdt') void handleDownloadOdt();
  });
  setEventListenersAttached(true);
}
