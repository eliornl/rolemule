/**
 * Typed access to server-injected window.APP_CONFIG.
 */

export interface AppConfig {
  apiBase: string;
  loginUrl: string;
  posthogEnabled: boolean;
}

export function getAppConfig(): AppConfig {
  return {
    apiBase: window.APP_CONFIG?.apiBase || '/api/v1',
    loginUrl: window.APP_CONFIG?.loginUrl || '/auth/login',
    posthogEnabled: Boolean(window.APP_CONFIG?.posthogEnabled),
  };
}
