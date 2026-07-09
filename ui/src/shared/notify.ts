import { escapeHtml } from './dom-security';

export type NotifyType = 'success' | 'error' | 'warning' | 'info';

/**
 * Show a notification — prefers window.app, falls back to #alertContainer.
 */
export function notify(msg: string, type: NotifyType = 'info'): void {
  if (window.app && typeof window.app.showNotification === 'function') {
    window.app.showNotification(msg, type);
    return;
  }
  const c = document.getElementById('alertContainer');
  if (!c) return;
  const d = document.createElement('div');
  d.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
  d.innerHTML = `${escapeHtml(msg)}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
  c.appendChild(d);
  setTimeout(() => d.remove(), 5000);
}
