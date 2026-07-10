import { BusEvents, getEventBus } from '../shared/bus';
import {
  TOAST_DISMISS_MS_ERROR,
  TOAST_DISMISS_MS_SUCCESS,
  getToastOutTimer,
  getToastRemoveTimer,
  setToastOutTimer,
  setToastRemoveTimer,
} from './state';

export type ApplicationToastType = 'success' | 'error';

export function showApplicationToast(
  message: string,
  type: ApplicationToastType = 'success',
): void {
  const notifType = type === 'success' ? 'success' : 'error';
  const dismissMs = type === 'success' ? TOAST_DISMISS_MS_SUCCESS : TOAST_DISMISS_MS_ERROR;

  const bus = getEventBus();
  if (bus) {
    const evtMap: Record<string, string> = {
      success: BusEvents.NOTIFY_SUCCESS,
      error: BusEvents.NOTIFY_ERROR,
    };
    bus.emit(evtMap[notifType] ?? BusEvents.NOTIFY_INFO, { message });
  }

  if (window.app && typeof window.app.showNotification === 'function') {
    window.app.showNotification(message, notifType);
    return;
  }

  const toast = document.createElement('div');
  const bg = type === 'success' ? '#10b981' : '#ef4444';
  toast.style.cssText =
    'position:fixed;bottom:20px;right:20px;max-width:min(420px,calc(100vw - 2rem));' +
    'line-height:1.5;background:' +
    bg +
    ';color:white;padding:.75rem 1.25rem;border-radius:8px;' +
    'z-index:9999;font-size:.85rem;animation:slideIn .3s ease;box-shadow:0 4px 16px rgba(0,0,0,.35)';
  toast.textContent = message;
  document.body.appendChild(toast);

  if (getToastOutTimer() !== null) clearTimeout(getToastOutTimer()!);
  if (getToastRemoveTimer() !== null) clearTimeout(getToastRemoveTimer()!);

  setToastOutTimer(
    window.setTimeout(() => {
      toast.style.animation = 'slideOut .3s ease';
      setToastRemoveTimer(
        window.setTimeout(() => {
          toast.remove();
          setToastRemoveTimer(null);
        }, 300),
      );
      setToastOutTimer(null);
    }, dismissMs),
  );
}

export function installToastAnimations(): void {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideIn {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
      from { transform: translateX(0); opacity: 1; }
      to { transform: translateX(100%); opacity: 0; }
    }
  `;
  document.head.appendChild(style);
}
