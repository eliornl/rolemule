export type NotifyType = 'success' | 'error' | 'warning' | 'info';

export function notify(message: string, type?: NotifyType): void {
  const toastType = type === 'success' ? 'success' : 'error';
  if (typeof window.showApplicationToast === 'function') {
    window.showApplicationToast(message, toastType);
    return;
  }
  const dismissMs = toastType === 'success' ? 4000 : 8000;
  const toast = document.createElement('div');
  toast.style.cssText =
    'position:fixed;bottom:20px;right:20px;max-width:min(420px,calc(100vw - 2rem));' +
    'line-height:1.5;background:' +
    (toastType === 'success' ? '#10b981' : '#ef4444') +
    ';color:white;padding:.75rem 1.25rem;border-radius:8px;z-index:9999;font-size:.85rem;' +
    'box-shadow:0 4px 16px rgba(0,0,0,.35)';
  toast.textContent = message;
  document.body.appendChild(toast);
  window.setTimeout(() => {
    toast.remove();
  }, dismissMs);
}
