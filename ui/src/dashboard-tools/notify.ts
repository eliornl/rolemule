import { escapeHtml } from '../shared/dom-security';
import type { AlertType } from './types';

export function notify(message: string, type: AlertType = 'info'): void {
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
  const icon =
    type === 'success'
      ? 'check-circle'
      : type === 'danger'
        ? 'exclamation-triangle'
        : 'info-circle';
  container.innerHTML =
    `<div class="alert alert-${type} alert-dismissible fade show" role="alert">` +
    `<i class="fas fa-${icon} me-2"></i>${escapeHtml(message)}` +
    `<button type="button" class="btn-close" data-bs-dismiss="alert"></button>` +
    `</div>`;
}

export function showAlert(message: string, type: AlertType): void {
  notify(message, type);
}
