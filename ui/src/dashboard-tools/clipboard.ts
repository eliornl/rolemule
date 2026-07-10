import { notify } from './notify';
import { el } from './dom';

export function clipboardWrite(text: string, successMsg = 'Copied to clipboard!'): void {
  const app = window.app;
  if (app && typeof app.copyToClipboard === 'function') {
    app.copyToClipboard(text);
    notify(successMsg, 'success');
    return;
  }

  const doFallback = (): void => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0;pointer-events:none';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
      document.execCommand('copy');
      notify(successMsg || 'Copied!', 'success');
    } catch {
      notify('Copy failed — please select and copy manually.', 'danger');
    }
    document.body.removeChild(ta);
  };

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard
      .writeText(text)
      .then(() => notify(successMsg || 'Copied!', 'success'))
      .catch(doFallback);
  } else {
    doFallback();
  }
}

export function copyToClipboard(elementId: string): void {
  const node = el(elementId);
  clipboardWrite(node?.textContent ?? node?.innerText ?? '', 'Copied to clipboard!');
}

export function copyEmailParts(
  subjectId: string,
  bodyId: string,
  successMsg = 'Email copied to clipboard!',
): void {
  const subjectText = (el(subjectId)?.textContent ?? '').trim();
  const bodyText = (el(bodyId)?.textContent ?? '').trim();
  const parts: string[] = [];
  if (subjectText) parts.push(`Subject: ${subjectText}`);
  if (bodyText) parts.push(bodyText);
  clipboardWrite(parts.join('\n\n'), successMsg);
}
