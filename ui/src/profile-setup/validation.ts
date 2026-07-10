import { VALIDATION_RULES } from './state';
import { getSkills, getWorkExperience, getEducationHistory } from './state-access';
import { parseSalaryDigits, isValidUrl } from './utils';
import { showError, showErrorMessage } from './alerts';
import { checkboxEl, inputEl, textareaEl, checkedInput } from './dom-helpers';

export function validateBasicInfo() {
    const requiredFields = [
        { id: "full-name", name: "Full Name" },
        { id: "city", name: "City" },
        { id: "state", name: "State" },
        { id: "country", name: "Country" },
        { id: "professional-title", name: "Professional Title" },
        { id: "years-experience", name: "Years of Experience" },
        { id: "summary", name: "Professional Summary" }
    ];

    // Optional URL fields (no validation required)
    const optionalUrlFields = [
        { id: "linkedin-url", name: "LinkedIn URL" },
        { id: "github-url", name: "GitHub URL" },
        { id: "portfolio-url", name: "Portfolio URL" },
    ];

    let isValid = true;
    const missingFields: string[] = [];

    // Check each required field
    requiredFields.forEach(fieldInfo => {
        const field = inputEl(fieldInfo.id) ?? textareaEl(fieldInfo.id);
        if (!field) return; // Skip if field doesn't exist

        const value = field.value.trim();
        if (value === "") {
            field.classList.add("is-invalid");
            isValid = false;
            missingFields.push(fieldInfo.name);
        } else {
            field.classList.remove("is-invalid");

            // Additional validation for specific fields
            if (fieldInfo.id === "years-experience") {
                const years = parseInt(value);
                if (isNaN(years) || years < 0 || years > 50) {
                    field.classList.add("is-invalid");
                    showError("Years of experience must be between 0 and 50");
                    return false;
                }
            }
        }
    });

    // Validate optional URL fields if they're not empty
    optionalUrlFields.forEach(fieldInfo => {
        const field = inputEl(fieldInfo.id) ?? textareaEl(fieldInfo.id);
        if (!field) return; // Skip if field doesn't exist

        const value = field.value.trim();
        if (value !== "" && !isValidUrl(value)) {
            field.classList.add("is-invalid");
            isValid = false;
            showError(`Please enter a valid URL for ${fieldInfo.name}`);
        } else {
            field.classList.remove("is-invalid");
        }
    });

    if (!isValid && missingFields.length > 0) {
        showError(`Please fill in the following required fields: ${missingFields.join(", ")}`);
    }

    return isValid;
}

export function validateWorkExperience() {
    // Check if the "no experience" checkbox is checked
    const noExperienceCheckbox = checkboxEl("no-experience");
    if (noExperienceCheckbox && noExperienceCheckbox.checked) {
        // If user has no experience, we don't need to validate further
        return true;
    }

    // Otherwise, require at least one work experience entry
    if (getWorkExperience().length < VALIDATION_RULES.MIN_EXPERIENCE_ENTRIES) {
        showError(`Please add at least ${VALIDATION_RULES.MIN_EXPERIENCE_ENTRIES} work experience entry or check the "I don't have any relevant work experience yet" box`);
        return false;
    }

    // Validate each work experience entry has required fields
    for (let i = 0; i < getWorkExperience().length; i++) {
        const exp = getWorkExperience()[i];
        if (!exp.company?.trim() || !exp.job_title?.trim() || !exp.start_date?.trim()) {
            showError(`Work experience entry ${i + 1}: Please fill in Company, Job Title, and Start Date`);
            return false;
        }

        // Validate date logic for completed positions
        if (!exp.is_current && !exp.end_date?.trim()) {
            showError(`Work experience entry ${i + 1}: Please provide an end date or mark as current position`);
            return false;
        }

    }

    return true;
}

export function validateEducation() {
    const noEd = checkboxEl("no-education");
    if (noEd && noEd.checked) {
        return true;
    }
    if (!getEducationHistory() || getEducationHistory().length < 1) {
        showError('Please add at least one education entry or check "I don\'t have formal education to add".');
        return false;
    }
    for (let i = 0; i < getEducationHistory().length; i++) {
        const edu = getEducationHistory()[i];
        if (!edu.institution?.trim() || !edu.degree?.trim() || !edu.field_of_study?.trim()) {
            showError(`Education entry ${i + 1}: Please fill in Institution, Degree, and Field of study`);
            return false;
        }
        if (!edu.start_date?.trim()) {
            showError(`Education entry ${i + 1}: Please fill in Start month and year`);
            return false;
        }
        if (!edu.is_current && !edu.end_date?.trim()) {
            showError(
                `Education entry ${i + 1}: Please fill in End month and year, or check Currently enrolled`,
            );
            return false;
        }
    }
    return true;
}

export function validateSkillsQualifications() {

    // Check if skills array has at least one entry
    if (getSkills().length < 1) {
        // If skills array is empty, check if there are any skill badges in the DOM
        // (in case the skills array wasn't properly updated)
        const skillsContainer = document.getElementById("skills-container");
        if (skillsContainer) {
            const skillElements = skillsContainer.querySelectorAll(".skill-badge");
            if (skillElements.length > 0) {
                return true;
            }
        }

        showError("Please add at least one skill");
        return false;
    }

    return true;
}

export function validateCareerPreferences() {
    let isValid = true;
    let errorMessages = [];

    // Validate Salary (both optional, but if both provided min must be less than max)
    const minSalary = inputEl("min-salary")?.value ?? "";
    const maxSalary = inputEl("max-salary")?.value ?? "";

    if (minSalary && maxSalary && parseSalaryDigits(minSalary) >= parseSalaryDigits(maxSalary)) {
        isValid = false;
        errorMessages.push('Minimum salary must be less than maximum salary');
    }

    // Validate Job Types (at least one required)
    const jobTypeElements = document.querySelectorAll('input[id^="job-type-"]:checked');
    if (!jobTypeElements || jobTypeElements.length === 0) {
        isValid = false;
        errorMessages.push('At least one job type must be selected');
    }

    // Validate Company Sizes (at least one required)
    const companySizeElements = document.querySelectorAll('input[id^="company-size-"]:checked');
    if (!companySizeElements || companySizeElements.length === 0) {
        isValid = false;
        errorMessages.push('At least one preferred company size must be selected');
    }

    // Validate Work Arrangements (at least one required)
    const workArrangementElements = document.querySelectorAll('input[id^="work-arrangement-"]:checked');
    if (!workArrangementElements || workArrangementElements.length === 0) {
        isValid = false;
        errorMessages.push('At least one work arrangement must be selected');
    }

    // Validate Travel Preference (one option required)
    const travelPreferenceElement = checkedInput('input[name="travel-preference"]:checked');
    if (!travelPreferenceElement) {
        isValid = false;
        errorMessages.push('Maximum travel preference must be selected');
    }

    const workAuthElement = checkedInput('input[name="work-authorization"]:checked');
    if (!workAuthElement) {
        isValid = false;
        errorMessages.push('Work authorization status must be selected');
    }

    // Show validation errors if any
    if (!isValid) {
        showErrorMessage('Please correct the following issues: ' + errorMessages.join(', '));
    } else {
    }

    return isValid;
}
