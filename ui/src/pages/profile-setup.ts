/**
 * Profile setup page entry — DOM init, navigation wiring, global exports.
 */
import { exchangeOAuthCodeIfPresent } from '../profile-setup/api';
import { checkAuthentication, logout } from '../profile-setup/auth';
import { completeProfile } from '../profile-setup/complete';
import {
  checkPreferencesStep,
  changeStep,
  goToNextStep,
  goToPrevStep,
  updateProgressBar,
  updateStepDisplay,
  updateStepIndicators,
} from '../profile-setup/navigation';
import {
  loadUserData,
  onlyCareerPreferencesMissing,
} from '../profile-setup/populate';
import {
  autoFillProfile,
  checkApiKeyStatus,
  setupInlineApiKey,
} from '../profile-setup/resume-upload';
import { initializeEventListeners } from '../profile-setup/listeners';
import { pageAbortController } from '../profile-setup/state';
import { nextBtn, prevBtn, completeBtn } from '../profile-setup/dom';
import { removeSkill } from '../profile-setup/skills';
import {
  removeWorkExperience,
  updateWorkExperience,
} from '../profile-setup/work-experience';

document.addEventListener('DOMContentLoaded', async () => {
  await exchangeOAuthCodeIfPresent();
  checkAuthentication();

  const urlParams = new URLSearchParams(window.location.search);
  const isEditMode = urlParams.get('edit') === 'true';
  const fromResume = urlParams.get('fromResume') === 'true';

  if (
    !isEditMode &&
    !fromResume &&
    localStorage.getItem('profile_completed') === 'true'
  ) {
    window.location.href = '/dashboard';
    return;
  }

  const profilePayload = await loadUserData();
  const completionStatus = profilePayload?.completion_status;

  initializeEventListeners();
  updateStepDisplay();

  nextBtn?.addEventListener('click', goToNextStep);
  prevBtn?.addEventListener('click', goToPrevStep);
  completeBtn?.addEventListener('click', () => {
    void completeProfile();
  });
  document.getElementById('logout-btn')?.addEventListener('click', logout);

  const skipResumeBtn = document.getElementById('skip-resume-btn');
  if (skipResumeBtn) {
    skipResumeBtn.addEventListener('click', () => {
      changeStep(1);
    });
  }

  void checkApiKeyStatus();
  setupInlineApiKey();

  if (fromResume) {
    const parsedData = sessionStorage.getItem('parsedResumeData');
    if (parsedData) {
      try {
        const resumeData = JSON.parse(parsedData) as Record<string, unknown>;
        await autoFillProfile(resumeData);
        sessionStorage.removeItem('parsedResumeData');
      } catch (e) {
        console.error('Failed to parse resume data:', e);
      }
    }
  }

  const returningUser =
    isEditMode ||
    (completionStatus &&
      !completionStatus.profile_completed &&
      (completionStatus.completion_percentage ?? 0) > 0);

  if (returningUser) {
    const targetStep = onlyCareerPreferencesMissing(completionStatus) ? 5 : 1;
    requestAnimationFrame(() => changeStep(targetStep));

    const headerTitle = document.querySelector('.sidebar h2');
    if (headerTitle) {
      headerTitle.textContent = 'Edit Your Profile';
    }
  }

  updateStepIndicators();
  updateProgressBar();
  checkPreferencesStep();
  updateStepDisplay();
});

window.addEventListener('beforeunload', () => {
  pageAbortController.abort();
});

window.removeSkill = removeSkill;
window.removeWorkExperience = removeWorkExperience;
window.updateWorkExperience = updateWorkExperience;
window.logout = logout;
