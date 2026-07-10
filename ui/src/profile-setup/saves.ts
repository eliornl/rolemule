import type { WorkExperienceEntry } from './types';
import { makeAuthenticatedApiCall, ProfileApiError } from './api';
import {
  getEducationHistory,
  getSkills,
  getWorkExperience,
  setEducationHistory,
  setWorkExperience,
} from './state-access';
import { formatDateForInput, readSalaryField, sanitizeText } from './utils';
import { showError } from './alerts';
import { checkboxEl, inputEl, checkedInput } from './dom-helpers';

export async function saveBasicInfo(): Promise<boolean> {
    try {
        const formEl = document.getElementById('basic-info-form') as HTMLFormElement | null;
        if (!formEl) throw new Error('Basic info form not found');
        const formData = new FormData(formEl);
        const entries = Object.fromEntries(formData.entries());

        const rawYears = entries['years_experience'];
        const yearsExperience =
            rawYears === undefined || rawYears === null || rawYears === ''
                ? NaN
                : parseInt(String(rawYears), 10);

        const payload: Record<string, unknown> = {
            ...entries,
            years_experience: yearsExperience,
            is_student: entries.is_student === 'on',
        };

        // Ensure all required fields are present (years_experience checked separately — 0 is valid)
        const requiredFields = ["city", "state", "country", "professional_title", "summary"];
        for (const field of requiredFields) {
            if (!payload[field]) {
                throw new Error(`Missing required field: ${field}`);
            }
        }
        if (Number.isNaN(yearsExperience)) {
            throw new Error('Missing required field: years_experience');
        }

        await makeAuthenticatedApiCall('/profile/basic-info', 'PUT', payload);

        console.log("Basic info saved successfully");
        return true; // Ensure we return true for success
    } catch (error) {
        console.error("Error saving basic info:", error);
        const details = (error instanceof ProfileApiError ? error.details : undefined);
        if (Array.isArray(details) && details.length > 0) {
            const fieldMessages = (
                details as Array<{ field?: string; message?: string }>
            )
                .map(
                    (d) =>
                        `${d.field || 'field'}: ${d.message || 'invalid value'}`,
                )
                .join('; ');
            throw new Error(`Failed to save basic information — ${fieldMessages}`);
        }
        throw new Error(`Failed to save basic information: ${(error instanceof Error ? error.message : String(error))}`);
    }
}

export async function saveWorkExperience() {
    try {
        const noExpCheckbox = (checkboxEl("no-experience"));
        // If "no experience" is checked, persist [] so the server can mark step 2 complete
        if (noExpCheckbox && noExpCheckbox.checked) {
            setWorkExperience([]);
            await makeAuthenticatedApiCall("/profile/work-experience", "PUT", {
                work_experience: [],
            });
            return true;
        }

        if (!getWorkExperience() || !Array.isArray(getWorkExperience()) || getWorkExperience().length === 0) {
            console.error("saveWorkExperience: empty work experience without no-experience option");
            showError(
                'Please add at least one work experience entry or check "I don\'t have any relevant work experience yet".',
            );
            return false;
        }

        // Create a deep copy of work experience to avoid modifying the original
        const workExperienceToSave = JSON.parse(JSON.stringify(getWorkExperience()));

        // Clean and validate each work experience entry to ensure it meets API requirements
        for (let i = 0; i < workExperienceToSave.length; i++) {
            const exp = workExperienceToSave[i];
            // Sanitize description field to avoid validation errors
            if (exp.description) {
                exp.description = sanitizeText(exp.description);
            }
            // Check required fields
            if (!exp.company || !exp.job_title || !exp.start_date) {
                console.warn(`Work experience entry ${i+1} is missing required fields:`, exp);
                // Remove this entry rather than failing the whole save
                workExperienceToSave.splice(i, 1);
                i--; // Adjust index since we removed an item
                continue;
            }

            // Make sure start_date is in YYYY-MM format as required by the API
            if (exp.start_date) {
                // Convert to YYYY-MM format if not already in that format
                if (!exp.start_date.match(/^\d{4}-\d{2}$/)) {
                    try {
                        const date = new Date(exp.start_date);
                        if (!isNaN(date.getTime())) {
                            exp.start_date = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
                        } else {
                            // If date parsing failed, remove this entry
                            console.warn(`Invalid start_date format for entry ${i+1}:`, exp.start_date);
                            workExperienceToSave.splice(i, 1);
                            i--; // Adjust index
                            continue;
                        }
                    } catch (e) {
                        console.warn(`Error formatting start_date for entry ${i+1}:`, e);
                        workExperienceToSave.splice(i, 1);
                        i--; // Adjust index
                        continue;
                    }
                }
            }

            // Handle end_date for current position and ensure proper format
            if (exp.is_current) {
                // Clear end_date for current positions as required by API
                exp.end_date = null;
            } else if (exp.end_date) {
                // For non-current positions, ensure end_date is in YYYY-MM format
                if (!exp.end_date.match(/^\d{4}-\d{2}$/)) {
                    try {
                        const date = new Date(exp.end_date);
                        if (!isNaN(date.getTime())) {
                            exp.end_date = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
                        } else {
                            // If we can't parse the end_date, set to null
                            console.warn(`Invalid end_date format for entry ${i+1}:`, exp.end_date);
                            exp.end_date = null;
                        }
                    } catch (e) {
                        console.warn(`Error formatting end_date for entry ${i+1}:`, e);
                        exp.end_date = null;
                    }
                }
            }
        }

        // Check if we have any entries left after validation
        if (workExperienceToSave.length === 0) {
            console.warn("All work experience entries were invalid and removed");
            // Return true since an empty array is valid
            const requestData = { work_experience: [] };
            await makeAuthenticatedApiCall("/profile/work-experience", "PUT", requestData);
            return true;
        }


        // Format data according to backend API expectations
        const requestData = { work_experience: workExperienceToSave };

        await makeAuthenticatedApiCall("/profile/work-experience", "PUT", requestData);

        console.log("Work experience saved successfully with", workExperienceToSave.length, "entries");
        return true; // Ensure we return true for success
    } catch (error) {
        console.error("Error saving work experience:", error);
        const details = (error instanceof ProfileApiError ? error.details : undefined);
        if (Array.isArray(details) && details.length > 0) {
            const fieldMessages = (
                details as Array<{ field?: string; message?: string }>
            )
                .map((d) => {
                const raw = (d.field || '').replace(/^body\.work_experience\./, '');
                const label =
                    raw.replace(
                        /^(\d+)\.(.+)$/,
                        (_: string, idx: string, field: string) =>
                            `Entry ${Number(idx) + 1} ${field.replace(/_/g, ' ')}`,
                    ) ||
                    raw.replace(/_/g, ' ') ||
                    'field';
                return `${label}: ${d.message || 'invalid value'}`;
            })
                .join('; ');
            showError(`Failed to save work experience — ${fieldMessages}`);
        } else {
            showError(
                'Failed to save work experience: ' +
                    (error instanceof Error ? error.message : 'Unknown error'),
            );
        }
        return false; // Return false on error
    }
}

export async function saveEducation() {
    try {
        const noEd = (checkboxEl("no-education"));
        if (noEd && noEd.checked) {
            setEducationHistory([]);
            await makeAuthenticatedApiCall("/profile/education", "PUT", {
                education: [],
            });
            return true;
        }
        if (!getEducationHistory() || getEducationHistory().length === 0) {
            showError(
                'Please add at least one education entry or check "I don\'t have formal education to add".',
            );
            return false;
        }
        const toSave = JSON.parse(JSON.stringify(getEducationHistory()));
        for (let i = 0; i < toSave.length; i++) {
            const edu = toSave[i];
            if (!edu.institution?.trim() || !edu.degree?.trim() || !edu.field_of_study?.trim()) {
                toSave.splice(i, 1);
                i--;
                continue;
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
            if (edu.is_current) {
                edu.end_date = null;
            }
            if (edu.start_date && !/^\d{4}-\d{2}$/.test(edu.start_date)) {
                edu.start_date = formatDateForInput(edu.start_date);
            }
            if (edu.end_date && !/^\d{4}-\d{2}$/.test(edu.end_date)) {
                edu.end_date = formatDateForInput(edu.end_date);
            }
            if (edu.field_of_study !== undefined && edu.field_of_study !== null) {
                edu.field_of_study = String(edu.field_of_study).trim();
            }
        }
        if (toSave.length === 0) {
            await makeAuthenticatedApiCall("/profile/education", "PUT", { education: [] });
            return true;
        }
        await makeAuthenticatedApiCall("/profile/education", "PUT", { education: toSave });
        return true;
    } catch (error) {
        console.error("Error saving education:", error);
        showError("Failed to save education: " + (error instanceof Error ? error.message : String(error)));
        return false;
    }
}

export async function saveSkillsQualifications() {
    try {

        // Backend expects just "skills" field
        const data = {
            skills: getSkills()
        };

        await makeAuthenticatedApiCall("/profile/skills-qualifications", "PUT", data);

        return true;
    } catch (error) {
        console.error("Error saving skills:", error);
        showError("Failed to save skills: " + (error instanceof Error ? error.message : String(error)));
        return false;
    }
}

export async function saveCareerPreferences() {
    try {

        // Initialize empty arrays for collections
        let jobTypes: string[] = [];
        let companySizes: string[] = [];
        let workArrangements: string[] = [];
        let travelPreference = "NONE";

        // Maps form values to API enum values
        const jobTypeMapping = {
            "full-time": "FULL_TIME",
            "part-time": "PART_TIME",
            "contract": "CONTRACT",
            "freelance": "FREELANCE",
            "internship": "INTERNSHIP"
        };

        const companySizeMapping = {
            "startup": "STARTUP",
            "small": "SMALL", 
            "medium": "MEDIUM",
            "large": "LARGE",
            "enterprise": "ENTERPRISE"
        };

        const workArrangementMapping = {
            "onsite": "ONSITE",
            "remote": "REMOTE",
            "hybrid": "HYBRID"
        };

        // Collect job types
        try {
            const jobTypeElements = document.querySelectorAll('input[id^="job-type-"]:checked');
            if (jobTypeElements && jobTypeElements.length > 0) {
                jobTypes = (Array.from(jobTypeElements) as HTMLInputElement[])
                    .map((input) => {
                        const mappedValue = jobTypeMapping[input.value as keyof typeof jobTypeMapping];
                        return mappedValue || "FULL_TIME";
                    })
                    .filter(Boolean);
            }

            // API requires at least one job type
            if (jobTypes.length === 0) {
                jobTypes = ["FULL_TIME"];
            }

        } catch (error) {
            console.error("Error mapping job types:", error);
            jobTypes = ["FULL_TIME"];
        }

        // Collect company sizes
        try {
            const companySizeElements = document.querySelectorAll('input[id^="company-size-"]:checked');
            if (companySizeElements && companySizeElements.length > 0) {
                companySizes = (Array.from(companySizeElements) as HTMLInputElement[])
                    .map((input) => {
                        const mappedValue = companySizeMapping[input.value as keyof typeof companySizeMapping];
                        return mappedValue || "MEDIUM";
                    })
                    .filter(Boolean);
            }

            // API requires at least one company size
            if (companySizes.length === 0) {
                companySizes = ["MEDIUM"];
            }

        } catch (error) {
            console.error("Error mapping company sizes:", error);
            companySizes = ["MEDIUM"];
        }

        // Collect work arrangements
        try {
            const workArrangementElements = document.querySelectorAll('input[id^="work-arrangement-"]:checked');
            if (workArrangementElements && workArrangementElements.length > 0) {
                workArrangements = (Array.from(workArrangementElements) as HTMLInputElement[])
                    .map((input) => {
                        const mappedValue = workArrangementMapping[input.value as keyof typeof workArrangementMapping];
                        return mappedValue || "REMOTE";
                    })
                    .filter(Boolean);
            }

            // API requires at least one work arrangement
            if (workArrangements.length === 0) {
                workArrangements = ["REMOTE"];
            }

        } catch (error) {
            console.error("Error mapping work arrangements:", error);
            workArrangements = ["REMOTE"];
        }

        // Get travel preference
        try {
            const travelPreferenceElement = checkedInput('input[name="travel-preference"]:checked');
            if (travelPreferenceElement && travelPreferenceElement.value) {
                travelPreference = travelPreferenceElement.value.toUpperCase();
            }
        } catch (error) {
            console.error("Error mapping travel preference:", error);
            travelPreference = "NONE";
        }

        const waEl = checkedInput('input[name="work-authorization"]:checked');
        if (!waEl) {
            showError("Work authorization status must be selected");
            return false;
        }
        const workAuthorization = String((waEl).value);

        const relocateChecked = (checkboxEl("willing-to-relocate")?.checked ?? false) || false;
        const visaSponsorshipChecked =
            (checkboxEl("requires-visa-sponsorship")?.checked ?? false) || false;
        const securityClearanceChecked = (checkboxEl("has-security-clearance")?.checked ?? false) || false;

        const minSalaryVal = readSalaryField(
            (inputEl("min-salary"))
        );
        const maxSalaryVal = readSalaryField(
            (inputEl("max-salary"))
        );
        const desiredSalaryRange: { min?: number; max?: number } = {};
        if (minSalaryVal > 0) desiredSalaryRange.min = minSalaryVal;
        if (maxSalaryVal > 0) desiredSalaryRange.max = maxSalaryVal;

        const data = {
            job_types: jobTypes,
            desired_company_sizes: companySizes,
            work_arrangements: workArrangements,
            max_travel_preference: travelPreference,
            desired_salary_range: Object.keys(desiredSalaryRange).length > 0 ? desiredSalaryRange : null,
            willing_to_relocate: relocateChecked,
            requires_visa_sponsorship: visaSponsorshipChecked,
            work_authorization: workAuthorization,
            has_security_clearance: securityClearanceChecked
        };


        const response = await makeAuthenticatedApiCall("/profile/career-preferences", "PUT", data);


        if (response && response.message === "Career preferences updated successfully") {
            return true;
        } else {
            console.error("Career preferences API returned unexpected response", response);
            showError("Failed to save career preferences: API validation failed");
            return false;
        }
    } catch (error) {
        console.error("Error saving career preferences:", error);
        showError("Failed to save career preferences: " + (error instanceof Error ? error.message : String(error)));
        return false;
    }
}
