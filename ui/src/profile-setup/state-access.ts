import {
  currentStep,
  educationHistory,
  hasApiKey,
  profileMonthDdCloser,
  skills,
  workExperience,
} from './state';

export {
  setCurrentStep,
  setEducationHistory,
  setHasApiKey,
  setProfileMonthDdCloser,
  setSkills,
  setWorkExperience,
} from './state';

export function getCurrentStep(): number {
  return currentStep;
}

export function getSkills(): string[] {
  return skills;
}

export function getWorkExperience() {
  return workExperience;
}

export function getEducationHistory() {
  return educationHistory;
}

export function getHasApiKey(): boolean {
  return hasApiKey;
}

export function getProfileMonthDdCloser(): (() => void) | null {
  return profileMonthDdCloser;
}
