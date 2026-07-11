export interface ConfirmOptions {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  type?: 'danger' | 'warning' | 'primary';
  inputPlaceholder?: string;
  inputType?: string;
  requiredInput?: string;
}

/**
 * Typed wrapper around the global confirm modal (confirm-modal.js).
 */
export async function showConfirm(
  opts: ConfirmOptions,
): Promise<string | boolean | null> {
  if (typeof window.showConfirm !== 'function') {
    console.error('showConfirm is not loaded');
    return null;
  }
  return window.showConfirm(opts);
}
