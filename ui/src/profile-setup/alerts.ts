import {
  completeBtn,
  errorAlert,
  errorMessage,
  nextBtn,
  successAlert,
  successMessage,
} from './dom';

export function showErrorMessage(message: string): void {
  if (errorAlert && errorMessage) {
    errorMessage.textContent = message;
    errorAlert.classList.remove('d-none');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else {
    console.error(message);
  }
}

export function showError(message: string): void {
  showErrorMessage(message);
  successAlert?.classList.add('d-none');
}

export function showSuccess(message: string): void {
  if (successMessage) successMessage.textContent = message;
  successAlert?.classList.remove('d-none');
  errorAlert?.classList.add('d-none');
}

export function hideAlerts(): void {
  errorAlert?.classList.add('d-none');
  successAlert?.classList.add('d-none');
}

export function setLoading(loading: boolean): void {
  if (nextBtn) {
    (nextBtn as HTMLButtonElement).disabled = loading;
    if (loading) {
      nextBtn.innerHTML =
        '<i class="fas fa-spinner fa-spin me-2"></i>Processing...';
    } else {
      nextBtn.innerHTML = 'Next<i class="fas fa-arrow-right ms-2"></i>';
    }
  }

  if (completeBtn) {
    (completeBtn as HTMLButtonElement).disabled = loading;
    if (loading) {
      completeBtn.innerHTML =
        '<i class="fas fa-spinner fa-spin me-2"></i>Completing...';
    } else {
      completeBtn.innerHTML =
        'Complete Profile<i class="fas fa-check ms-2"></i>';
    }
  }
}
