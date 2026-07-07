/**
 * @fileoverview Lightweight event bus for decoupled cross-module communication.
 *
 * Usage:
 *   window.eventBus.on('auth:logout', handler)
 *   window.eventBus.emit('auth:logout', { reason: 'token_expired' })
 *   window.eventBus.off('auth:logout', handler)
 *   window.eventBus.once('workflow:complete', handler)
 */

/**
 * @typedef {Object} EventBusEvent
 * @property {string} type
 * @property {unknown} data
 * @property {number} timestamp
 */

/** @typedef {(event: EventBusEvent) => void} EventHandler */

class EventBus {
    constructor() {
        /** @type {Map<string, Set<EventHandler>>} */
        this._listeners = new Map();

        /** @type {Map<string, Set<EventHandler>>} */
        this._onceListeners = new Map();
    }

    /**
     * Subscribe to an event.
     * @param {string} event
     * @param {EventHandler} callback
     * @returns {() => void} Unsubscribe function
     */
    on(event, callback) {
        if (!this._listeners.has(event)) {
            this._listeners.set(event, new Set());
        }
        const listeners = this._listeners.get(event);
        if (listeners) {
            listeners.add(callback);
        }
        return () => this.off(event, callback);
    }

    /**
     * Subscribe to an event once; auto-unsubscribes after first call.
     * @param {string} event
     * @param {EventHandler} callback
     */
    once(event, callback) {
        if (!this._onceListeners.has(event)) {
            this._onceListeners.set(event, new Set());
        }
        /** @type {Set<EventHandler>} */ (this._onceListeners.get(event)).add(callback);
    }

    /**
     * Unsubscribe from an event.
     * @param {string} event
     * @param {EventHandler} callback
     */
    off(event, callback) {
        this._listeners.get(event)?.delete(callback);
        this._onceListeners.get(event)?.delete(callback);
    }

    /**
     * Emit an event to all subscribers.
     * @param {string} event
     * @param {unknown} [data]
     */
    emit(event, data) {
        /** @type {EventBusEvent} */
        const eventObj = { type: event, data, timestamp: Date.now() };

        this._listeners.get(event)?.forEach(cb => {
            try { cb(eventObj); } catch (err) {
                console.error(`[EventBus] Error in handler for "${event}":`, err);
            }
        });

        const once = this._onceListeners.get(event);
        if (once && once.size > 0) {
            once.forEach(cb => {
                try { cb(eventObj); } catch (err) {
                    console.error(`[EventBus] Error in once-handler for "${event}":`, err);
                }
            });
            this._onceListeners.delete(event);
        }
    }

    /**
     * Remove all listeners for one event, or all if no event given.
     * @param {string} [event]
     */
    clear(event) {
        if (event) {
            this._listeners.delete(event);
            this._onceListeners.delete(event);
        } else {
            this._listeners.clear();
            this._onceListeners.clear();
        }
    }
}

// =============================================================================
// KNOWN EVENT NAMES
// =============================================================================

/** @enum {string} */
const BusEvents = {
    // Auth lifecycle
    AUTH_LOGIN:           'auth:login',
    AUTH_LOGOUT:          'auth:logout',
    AUTH_SESSION_SET:     'auth:session_set',
    AUTH_TOKEN_REFRESHED: 'auth:token_refreshed',
    AUTH_REGISTER:        'auth:register',

    // Workflow lifecycle
    WORKFLOW_STARTED:     'workflow:started',
    WORKFLOW_PROGRESS:    'workflow:progress',
    WORKFLOW_COMPLETE:    'workflow:complete',
    WORKFLOW_ERROR:       'workflow:error',
    WORKFLOW_GATE_FAIL:   'workflow:gate_fail',
    WORKFLOW_CANCELLED:   'workflow:cancelled',

    // Profile
    PROFILE_UPDATED:      'profile:updated',
    PROFILE_SAVED:        'profile:saved',
    PROFILE_SETUP_COMPLETE: 'profile:setup_complete',

    // Application CRUD
    APPLICATION_CREATED:  'application:created',
    APPLICATION_UPDATED:  'application:updated',
    APPLICATION_DELETED:  'application:deleted',
    APPLICATION_STATUS_CHANGED: 'application:status_changed',

    // Career tools
    TOOL_GENERATED:       'tool:generated',
    TOOL_ERROR:           'tool:error',

    // API key (BYOK)
    APIKEY_SAVED:         'apikey:saved',
    APIKEY_DELETED:       'apikey:deleted',

    // Settings
    SETTINGS_UPDATED:     'settings:updated',

    // Notifications
    NOTIFY_SUCCESS:       'notify:success',
    NOTIFY_ERROR:         'notify:error',
    NOTIFY_WARNING:       'notify:warning',
    NOTIFY_INFO:          'notify:info',
};

// @ts-ignore – extending window with app globals
window.eventBus = new EventBus();
// @ts-ignore
window.BusEvents = BusEvents;
