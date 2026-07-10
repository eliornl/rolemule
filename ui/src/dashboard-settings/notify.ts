import { escapeHtml } from '../shared/dom-security';
import type { AlertType, NotifyOptions } from './types';

export function notify(
  message: string,
  type: AlertType = 'info',
  opts?: NotifyOptions,
): void {
  const loading = Boolean(opts?.loading);
  const notifType = type === 'danger' ? 'error' : type;
  const bus = window.eventBus;
  const busEvents = window.BusEvents;
  if (bus && busEvents) {
    const evtMap: Record<string, string> = {
      success: busEvents.NOTIFY_SUCCESS,
      error: busEvents.NOTIFY_ERROR,
      warning: busEvents.NOTIFY_WARNING,
      info: busEvents.NOTIFY_INFO,
    };
    bus.emit(evtMap[notifType] ?? busEvents.NOTIFY_INFO, { message });
  }
  const app = window.app;
  if (app && typeof app.showNotification === 'function') {
    app.showNotification(message, notifType);
    return;
  }
  const container = document.getElementById('alertContainer');
  if (!container) return;
  let iconClass = 'fa-info-circle';
  if (type === 'success') iconClass = 'fa-check-circle';
  else if (type === 'danger') iconClass = 'fa-exclamation-circle';
  else if (type === 'warning') iconClass = 'fa-exclamation-triangle';
  else if (loading) iconClass = 'fa-circle-notch fa-spin';
  container.innerHTML =
    `<div class="alert alert-${type} alert-dismissible fade show" role="alert">` +
    `<i class="fas ${iconClass} me-2" aria-hidden="true"></i>` +
    `${escapeHtml(message)}` +
    `<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Dismiss"></button>` +
    `</div>`;
}

export function showAlert(
  message: string,
  type: AlertType = 'info',
  opts?: NotifyOptions,
): void {
  notify(message, type, opts);
}
