import { getAuthToken } from '../shared/auth';
import { ALL_STEPS } from './steps';
import { getActiveSteps, setActiveSteps } from './state';
import {
  ONBOARDING_KEY,
  ONBOARDING_VERSION,
  type ApiKeyStatusResponse,
  type ApplicationStatsOverview,
  type OnboardingCompletionRecord,
  type OnboardingController,
} from './types';

function markComplete(): void {
  try {
    const record: OnboardingCompletionRecord = {
      version: ONBOARDING_VERSION,
      completedAt: new Date().toISOString(),
    };
    localStorage.setItem(ONBOARDING_KEY, JSON.stringify(record));
  } catch (e) {
    console.warn('Could not save onboarding status:', e);
  }
}

function clearHighlights(): void {
  document.querySelectorAll('.onboarding-highlight').forEach((el) => {
    el.classList.remove('onboarding-highlight');
  });
}

function destroyOverlay(controller: OnboardingController): void {
  clearHighlights();
  if (controller.overlay) {
    controller.overlay.classList.remove('visible');
    const overlay = controller.overlay;
    window.setTimeout(() => {
      overlay.remove();
      controller.overlay = null;
      controller.modal = null;
    }, 300);
  }
}

function createOverlay(controller: OnboardingController): void {
  const overlay = document.createElement('div');
  overlay.id = 'onboarding-overlay';
  overlay.innerHTML = `
                <div class="onboarding-modal" id="onboarding-modal">
                    <div class="onboarding-image" id="onboarding-image"></div>
                    <div class="onboarding-content">
                        <h2 class="onboarding-title" id="onboarding-title"></h2>
                        <div class="onboarding-body" id="onboarding-body"></div>
                    </div>
                    <div class="onboarding-progress" id="onboarding-progress"></div>
                    <div class="onboarding-actions">
                        <button class="onboarding-btn onboarding-btn-skip" data-action="onboarding-skip">
                            Skip Tour
                        </button>
                        <div class="onboarding-nav">
                            <button class="onboarding-btn onboarding-btn-prev" id="onboarding-prev" data-action="onboarding-prev">
                                <i class="fas fa-arrow-left"></i> Back
                            </button>
                            <button class="onboarding-btn onboarding-btn-next" id="onboarding-next" data-action="onboarding-next">
                                Next <i class="fas fa-arrow-right"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
  document.body.appendChild(overlay);
  controller.overlay = overlay;
  controller.modal = document.getElementById('onboarding-modal');

  overlay.addEventListener('click', (e) => {
    const actionEl = (e.target as HTMLElement).closest<HTMLElement>('[data-action]');
    if (!actionEl) return;
    switch (actionEl.dataset.action) {
      case 'onboarding-skip':
        controller.skip();
        break;
      case 'onboarding-prev':
        controller.prev();
        break;
      case 'onboarding-next':
        controller.next();
        break;
      default:
        break;
    }
  });

  window.setTimeout(() => {
    overlay.classList.add('visible');
  }, 10);
}

function renderStep(controller: OnboardingController): void {
  const steps = getActiveSteps();
  const step = steps[controller.currentStep];

  const imgEl = document.getElementById('onboarding-image');
  const titleEl = document.getElementById('onboarding-title');
  const bodyEl = document.getElementById('onboarding-body');
  const progressEl = document.getElementById('onboarding-progress');
  const prevBtn = document.getElementById('onboarding-prev');
  const nextBtn = document.getElementById('onboarding-next');

  if (!imgEl || !titleEl || !bodyEl || !progressEl || !prevBtn || !nextBtn || !step) {
    return;
  }

  imgEl.textContent = step.image;
  titleEl.textContent = step.title;
  bodyEl.innerHTML = step.content;

  progressEl.innerHTML = steps
    .map(
      (s, i) =>
        `<span class="progress-dot ${i === controller.currentStep ? 'active' : ''} ${i < controller.currentStep ? 'completed' : ''}"></span>`,
    )
    .join('');

  prevBtn.style.visibility = controller.currentStep === 0 ? 'hidden' : 'visible';

  if (controller.currentStep === steps.length - 1) {
    nextBtn.innerHTML = 'Get Started <i class="fas fa-check"></i>';
  } else {
    nextBtn.innerHTML = 'Next <i class="fas fa-arrow-right"></i>';
  }

  clearHighlights();
  if (step.highlight) {
    document.querySelector(step.highlight)?.classList.add('onboarding-highlight');
  }
}

async function userHasExistingApplications(): Promise<boolean> {
  try {
    const token = getAuthToken();
    if (!token) return false;
    const res = await fetch('/api/v1/applications/stats/overview', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return false;
    const stats = (await res.json()) as ApplicationStatsOverview;
    return (stats.total_applications || 0) > 0;
  } catch (e) {
    console.warn('Could not check application stats for onboarding:', e);
    return false;
  }
}

async function checkServerApiKey(): Promise<boolean> {
  try {
    const token = getAuthToken();
    const res = await fetch('/api/v1/profile/api-key/status', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return false;
    const data = (await res.json()) as ApiKeyStatusResponse;
    return Boolean(data.has_user_key || data.server_has_key || data.use_vertex_ai);
  } catch (e) {
    console.warn('Could not check API key status:', e);
    return false;
  }
}

export const Onboarding: OnboardingController = {
  currentStep: 0,
  overlay: null,
  modal: null,
  serverHasApiKey: false,

  shouldShow(): boolean {
    try {
      return !localStorage.getItem(ONBOARDING_KEY);
    } catch {
      return true;
    }
  },

  checkServerApiKey,

  filterSteps(): void {
    setActiveSteps(
      ALL_STEPS.filter((step) => {
        if (step.condition === null) return true;
        if (step.condition === 'needsApiKey') return !this.serverHasApiKey;
        return true;
      }),
    );
  },

  async init(): Promise<void> {
    if (!this.shouldShow()) return;
    if (await userHasExistingApplications()) {
      markComplete();
      return;
    }
    this.serverHasApiKey = await this.checkServerApiKey();
    this.filterSteps();
    window.setTimeout(() => this.start(), 500);
  },

  start(): void {
    if (getActiveSteps().length === 0) {
      this.filterSteps();
    }
    this.currentStep = 0;
    createOverlay(this);
    renderStep(this);
  },

  next(): void {
    const steps = getActiveSteps();
    if (this.currentStep < steps.length - 1) {
      this.currentStep += 1;
      renderStep(this);
    } else {
      this.complete();
    }
  },

  prev(): void {
    if (this.currentStep > 0) {
      this.currentStep -= 1;
      renderStep(this);
    }
  },

  skip(): void {
    markComplete();
    destroyOverlay(this);
  },

  complete(): void {
    markComplete();
    destroyOverlay(this);
  },

  async reset(): Promise<void> {
    localStorage.removeItem(ONBOARDING_KEY);
    this.serverHasApiKey = await this.checkServerApiKey();
    this.filterSteps();
    this.start();
  },
};
