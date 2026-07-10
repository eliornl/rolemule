/** Profile setup domain types. */

export interface WorkExperienceEntry {
  company: string;
  job_title: string;
  start_date: string;
  end_date: string;
  description: string;
  is_current: boolean;
  [key: string]: string | boolean | undefined;
}

export interface EducationEntry {
  institution: string;
  degree: string;
  field_of_study: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  graduation_date?: string;
  field?: string;
  [key: string]: string | boolean | undefined;
}

export interface CompletionStatus {
  profile_completed?: boolean;
  completion_percentage?: number;
  basic_info?: boolean;
  work_experience?: boolean;
  education?: boolean;
  skills_qualifications?: boolean;
  career_preferences?: boolean;
}

export interface ProfileData {
  city?: string;
  state?: string;
  country?: string;
  professional_title?: string;
  years_experience?: number;
  summary?: string;
  phone?: string;
  linkedin_url?: string;
  github_url?: string;
  portfolio_url?: string;
  work_experience?: WorkExperienceEntry[];
  education?: EducationEntry[];
  skills?: string[];
  is_student?: boolean;
  desired_salary_range?: { min?: number; max?: number };
  desired_company_sizes?: string[];
  job_types?: string[];
  work_arrangements?: string[];
  willing_to_relocate?: boolean;
  work_authorization?: string;
  requires_visa_sponsorship?: boolean;
  has_security_clearance?: boolean;
  max_travel_preference?: string;
}

export interface ProfilePayload {
  profile_data?: ProfileData;
  completion_status?: CompletionStatus;
}

export interface ParsedResumeData {
  city?: string;
  state?: string;
  country?: string;
  professional_title?: string;
  years_experience?: number;
  summary?: string;
  is_student?: boolean;
  phone?: string;
  linkedin_url?: string;
  github_url?: string;
  portfolio_url?: string;
  work_experience?: Array<Record<string, unknown>>;
  education?: Array<Record<string, unknown>>;
  skills?: string[];
}

export interface DropdownOption {
  value: string;
  label: string;
}
