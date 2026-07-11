/** Core API / domain types ported from ui/static/js/types.js */

export interface ApiResponse {
  success?: boolean;
  message?: string;
  error?: string;
  redirect?: string;
  error_code?: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  profile_completed: boolean;
  profile_completion_percentage?: number;
  created_at?: string;
  last_login?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
  user?: User;
}

export interface PaginatedResponse {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
  has_prev: boolean;
  has_next: boolean;
}

export interface DashboardApplication {
  id: string;
  workflow_session_id?: string;
  status?: string;
  job_title?: string;
  company_name?: string;
  created_at?: string;
  updated_at?: string;
  match_score?: number;
}

export interface ApplicationsListResponse {
  total: number;
  applications: DashboardApplication[];
}

export interface ApplicationStatsResponse {
  total: number;
  applied: number;
  interviews: number;
  response_rate: number;
}

export interface WorkflowStartResponse {
  session_id?: string;
}

export interface WorkflowStatusResponse {
  status?: string;
  error_messages?: string[];
}
