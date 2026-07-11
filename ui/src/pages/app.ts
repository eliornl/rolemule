/**
 * Landing page app shell — JobApplicationAssistant + event bus wiring.
 */
import { initJobApplicationAssistant } from '../app/job-application-assistant';

document.addEventListener('DOMContentLoaded', () => {
  initJobApplicationAssistant();
});
