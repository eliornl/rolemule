/**
 * Settings page entry — tabs, preferences auto-save, API keys, account actions.
 */
import { requireLogin } from '../shared/auth';
import {
  deleteApiKey,
  toggleApiKeyVisibility,
  validateApiKey,
} from '../dashboard-settings/api-keys';
import { attachEventListeners, initSettingsPage } from '../dashboard-settings/listeners';
import { showSection } from '../dashboard-settings/navigation';
import {
  togglePasswordField,
  togglePasswordSection,
} from '../dashboard-settings/password';
import {
  clearAllData,
  deleteAccount,
  exportData,
  restartOnboarding,
} from '../dashboard-settings/privacy';
import { handleResumeUpload } from '../dashboard-settings/resume';

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireLogin()) return;
  if (
    typeof window.syncProfileCompletionFromApi !== 'function' ||
    !(await window.syncProfileCompletionFromApi())
  ) {
    return;
  }

  attachEventListeners();
  await initSettingsPage();
});

window.clearAllData = clearAllData;
window.deleteAccount = deleteAccount;
window.deleteApiKey = deleteApiKey;
window.exportData = exportData;
window.handleResumeUpload = (input: HTMLInputElement) => {
  void handleResumeUpload(input);
};
window.restartOnboarding = restartOnboarding;
window.showSection = showSection;
window.toggleApiKeyVisibility = toggleApiKeyVisibility;
window.togglePasswordField = togglePasswordField;
window.togglePasswordSection = togglePasswordSection;
window.validateApiKey = () => {
  void validateApiKey();
};
