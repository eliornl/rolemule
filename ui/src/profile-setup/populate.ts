import type { ProfilePayload } from './types';
import { makeAuthenticatedApiCall } from './api';
import {
  getEducationHistory,
  getWorkExperience,
  setEducationHistory,
  setSkills,
  setWorkExperience,
} from './state-access';
import { parseSalaryDigits } from './utils';
import { renderEducation } from './education';
import { renderSkills } from './skills';
import { renderWorkExperience } from './work-experience';
import { checkboxEl, inputEl, textareaEl } from './dom-helpers';

export function onlyCareerPreferencesMissing(
  completionStatus: import('./types').CompletionStatus | null | undefined,
): boolean {
    const cs = completionStatus;
    if (!cs || cs.profile_completed) return false;
    return (
        cs.career_preferences === false &&
        cs.basic_info !== false &&
        cs.work_experience !== false &&
        cs.education !== false &&
        cs.skills_qualifications !== false
    );
}

export async function loadUserData(): Promise<ProfilePayload | null> {
    try {
        const data = await makeAuthenticatedApiCall("/profile/");
        populateFormData(data);
        return data;
    } catch (error) {
        // For new users, this error is expected and will be silently ignored
        return null;
    }
}

export function populateFormData(data: ProfilePayload): void {
    const profileData = data.profile_data;
    if (!profileData) return;

    // Populate location fields
    if (profileData.city) { const el = inputEl("city"); if (el) el.value = profileData.city; }
    if (profileData.state) { const el = inputEl("state"); if (el) el.value = profileData.state; }
    if (profileData.country) { const el = inputEl("country"); if (el) el.value = profileData.country; }

    // Populate professional details
    if (profileData.professional_title) { const el = inputEl("professional-title"); if (el) el.value = profileData.professional_title; }
    if (profileData.years_experience !== undefined && profileData.years_experience !== null) { const el = inputEl("years-experience"); if (el) el.value = String(profileData.years_experience); }
    if (profileData.summary) { const el = textareaEl("summary"); if (el) el.value = profileData.summary; }

    const phoneEl = inputEl("phone");
    if (phoneEl && profileData.phone) phoneEl.value = profileData.phone;
    const liEl = inputEl("linkedin-url");
    if (liEl && profileData.linkedin_url) liEl.value = profileData.linkedin_url;
    const ghEl = inputEl("github-url");
    if (ghEl && profileData.github_url) ghEl.value = profileData.github_url;
    const pfEl = inputEl("portfolio-url");
    if (pfEl && profileData.portfolio_url) pfEl.value = profileData.portfolio_url;

    // Student status field has been removed

    // Work experience — empty array is truthy in JS; sync "no experience" checkbox
    setWorkExperience(
        Array.isArray(profileData.work_experience)
            ? profileData.work_experience
            : [],
    );
    getWorkExperience().forEach((exp) => {
        if (String(exp.end_date || "").trim()) {
            exp.is_current = false;
        }
    });
    renderWorkExperience();
    const noExpOnLoad = document.getElementById('no-experience') as HTMLInputElement | null;
    if (noExpOnLoad) {
        noExpOnLoad.checked = getWorkExperience().length === 0;
        if (noExpOnLoad.checked) {
            noExpOnLoad.dispatchEvent(new Event("change"));
        }
    }

    // Skills
    if (profileData.skills) {
        setSkills(profileData.skills);
        renderSkills();
    }

    setEducationHistory(
        Array.isArray(profileData.education) ? profileData.education : [],
    );
    getEducationHistory().forEach((edu) => {
        const endLike = edu.end_date || edu.graduation_date;
        if (String(endLike || "").trim()) {
            edu.is_current = false;
        }
    });
    renderEducation();
    const noEdOnLoad = document.getElementById('no-education') as HTMLInputElement | null;
    if (noEdOnLoad) {
        noEdOnLoad.checked = getEducationHistory().length === 0;
        if (noEdOnLoad.checked) {
            noEdOnLoad.dispatchEvent(new Event("change"));
        }
    }

    if (profileData.is_student !== undefined) {
        const el = checkboxEl('is-student');
        if (el) el.checked = !!profileData.is_student;
    }

    // Job preferences
    if (profileData.desired_salary_range) {
        const minSalaryEl = (inputEl("min-salary"));
        const maxSalaryEl = (inputEl("max-salary"));
        const parsedMin = parseSalaryDigits(profileData.desired_salary_range.min);
        const parsedMax = parseSalaryDigits(profileData.desired_salary_range.max);
        if (minSalaryEl) minSalaryEl.value = parsedMin > 0 ? String(parsedMin) : "";
        if (maxSalaryEl) maxSalaryEl.value = parsedMax > 0 ? String(parsedMax) : "";
    }

    // Company sizes
    if (profileData.desired_company_sizes) {
        profileData.desired_company_sizes.forEach((size) => {
            // Extract the lowercase first word for matching
            const sizeKey = size.split(' ')[0].toLowerCase();
            const checkbox = document.querySelector(
                `input[value="${sizeKey}"][id^="company-size-"]`,
            );
            if (checkbox instanceof HTMLInputElement) checkbox.checked = true;
        });
    }

    // Job types
    if (profileData.job_types) {
        profileData.job_types.forEach((type) => {
            // Convert "Full-time" to "full-time", etc.
            const typeKey = type.toLowerCase().replace(' ', '-');
            const checkbox = document.querySelector(
                `input[value="${typeKey}"][id^="job-type-"]`,
            );
            if (checkbox instanceof HTMLInputElement) checkbox.checked = true;
        });
    }

    // Work arrangements
    if (profileData.work_arrangements) {
        profileData.work_arrangements.forEach((arrangement) => {
            // Convert "Onsite" to "onsite", etc.
            const arrangementKey = arrangement.toLowerCase();
            const checkbox = document.querySelector(`input[value="${arrangementKey}"][id^="work-arrangement-"]`);
            if (checkbox instanceof HTMLInputElement) checkbox.checked = true;
        });
    }

    // Populate additional career options
    if (profileData.willing_to_relocate) {
        const el = checkboxEl('willing-to-relocate');
        if (el) el.checked = true;
    }

    // Work authorization (career step)
    const validWorkAuth = new Set([
        "no_work_authorization",
        "has_work_authorization",
        "us_lawful_permanent_resident",
        "us_citizen",
    ]);
    let workAuth = profileData.work_authorization;
    if (workAuth && validWorkAuth.has(workAuth)) {
        document.querySelectorAll('input[name="work-authorization"]').forEach((el) => {
            const inp = el as HTMLInputElement;
            inp.checked = inp.value === workAuth;
        });
    }

    if (profileData.requires_visa_sponsorship === true) {
        const visaEl = checkboxEl("requires-visa-sponsorship");
        if (visaEl) visaEl.checked = true;
    }

    if (profileData.has_security_clearance) {
        const el = checkboxEl('has-security-clearance');
        if (el) el.checked = true;
    }

    if (profileData.is_student === true) {
        const el = checkboxEl('is-student');
        if (el) el.checked = true;
    }

    // Set travel preference
    if (profileData.max_travel_preference) {

        // Map percentage values to enum values
        const travelPreferenceMap: Record<string, string> = {
            "0": "NONE",
            "25": "MINIMAL",
            "50": "MODERATE",
            "75": "FREQUENT",
            "100": "EXTENSIVE"
        };

        // Try direct match first
        let travelRadio = document.querySelector(`input[name="travel-preference"][value="${profileData.max_travel_preference}"]`);

        // If not found, try mapping from percentage to enum value
        if (!travelRadio && travelPreferenceMap[profileData.max_travel_preference]) {
            const mappedValue = travelPreferenceMap[profileData.max_travel_preference];
            travelRadio = document.querySelector(`input[name="travel-preference"][value="${mappedValue}"]`);
        }

        if (travelRadio instanceof HTMLInputElement) {
            travelRadio.checked = true;
        }
    }
}
