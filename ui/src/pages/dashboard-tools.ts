/**
 * Career tools page entry — six on-demand AI tools with tab navigation.
 */
import { requireLogin } from '../shared/auth';
import { copyAllScripts } from '../dashboard-tools/salary';
import { copyToClipboard } from '../dashboard-tools/clipboard';
import { toggleJob3 } from '../dashboard-tools/comparison';
import { copyFollowupEmail } from '../dashboard-tools/followup';
import { attachEventListeners } from '../dashboard-tools/listeners';
import { showTool } from '../dashboard-tools/navigation';
import { copyReferenceEmail } from '../dashboard-tools/reference';
import { copyFollowUpTemplate } from '../dashboard-tools/rejection';
import { copyThankYouNote } from '../dashboard-tools/thank-you';

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireLogin()) return;
  if (
    typeof window.syncProfileCompletionFromApi !== 'function' ||
    !(await window.syncProfileCompletionFromApi())
  ) {
    return;
  }

  attachEventListeners();
});

window.copyAllScripts = copyAllScripts;
window.copyFollowupEmail = copyFollowupEmail;
window.copyThankYouNote = copyThankYouNote;
window.copyFollowUpTemplate = copyFollowUpTemplate;
window.copyReferenceEmail = copyReferenceEmail;
window.copyToClipboard = copyToClipboard;
window.showTool = showTool;
window.toggleJob3 = toggleJob3;
