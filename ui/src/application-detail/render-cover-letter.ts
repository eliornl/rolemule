import { decodeEntities, escapeHtml } from '../shared/dom-security';
import { getCurrentSessionId } from './state';
import type { CoverLetter, GenerateDocKind, JobAnalysis } from './types';

type GenerateHandler = (kind: GenerateDocKind, btn: HTMLButtonElement) => void;

let generateHandler: GenerateHandler | null = null;

/** Wire after `generateSingle` is defined in the page entry (avoids circular imports). */
export function wireCoverLetterGenerate(handler: GenerateHandler): void {
  generateHandler = handler;
}

export function renderCoverLetter(
  cover: CoverLetter,
  _job?: JobAnalysis,
): void {
  const letter =
    cover.content ||
    cover.cover_letter_text ||
    cover.letter ||
    cover.cover_letter ||
    '';

  const coverEl = document.getElementById('coverContent');
  if (!coverEl) return;

  if (!letter) {
    coverEl.innerHTML = `
      <div class="empty-state">
        <i class="fas fa-envelope empty-state-icon"></i>
        <p class="empty-state-title">Cover Letter</p>
        <p class="empty-state-desc">Generate a tailored cover letter based on the job requirements and your profile.</p>
        ${
          getCurrentSessionId()
            ? `<button class="regen-btn" id="generateCoverBtn">
          <span class="spinner"></span>
          <span class="btn-text">Generate Cover Letter</span>
        </button>`
            : ''
        }
      </div>`;
    const genCoverBtn = document.getElementById('generateCoverBtn') as HTMLButtonElement | null;
    if (genCoverBtn && generateHandler) {
      genCoverBtn.addEventListener('click', () => generateHandler!('cover', genCoverBtn));
    }
    return;
  }

  const wordCount = letter.trim().split(/\s+/).filter(Boolean).length;
  const generatedAt = cover.generated_at
    ? new Date(cover.generated_at).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : '';

  coverEl.innerHTML = `
    <div class="cover-letter-wrapper">
      <div class="cover-letter-box">
        <div class="cover-letter-body" id="coverLetterText"></div>
        <div class="cover-letter-box-footer">
          <div class="cl-footer-meta">
            <span><i class="fas fa-align-left"></i> ${wordCount} words</span>
            ${
              generatedAt
                ? `<span><i class="fas fa-clock"></i> Generated ${escapeHtml(generatedAt)}</span>`
                : ''
            }
          </div>
          <div class="cl-footer-actions">
            <button class="cl-copy-btn" data-action="copy-cover" aria-label="Copy cover letter">
              <i class="fas fa-copy"></i> Copy
            </button>
            <button class="cl-copy-btn regen-btn" data-action="regen-cover" aria-label="Regenerate cover letter">
              <span class="spinner"></span>
              <span class="btn-text"><i class="fas fa-sync-alt"></i> Regenerate</span>
            </button>
          </div>
        </div>
      </div>
    </div>`;
  const cltEl = document.getElementById('coverLetterText');
  if (cltEl) cltEl.textContent = decodeEntities(letter);
}
