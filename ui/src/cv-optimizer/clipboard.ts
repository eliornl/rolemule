import { notify } from './notify';

export function downloadTextFile(
  text: string,
  filename: string,
  mimeType: string,
): void {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function clipboardWrite(text: string, successMsg?: string): void {
  const msg = successMsg || 'Copied to clipboard!';
  const showSuccess = (): void => {
    notify(msg, 'success');
  };
  const fallback = (): void => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.className = 'clipboard-offscreen';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      document.execCommand('copy');
      showSuccess();
    } catch (e) {
      console.error('Clipboard fallback failed', e);
    }
    document.body.removeChild(ta);
  };
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(showSuccess, fallback);
  } else {
    fallback();
  }
}
