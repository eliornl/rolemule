import { getAuthToken } from '../shared/auth';

export function getAuthHeaders(): Record<string, string> {
  const token = getAuthToken();
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}
