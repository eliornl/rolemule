/**
 * Help page — FAQ accordion, search filter, logout.
 */
import { logout } from '../shared/auth';

function toggleFAQ(element: HTMLElement): void {
  const item = element.parentElement;
  if (!item) return;
  const wasActive = item.classList.contains('active');

  document.querySelectorAll('.faq-item').forEach((i) => {
    i.classList.remove('active');
  });

  if (!wasActive) {
    item.classList.add('active');
  }
}

function filterFAQ(): void {
  const searchInput = document.getElementById('helpSearch') as HTMLInputElement | null;
  const searchTerm = searchInput?.value.toLowerCase() ?? '';
  const items = document.querySelectorAll('.faq-item');

  items.forEach((i) => {
    const item = i as HTMLElement;
    const question = (item.querySelector('.faq-question')?.textContent ?? '').toLowerCase();
    const answer = (item.querySelector('.faq-answer')?.textContent ?? '').toLowerCase();

    if (question.includes(searchTerm) || answer.includes(searchTerm)) {
      item.style.display = 'block';
      if (searchTerm.length > 2) {
        item.classList.add('active');
      }
    } else {
      item.style.display = searchTerm.length > 0 ? 'none' : 'block';
    }
  });
}

function initHelpPage(): void {
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener('click', (e) => {
      e.preventDefault();
      const href = anchor.getAttribute('href');
      const target = href ? document.querySelector(href) : null;
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  document.querySelector('.faq-section')?.addEventListener('click', (e) => {
    const target = e.target as HTMLElement | null;
    const question = target?.closest('.faq-question') as HTMLElement | null;
    if (question) toggleFAQ(question);
  });

  document.getElementById('helpSearch')?.addEventListener('input', filterFAQ);

  document.querySelector('[data-action="logout"]')?.addEventListener('click', (e) => {
    e.preventDefault();
    logout();
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initHelpPage);
} else {
  initHelpPage();
}
