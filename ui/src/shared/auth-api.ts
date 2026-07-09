/**
 * Auth-specific API response shapes.
 */
import type { User } from './types';

export interface VerifyCodeResponse {
  access_token?: string;
  token_type?: string;
  user?: User;
  profile_completed?: boolean;
  message?: string;
  redirect?: string;
}

export interface ResendVerificationResponse {
  message?: string;
  detail?: string;
}

export interface ForgotPasswordResponse {
  message?: string;
  detail?: string;
  reset_url?: string;
}

export interface ResetPasswordResponse {
  message?: string;
  detail?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type?: string;
  user?: User;
  profile_completed?: boolean;
}

export interface RegisterResponse {
  access_token?: string;
  token_type?: string;
  user?: User & { email_verified?: boolean };
  profile_completed?: boolean;
  message?: string;
  detail?: string;
  error?: string;
  errors?: unknown[];
}

export interface OAuthStatusResponse {
  google_oauth_enabled?: boolean;
}

/** Parse FastAPI error body — message (APIError) or detail (validation). */
export function errorMessageFromBody(
  body: { message?: string; detail?: string },
  fallback: string,
): string {
  if (typeof body.message === 'string' && body.message) return body.message;
  if (typeof body.detail === 'string' && body.detail) return body.detail;
  return fallback;
}
