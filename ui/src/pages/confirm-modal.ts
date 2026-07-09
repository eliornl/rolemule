/**
 * Migrated from ui/static/js/confirm-modal.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
/**
 * Shared confirmation modal — replaces all native confirm()/prompt() calls.
 * Exposes window.showConfirm() for use across all dashboard pages.
 *
 * @param {{ title: string, message: string, confirmText?: string, cancelText?: string,
 *           type?: 'danger'|'warning'|'primary', inputPlaceholder?: string,
 *           inputType?: string, requiredInput?: string }} opts
 * @returns {Promise<string|boolean|null>} null = cancelled, true = confirmed (no input), string = input value
 */
window.showConfirm = function showConfirm(opts) {
    'use strict';

    /** @param {string} str */
    function esc(str) {
        return String(str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    return new Promise((resolve) => {
        const existing = document.getElementById('sharedConfirmModal');
        if (existing) existing.remove();

        const btnClass     = opts.type === 'warning' ? 'btn-warning'
                           : opts.type === 'primary'  ? 'btn-primary'
                           : 'btn-danger';
        const hasInput     = !!opts.inputPlaceholder;
        const requiredInput = opts.requiredInput || null;
        const inputHtml = hasInput
            ? `<input type="${esc(opts.inputType || 'text')}" class="confirm-modal-input" id="sharedConfirmInput"
                 placeholder="${esc(opts.inputPlaceholder || '')}" autocomplete="off">`
            : '';

        const el = document.createElement('div');
        el.id = 'sharedConfirmModal';
        el.className = 'modal fade confirm-modal';
        el.setAttribute('tabindex', '-1');
        el.setAttribute('aria-modal', 'true');
        el.setAttribute('role', 'dialog');
        el.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header pb-0">
                        <h5 class="modal-title">${esc(opts.title)}</h5>
                    </div>
                    <div class="modal-body pt-2">
                        <p>${esc(opts.message)}</p>
                        ${inputHtml}
                    </div>
                    <div class="modal-footer pt-0">
                        <button type="button" class="btn btn-outline-secondary" id="sharedConfirmCancel">${esc(opts.cancelText || 'Cancel')}</button>
                        <button type="button" class="btn ${btnClass}" id="sharedConfirmOk"
                            ${requiredInput ? 'disabled' : ''}>${esc(opts.confirmText || 'Confirm')}</button>
                    </div>
                </div>
            </div>`;
        document.body.appendChild(el);

        // @ts-ignore
        const modal = new bootstrap.Modal(el);

        el.addEventListener('shown.bs.modal', () => {
            const inp = /** @type {HTMLInputElement|null} */ (document.getElementById('sharedConfirmInput'));
            if (inp) inp.focus();
        });
        el.addEventListener('hidden.bs.modal', () => el.remove());

        // Enable confirm button only when input matches the required value
        if (requiredInput && hasInput) {
            const okBtn = /** @type {HTMLButtonElement|null} */ (document.getElementById('sharedConfirmOk'));
            el.addEventListener('input', (e) => {
                const target = /** @type {HTMLInputElement} */ (e.target);
                if (target.id === 'sharedConfirmInput' && okBtn) {
                    okBtn.disabled = target.value !== requiredInput;
                }
            });
        }

        document.getElementById('sharedConfirmCancel')?.addEventListener('click', () => {
            modal.hide();
            resolve(null);
        });
        document.getElementById('sharedConfirmOk')?.addEventListener('click', () => {
            const inp = /** @type {HTMLInputElement|null} */ (document.getElementById('sharedConfirmInput'));
            modal.hide();
            resolve(hasInput ? (inp ? inp.value : '') : true);
        });

        modal.show();
    });
};
