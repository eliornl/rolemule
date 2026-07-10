import { debounce, readSalaryField } from './utils';
import { initializeResumeUpload } from './resume-upload';
import { addSkill } from './skills';
import { addWorkExperience } from './work-experience';
import { addEducation } from './education';
import { educationContainer, experienceContainer } from './dom';

export function initializeEventListeners(): void {
  initializeResumeUpload();

  const skillsInput = document.getElementById(
    'skills-input',
  ) as HTMLInputElement | null;
  skillsInput?.addEventListener('keypress', function (e: KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault();
      addSkill(this.value.trim());
      this.value = '';
    }
  });

  const debouncedSalaryValidate = debounce(() => {
    const minEl = document.getElementById(
      'min-salary',
    ) as HTMLInputElement | null;
    const maxEl = document.getElementById(
      'max-salary',
    ) as HTMLInputElement | null;
    const min = readSalaryField(minEl);
    const max = readSalaryField(maxEl);
    if (maxEl && max > 0 && min > 0 && max <= min) {
      maxEl.setCustomValidity(
        'Maximum salary must be greater than minimum salary.',
      );
    } else if (maxEl) {
      maxEl.setCustomValidity('');
    }
  }, 300);

  ['min-salary', 'max-salary'].forEach((id) => {
    const salaryInput = document.getElementById(id) as HTMLInputElement | null;
    salaryInput?.addEventListener('input', debouncedSalaryValidate);
    salaryInput?.addEventListener('blur', () => {
      if (!salaryInput) return;
      const n = readSalaryField(salaryInput);
      salaryInput.value = n > 0 ? String(n) : '';
      debouncedSalaryValidate();
    });
  });

  document
    .getElementById('add-experience-btn')
    ?.addEventListener('click', addWorkExperience);

  const noExperienceCheckbox = document.getElementById(
    'no-experience',
  ) as HTMLInputElement | null;
  const addExperienceBtn = document.getElementById('add-experience-btn');
  if (noExperienceCheckbox) {
    noExperienceCheckbox.addEventListener('change', function () {
      const container =
        experienceContainer ||
        document.getElementById('experience-container');
      if (this.checked) {
        if (addExperienceBtn) {
          addExperienceBtn.style.opacity = '0.5';
          addExperienceBtn.style.pointerEvents = 'none';
        }
        if (container) container.style.opacity = '0.5';
      } else {
        if (addExperienceBtn) {
          addExperienceBtn.style.opacity = '1';
          addExperienceBtn.style.pointerEvents = 'auto';
        }
        if (container) container.style.opacity = '1';
      }
    });
  }

  document
    .getElementById('add-education-btn')
    ?.addEventListener('click', addEducation);

  const noEducationCheckbox = document.getElementById(
    'no-education',
  ) as HTMLInputElement | null;
  const addEducationBtn = document.getElementById('add-education-btn');
  if (noEducationCheckbox) {
    noEducationCheckbox.addEventListener('change', function () {
      const ec =
        educationContainer || document.getElementById('education-container');
      if (this.checked) {
        if (addEducationBtn) {
          addEducationBtn.style.opacity = '0.5';
          addEducationBtn.style.pointerEvents = 'none';
        }
        if (ec) ec.style.opacity = '0.5';
      } else {
        if (addEducationBtn) {
          addEducationBtn.style.opacity = '1';
          addEducationBtn.style.pointerEvents = 'auto';
        }
        if (ec) ec.style.opacity = '1';
      }
    });
  }
}
