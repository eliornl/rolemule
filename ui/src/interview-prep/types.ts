export interface InterviewPrepStatusResponse {
  has_interview_prep?: boolean;
  interview_prep?: Record<string, unknown>;
}

export interface InterviewPrepLoadResponse {
  has_interview_prep?: boolean;
  interview_prep?: Record<string, unknown>;
}

export interface WorkflowResultsResponse {
  job_analysis?: {
    job_title?: string;
    company_name?: string;
  };
}

export interface WsMessage {
  type?: string;
  [key: string]: unknown;
}

export interface QuestionCategory {
  key: string;
  title: string;
  icon: string;
}
