import { BusEvents, getEventBus } from './bus';
import { escapeHtml } from './dom-security';

export type NotifyType = 'success' | 'error' | 'warning' | 'info' | 'danger';

export interface NotifyOptions {
  scrollTop?: boolean;
  /** Replace #alertContainer contents instead of appending (new-application page). */
  replace?: boolean;
}

function normalizeNotifyType(type: NotifyType): 'success' | 'error' | 'warning' | 'info' {
  return type === 'danger' ? 'error' : type;
}

function emitBusNotify(type: 'success' | 'error' | 'warning' | 'info', message: string): void {
  const bus = getEventBus();
  if (!bus || !window.BusEvents) return;
  const evtMap: Record<string, string> = {
    success: BusEvents.NOTIFY_SUCCESS,
    error: BusEvents.NOTIFY_ERROR,
    warning: BusEvents.NOTIFY_WARNING,
    info: BusEvents.NOTIFY_INFO,
  };
  bus.emit(evtMap[type] ?? BusEvents.NOTIFY_INFO, { message });
}

/**
 * Show a notification — event bus, window.app, then #alertContainer fallback.
 */
export function notify(
  msg: string,
  type: NotifyType = 'info',
  options: boolean | NotifyOptions = {},
): void {
  const opts: NotifyOptions = typeof options === 'boolean' ? { scrollTop: options } : options;
  const notifType = normalizeNotifyType(type);

  emitBusNotify(notifType, msg);

  if (window.app && typeof window.app.showNotification === 'function') {
    window.app.showNotification(msg, notifType);
    return;
  }

  const c = document.getElementById('alertContainer');
  if (!c) return;

  const alertClass = notifType === 'error' ? 'danger' : notifType;
  const icon =
    notifType === 'error'
      ? 'exclamation-triangle'
      : notifType === 'success'
        ? 'check-circle'
        : 'info-circle';

  if (opts.replace) {
    c.innerHTML = `<div class="alert alert-${alertClass} alert-dismissible fade show" role="alert"><i class="fas fa-${icon} me-2"></i>${escapeHtml(msg)}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button></div>`;
    return;
  }

  const d = document.createElement('div');
  d.className = `alert alert-${alertClass} alert-dismissible fade show`;
  d.setAttribute('role', 'alert');
  d.innerHTML = `${escapeHtml(msg)}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
  c.appendChild(d);

  if (opts.scrollTop) {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  if (notifType !== 'error') {
    window.setTimeout(() => {
      d.classList.remove('show');
      window.setTimeout(() => d.remove(), 300);
    }, 6000);
  }
}
