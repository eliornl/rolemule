export const ONBOARDING_KEY = 'onboarding_completed';
export const ONBOARDING_VERSION = '2.0';

export type OnboardingStepCondition = null | 'needsApiKey';

export interface OnboardingStep {
  id: string;
  title: string;
  content: string;
  image: string;
  position: string;
  condition: OnboardingStepCondition;
  highlight?: string;
}

export interface OnboardingCompletionRecord {
  version: string;
  completedAt: string;
}

export interface ApiKeyStatusResponse {
  has_user_key?: boolean;
  has_api_key?: boolean;
  has_credentials?: boolean;
  server_has_key?: boolean;
  use_vertex_ai?: boolean;
  preferred_provider?: string | null;
}

export interface ApplicationStatsOverview {
  total_applications?: number;
}

export interface OnboardingController {
  currentStep: number;
  overlay: HTMLElement | null;
  modal: HTMLElement | null;
  serverHasApiKey: boolean;
  shouldShow: () => boolean;
  checkServerApiKey: () => Promise<boolean>;
  filterSteps: () => void;
  init: () => Promise<void>;
  start: () => void;
  next: () => void;
  prev: () => void;
  skip: () => void;
  complete: () => void;
  reset: () => Promise<void>;
}
