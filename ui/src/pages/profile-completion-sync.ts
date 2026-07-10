/**
 * Profile completion sync — global for dashboard pages loaded before page entries.
 */
import { syncProfileCompletionFromApi } from '../shared/profile-completion';

window.syncProfileCompletionFromApi = syncProfileCompletionFromApi;
