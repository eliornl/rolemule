import { VALIDATION_RULES } from './state';
import { getSkills } from './state-access';
import {
  validateBasicInfo,
  validateCareerPreferences,
  validateEducation,
  validateWorkExperience,
} from './validation';
import { escapeHtml } from '../shared/dom-security';

export function updateCompletionSummary(): void {
  const container = document.getElementById('completion-items');
  if (!container) return;

  container.innerHTML = '';

  const items = [
    { name: 'Basic Information', completed: validateBasicInfo() },
    { name: 'Work Experience', completed: validateWorkExperience() },
    { name: 'Education', completed: validateEducation() },
    {
      name: 'Skills',
      completed: getSkills().length >= VALIDATION_RULES.MIN_SKILLS,
    },
    { name: 'Career Preferences', completed: validateCareerPreferences() },
  ];

  items.forEach((item) => {
    const div = document.createElement('div');
    div.className = 'completion-item';
    div.innerHTML = `
        <span>${escapeHtml(item.name)}</span>
        <span class="completion-status">
            ${item.completed ? '<i class="fas fa-check text-success"></i> Complete' : '<i class="fas fa-times text-danger"></i> Incomplete'}
        </span>
    `;
    container.appendChild(div);
  });
}
