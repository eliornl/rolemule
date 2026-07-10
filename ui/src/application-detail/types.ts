/** Agent JSON blobs — typed at the fields the UI reads; extra keys allowed. */

export interface SalaryRange {
  min?: number;
  max?: number;
  currency?: string;
}

export interface JobAnalysis {
  job_title?: string;
  company_name?: string;
  job_city?: string;
  job_state?: string;
  job_country?: string;
  additional_locations?: string[];
  posted_date?: string;
  salary_range?: SalaryRange | string;
  employment_type?: string;
  work_arrangement?: string;
  required_skills?: unknown[];
  ats_keywords?: unknown[];
  keywords?: unknown[];
  required_qualifications?: unknown;
  preferred_qualifications?: unknown;
  responsibilities?: unknown;
  soft_skills?: unknown;
  job_description?: string;
  [key: string]: unknown;
}

export interface ProfileMatching {
  executive_summary?: Record<string, unknown>;
  quantified_assessment?: Record<string, unknown>;
  final_scores?: Record<string, unknown>;
  overall_match_score?: number;
  overall_score?: number;
  recommendation?: string;
  detailed_analysis?: Record<string, unknown>;
  key_strengths?: unknown;
  critical_gaps?: unknown;
  gaps?: unknown;
  application_strategy?: Record<string, unknown>;
  competitive_positioning?: Record<string, unknown>;
  risk_assessment?: Record<string, unknown>;
  deal_breaker_analysis?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface CompanyResearch {
  company_name?: string;
  website?: string;
  interview_preparation?: InterviewPrep | null;
  [key: string]: unknown;
}

export interface CoverLetter {
  content?: string;
  cover_letter_text?: string;
  letter?: string;
  cover_letter?: string;
  generated_at?: string;
  [key: string]: unknown;
}

export interface ResumeRecommendations {
  comprehensive_advice?: Record<string, unknown>;
  error?: string;
  [key: string]: unknown;
}

export interface InterviewPrep {
  parse_error?: string;
  interview_process?: unknown;
  predicted_questions?: unknown;
  interview_stages?: unknown;
  likely_questions?: unknown;
  [key: string]: unknown;
}

export interface WorkflowResults {
  status?: string;
  current_agent?: string | null;
  error_messages?: string[];
  job_url?: string;
  job_analysis?: JobAnalysis;
  profile_matching?: ProfileMatching;
  company_research?: CompanyResearch;
  resume_recommendations?: ResumeRecommendations;
  cover_letter?: CoverLetter;
  [key: string]: unknown;
}

export type GenerateDocKind = 'cover' | 'resume';
