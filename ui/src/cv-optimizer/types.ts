export type CvOptimizerUiState = 'not_started' | 'running' | 'complete' | 'error';

export interface IterationHistoryRow {
  iteration: number;
  score: number;
  strengths?: string[];
  gaps?: string[];
}

export interface CvOptimizationResult {
  optimized_cv?: string;
  cover_letter?: string;
  best_score?: number;
  best_iteration?: number;
  stop_reason?: string;
  completed_at?: string;
  gap_analysis?: string[];
  iteration_history?: IterationHistoryRow[];
}

export interface CvOptimizerStatusResponse {
  is_running?: boolean;
  has_result?: boolean;
}

export interface CvOptimizerResultResponse {
  has_result?: boolean;
  result?: CvOptimizationResult;
}
