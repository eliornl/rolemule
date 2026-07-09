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

/** Parse FastAPI error body — message (APIError) or detail (validation). */
export function errorMessageFromBody(
  body: { message?: string; detail?: string },
  fallback: string,
): string {
  if (typeof body.message === 'string' && body.message) return body.message;
  if (typeof body.detail === 'string' && body.detail) return body.detail;
  return fallback;
}
