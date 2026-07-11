import { getSkills, setSkills } from './state-access';
import { skillsContainer } from './dom';

export function addSkill(skill: string): void {
  if (skill && !getSkills().includes(skill)) {
    getSkills().push(skill);
    renderSkills();
  }
}

export function removeSkill(skill: string): void {
  setSkills(getSkills().filter((s) => s !== skill));
  renderSkills();
}

export function renderSkills(): void {
  const container =
    skillsContainer || document.getElementById('skills-container');
  if (!container) return;
  container.innerHTML = '';

  getSkills().forEach((skill) => {
    const tag = document.createElement('div');
    tag.className = 'skill-tag';
    const span = document.createElement('span');
    span.textContent = skill;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'skill-remove';
    btn.setAttribute('aria-label', `Remove skill: ${skill}`);
    btn.innerHTML = '<i class="fas fa-times"></i>';
    btn.addEventListener('click', () => removeSkill(skill));
    tag.appendChild(span);
    tag.appendChild(btn);
    container.appendChild(tag);
  });
}
