import type { ConfirmOptions } from './confirm';

function esc(str: string): string {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Bootstrap modal instance (loaded globally from base.html). */
interface BootstrapModal {
  hide(): void;
  show(): void;
}

declare const bootstrap: {
  Modal: new (el: Element) => BootstrapModal;
};

export function showConfirmModal(
  opts: ConfirmOptions,
): Promise<string | boolean | null> {
  return new Promise((resolve) => {
    const existing = document.getElementById('sharedConfirmModal');
    if (existing) existing.remove();

    const btnClass =
      opts.type === 'warning'
        ? 'btn-warning'
        : opts.type === 'primary'
          ? 'btn-primary'
          : 'btn-danger';
    const hasInput = Boolean(opts.inputPlaceholder);
    const requiredInput = opts.requiredInput ?? null;
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

    const modal = new bootstrap.Modal(el);

    el.addEventListener('shown.bs.modal', () => {
      const inp = document.getElementById('sharedConfirmInput') as HTMLInputElement | null;
      if (inp) inp.focus();
    });
    el.addEventListener('hidden.bs.modal', () => el.remove());

    if (requiredInput && hasInput) {
      const okBtn = document.getElementById('sharedConfirmOk') as HTMLButtonElement | null;
      el.addEventListener('input', (e) => {
        const target = e.target as HTMLInputElement;
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
      const inp = document.getElementById('sharedConfirmInput') as HTMLInputElement | null;
      modal.hide();
      resolve(hasInput ? (inp ? inp.value : '') : true);
    });

    modal.show();
  });
}

export function installConfirmModalGlobal(): void {
  window.showConfirm = showConfirmModal;
}
