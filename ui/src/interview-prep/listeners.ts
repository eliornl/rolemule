import {
  generateInterviewPrep,
  regenerateInterviewPrep,
} from './generate';
import { stopPolling } from './poll';
import { disconnectWs } from './websocket';

export function attachEventListeners(): void {
  document.addEventListener('click', (e) => {
    const actionEl = (e.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!actionEl) return;
    switch (actionEl.dataset.action) {
      case 'generate-interview-prep':
        void generateInterviewPrep();
        break;
      case 'regenerate-interview-prep':
        void regenerateInterviewPrep();
        break;
      case 'print-page':
        window.print();
        break;
      default:
        break;
    }
  });

  window.addEventListener('beforeunload', () => {
    stopPolling();
    disconnectWs();
  });
}
