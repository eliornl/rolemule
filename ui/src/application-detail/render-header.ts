import { decodeEntities } from '../shared/dom-security';
import {
  resolveEffectiveCompanyName,
} from '../shared/dashboard-display';
import { formatPostedDate, toTitleCase } from './utils';
import type { JobAnalysis, ProfileMatching } from './types';

export function renderHeader(job: JobAnalysis, match: ProfileMatching): void {
  const jtEl = document.getElementById('jobTitle');
  const cnEl = document.getElementById('companyName');
  const cdEl = document.getElementById('createdDate');
  if (jtEl) jtEl.textContent = decodeEntities(job.job_title || 'Job Application');
  if (cnEl) {
    const effective = resolveEffectiveCompanyName({
      analysisCompanyName: job.company_name,
      applicationCompanyName: job.application_company_name,
      detectedCompany: job.detected_company,
    });
    cnEl.textContent = effective ? decodeEntities(effective) : 'Unknown';
  }
  if (cdEl) cdEl.textContent = new Date().toLocaleDateString();

  const extraLocations = Array.isArray(job.additional_locations)
    ? job.additional_locations.filter(Boolean)
    : [];
  const primaryLocation = [job.job_city, job.job_state, job.job_country]
    .filter(Boolean)
    .join(', ');
  const location = [primaryLocation, ...extraLocations].filter(Boolean).join(' | ');
  if (location) {
    const jlEl = document.getElementById('jobLocation');
    const lmEl = document.getElementById('locationMeta');
    if (jlEl) jlEl.textContent = location;
    if (lmEl) lmEl.style.display = 'flex';
  }

  const formattedPostedDate = formatPostedDate(job.posted_date);
  if (formattedPostedDate) {
    const pdEl = document.getElementById('postedDateText');
    const pmEl = document.getElementById('postedDateMeta');
    if (pdEl) pdEl.textContent = formattedPostedDate;
    if (pmEl) pmEl.style.display = 'flex';
  }

  let salaryDisplay: string | null = null;
  if (job.salary_range && typeof job.salary_range === 'object') {
    const range = job.salary_range;
    if (range.min || range.max) {
      const curr = range.currency || '$';
      const min = range.min ? `${curr}${(range.min / 1000).toFixed(0)}K` : '';
      const max = range.max ? `${curr}${(range.max / 1000).toFixed(0)}K` : '';
      if (min && max) salaryDisplay = `${min} - ${max}`;
      else if (min) salaryDisplay = `${min}+`;
      else if (max) salaryDisplay = `Up to ${max}`;
    }
  } else if (typeof job.salary_range === 'string') {
    const trimmed = job.salary_range.trim();
    if (trimmed && /\d/.test(trimmed)) salaryDisplay = trimmed;
  }
  if (salaryDisplay) {
    const srEl = document.getElementById('salaryRange');
    const sbEl = document.getElementById('salaryBadge');
    if (srEl) srEl.textContent = salaryDisplay;
    if (sbEl) sbEl.style.display = 'inline-flex';
  }

  if (job.employment_type) {
    const etEl = document.getElementById('employmentType');
    const tbEl = document.getElementById('typeBadge');
    if (etEl) etEl.textContent = toTitleCase(decodeEntities(job.employment_type));
    if (tbEl) tbEl.style.display = 'inline-flex';
  }

  if (job.work_arrangement) {
    const wtEl = document.getElementById('workType');
    const wbEl = document.getElementById('workBadge');
    if (wtEl) wtEl.textContent = toTitleCase(decodeEntities(job.work_arrangement));
    if (wbEl) wbEl.style.display = 'inline-flex';
  }

  const qa = (match.quantified_assessment || match.final_scores || {}) as Record<
    string,
    unknown
  >;
  const matchScore =
    (qa.overall_match_score as number | undefined) ||
    match.overall_match_score ||
    match.overall_score ||
    0;
  const scorePercent =
    matchScore > 1 ? Math.round(matchScore) : Math.round(matchScore * 100);

  const msEl = document.getElementById('matchScore');
  const mcEl = document.getElementById('matchCircle');
  if (msEl) msEl.textContent = `${scorePercent}%`;
  if (mcEl) mcEl.style.setProperty('--score', String(scorePercent));

  const exec = (match.executive_summary || {}) as Record<string, unknown>;
  const rec = String(exec.recommendation || match.recommendation || 'REVIEW').toUpperCase();
  const statusEl = document.getElementById('matchStatus');

  if (statusEl) {
    if (rec.includes('GOOD') || rec.includes('STRONG')) {
      statusEl.textContent = 'Good Match';
      statusEl.className = 'match-status good';
    } else if (rec.includes('POOR') || rec.includes('PASS')) {
      statusEl.textContent = 'Weak Match';
      statusEl.className = 'match-status poor';
    } else {
      statusEl.textContent = 'Review';
      statusEl.className = 'match-status review';
    }
  }
}
