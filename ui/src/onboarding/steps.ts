import type { OnboardingStep } from './types';

export const ALL_STEPS: OnboardingStep[] = [
  {
    id: 'welcome',
    title: 'Welcome to RoleMule! 🎉',
    content: `
                <p><strong>One mule for every role.</strong></p>
                <p>Paste a job, run five AI agents in ~30 seconds, then optimize your CV, practice interviews, draft outreach, and use career tools — with your data 100% local.</p>
                <p>This quick tour covers the essentials.</p>
            `,
    image: '🚀',
    position: 'center',
    condition: null,
  },
  {
    id: 'extension',
    title: 'Install Chrome Extension',
    content: `
                <p>The <strong>Chrome Extension</strong> works on any job site or company careers page:</p>
                <ul>
                    <li><strong>Analyze This Job</strong> — send the posting to your dashboard for the full AI workflow</li>
                    <li><strong>Match Form To Profile</strong> — map visible application fields to your profile (review before you submit)</li>
                </ul>
                <p>Load it in 3 steps:</p>
                <ol>
                    <li>Open <strong>chrome://extensions</strong> in Chrome</li>
                    <li>Enable <strong>Developer Mode</strong> (top-right toggle)</li>
                    <li>Click <strong>Load unpacked</strong> and select the <code>extension/</code> folder from the project directory</li>
                </ol>
            `,
    image: '🧩',
    position: 'center',
    condition: null,
  },
  {
    id: 'api-key',
    title: 'Set Up Your AI Provider',
    content: `
                <p>AI features need a provider in <strong>Settings → AI Setup</strong>.</p>
                <ol>
                    <li>Choose <strong>Gemini</strong>, <strong>OpenAI</strong>, <strong>Anthropic</strong>, or local <strong>Ollama</strong></li>
                    <li>For cloud providers, create an API key and paste it (Ollama needs no key)</li>
                    <li>Confirm or change the preferred model (recommended is selected by default)</li>
                </ol>
            `,
    image: '🔑',
    highlight: '[href*="settings"]',
    position: 'center',
    condition: 'needsApiKey',
  },
  {
    id: 'analyze',
    title: 'Analyze Job Postings',
    content: `
                <p>Start a new application in any of these ways:</p>
                <ol>
                    <li><strong>Paste</strong> the full job description</li>
                    <li><strong>Upload</strong> a PDF, TXT, or Word (<code>.docx</code>) file</li>
                    <li><strong>Chrome Extension</strong> — Analyze This Job from a posting page</li>
                </ol>
                <p>Five agents run in ~30 seconds (analyze → match → company research → cover letter + resume tips). Open the application to review fit, strategy, interview prep, and more.</p>
            `,
    image: '📋',
    highlight: '[href*="new-application"]',
    position: 'center',
    condition: null,
  },
  {
    id: 'tools',
    title: 'Career Tools & Beyond',
    content: `
                <p>After analysis, keep going from the application page and dashboard:</p>
                <ul>
                    <li><strong>Optimize CV</strong> — iterative rewrite loop for the role</li>
                    <li><strong>Mock Session</strong> &amp; interview prep — practice before the real thing</li>
                    <li><strong>Outreach</strong> — copy-ready drafts (you send messages yourself)</li>
                    <li><strong>Career Tools</strong> — thank you notes, follow-ups, salary coach, job comparison, and more</li>
                    <li><strong>CLI</strong> — run the same workflows from the terminal with <code>rolemule</code> (Claude / Cursor friendly)</li>
                </ul>
            `,
    image: '🛠️',
    highlight: '[href*="tools"]',
    position: 'center',
    condition: null,
  },
];
