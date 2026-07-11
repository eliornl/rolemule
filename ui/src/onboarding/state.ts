import type { OnboardingStep } from './types';

export let activeSteps: OnboardingStep[] = [];

export function setActiveSteps(steps: OnboardingStep[]): void {
  activeSteps = steps;
}

export function getActiveSteps(): OnboardingStep[] {
  return activeSteps;
}
