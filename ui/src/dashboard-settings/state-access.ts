import {
  modelSaveTimer,
  prefsSaveTimer,
  userHasPassword,
} from './state';

export {
  setModelSaveTimer,
  setPrefsSaveTimer,
  setUserHasPassword,
} from './state';

export function getUserHasPassword(): boolean {
  return userHasPassword;
}

export function getPrefsSaveTimer(): number | null {
  return prefsSaveTimer;
}

export function getModelSaveTimer(): number | null {
  return modelSaveTimer;
}
