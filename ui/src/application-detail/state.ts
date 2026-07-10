import type { WorkflowResults } from './types';

let applicationData: WorkflowResults | null = null;
let currentSessionId: string | null = null;
let processingRefreshTimer: number | null = null;
let toastOutTimer: number | null = null;
let toastRemoveTimer: number | null = null;
let workflowStatus: string | null = null;
let regeneratingCoverLetter = false;
let regeneratingResume = false;
let generatingInterviewPrep = false;
let continuingWorkflow = false;

export const TOAST_DISMISS_MS_SUCCESS = 4000;
export const TOAST_DISMISS_MS_ERROR = 8000;

export function getApplicationData(): WorkflowResults | null {
  return applicationData;
}

export function setApplicationData(data: WorkflowResults | null): void {
  applicationData = data;
}

export function patchApplicationData(patch: Partial<WorkflowResults>): void {
  if (!applicationData) applicationData = {};
  Object.assign(applicationData, patch);
}

export function getCurrentSessionId(): string | null {
  return currentSessionId;
}

export function setCurrentSessionId(id: string | null): void {
  currentSessionId = id;
}

export function getProcessingRefreshTimer(): number | null {
  return processingRefreshTimer;
}

export function setProcessingRefreshTimer(id: number | null): void {
  processingRefreshTimer = id;
}

export function clearProcessingRefreshTimer(): void {
  if (processingRefreshTimer !== null) {
    clearTimeout(processingRefreshTimer);
    processingRefreshTimer = null;
  }
}

export function getToastOutTimer(): number | null {
  return toastOutTimer;
}

export function setToastOutTimer(id: number | null): void {
  toastOutTimer = id;
}

export function getToastRemoveTimer(): number | null {
  return toastRemoveTimer;
}

export function setToastRemoveTimer(id: number | null): void {
  toastRemoveTimer = id;
}

export function clearToastTimers(): void {
  if (toastOutTimer !== null) clearTimeout(toastOutTimer);
  if (toastRemoveTimer !== null) clearTimeout(toastRemoveTimer);
  toastOutTimer = null;
  toastRemoveTimer = null;
}

export function getWorkflowStatus(): string | null {
  return workflowStatus;
}

export function setWorkflowStatus(status: string | null): void {
  workflowStatus = status;
}

export function isRegeneratingCoverLetter(): boolean {
  return regeneratingCoverLetter;
}

export function setRegeneratingCoverLetter(v: boolean): void {
  regeneratingCoverLetter = v;
}

export function isRegeneratingResume(): boolean {
  return regeneratingResume;
}

export function setRegeneratingResume(v: boolean): void {
  regeneratingResume = v;
}

export function isGeneratingInterviewPrep(): boolean {
  return generatingInterviewPrep;
}

export function setGeneratingInterviewPrep(v: boolean): void {
  generatingInterviewPrep = v;
}

export function isContinuingWorkflow(): boolean {
  return continuingWorkflow;
}

export function setContinuingWorkflow(v: boolean): void {
  continuingWorkflow = v;
}
