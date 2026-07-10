export interface ScoreTier {
  bannerClass: string;
  icon: string;
  scoreClass: string;
  spinning: boolean;
}

export function scoreTier(score: number | null | undefined): ScoreTier {
  if (typeof score !== 'number') {
    return {
      bannerClass: 'apply-muted',
      icon: 'fa-chart-line',
      scoreClass: '',
      spinning: false,
    };
  }
  if (score >= 8.5) {
    return {
      bannerClass: 'apply-good',
      icon: 'fa-check-circle',
      scoreClass: 'cvo-score-excellent',
      spinning: false,
    };
  }
  if (score >= 5.0) {
    return {
      bannerClass: 'apply-review',
      icon: 'fa-chart-line',
      scoreClass: 'cvo-score-fair',
      spinning: false,
    };
  }
  return {
    bannerClass: 'apply-poor',
    icon: 'fa-exclamation-circle',
    scoreClass: 'cvo-score-poor',
    spinning: false,
  };
}

export function progressAnswerText(score: number | null | undefined): string {
  return typeof score === 'number' ? `${score.toFixed(1)} / 10` : 'Evaluating…';
}

export function scoreClass(score: number | null | undefined): string {
  if (typeof score !== 'number') return '';
  return scoreTier(score).scoreClass;
}

export function chartScoreClass(score: number | null | undefined): string {
  if (typeof score !== 'number') return '';
  if (score >= 8.5) return 'cvo-score-high';
  if (score >= 7.0) return 'cvo-score-medium';
  return 'cvo-score-low';
}

export function resultBannerClass(stopReason: string | null | undefined): string {
  switch (stopReason) {
    case 'score_threshold':
      return 'apply-good';
    case 'score_plateau':
      return 'apply-review';
    case 'api_rate_limit':
      return 'apply-review';
    case 'score_decrease':
      return 'apply-poor';
    default:
      return 'apply-muted';
  }
}

export function resultBannerIcon(stopReason: string | null | undefined): string {
  switch (stopReason) {
    case 'score_threshold':
      return 'fa-check-circle';
    case 'score_plateau':
      return 'fa-pause-circle';
    case 'api_rate_limit':
      return 'fa-hourglass-half';
    case 'score_decrease':
      return 'fa-arrow-down';
    default:
      return 'fa-flag-checkered';
  }
}

export function stopReasonLabel(stopReason: string | null | undefined): string {
  switch (stopReason) {
    case 'score_threshold':
      return 'Score threshold reached';
    case 'score_decrease':
      return 'Score decreased — kept best version';
    case 'score_plateau':
      return 'Score plateaued';
    case 'api_rate_limit':
      return 'AI rate limit reached — best progress saved';
    case 'max_iterations':
      return 'Max iterations reached';
    default:
      return stopReason || '';
  }
}
