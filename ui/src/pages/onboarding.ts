/**
 * Onboarding tutorial — auto-shows on dashboard for new users.
 */
import { Onboarding } from '../onboarding/manager';

function maybeInitOnboarding(): void {
  if (!window.location.pathname.includes('/dashboard')) return;
  void Onboarding.init();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', maybeInitOnboarding);
} else {
  maybeInitOnboarding();
}

window.Onboarding = Onboarding;
