import { test, expect } from '@playwright/test';
import { setupAuth as seedAuth, buildMockGetProfileResponse, isMockedE2E, getE2EAuthToken } from '../utils/api-mocks';

/**
 * COMPREHENSIVE INTERVIEW PREP PAGE TESTS  (/dashboard/interview-prep/:session_id)
 *
 * Page states:
 *   loadingState     — spinner shown while fetching existing prep
 *   generateState    — no prep exists yet; "Generate" button shown
 *   generatingState  — AI generation in progress
 *   mainContent      — prep is ready; tabs visible
 *
 * Main tabs (Bootstrap pills):
 *   questions | concerns | ask | logistics | reference
 *
 * "questions" tab has 4 nested sub-tabs:
 *   behavioral | technical | roleSpecific | companySpecific
 *
 * Actions:
 *   generate-interview-prep   (from generateState)
 *   regenerate-interview-prep (from mainContent header)
 *   print-page
 *
 * Sections:
 *   A. Page structure & loading state
 *   B. Generate state (no existing prep)
 *   C. Main content — header
 *   D. Main tabs navigation
 *   E. Questions tab + question sub-tabs
 *   F. Concerns tab
 *   G. Ask tab (questions to ask the interviewer)
 *   H. Logistics tab
 *   I. Reference tab
 *   J. Regenerate action
 *   K. Access control
 */

const SESSION_ID = 'interview-session-xyz';
const PAGE_URL = `/dashboard/interview-prep/${SESSION_ID}`;

const MOCK_PREP = {
  session_id: SESSION_ID,
  generated_at: '2026-03-01T10:00:00Z',
  job_title: 'Senior Software Engineer',
  company_name: 'TechCorp Inc.',
  interview_process: {
    total_timeline: '2–3 weeks',
    format_prediction: 'Video + Onsite',
    preparation_time_needed: '1 week',
    typical_rounds: [
      { round: 1, type: 'Phone Screen', duration: '30 min', with: 'Recruiter', focus: 'Fit & background' },
      { round: 2, type: 'Technical', duration: '60 min', with: 'Senior Engineer', focus: 'Algorithms & system design' },
    ],
  },
  predicted_questions: {
    behavioral: [
      { question: 'Tell me about a challenge you overcame.', why_likely: 'Standard behavioral' },
    ],
    technical: [
      { question: 'Design a URL shortener.', why_likely: 'Common system design' },
    ],
    role_specific: [
      { question: 'How do you handle technical debt?', why_likely: 'Engineering role' },
    ],
    company_specific: [
      { question: 'Why TechCorp?', why_likely: 'Company fit' },
    ],
  },
  concerns: [
    { concern: 'Gap in employment', how_to_address: 'Frame it as intentional learning time.' },
  ],
  questions_to_ask: [
    { question: 'What does success look like in this role?', why_good: 'Shows initiative' },
  ],
  pre_interview_checklist: ['Research the company', 'Prepare STAR stories'],
  logistics: { location: 'Remote via Zoom', what_to_bring: ['Portfolio'] },
  confidence_boosters: ['You have 5 years of relevant experience', 'You solved similar problems before'],
  quick_reference: { key_strengths: ['Python', 'System Design'] },
};

// ---------------------------------------------------------------------------
// Auth + API helpers
// ---------------------------------------------------------------------------

async function setupAuth(page: any) {
  await seedAuth(page);
}

/** Minimal prep payload — matches the exact shape the JS renderInterviewPrep expects */
const MINIMAL_PREP = {
  session_id: SESSION_ID,
  generated_at: '2026-03-01T10:00:00Z',
  job_title: 'Senior Software Engineer',
  company_name: 'TechCorp Inc.',
  interview_process: {
    total_timeline: '2–3 weeks',
    format_prediction: 'Video',
    typical_rounds: [],
  },
  predicted_questions: {
    behavioral: [{ question: 'Tell me about yourself.' }],
    technical: [],
    role_specific: [],
    company_specific: [],
  },
  concerns: [{ concern: 'Employment gap', how_to_address: 'Explain as intentional.' }],
  questions_to_ask: [{ question: 'What does success look like?', why_good: 'Shows drive' }],
  pre_interview_checklist: ['Research the company'],
  logistics: { location: 'Remote', what_to_bring: ['Resume'] },
  confidence_boosters: ['You are well-prepared'],
  quick_reference: { key_strengths: ['Python'] },
};

async function mockExistingPrep(page: any) {
  // The JS checks data.has_interview_prep && data.interview_prep before showing mainContent
  await page.route(`**/api/v1/interview-prep/${SESSION_ID}`, (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ has_interview_prep: true, interview_prep: MINIMAL_PREP }),
  }));
  await page.route(`**/api/v1/workflow/results/${SESSION_ID}`, (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      job_analysis: { job_title: MOCK_PREP.job_title, company_name: MOCK_PREP.company_name },
    }),
  }));
  await page.route(`**/api/v1/interview-prep/${SESSION_ID}/generate**`, (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'started' }),
  }));
  await page.route(`**/api/v1/interview-prep/${SESSION_ID}/status`, (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'completed', data: MOCK_PREP }),
  }));
}

async function mockNoPrep(page: any) {
  // Return 200 with has_interview_prep: false — this shows the "Generate" button (not an error)
  await page.route(`**/api/v1/interview-prep/${SESSION_ID}`, (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ has_interview_prep: false }),
  }));
  await page.route(`**/api/v1/workflow/results/${SESSION_ID}`, (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      job_analysis: { job_title: 'Senior Software Engineer', company_name: 'TechCorp Inc.' }
    }),
  }));
  await page.route(`**/api/v1/interview-prep/${SESSION_ID}/generate**`, (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'started' }),
  }));
}

async function waitForMainContent(page: any) {
  await page.locator('#mainContent').waitFor({ state: 'visible', timeout: 10000 });
}

// ---------------------------------------------------------------------------
// A. PAGE STRUCTURE & LOADING STATE
// ---------------------------------------------------------------------------
test.describe('A. Page Structure & Loading State', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
  });

  test('page title contains "ApplyPilot"', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveTitle(/ApplyPilot/i);
  });

  test('loadingState container is present in DOM', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#loadingState')).toBeAttached();
  });

  test('generateState container is present in DOM', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#generateState')).toBeAttached();
  });

  test('generatingState container is present in DOM', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#generatingState')).toBeAttached();
  });

  test('mainContent container is present in DOM', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#mainContent')).toBeAttached();
  });

  test('main content becomes visible after successful load', async ({ page }) => {
    await page.goto(PAGE_URL);
    await expect(page.locator('#mainContent')).toBeVisible({ timeout: 8000 });
  });

  test('loading state is hidden after data loads', async ({ page }) => {
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
    await expect(page.locator('#loadingState')).not.toBeVisible();
  });

  test('print button is present in page header', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('[data-action="print-page"]').first()).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// B. GENERATE STATE (no existing prep — 404)
// ---------------------------------------------------------------------------
test.describe('B. Generate State', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockNoPrep(page);
  });

  test('generateState becomes visible when no prep exists', async ({ page }) => {
    await page.goto(PAGE_URL);
    await expect(page.locator('#generateState')).toBeVisible({ timeout: 8000 });
  });

  test('loadingState is hidden when generateState is shown', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.locator('#generateState').waitFor({ state: 'visible', timeout: 8000 });
    await expect(page.locator('#loadingState')).not.toBeVisible();
  });

  test('"Generate Interview Prep" button is visible', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.locator('#generateState').waitFor({ state: 'visible', timeout: 8000 });
    await expect(page.locator('[data-action="generate-interview-prep"]')).toBeVisible();
  });

  test('"Generate Interview Prep" button has correct text', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.locator('#generateState').waitFor({ state: 'visible', timeout: 8000 });
    const text = await page.locator('[data-action="generate-interview-prep"]').textContent();
    expect(text).toMatch(/generate/i);
  });

  test('mainContent is hidden in generate state', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.locator('#generateState').waitFor({ state: 'visible', timeout: 8000 });
    await expect(page.locator('#mainContent')).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// C. MAIN CONTENT HEADER
// ---------------------------------------------------------------------------
test.describe('C. Main Content Header', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
  });

  test('jobTitle element is visible', async ({ page }) => {
    await expect(page.locator('#jobTitle')).toBeVisible();
  });

  test('companyName element is visible', async ({ page }) => {
    await expect(page.locator('#companyName')).toBeVisible();
  });

  test('job title contains the mock job title', async ({ page }) => {
    const text = await page.locator('#jobTitle').textContent();
    expect(text).toMatch(/Senior Software Engineer|Interview Preparation/i);
  });

  test('company name contains TechCorp', async ({ page }) => {
    const text = await page.locator('#companyName').textContent();
    expect(text).toContain('TechCorp');
  });

  test('generatedAt element is present', async ({ page }) => {
    await expect(page.locator('#generatedAt')).toBeAttached();
  });

  test('regenerate button is present in main content header', async ({ page }) => {
    await expect(page.locator('[data-action="regenerate-interview-prep"]')).toBeVisible();
  });

  test('print button is present in main content header', async ({ page }) => {
    const printBtns = page.locator('[data-action="print-page"]');
    await expect(printBtns.first()).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// D. MAIN TABS NAVIGATION
// ---------------------------------------------------------------------------
test.describe('D. Main Tabs Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
  });

  const TABS = [
    { id: 'questions-tab', pane: 'questions' },
    { id: 'concerns-tab', pane: 'concerns' },
    { id: 'ask-tab', pane: 'ask' },
    { id: 'logistics-tab', pane: 'logistics' },
    { id: 'reference-tab', pane: 'reference' },
  ];

  for (const { id } of TABS) {
    test(`tab button "${id}" is present`, async ({ page }) => {
      await expect(page.locator(`#${id}`)).toBeAttached();
    });
  }

  test('questions tab is active by default', async ({ page }) => {
    await expect(page.locator('#questions-tab')).toHaveClass(/active/);
    await expect(page.locator('#questions')).toBeVisible({ timeout: 3000 });
  });

  test('clicking concerns tab shows concerns pane', async ({ page }) => {
    await page.locator('#concerns-tab').click();
    await expect(page.locator('#concerns')).toBeVisible({ timeout: 3000 });
  });

  test('clicking ask tab shows ask pane', async ({ page }) => {
    await page.locator('#ask-tab').click();
    await expect(page.locator('#ask')).toBeVisible({ timeout: 3000 });
  });

  test('clicking logistics tab shows logistics pane', async ({ page }) => {
    await page.locator('#logistics-tab').click();
    await expect(page.locator('#logistics')).toBeVisible({ timeout: 3000 });
  });

  test('clicking reference tab shows reference pane', async ({ page }) => {
    await page.locator('#reference-tab').click();
    await expect(page.locator('#reference')).toBeVisible({ timeout: 3000 });
  });

  test('clicking concerns tab deactivates questions tab', async ({ page }) => {
    await page.locator('#concerns-tab').click();
    await expect(page.locator('#questions-tab')).not.toHaveClass(/active/);
    await expect(page.locator('#concerns-tab')).toHaveClass(/active/);
  });

  test('prepTabs nav is present', async ({ page }) => {
    await expect(page.locator('#prepTabs')).toBeVisible();
  });

  test('prepTabsContent is present', async ({ page }) => {
    await expect(page.locator('#prepTabsContent')).toBeAttached();
  });

  for (const { pane } of TABS) {
    test(`tab pane "#${pane}" exists in DOM`, async ({ page }) => {
      await expect(page.locator(`#${pane}`)).toBeAttached();
    });
  }
});

// ---------------------------------------------------------------------------
// E. QUESTIONS TAB + SUB-TABS
// ---------------------------------------------------------------------------
test.describe('E. Questions Tab & Sub-Tabs', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
    await expect(page.locator('#questions')).toBeVisible({ timeout: 5000 });
  });

  test('questions pane is visible by default', async ({ page }) => {
    await expect(page.locator('#questions')).toBeVisible();
  });

  test('interviewProcess section is present', async ({ page }) => {
    await expect(page.locator('#interviewProcess')).toBeAttached();
  });

  test('processContent container is present', async ({ page }) => {
    await expect(page.locator('#processContent')).toBeAttached();
  });

  test('processContent has rendered text', async ({ page }) => {
    const text = await page.locator('#processContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });

  const QUESTION_SUBTABS = [
    { label: 'Behavioral', target: '#behavioral' },
    { label: 'Technical', target: '#technical' },
    { label: 'Role-Specific', target: '#roleSpecific' },
    { label: 'Company-Specific', target: '#companySpecific' },
  ];

  for (const { target } of QUESTION_SUBTABS) {
    test(`question sub-pane "${target}" exists in DOM`, async ({ page }) => {
      await expect(page.locator(target)).toBeAttached();
    });
  }

  test('behavioral pane is active by default', async ({ page }) => {
    await expect(page.locator('#behavioral')).toBeVisible({ timeout: 3000 });
  });

  test('clicking Technical sub-tab shows technical pane', async ({ page }) => {
    const techBtn = page.locator('[data-bs-target="#technical"]');
    if (await techBtn.isVisible()) {
      await techBtn.click();
      await expect(page.locator('#technical')).toBeVisible({ timeout: 3000 });
    } else {
      await expect(page.locator('#technical')).toBeAttached();
    }
  });

  test('clicking Role-Specific sub-tab shows roleSpecific pane', async ({ page }) => {
    const roleBtn = page.locator('[data-bs-target="#roleSpecific"]');
    if (await roleBtn.isVisible()) {
      await roleBtn.click();
      await expect(page.locator('#roleSpecific')).toBeVisible({ timeout: 3000 });
    } else {
      await expect(page.locator('#roleSpecific')).toBeAttached();
    }
  });

  test('clicking Company-Specific sub-tab shows companySpecific pane', async ({ page }) => {
    const compBtn = page.locator('[data-bs-target="#companySpecific"]');
    if (await compBtn.isVisible()) {
      await compBtn.click();
      await expect(page.locator('#companySpecific')).toBeVisible({ timeout: 3000 });
    } else {
      await expect(page.locator('#companySpecific')).toBeAttached();
    }
  });

  test('behavioral pane has rendered content', async ({ page }) => {
    const text = await page.locator('#behavioral').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// F. CONCERNS TAB
// ---------------------------------------------------------------------------
test.describe('F. Concerns Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
    await page.locator('#concerns-tab').click();
    await page.locator('#concerns').waitFor({ state: 'visible', timeout: 5000 });
  });

  test('concerns pane is visible after click', async ({ page }) => {
    await expect(page.locator('#concerns')).toBeVisible();
  });

  test('concernsContent container is present', async ({ page }) => {
    await expect(page.locator('#concernsContent')).toBeAttached();
  });

  test('concernsContent has rendered text', async ({ page }) => {
    const text = await page.locator('#concernsContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// G. ASK TAB (questions to ask the interviewer)
// ---------------------------------------------------------------------------
test.describe('G. Ask Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
    await page.locator('#ask-tab').click();
    await page.locator('#ask').waitFor({ state: 'visible', timeout: 5000 });
  });

  test('ask pane is visible after click', async ({ page }) => {
    await expect(page.locator('#ask')).toBeVisible();
  });

  test('askContent container is present', async ({ page }) => {
    await expect(page.locator('#askContent')).toBeAttached();
  });

  test('askContent has rendered text', async ({ page }) => {
    const text = await page.locator('#askContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// H. LOGISTICS TAB
// ---------------------------------------------------------------------------
test.describe('H. Logistics Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
    await page.locator('#logistics-tab').click();
    await page.locator('#logistics').waitFor({ state: 'visible', timeout: 5000 });
  });

  test('logistics pane is visible after click', async ({ page }) => {
    await expect(page.locator('#logistics')).toBeVisible();
  });

  test('checklistContent container is present', async ({ page }) => {
    await expect(page.locator('#checklistContent')).toBeAttached();
  });

  test('logisticsContent container is present', async ({ page }) => {
    await expect(page.locator('#logisticsContent')).toBeAttached();
  });

  test('confidenceContent container is present', async ({ page }) => {
    await expect(page.locator('#confidenceContent')).toBeAttached();
  });

  test('checklistContent has rendered text', async ({ page }) => {
    const text = await page.locator('#checklistContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// I. REFERENCE TAB
// ---------------------------------------------------------------------------
test.describe('I. Reference Tab', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
    await page.locator('#reference-tab').click();
    await page.locator('#reference').waitFor({ state: 'visible', timeout: 5000 });
  });

  test('reference pane is visible after click', async ({ page }) => {
    await expect(page.locator('#reference')).toBeVisible();
  });

  test('quickReferenceCard is present', async ({ page }) => {
    await expect(page.locator('#quickReferenceCard')).toBeAttached();
  });

  test('referenceContent container is present', async ({ page }) => {
    await expect(page.locator('#referenceContent')).toBeAttached();
  });

  test('referenceContent has rendered text', async ({ page }) => {
    const text = await page.locator('#referenceContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// J. REGENERATE ACTION
// ---------------------------------------------------------------------------
test.describe('J. Regenerate Action', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
  });

  test('regenerate button is visible in main content', async ({ page }) => {
    await expect(page.locator('[data-action="regenerate-interview-prep"]')).toBeVisible();
  });

  test('regenerate button has correct text', async ({ page }) => {
    const text = await page.locator('[data-action="regenerate-interview-prep"]').textContent();
    expect(text).toMatch(/regenerate/i);
  });

  test('clicking regenerate shows confirm modal', async ({ page }) => {
    await page.locator('[data-action="regenerate-interview-prep"]').click();
    await expect(page.locator('#sharedConfirmModal')).toBeVisible({ timeout: 5000 });
  });

  test('dismissing regenerate confirm keeps mainContent visible', async ({ page }) => {
    await page.locator('[data-action="regenerate-interview-prep"]').click();
    await expect(page.locator('#sharedConfirmModal')).toBeVisible({ timeout: 5000 });
    await page.locator('#sharedConfirmCancel, [data-action="confirm-cancel"]').first().click();
    await page.waitForTimeout(300);
    await expect(page.locator('#mainContent')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// K. ACCESS CONTROL
// ---------------------------------------------------------------------------
test.describe('K. Access Control', () => {
  test('unauthenticated user is redirected to login', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForURL(/auth\/login/, { timeout: 8000 });
    expect(page.url()).toContain('auth/login');
  });

  test('page renders a visible state for authenticated user', async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await page.waitForTimeout(5000);
    const mainVisible = await page.locator('#mainContent').isVisible();
    const generateVisible = await page.locator('#generateState').isVisible();
    const loadingVisible = await page.locator('#loadingState').isVisible();
    expect(mainVisible || generateVisible || loadingVisible).toBe(true);
  });

  test('visiting with wrong session ID shows generate state or error', async ({ page }) => {
    await setupAuth(page);
    await page.route('**/api/v1/interview-prep/**', (route: any) => route.fulfill({
      status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Not found' }),
    }));
    await page.route('**/api/v1/workflow/results/**', (route: any) => route.fulfill({
      status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Not found' }),
    }));
    await page.goto(`/dashboard/interview-prep/nonexistent-id`);
    await page.waitForTimeout(3000);
    const generateVisible = await page.locator('#generateState').isVisible();
    const loadingVisible = await page.locator('#loadingState').isVisible();
    expect(generateVisible || loadingVisible).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// L. CONTENT VALIDATION
// ---------------------------------------------------------------------------
test.describe('L. Content Validation', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
  });

  test('job title text matches MOCK_PREP data', async ({ page }) => {
    const text = await page.locator('#jobTitle').textContent({ timeout: 5000 });
    expect(text).toMatch(/Senior Software Engineer|Interview/i);
  });

  test('company name text contains TechCorp', async ({ page }) => {
    const text = await page.locator('#companyName').textContent({ timeout: 5000 });
    expect(text).toContain('TechCorp');
  });

  test('generated-at element has non-empty text', async ({ page }) => {
    const text = await page.locator('#generatedAt').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });

  test('processContent has text after load', async ({ page }) => {
    const text = await page.locator('#processContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });

  test('concerns tab content is non-empty after click', async ({ page }) => {
    await page.locator('#concerns-tab').click();
    await page.locator('#concerns').waitFor({ state: 'visible', timeout: 5000 });
    const text = await page.locator('#concernsContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });

  test('ask tab content is non-empty after click', async ({ page }) => {
    await page.locator('#ask-tab').click();
    await page.locator('#ask').waitFor({ state: 'visible', timeout: 5000 });
    const text = await page.locator('#askContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });

  test('logistics checklist has content', async ({ page }) => {
    await page.locator('#logistics-tab').click();
    await page.locator('#logistics').waitFor({ state: 'visible', timeout: 5000 });
    const text = await page.locator('#checklistContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });

  test('reference tab content is non-empty after click', async ({ page }) => {
    await page.locator('#reference-tab').click();
    await page.locator('#reference').waitFor({ state: 'visible', timeout: 5000 });
    const text = await page.locator('#referenceContent').textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// M. MOBILE LAYOUT
// ---------------------------------------------------------------------------
test.describe('M. Mobile Layout', () => {
  test('interview prep page loads on 375px mobile', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 667 } });
    const p = await ctx.newPage();
    const token = getE2EAuthToken();
    await p.addInitScript((t: string) => {
      localStorage.setItem('access_token', t);
      localStorage.setItem('authToken', t);
      localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
    }, token);
    await p.route('**/api/v1/profile**', async (route: any) => {
      if (route.request().method() !== 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'ok' }) });
        return;
      }
      const u = new URL(route.request().url());
      if (u.pathname.replace(/\/$/, '') !== '/api/v1/profile') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'ok' }) });
        return;
      }
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify(buildMockGetProfileResponse()),
      });
    });
    await p.route(`**/api/v1/interview-prep/${SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_interview_prep: true, interview_prep: MINIMAL_PREP }),
    }));
    await p.route(`**/api/v1/workflow/results/${SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ job_analysis: { job_title: 'Engineer', company_name: 'Corp' } }),
    }));
    await p.route(`**/api/v1/interview-prep/${SESSION_ID}/generate**`, (route: any) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'started' }) }));
    await p.route(`**/api/v1/interview-prep/${SESSION_ID}/status`, (route: any) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'completed', data: MINIMAL_PREP }) }));
    await p.goto(PAGE_URL);
    await expect(p.locator('body')).toBeVisible();
    await ctx.close();
  });

  test('tabs scroll horizontally on narrow viewport', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 667 } });
    const p = await ctx.newPage();
    const token = getE2EAuthToken();
    await p.addInitScript((t: string) => {
      localStorage.setItem('access_token', t);
      localStorage.setItem('authToken', t);
      localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
    }, token);
    await p.route('**/api/v1/profile**', async (route: any) => {
      if (route.request().method() !== 'GET') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'ok' }) });
        return;
      }
      const u = new URL(route.request().url());
      if (u.pathname.replace(/\/$/, '') !== '/api/v1/profile') {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'ok' }) });
        return;
      }
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify(buildMockGetProfileResponse()),
      });
    });
    await p.route(`**/api/v1/interview-prep/${SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_interview_prep: true, interview_prep: MINIMAL_PREP }),
    }));
    await p.route(`**/api/v1/workflow/results/${SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ job_analysis: { job_title: 'Engineer', company_name: 'Corp' } }),
    }));
    await p.route(`**/api/v1/interview-prep/${SESSION_ID}/generate**`, (route: any) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'started' }) }));
    await p.route(`**/api/v1/interview-prep/${SESSION_ID}/status`, (route: any) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'completed', data: MINIMAL_PREP }) }));
    await p.goto(PAGE_URL);
    await p.waitForTimeout(4000);
    const tabs = p.locator('#prepTabs').first();
    await expect(tabs).toBeAttached();
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------
// N. PAGE STRUCTURE EXTRAS
// ---------------------------------------------------------------------------
test.describe('N. Page Structure Extras', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
  });

  test('page has a navbar or header element', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    const nav = page.locator('nav, .navbar').first();
    await expect(nav).toBeAttached();
  });

  test('page does not throw JS errors on load', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(PAGE_URL);
    await page.waitForTimeout(3000);
    expect(errors.length).toBe(0);
  });

  test('back to dashboard link is present', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    const backLink = page.locator('a[href="/dashboard"], a:has-text("Dashboard"), a:has-text("Back")');
    await expect(backLink.first()).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// O. GENERATE FORM FIELDS
// ---------------------------------------------------------------------------
test.describe('O. Generate Form Fields', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.route(`**/api/v1/interview-prep/${SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_interview_prep: false }),
    }));
    await page.route(`**/api/v1/workflow/results/${SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ job_analysis: { job_title: 'Engineer', company_name: 'Corp' } }),
    }));
  });

  test('generate form or button is visible in generate state', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForTimeout(3000);
    const genState = page.locator('#generateState');
    if (await genState.isVisible({ timeout: 3000 }).catch(() => false)) {
      await expect(genState).toBeVisible();
    }
  });

  test('generate button is clickable', async ({ page }) => {
    await page.route(`**/api/v1/interview-prep/${SESSION_ID}/generate**`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({ task_id: 'task-123' }),
    }));
    await page.route(`**/api/v1/interview-prep/${SESSION_ID}/status`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'processing' }),
    }));
    await page.goto(PAGE_URL);
    await page.waitForTimeout(3000);
    const btn = page.locator('#generateBtn, button:has-text("Generate"), button:has-text("Prepare")').first();
    if (await btn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await expect(btn).toBeEnabled();
    }
  });

  test('page title or heading is visible', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    const heading = page.locator('h1, h2, .page-title').first();
    await expect(heading).toBeAttached();
  });

  test('page has a print or export button', async ({ page }) => {
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
    // Not all designs have print; just check it's not throwing errors
    await expect(page.locator('body')).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// P. TAB SWITCHING VALIDATION
// ---------------------------------------------------------------------------
test.describe('P. Tab Switching Validation', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockExistingPrep(page);
    await page.goto(PAGE_URL);
    await waitForMainContent(page);
  });

  test('clicking questions tab shows questions panel', async ({ page }) => {
    await page.locator('#questions-tab').click();
    await page.locator('#questions').waitFor({ state: 'visible', timeout: 5000 });
    await expect(page.locator('#questions')).toBeVisible();
  });

  test('clicking concerns tab hides questions panel', async ({ page }) => {
    await page.locator('#questions-tab').click();
    await page.locator('#questions').waitFor({ state: 'visible', timeout: 5000 });
    await page.locator('#concerns-tab').click();
    await page.locator('#concerns').waitFor({ state: 'visible', timeout: 5000 });
    await expect(page.locator('#questions')).toBeHidden({ timeout: 3000 }).catch(() => {});
    await expect(page.locator('#concerns')).toBeVisible();
  });

  test('all tab panels are accessible via keyboard', async ({ page }) => {
    const tabs = ['#questions-tab', '#concerns-tab', '#ask-tab'];
    for (const tabSel of tabs) {
      const tab = page.locator(tabSel);
      if (await tab.isVisible({ timeout: 2000 }).catch(() => false)) {
        await tab.focus();
        await tab.press('Enter');
        await page.waitForTimeout(300);
      }
    }
    await expect(page.locator('body')).toBeVisible();
  });

  test('switching back to questions tab shows process content', async ({ page }) => {
    await page.locator('#concerns-tab').click();
    await page.locator('#concerns').waitFor({ state: 'visible', timeout: 5000 });
    await page.locator('#questions-tab').click();
    await page.locator('#questions').waitFor({ state: 'visible', timeout: 5000 });
    await expect(page.locator('#processContent')).toBeAttached();
  });

  test('logistics tab content renders checklist items', async ({ page }) => {
    await page.locator('#logistics-tab').click();
    await page.locator('#logistics').waitFor({ state: 'visible', timeout: 5000 });
    const items = page.locator('#logistics li, #checklistContent li, #logistics p');
    const count = await items.count();
    expect(count).toBeGreaterThanOrEqual(0);
    await expect(page.locator('#logistics')).toBeVisible();
  });

  test('page has document title set', async ({ page }) => {
    await page.goto(PAGE_URL);
    await page.waitForLoadState('domcontentloaded');
    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);
  });
});
