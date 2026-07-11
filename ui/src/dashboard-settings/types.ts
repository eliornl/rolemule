export interface ApplicationPreferences {
  workflow_gate_threshold?: number;
  auto_generate_documents?: boolean;
  cover_letter_tone?: string;
  resume_length?: string;
  preferred_model?: string | null;
}

export interface ApiKeyStatusResponse {
  has_user_key?: boolean;
  has_api_key?: boolean;
  server_has_key?: boolean;
  use_vertex_ai?: boolean;
  key_preview?: string | null;
}

export interface ApiKeyValidateResponse {
  valid?: boolean;
  models_available?: number | string;
  message?: string;
  detail?: string;
}

export interface UserProfilePayload {
  user_info?: {
    auth_method?: string;
    has_password?: boolean;
  };
}

export interface ApplicationStatsOverview {
  total_applications?: number;
}

export type AlertType = 'success' | 'danger' | 'warning' | 'info';

export interface NotifyOptions {
  loading?: boolean;
}
