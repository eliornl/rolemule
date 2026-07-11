import type { EventHandler, EventBusEvent } from './bus';
import { BusEvents } from './bus';

export class EventBusImpl {
  private readonly _listeners = new Map<string, Set<EventHandler>>();
  private readonly _onceListeners = new Map<string, Set<EventHandler>>();

  on(event: string, callback: EventHandler): () => void {
    if (!this._listeners.has(event)) {
      this._listeners.set(event, new Set());
    }
    this._listeners.get(event)!.add(callback);
    return () => this.off(event, callback);
  }

  once(event: string, callback: EventHandler): void {
    if (!this._onceListeners.has(event)) {
      this._onceListeners.set(event, new Set());
    }
    this._onceListeners.get(event)!.add(callback);
  }

  off(event: string, callback: EventHandler): void {
    this._listeners.get(event)?.delete(callback);
    this._onceListeners.get(event)?.delete(callback);
  }

  emit(event: string, data?: unknown): void {
    const eventObj: EventBusEvent = { type: event, data, timestamp: Date.now() };

    this._listeners.get(event)?.forEach((cb) => {
      try {
        cb(eventObj);
      } catch (err) {
        console.error(`[EventBus] Error in handler for "${event}":`, err);
      }
    });

    const once = this._onceListeners.get(event);
    if (once && once.size > 0) {
      once.forEach((cb) => {
        try {
          cb(eventObj);
        } catch (err) {
          console.error(`[EventBus] Error in once-handler for "${event}":`, err);
        }
      });
      this._onceListeners.delete(event);
    }
  }

  clear(event?: string): void {
    if (event) {
      this._listeners.delete(event);
      this._onceListeners.delete(event);
    } else {
      this._listeners.clear();
      this._onceListeners.clear();
    }
  }
}

export function installEventBusGlobals(): void {
  window.eventBus = new EventBusImpl();
  window.BusEvents = BusEvents;
}
