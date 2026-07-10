export let userHasPassword = true;
export let prefsSaveTimer: number | null = null;
export let modelSaveTimer: number | null = null;

export function setUserHasPassword(value: boolean): void {
  userHasPassword = value;
}

export function setPrefsSaveTimer(timer: number | null): void {
  prefsSaveTimer = timer;
}

export function setModelSaveTimer(timer: number | null): void {
  modelSaveTimer = timer;
}
