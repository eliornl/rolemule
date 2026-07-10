import { el } from './dom';

export function showLoading(text = 'Generating...'): void {
  const loadingEl = el('loadingText');
  if (loadingEl) loadingEl.textContent = text;
  el('loadingOverlay')?.classList.add('show');
}

export function hideLoading(): void {
  el('loadingOverlay')?.classList.remove('show');
}
