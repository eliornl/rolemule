import type { EducationEntry, WorkExperienceEntry } from './types';

export const TOTAL_STEPS = 5;
export const API_BASE =
  (window.APP_CONFIG && window.APP_CONFIG.apiBase) || '/api/v1';

export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'access_token',
  TOKEN_TYPE: 'token_type',
  USER_DATA: 'user_data',
  PROFILE_COMPLETED: 'profile_completed',
} as const;

export const VALIDATION_RULES = {
  MIN_EXPERIENCE_ENTRIES: 1,
  MIN_SKILLS: 1,
  MIN_JOB_TYPES: 1,
  MIN_COMPANY_SIZES: 1,
  MIN_WORK_ARRANGEMENTS: 1,
} as const;

export let currentStep = 0;
export let skills: string[] = [];
export let workExperience: WorkExperienceEntry[] = [];
export let educationHistory: EducationEntry[] = [];
export let pageAbortController = new AbortController();
export let hasApiKey = true;
export let profileMonthDdCloser: (() => void) | null = null;

export function setCurrentStep(step: number): void {
  currentStep = step;
}

export function setSkills(next: string[]): void {
  skills = next;
}

export function setWorkExperience(next: WorkExperienceEntry[]): void {
  workExperience = next;
}

export function setEducationHistory(next: EducationEntry[]): void {
  educationHistory = next;
}

export function setHasApiKey(value: boolean): void {
  hasApiKey = value;
}

export function setProfileMonthDdCloser(fn: (() => void) | null): void {
  profileMonthDdCloser = fn;
}
