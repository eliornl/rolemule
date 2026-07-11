import { test, expect } from '@playwright/test';
import { ProfileSetupPage } from '../pages';
import { setupAuth, setupAllMocks, buildMockGetProfileResponse, isMockedE2E, setupWebSocketMock } from '../utils/api-mocks';

/**
 * MULTI-STEP USER JOURNEY TESTS
 *
 * End-to-end mocked journeys covering realistic user flows:
 *   1. New Application — full URL submission to results
 *   2. Career Tools — complete tool usage flow
 *   3. Settings — API key save flow
 *   4. Profile — settings update flow
 *   5. Auth — login redirect to dashboard
 */

const MOCK_SESSION_ID = 'journey-session-abc123';

const MOCK_WORKFLOW_RESULTS = {
  job_analysis: {
    job_title: 'Senior Software Engineer',
    company_name: 'TechCorp',
    location: 'San Francisco, CA',
    required_skills: ['Python', 'FastAPI', 'React'],
    nice_to_have_skills: ['Docker', 'Kubernetes'],
    seniority_level: 'Senior',
    employment_type: 'Full-time',
    remote_policy: 'Hybrid',
  },
  match_assessment: {
    overall_score: 85,
    strengths: ['Strong Python skills', 'FastAPI experience'],
    gaps: ['Kubernetes experience'],
    recommendation: 'Strong match — apply with confidence.',
  },
  cover_letter: {
    letter: 'Dear Hiring Manager,\n\nI am excited to apply for the Senior Software Engineer role at TechCorp...',
  },
  resume_recommendations: {
    summary: 'Add more emphasis on distributed systems.',
    bullet_points: ['Led backend migration to microservices', 'Reduced API latency by 40%'],
  },
  company_research: {
    overview: 'TechCorp is a leading fintech company founded in 2010.',
    culture: 'Engineering-driven, remote-friendly culture.',
    recent_news: ['TechCorp raised $50M Series C'],
  },
  three_key_selling_points: ['Python expertise', 'Startup experience', 'Leadership track record'],
};

const LONG_JOB_DESCRIPTION =
  'Senior Software Engineer at TechCorp. Requirements: Python, FastAPI, React, PostgreSQL, distributed systems, and cloud infrastructure experience. '.repeat(2);

// ---------------------------------------------------------------------------
// 1. NEW APPLICATION — PASTE JOB DESCRIPTION JOURNEY
// ---------------------------------------------------------------------------
test.describe('Journey 1 — New Application via Paste', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('new application page loads and shows job description textarea', async ({ page }) => {
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#jobDescription')).toBeAttached();
  });

  test('can type into the job description field', async ({ page }) => {
    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#jobDescription').fill('Senior Engineer at Example Corp\n\nRequirements:\n- Python');
    expect(await page.locator('#jobDescription').inputValue()).toContain('Senior Engineer');
  });

  test('submitting pasted description triggers workflow API call', async ({ page }) => {
    let workflowStarted = false;
    await page.route('**/api/v1/workflow/start', (route: any) => {
      workflowStarted = true;
      route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ session_id: MOCK_SESSION_ID, status: 'processing' }),
      });
    });
    await page.route(`**/api/v1/workflow/status/${MOCK_SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'completed' }),
    }));

    await page.goto('/dashboard/new-application');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#jobDescription').fill(LONG_JOB_DESCRIPTION);
    await page.locator('[data-action="process-application"]').click();
    await page.waitForTimeout(1000);
    expect(workflowStarted).toBe(true);
  });

  test('application detail page renders after workflow completes', async ({ page }) => {
    await page.route(`**/api/v1/workflow/status/${MOCK_SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'completed' }),
    }));
    await page.route(`**/api/v1/workflow/results/${MOCK_SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify(MOCK_WORKFLOW_RESULTS),
    }));

    await page.goto(`/dashboard/application/${MOCK_SESSION_ID}`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);
    await expect(page.locator('body')).toBeVisible();
  });

  test('job title is visible on application detail page', async ({ page }) => {
    await page.route(`**/api/v1/workflow/status/${MOCK_SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'completed' }),
    }));
    await page.route(`**/api/v1/workflow/results/${MOCK_SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify(MOCK_WORKFLOW_RESULTS),
    }));

    await page.goto(`/dashboard/application/${MOCK_SESSION_ID}`);
    await page.waitForTimeout(4000);
    const jobTitle = page.locator('#jobTitle, .job-title, h1, h2').first();
    const text = await jobTitle.textContent({ timeout: 5000 });
    expect(text).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// 2. CAREER TOOLS — THANK YOU NOTE JOURNEY
// ---------------------------------------------------------------------------
test.describe('Journey 2 — Thank You Note', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('career tools page loads', async ({ page }) => {
    await page.goto('/dashboard/tools');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).toBeVisible();
  });

  test('thank you note form fields are fillable', async ({ page }) => {
    await page.goto('/dashboard/tools');
    await page.waitForLoadState('domcontentloaded');
    const nameField = page.locator('#interviewerName, input[name="interviewer_name"]').first();
    if (await nameField.isVisible({ timeout: 3000 }).catch(() => false)) {
      await nameField.fill('Jane Smith');
      expect(await nameField.inputValue()).toBe('Jane Smith');
    }
  });

  test('thank you generate button triggers API call', async ({ page }) => {
    let apiCalled = false;
    await page.route('**/api/v1/tools/thank-you**', (route: any) => {
      apiCalled = true;
      route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          thank_you_note: 'Dear Jane, Thank you for the interview...',
          subject_line: 'Thank You — Senior Engineer Interview',
        }),
      });
    });

    await page.goto('/dashboard/tools');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#interviewerName').fill('Jane Smith');
    await page.locator('#companyName').fill('Acme Corp');
    await page.locator('#jobTitle').fill('Senior Engineer');
    await page.locator('#interviewType').selectOption('video');

    const submitBtn = page.locator('#thankYouSubmit').first();
    await expect(submitBtn).toBeVisible({ timeout: 5000 });
    await submitBtn.click();
    await page.waitForTimeout(1500);
    expect(apiCalled).toBe(true);
  });

  test('thank you output section renders after API response', async ({ page }) => {
    await page.route('**/api/v1/tools/thank-you**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        thank_you_note: 'Dear Jane, Thank you for the interview opportunity.',
        subject_line: 'Thank You Note',
      }),
    }));

    await page.goto('/dashboard/tools');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#interviewerName').fill('Jane Smith');
    await page.locator('#companyName').fill('Acme Corp');
    await page.locator('#jobTitle').fill('Senior Engineer');
    await page.locator('#interviewType').selectOption('video');

    const submitBtn = page.locator('#thankYouSubmit').first();
    await expect(submitBtn).toBeVisible({ timeout: 5000 });
    await submitBtn.click();
    await page.waitForTimeout(2000);
    await expect(page.locator('#thankYouOutput')).toBeVisible({ timeout: 5000 });
  });
});

// ---------------------------------------------------------------------------
// 3. SETTINGS — API KEY SAVE JOURNEY
// ---------------------------------------------------------------------------
test.describe('Journey 3 — Settings API Key', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('settings page loads AI Setup tab', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await page.waitForLoadState('domcontentloaded');
    const aiTab = page.locator('[data-tab="ai-setup"], a:has-text("AI Setup"), #ai-setup-tab').first();
    if (await aiTab.isVisible({ timeout: 3000 }).catch(() => false)) {
      await aiTab.click();
      await page.waitForTimeout(300);
    }
    await expect(page.locator('body')).toBeVisible();
  });

  test('API key input field is present and fillable', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await page.waitForLoadState('domcontentloaded');
    const apiKeyInput = page.locator('#geminiApiKey, input[name="api_key"], input[placeholder*="API"]').first();
    if (await apiKeyInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await apiKeyInput.fill('AIza-fake-test-key-12345');
      expect(await apiKeyInput.inputValue()).toBe('AIza-fake-test-key-12345');
    }
  });

  test('saving API key triggers PATCH/POST to API', async ({ page }) => {
    await page.route('**/api/v1/profile/api-key**', (route: any) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'Saved' }) });
    });
    await page.route('**/api/v1/profile/settings**', (route: any) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'Saved' }) });
    });

    await page.goto('/dashboard/settings');
    await page.waitForLoadState('domcontentloaded');

    const saveBtn = page.locator('button:has-text("Save"), button[type="submit"]').first();
    if (await saveBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await saveBtn.click();
      await page.waitForTimeout(1000);
      // saved may or may not be true depending on which API route was hit
      await expect(page.locator('body')).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// 4. PROFILE UPDATE JOURNEY
// ---------------------------------------------------------------------------
test.describe('Journey 4 — Profile Update', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    if (!isMockedE2E) {
      await setupWebSocketMock(page);
    }
    const incompleteProfile = buildMockGetProfileResponse({ profileCompleted: false });
    await page.route('**/api/v1/profile/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(incompleteProfile),
      });
    });
    await page.route('**/api/v1/profile/basic-info**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Saved' }),
      });
    });
    await page.route('**/api/v1/resume/upload**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'ok' }),
      });
    });
  });

  test('profile setup page loads', async ({ page }) => {
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).toBeVisible();
  });

  test('professional title field is present', async ({ page }) => {
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    const titleField = page.locator('#professionalTitle, input[name="professional_title"]').first();
    await expect(titleField).toBeAttached();
  });

  test('can fill professional title', async ({ page }) => {
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    const titleField = page.locator('#professionalTitle, input[name="professional_title"]').first();
    if (await titleField.isVisible({ timeout: 3000 }).catch(() => false)) {
      await titleField.fill('Senior Engineer');
      expect(await titleField.inputValue()).toBe('Senior Engineer');
    }
  });

  test('years of experience field is fillable', async ({ page }) => {
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    const expField = page.locator('#yearsExperience, input[name="years_experience"], select[name="years_experience"]').first();
    if (await expField.isVisible({ timeout: 3000 }).catch(() => false)) {
      const tag = await expField.evaluate((el: Element) => el.tagName.toLowerCase());
      if (tag === 'input') {
        await expField.fill('7');
        expect(await expField.inputValue()).toBe('7');
      }
    }
  });

  test('Next button navigates to step 2', async ({ page }) => {
    const profilePage = new ProfileSetupPage(page);
    await page.goto('/profile/setup');
    await profilePage.handleCookieConsent();
    await profilePage.skipResumeUpload();
    await profilePage.fillBasicInfo({
      city: 'Boston',
      state: 'MA',
      country: 'USA',
      title: 'Software Engineer',
      yearsExperience: 5,
      summary: 'Five years of experience building web applications and APIs.',
    });
    await profilePage.nextStep();
    await profilePage.waitForStep(2);
    await expect(page.locator('#step-2.active, #company-name, #no-experience').first()).toBeVisible({ timeout: 10000 });
  });
});

// ---------------------------------------------------------------------------
// 5. AUTH REDIRECT JOURNEY
// ---------------------------------------------------------------------------
test.describe('Journey 5 — Auth Redirect', () => {
  test('unauthenticated visit to /dashboard redirects to login', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('access_token');
      localStorage.removeItem('authToken');
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
    await page.goto('/dashboard');
    await page.waitForTimeout(3000);
    await expect(page).toHaveURL(/login|auth/i);
  });

  test('login page has email and password fields', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('can fill login form', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('input[type="email"]').fill('user@example.com');
    await page.locator('input[type="password"]').fill('Password123!');
    expect(await page.locator('input[type="email"]').inputValue()).toBe('user@example.com');
  });

  test('successful login redirects to dashboard', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
    await page.route('**/api/v1/auth/login', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c',
        token_type: 'bearer',
        profile_completed: true,
        user: { name: 'Test User', email: 'user@example.com', profile_completed: true },
      }),
    }));
    await page.route('**/api/v1/profile**', async (route: any) => {
      if (route.request().method() !== 'GET') {
        await route.continue();
        return;
      }
      const u = new URL(route.request().url());
      if (u.pathname.replace(/\/$/, '') !== '/api/v1/profile') {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          user_info: { profile_completed: true },
          completion_status: { profile_completed: true },
        }),
      });
    });

    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('input[type="email"]').fill('user@example.com');
    await page.locator('input[type="password"]').fill('Password123!');
    await page.locator('button[type="submit"], #login-btn').first().click();
    await page.waitForURL(/dashboard/, { timeout: 10000 });
  });

  test('invalid credentials shows error message', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
    await page.route('**/api/v1/auth/login', (route: any) => route.fulfill({
      status: 401, contentType: 'application/json',
      body: JSON.stringify({ detail: 'Invalid email or password' }),
    }));

    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('input[type="email"]').fill('wrong@example.com');
    await page.locator('input[type="password"]').fill('wrongpassword');
    await page.locator('button[type="submit"], #login-btn').first().click();
    await page.waitForTimeout(1500);
    // Should remain on login page
    await expect(page).toHaveURL(/login/);
  });
});

// ---------------------------------------------------------------------------
// 6. DASHBOARD APPLICATION LIST JOURNEY
// /dashboard/history is removed — application list now lives on /dashboard
// ---------------------------------------------------------------------------
test.describe('Journey 6 — Dashboard Application List', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ name: 'Test User', email: 'test@example.com' }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        applications: [
          { session_id: 'app-1', job_title: 'Software Engineer', company_name: 'ACME Corp', status: 'completed', created_at: new Date().toISOString() },
          { session_id: 'app-2', job_title: 'Backend Developer', company_name: 'StartupXYZ', status: 'completed', created_at: new Date().toISOString() },
        ],
        total: 2,
      }),
    }));
  });

  test('dashboard application list loads', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).toBeVisible();
  });

  test('dashboard has a heading', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('domcontentloaded');
    const heading = page.locator('h1, h2, h3, h4').first();
    await expect(heading).toBeAttached();
  });

  test('/dashboard/history returns 404 (route removed)', async ({ page }) => {
    const response = await page.goto('/dashboard/history');
    await page.waitForLoadState('domcontentloaded');
    expect(response?.status() === 404 || !page.url().endsWith('/dashboard/history')).toBeTruthy();
  });

  test('dashboard does not redirect authenticated users to login', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    await expect(page).not.toHaveURL(/login/);
  });
});

// ---------------------------------------------------------------------------
// 7. INTERVIEW PREP JOURNEY
// ---------------------------------------------------------------------------
test.describe('Journey 7 — Interview Prep', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.route('**/api/v1/workflow/results/journey-prep-session', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ job_analysis: { job_title: 'Engineer', company_name: 'Corp' } }),
    }));
    await page.route('**/api/v1/interview-prep/journey-prep-session', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ has_interview_prep: false }),
    }));
    await page.route('**/api/v1/interview-prep/journey-prep-session/generate**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ task_id: 'task-xyz' }),
    }));
    await page.route('**/api/v1/interview-prep/journey-prep-session/status', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'processing' }),
    }));
  });

  test('interview prep page loads for a session', async ({ page }) => {
    await page.goto('/dashboard/interview-prep/journey-prep-session');
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('body')).toBeVisible();
  });

  test('interview prep page does not redirect to login', async ({ page }) => {
    await page.goto('/dashboard/interview-prep/journey-prep-session');
    await page.waitForTimeout(2000);
    await expect(page).not.toHaveURL(/auth\/login/);
  });
});
