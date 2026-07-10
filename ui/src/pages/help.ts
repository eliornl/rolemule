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
  const searchTerm = searchInput?.value.trim().toLowerCase() ?? '';
  const helpPage = document.querySelector('.help-page');
  const quickLinks = document.querySelector('.quick-links') as HTMLElement | null;
  const items = document.querySelectorAll('.faq-item');
  const visibleMatches: HTMLElement[] = [];

  helpPage?.classList.toggle('is-searching', searchTerm.length > 0);
  if (quickLinks) {
    quickLinks.style.display = searchTerm.length > 0 ? 'none' : '';
  }

  items.forEach((node) => {
    const item = node as HTMLElement;
    const question = (item.querySelector('.faq-question')?.textContent ?? '').toLowerCase();
    const answer = (item.querySelector('.faq-answer')?.textContent ?? '').toLowerCase();
    const categoryTitle =
      item.closest('.faq-category')?.querySelector('h2')?.textContent?.toLowerCase() ?? '';
    const matches =
      searchTerm.length === 0 ||
      question.includes(searchTerm) ||
      answer.includes(searchTerm) ||
      categoryTitle.includes(searchTerm);

    item.classList.toggle('is-search-hidden', !matches);
    item.classList.toggle('active', matches && searchTerm.length > 0);

    if (matches && searchTerm.length > 0) {
      visibleMatches.push(item);
    }
  });

  document.querySelectorAll('.faq-category').forEach((node) => {
    const category = node as HTMLElement;
    const hasVisibleItem = category.querySelector('.faq-item:not(.is-search-hidden)') !== null;
    category.classList.toggle('is-search-hidden', searchTerm.length > 0 && !hasVisibleItem);
  });

  if (visibleMatches.length > 0) {
    visibleMatches[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
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
