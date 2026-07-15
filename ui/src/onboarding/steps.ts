import type { OnboardingStep } from './types';

export const ALL_STEPS: OnboardingStep[] = [
  {
    id: 'welcome',
    title: 'Welcome to ApplyPilot! 🎉',
    content: `
                <p>Your AI-powered career co-pilot is ready to help you land your dream job.</p>
                <p>Let's take a quick tour so you know exactly what's available.</p>
            `,
    image: '🚀',
    position: 'center',
    condition: null,
  },
  {
    id: 'extension',
    title: 'Install Chrome Extension',
    content: `
                <p>Get the most out of ApplyPilot with our <strong>Chrome Extension</strong>!</p>
                <p>With the extension, you can:</p>
                <ul>
                    <li>🌐 Analyze jobs from <strong>any job site or company careers page</strong></li>
                    <li>⚡ One-click job extraction</li>
                    <li>📋 Auto-detect job postings</li>
                </ul>
                <p>Load the extension in 3 steps:</p>
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
                <p>There are 3 ways to analyze a job:</p>
                <ol>
                    <li><strong>Chrome Extension:</strong> Browse to any job posting and click the extension to auto-extract</li>
                    <li><strong>Paste Job Description:</strong> Copy the full job description and paste it directly</li>
                    <li><strong>File Upload:</strong> Upload a saved job description file</li>
                </ol>
                <p>Our AI will analyze the job, research the company, match your profile, and create personalized materials!</p>
            `,
    image: '📋',
    highlight: '[href*="new-application"]',
    position: 'center',
    condition: null,
  },
  {
    id: 'tools',
    title: 'Career Tools',
    content: `
                <p>Beyond job analysis, we have <strong>6 career tools</strong> to help throughout your search:</p>
                <ul>
                    <li>📝 Thank You Notes</li>
                    <li>📊 Rejection Analysis</li>
                    <li>👥 Reference Requests</li>
                    <li>⚖️ Job Comparison</li>
                    <li>📧 Follow-up Emails</li>
                    <li>💰 Salary Negotiation</li>
                </ul>
            `,
    image: '🛠️',
    highlight: '[href*="tools"]',
    position: 'center',
    condition: null,
  },
];
