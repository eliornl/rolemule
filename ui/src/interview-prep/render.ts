import { escapeHtml } from '../shared/dom-security';
import { el } from './dom';
import { getInterviewPrepData } from './state-access';
import type { QuestionCategory } from './types';

const QUESTION_CATEGORIES: QuestionCategory[] = [
  { key: 'for_recruiter', title: 'For the Recruiter', icon: 'fa-phone' },
  { key: 'for_hiring_manager', title: 'For the Hiring Manager', icon: 'fa-user-tie' },
  { key: 'for_team_members', title: 'For Team Members', icon: 'fa-users' },
  { key: 'red_flag_questions', title: 'Red Flag Questions', icon: 'fa-flag' },
];

export function renderInterviewPrep(): void {
  const data = getInterviewPrepData();
  if (!data) return;

  if (data.generated_at) {
    const generatedEl = el('generatedAt');
    if (generatedEl) {
      generatedEl.textContent = new Date(String(data.generated_at)).toLocaleString();
    }
  }

  renderInterviewProcess();
  const pq = (data.predicted_questions ?? {}) as Record<string, unknown[]>;
  renderQuestions('behavioral', (pq.behavioral ?? []) as Record<string, unknown>[]);
  renderQuestions('technical', (pq.technical ?? []) as Record<string, unknown>[]);
  renderQuestions('roleSpecific', (pq.role_specific ?? []) as Record<string, unknown>[]);
  renderQuestions('companySpecific', (pq.company_specific ?? []) as Record<string, unknown>[]);
  renderConcerns();
  renderQuestionsToAsk();
  renderChecklist();
  renderLogistics();
  renderConfidenceBoosters();
  renderQuickReference();
}

function renderInterviewProcess(): void {
  const data = getInterviewPrepData();
  const process = data?.interview_process as Record<string, unknown> | undefined;
  const section = el('interviewProcess');
  if (!process) {
    if (section) section.style.display = 'none';
    return;
  }

  let html = '';
  if (process.total_timeline || process.format_prediction) {
    html += `<div class="mb-4">
                ${process.total_timeline ? `<p><i class="fas fa-calendar-alt me-2 text-primary"></i><strong>Expected Timeline:</strong> ${escapeHtml(String(process.total_timeline))}</p>` : ''}
                ${process.format_prediction ? `<p><i class="fas fa-video me-2 text-primary"></i><strong>Format:</strong> ${escapeHtml(String(process.format_prediction))}</p>` : ''}
                ${process.preparation_time_needed ? `<p><i class="fas fa-hourglass-half me-2 text-primary"></i><strong>Prep Time Needed:</strong> ${escapeHtml(String(process.preparation_time_needed))}</p>` : ''}
            </div>`;
  }

  const rounds = (process.typical_rounds ?? []) as Record<string, unknown>[];
  if (rounds.length > 0) {
    html += '<div class="round-timeline">';
    rounds.forEach((round, i) => {
      html += `<div class="round-item"><div class="round-content">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <strong>Round ${round.round || i + 1}: ${escapeHtml(String(round.type || 'Interview'))}</strong>
                        <span class="badge bg-secondary">${escapeHtml(String(round.duration || ''))}</span>
                    </div>
                    <p class="mb-1 text-muted"><i class="fas fa-user me-1"></i>${escapeHtml(String(round.with || 'Interviewer'))}</p>
                    <p class="mb-1"><strong>Focus:</strong> ${escapeHtml(String(round.focus || ''))}</p>
                    ${round.tips ? `<p class="mb-0 text-success"><i class="fas fa-lightbulb me-1"></i>${escapeHtml(String(round.tips))}</p>` : ''}
                </div></div>`;
    });
    html += '</div>';
  }

  const contentEl = el('processContent');
  if (contentEl) {
    contentEl.innerHTML =
      html || "<p class='text-muted'>No interview process information available.</p>";
  }
}

function renderQuestions(
  containerId: string,
  questions: Record<string, unknown>[],
): void {
  const container = el(containerId);
  if (!container) return;
  if (!questions || questions.length === 0) {
    container.innerHTML = "<p class='text-muted'>No questions in this category.</p>";
    return;
  }

  let html = '';
  for (const q of questions) {
    html += '<div class="question-card">';
    html += `<div class="question-text">${escapeHtml(String(q.question ?? ''))}</div>`;
    if (q.why_likely) {
      html += `<div class="question-meta"><i class="fas fa-info-circle me-1"></i>${escapeHtml(String(q.why_likely))}</div>`;
    }
    const story = q.your_story as Record<string, unknown> | undefined;
    if (story) {
      html += '<div class="star-section"><div class="star-label">Your STAR Answer</div>';
      if (story.use_this_experience) {
        html += `<p class="mb-2"><strong>Use:</strong> ${escapeHtml(String(story.use_this_experience))}</p>`;
      }
      if (story.situation) {
        html += `<p class="mb-1"><span class="badge bg-primary me-2">S</span>${escapeHtml(String(story.situation))}</p>`;
      }
      if (story.task) {
        html += `<p class="mb-1"><span class="badge bg-primary me-2">T</span>${escapeHtml(String(story.task))}</p>`;
      }
      if (story.action) {
        html += `<p class="mb-1"><span class="badge bg-primary me-2">A</span>${escapeHtml(String(story.action))}</p>`;
      }
      if (story.result) {
        html += `<p class="mb-0"><span class="badge bg-primary me-2">R</span>${escapeHtml(String(story.result))}</p>`;
      }
      html += '</div>';
    }
    if (q.preparation_approach) {
      html += `<div class="star-section"><p class="mb-2"><strong>Preparation:</strong> ${escapeHtml(String(q.preparation_approach))}</p>`;
      const kp = (q.key_points_to_cover ?? []) as string[];
      if (kp.length > 0) {
        html += `<p class="mb-1"><strong>Key Points:</strong></p><ul class="mb-0">${kp.map((p) => `<li>${escapeHtml(p)}</li>`).join('')}</ul>`;
      }
      html += '</div>';
    }
    if (q.answer_strategy) {
      html += `<div class="star-section"><p class="mb-0"><strong>Strategy:</strong> ${escapeHtml(String(q.answer_strategy))}</p></div>`;
    }
    if (q.personalized_answer) {
      html += `<div class="star-section"><p class="mb-0"><strong>Your Answer:</strong> ${escapeHtml(String(q.personalized_answer))}</p></div>`;
    }
    if (q.what_they_evaluate) {
      html += `<div class="mt-2 text-muted small"><i class="fas fa-search me-1"></i>They're evaluating: ${escapeHtml(String(q.what_they_evaluate))}</div>`;
    }
    if (q.danger_zone) {
      html += `<div class="danger-zone"><div class="danger-zone-label"><i class="fas fa-exclamation-triangle me-1"></i>Don't Say</div><div>${escapeHtml(String(q.danger_zone))}</div></div>`;
    }
    html += '</div>';
  }
  container.innerHTML = html;
}

function renderConcerns(): void {
  const data = getInterviewPrepData();
  const concerns = (data?.addressing_concerns ?? []) as Record<string, unknown>[];
  const container = el('concernsContent');
  if (!container) return;
  if (concerns.length === 0) {
    container.innerHTML =
      '<div class="empty-state"><i class="fas fa-check-circle text-success"></i><p>No significant concerns identified. You\'re well-matched for this role!</p></div>';
    return;
  }
  container.innerHTML = concerns
    .map((concern) => {
      let html =
        `<div class="concern-card"><div class="concern-title"><i class="fas fa-exclamation-circle me-2"></i>${escapeHtml(String(concern.concern ?? ''))}</div>`;
      if (concern.why_its_a_concern) {
        html += `<p class="text-muted mb-2"><strong>What they might think:</strong> ${escapeHtml(String(concern.why_its_a_concern))}</p>`;
      }
      if (concern.your_counter_narrative) {
        html += `<p class="mb-2"><strong>Your counter-narrative:</strong> ${escapeHtml(String(concern.your_counter_narrative))}</p>`;
      }
      const pts = (concern.talking_points ?? []) as string[];
      if (pts.length > 0) {
        html += `<div class="talking-point"><strong>Talking Points:</strong><ul class="mb-0 mt-1">${pts.map((p) => `<li>${escapeHtml(p)}</li>`).join('')}</ul></div>`;
      }
      if (concern.when_to_bring_up) {
        html += `<p class="mt-2 mb-0 text-info"><i class="fas fa-clock me-1"></i><strong>When:</strong> ${escapeHtml(String(concern.when_to_bring_up))}</p>`;
      }
      return `${html}</div>`;
    })
    .join('');
}

function renderQuestionsToAsk(): void {
  const data = getInterviewPrepData();
  const questions = (data?.questions_for_them ?? {}) as Record<string, unknown[]>;
  const container = el('askContent');
  if (!container) return;

  let html = '';
  for (const cat of QUESTION_CATEGORIES) {
    const qs = (questions[cat.key] ?? []) as Record<string, unknown>[];
    if (qs.length > 0) {
      html += `<h6 class="mt-4 mb-3"><i class="fas ${cat.icon} me-2"></i>${cat.title}</h6>`;
      for (const q of qs) {
        html += `<div class="ask-question-card"><div class="fw-bold mb-2">"${escapeHtml(String(q.question ?? ''))}"</div>`;
        if (q.why_good) {
          html += `<p class="text-muted mb-1"><i class="fas fa-lightbulb me-1"></i>${escapeHtml(String(q.why_good))}</p>`;
        }
        if (q.listen_for) {
          html += `<p class="mb-0 text-success"><i class="fas fa-ear-listen me-1"></i><strong>Listen for:</strong> ${escapeHtml(String(q.listen_for))}</p>`;
        }
        if (q.when_to_ask) {
          html += `<p class="mb-0 text-info"><i class="fas fa-clock me-1"></i><strong>When:</strong> ${escapeHtml(String(q.when_to_ask))}</p>`;
        }
        html += '</div>';
      }
    }
  }
  container.innerHTML = html || "<p class='text-muted'>No questions to ask available.</p>";
}

function renderChecklist(): void {
  const data = getInterviewPrepData();
  const checklist = (data?.day_before_checklist ?? []) as string[];
  const container = el('checklistContent');
  if (!container) return;
  if (checklist.length === 0) {
    container.innerHTML = "<p class='text-muted'>No checklist available.</p>";
    return;
  }
  container.innerHTML = checklist
    .map(
      (item) =>
        `<div class="checklist-item"><i class="fas fa-check-square"></i><span>${escapeHtml(item)}</span></div>`,
    )
    .join('');
}

function renderLogistics(): void {
  const data = getInterviewPrepData();
  const logistics = (data?.logistics ?? {}) as Record<string, unknown>;
  const container = el('logisticsContent');
  if (!container) return;

  let html = '';
  if (logistics.dress_code) {
    html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-tshirt"></i></div><div><strong>Dress Code:</strong> ${escapeHtml(String(logistics.dress_code))}</div></div>`;
  }
  const timing = logistics.timing as Record<string, string> | undefined;
  if (timing) {
    html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-clock"></i></div><div><strong>Arrive:</strong> ${escapeHtml(timing.arrive ?? '')}`;
    if (timing.expected_duration) {
      html += `<br><strong>Duration:</strong> ${escapeHtml(timing.expected_duration)}`;
    }
    html += '</div></div>';
  }
  const bring = (logistics.what_to_bring ?? []) as string[];
  if (bring.length > 0) {
    html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-briefcase"></i></div><div><strong>Bring:</strong> ${bring.map(escapeHtml).join(', ')}</div></div>`;
  }
  const vTips = (logistics.virtual_interview_tips ?? []) as string[];
  if (vTips.length > 0) {
    html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-video"></i></div><div><strong>Virtual Tips:</strong><ul class="mb-0 mt-1">${vTips.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul></div></div>`;
  }
  const post = logistics.post_interview as Record<string, string> | undefined;
  if (post) {
    html += `<div class="logistics-item"><div class="logistics-icon"><i class="fas fa-envelope"></i></div><div><strong>After:</strong> ${escapeHtml(post.thank_you_note ?? '')}`;
    if (post.follow_up_timeline) {
      html += `<br><strong>Follow up:</strong> ${escapeHtml(post.follow_up_timeline)}`;
    }
    html += '</div></div>';
  }
  container.innerHTML = html || "<p class='text-muted'>No logistics information available.</p>";
}

function renderConfidenceBoosters(): void {
  const data = getInterviewPrepData();
  const boosters = (data?.confidence_boosters ?? []) as string[];
  const container = el('confidenceContent');
  if (!container) return;
  if (boosters.length === 0) {
    container.innerHTML = "<p class='text-muted'>No confidence boosters available.</p>";
    return;
  }
  container.innerHTML = boosters
    .map(
      (b) =>
        `<div class="confidence-booster"><i class="fas fa-star me-2"></i>${escapeHtml(b)}</div>`,
    )
    .join('');
}

function renderQuickReference(): void {
  const data = getInterviewPrepData();
  const ref = (data?.quick_reference_card ?? {}) as Record<string, unknown>;
  const container = el('referenceContent');
  if (!container) return;

  let html = '';
  if (ref.elevator_pitch) {
    html += `<div class="reference-item"><div class="reference-label">Elevator Pitch (30 sec)</div><div>${escapeHtml(String(ref.elevator_pitch))}</div></div>`;
  }
  const selling = (ref.three_key_selling_points ?? []) as string[];
  if (selling.length > 0) {
    html += `<div class="reference-item"><div class="reference-label">Your 3 Key Selling Points</div><ol class="mb-0">${selling.map((p) => `<li>${escapeHtml(p)}</li>`).join('')}</ol></div>`;
  }
  const wa = ref.weakness_answer as Record<string, string> | undefined;
  if (wa?.weakness) {
    html += `<div class="reference-item"><div class="reference-label">Weakness Answer</div><div><strong>${escapeHtml(wa.weakness)}</strong>`;
    if (wa.how_addressing) html += ` - ${escapeHtml(wa.how_addressing)}`;
    html += '</div></div>';
  }
  if (ref.why_this_company) {
    html += `<div class="reference-item"><div class="reference-label">Why This Company?</div><div>${escapeHtml(String(ref.why_this_company))}</div></div>`;
  }
  const sd = ref.salary_discussion as Record<string, string> | undefined;
  if (sd?.anchor_range) {
    html += `<div class="reference-item"><div class="reference-label">Salary Discussion</div><div><strong>Target:</strong> ${escapeHtml(sd.anchor_range)}`;
    if (sd.deflection_phrase) {
      html += `<br><strong>If asked early:</strong> "${escapeHtml(sd.deflection_phrase)}"`;
    }
    html += '</div></div>';
  }
  if (ref.closing_statement) {
    html += `<div class="reference-item"><div class="reference-label">Closing Statement</div><div>${escapeHtml(String(ref.closing_statement))}</div></div>`;
  }
  container.innerHTML = html || "<p class='opacity-75'>No quick reference available.</p>";
}
