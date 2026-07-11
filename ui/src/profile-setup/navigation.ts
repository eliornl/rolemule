import { TOTAL_STEPS } from './state';
import { getCurrentStep, setCurrentStep } from './state-access';
import {
  completeBtn,
  nextBtn,
  prevBtn,
  progressBar,
} from './dom';
import {
  validateBasicInfo,
  validateCareerPreferences,
  validateEducation,
  validateSkillsQualifications,
  validateWorkExperience,
} from './validation';
import { hideAlerts, showError } from './alerts';
import { updateCompletionSummary } from './completion-summary';

export function changeStep(newStep: number): void {
    if (newStep < 1 || newStep > TOTAL_STEPS) return;

    // Update step
    setCurrentStep(newStep);
    updateStepDisplay();

    // Update UI elements
    updateStepIndicators();
    updateProgressBar();

}

export function updateStepIndicators() {
    // Step indicators are for steps 1-4 (Basic Info to Preferences)
    // Step 0 (resume upload) doesn't have an indicator
    document
        .querySelectorAll(".step-indicator")
        .forEach((indicator, index) => {
            const stepNum = index + 1; // Indicators are 1-indexed (1, 2, 3, 4)
            indicator.classList.remove("active", "completed");

            if (getCurrentStep() === 0) {
                // On step 0, no indicator is active yet
                return;
            }

            if (stepNum === getCurrentStep()) {
                indicator.classList.add("active");
            } else if (stepNum < getCurrentStep()) {
                indicator.classList.add("completed");
            }
        });
}

export function updateProgressBar() {
    // Progress is calculated based on steps 1–5 (Basic Info through Preferences)
    const mainSteps = 5;
    const adjustedStep = Math.max(0, getCurrentStep()); // Current position in main flow
    const progress = getCurrentStep() === 0 ? 0 : (adjustedStep / mainSteps) * 100;
    progressBar!.style.width = `${progress}%`;
}

export function updateStepDisplay() {
    // Show/hide step forms based on current step
    document.querySelectorAll(".step-form").forEach((form) => {
        const formId = form.id;
        const stepNum = parseInt(formId.replace("step-", ""), 10);
        form.classList.remove("active");
        if (stepNum === getCurrentStep()) {
            form.classList.add("active");
        }
    });

    // Update navigation buttons
    // Step 0: No prev/next buttons (handled by skip button)
    // Step 1: No prev (or prev goes to step 0), has next
    // Step 2-3: Has prev and next
    // Step 4: Has prev and complete
    // Show/hide progress container based on step
    const progressContainer = document.querySelector(".progress-container");
    if (progressContainer) {
        if (getCurrentStep() === 0) {
            progressContainer.classList.add("hidden");
        } else {
            progressContainer.classList.remove("hidden");
        }
    }

    if (getCurrentStep() === 0) {
        prevBtn!.style.display = "none";
        nextBtn!.style.display = "none";
        completeBtn!.style.display = "none";
    } else {
        prevBtn!.style.display = getCurrentStep() > 1 ? "block" : "none";
        nextBtn!.style.display = getCurrentStep() < 5 ? "block" : "none";
        completeBtn!.style.display = getCurrentStep() === 5 ? "block" : "none";
    }

    // Update completion summary on final step
    if (getCurrentStep() === TOTAL_STEPS) {
        updateCompletionSummary();
    }
}

export function goToNextStep() {

    try {
        // Hide any previous error messages
        hideAlerts();

        // Validate the current step before proceeding
        let isValid = false;

        // Step-specific validation
        switch(getCurrentStep()) {
            case 1: // Basic Info
                isValid = validateBasicInfo();
                break;
            case 2: // Work Experience
                isValid = validateWorkExperience();
                break;
            case 3: // Education
                isValid = validateEducation();
                break;
            case 4: // Skills
                isValid = validateSkillsQualifications();
                break;
            case 5: // Career Preferences
                isValid = validateCareerPreferences();
                break;
            default:
                isValid = true;
        }

        // Only proceed if validation passes
        if (isValid) {
            changeStep(getCurrentStep() + 1);
        } else {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    } catch (error) {
        console.error("Error in goToNextStep:", error);
        showError('Error moving to next step: ' + (error instanceof Error ? error.message : String(error)));
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

export function goToPrevStep() {
    changeStep(getCurrentStep() - 1);
}

export function checkPreferencesStep() {
    // If we're on step 4, make sure the complete button is visible
    if (getCurrentStep() === TOTAL_STEPS) {
        nextBtn!.style.display = "none";
        completeBtn!.style.display = "inline-block";
    }
}
