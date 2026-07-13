import { API_BASE } from './state';
import { getAuthToken } from './api';
import { getSkills } from './state-access';
import {
  validateBasicInfo,
  validateCareerPreferences,
  validateEducation,
  validateSkillsQualifications,
  validateWorkExperience,
} from './validation';
import { changeStep } from './navigation';
import {
  saveBasicInfo,
  saveCareerPreferences,
  saveEducation,
  saveSkillsQualifications,
  saveWorkExperience,
} from './saves';
import { hideAlerts, setLoading, showError, showSuccess } from './alerts';

export async function completeProfile() {
    try {
        // Validate ALL steps upfront before making any API calls.
        // Run each validator first — it shows its own error message via showErrorMessage().
        // If it fails, navigate to that step (changeStep no longer clears the error).
        const stepValidations = [
            { step: 1, fn: validateBasicInfo },
            { step: 2, fn: validateWorkExperience },
            { step: 3, fn: validateEducation },
            { step: 4, fn: validateSkillsQualifications },
            { step: 5, fn: validateCareerPreferences },
        ];

        for (const { step, fn } of stepValidations) {
            if (!fn()) {
                changeStep(step);
                window.scrollTo({ top: 0, behavior: "smooth" });
                return;
            }
        }

        hideAlerts();
        setLoading(true);

        // Get token from URL or localStorage with consistent approach
        const urlParams = new URLSearchParams(window.location.search);
        let token = urlParams.get('token');


        if (token) {
            // Save token to localStorage for consistent access
            localStorage.setItem("access_token", token);
            // Also save with alternate key for backward compatibility
            localStorage.setItem("authToken", token);
        } else {
            // Get token from localStorage if not in URL
            token = localStorage.getItem("access_token") || localStorage.getItem("authToken");
        }

        if (!token) {
            console.error("No authentication token found");
            showError("Authentication token not found. Please log in again.");
            setLoading(false);
            return;
        }


        // Save basic info first
        try {
            if (validateBasicInfo()) {
                const basicInfoResult = await saveBasicInfo();
                if (basicInfoResult) {
                } else {
                    console.error("Basic info save returned false");
                    showError("Failed to save basic information. Please try again.");
                    setLoading(false);
                    return false;
                }
            } else {
                console.error("Basic info validation failed");
                showError("Please complete all required basic information fields before proceeding.");
                setLoading(false);
                return false;
            }
        } catch (error) {
            console.error("Error saving basic info:", error);
            showError("Error saving basic information: " + ((error instanceof Error ? error.message : String(error)) || "Unknown error"));
            setLoading(false);
            return false;
        }

        // Save work experience
        try {
            if (validateWorkExperience()) {
                const workExpResult = await saveWorkExperience();
                if (workExpResult) {
                } else {
                    console.error("Work experience save returned false");
                    setLoading(false);
                    return false;
                }
            } else {
                console.error("Work experience validation failed");
                showError("Please add at least one work experience entry or check the 'I don't have any relevant work experience yet' box.");
                setLoading(false);
                return false;
            }
        } catch (error) {
            console.error("Error saving work experience:", error);
            showError("Error saving work experience: " + ((error instanceof Error ? error.message : String(error)) || "Unknown error"));
            setLoading(false);
            return false;
        }

        // Save education
        try {
            if (validateEducation()) {
                const eduResult = await saveEducation();
                if (!eduResult) {
                    console.error("Education save returned false");
                    showError("Failed to save education. Please try again.");
                    setLoading(false);
                    return false;
                }
            } else {
                console.error("Education validation failed");
                showError(
                    'Please add at least one education entry or check "I don\'t have formal education to add".',
                );
                setLoading(false);
                return false;
            }
        } catch (error) {
            console.error("Error saving education:", error);
            showError("Error saving education: " + ((error instanceof Error ? error.message : String(error)) || "Unknown error"));
            setLoading(false);
            return false;
        }

        // Save skills
        try {
            // Make sure skills array is populated from UI if empty
            if (getSkills().length === 0) {
                const skillsContainer = document.getElementById("skills-container");
                if (skillsContainer) {
                    const skillElements = skillsContainer.querySelectorAll(".skill-badge");
                    if (skillElements.length > 0) {
                        skillElements.forEach(element => {
                            const skillText = element.textContent.trim().replace("×", "").trim();
                            if (skillText && !getSkills().includes(skillText)) {
                                getSkills().push(skillText);
                            }
                        });
                    }
                }
            }

            if (validateSkillsQualifications()) {
                const skillsResult = await saveSkillsQualifications();
                if (skillsResult) {
                } else {
                    console.error("Skills save returned false");
                    showError("Failed to save skills. Please try again.");
                    setLoading(false);
                    return false;
                }
            } else {
                console.error("Skills validation failed");
                showError("Please add at least one skill before proceeding.");
                setLoading(false);
                return false;
            }
        } catch (error) {
            console.error("Error saving skills:", error);
            showError("Error saving skills: " + ((error instanceof Error ? error.message : String(error)) || "Unknown error"));
            setLoading(false);
            return false;
        }

        // Step 4: Save Career Preferences
        try {
            if (validateCareerPreferences()) {
                await saveCareerPreferences();
            } else {
                console.error("Career preferences validation failed");
                showError("Please complete all required career preference fields before proceeding.");
                setLoading(false);
                return false; // Stop the profile completion process if validation fails
            }
        } catch (error) {
            console.error("Failed to save career preferences:", error);
            showError("Error saving career preferences: " + ((error instanceof Error ? error.message : String(error)) || "Unknown error"));
            setLoading(false);
            return false; // Stop the profile completion process if saving fails
        }

        // All sections have been successfully saved, mark profile as complete

        try {
            // Make API call to mark profile as complete
            const token = getAuthToken();
            const completeResponse = await fetch(`${API_BASE}/profile/complete`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                }
            });

            if (!completeResponse.ok) {
                const errorData = await completeResponse.json().catch(() => ({}));
                throw new Error(errorData.message || errorData.detail || `Server error: ${completeResponse.status}`);
            }

            // Set profile completed flag in localStorage
            localStorage.setItem("profile_completed", "true");

            // Show success message
            showSuccess("Profile completed successfully! Redirecting to dashboard...");

            // Redirect to dashboard — token is already in localStorage.
            // Use a short delay so the success message is visible before navigation.
            const successEl = document.getElementById('success-alert');
            if (successEl && typeof successEl.ontransitionend !== 'undefined') {
                successEl.addEventListener('transitionend', () => { window.location.href = '/dashboard'; }, { once: true });
                // Fallback in case transitionend never fires
                setTimeout(() => { window.location.href = '/dashboard'; }, 1200);
            } else {
                setTimeout(() => { window.location.href = '/dashboard'; }, 1200);
            }
        } catch (error) {
            console.error("Error marking profile as complete:", error);
            showError("Error completing profile: " + ((error instanceof Error ? error.message : String(error)) || "Unknown error"));
            setLoading(false);
            return false;
        }
    } catch (error) {
        console.error("Error completing profile:", error);
        showError("Failed to complete profile: " + (error instanceof Error ? error.message : String(error)));
    } finally {
        setLoading(false);
    }
}
