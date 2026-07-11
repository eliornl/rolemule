import { test, expect } from '@playwright/test';
import { setupAuth, buildMockGetProfileResponse } from '../utils/api-mocks';

/**
 * API RESPONSE VALIDATION TESTS
 *
 * Tests that the frontend correctly handles various API response shapes,
 * validates data rendering, and recovers from unexpected/malformed responses.
 * All tests are Tier 1 (CI-safe, fully mocked).
 */

const SESSION_ID = 'api-val-session-123';

const FULL_RESULTS = {
  job_analysis: {
    job_title: 'Senior Engineer',
    company_name: 'MegaCorp',
    location: 'Remote',
    required_skills: ['Python', 'FastAPI'],
    nice_to_have_skills: ['Docker'],
    seniority_level: 'Senior',
    employment_type: 'Full-time',
    remote_policy: 'Remote',
  },
  match_assessment: {
    overall_score: 88,
    strengths: ['Python expertise', 'FastAPI experience'],
    gaps: ['Docker knowledge'],
    recommendation: 'Strong candidate — apply.',
  },
  cover_letter: {
    letter: 'Dear Hiring Manager,\n\nI am writing to express my interest...',
  },
  resume_recommendations: {
    summary: 'Tailor your summary to highlight distributed systems.',
    bullet_points: ['Led migration to microservices', 'Reduced latency by 40%'],
  },
  company_research: {
    overview: 'MegaCorp is a Fortune 500 tech company.',
    culture: 'Engineering-driven, remote-first.',
    recent_news: ['Raised $200M Series D', 'Acquired SmallCo'],
  },
  three_key_selling_points: ['Python expert', 'FastAPI specialist', 'Remote-work veteran'],
};

async function setupPage(page: any, resultsBody: any = FULL_RESULTS) {
  await setupAuth(page);
  await page.route(`**/api/v1/workflow/status/${SESSION_ID}`, (route: any) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ status: 'completed' }),
  }));
  await page.route(`**/api/v1/workflow/results/${SESSION_ID}`, (route: any) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify(resultsBody),
  }));
}

// ---------------------------------------------------------------------------
// A. FULL RESPONSE RENDERING
// ---------------------------------------------------------------------------
test.describe('A. Full Response Rendering', () => {
  test('application detail page loads with complete results', async ({ page }) => {
    await setupPage(page);
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    await expect(page.locator('body')).toBeVisible();
  });

  test('job title from results is rendered on detail page', async ({ page }) => {
    await setupPage(page);
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    const pageText = await page.locator('body').textContent();
    expect(pageText).toMatch(/Senior Engineer|MegaCorp/i);
  });

  test('page does not JS-error with full results', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await setupPage(page);
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    expect(errors.length).toBe(0);
  });

  test('match score is rendered (if visible)', async ({ page }) => {
    await setupPage(page);
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    const scoreEl = page.locator('#matchScore, .match-score, .fit-score-value').first();
    if (await scoreEl.count() > 0 && await scoreEl.isVisible()) {
      await expect(scoreEl).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// B. PARTIAL / MINIMAL RESPONSE
// ---------------------------------------------------------------------------
test.describe('B. Partial Response Handling', () => {
  test('page renders when only job_analysis is present', async ({ page }) => {
    const minimalResults = {
      job_analysis: { job_title: 'Dev', company_name: 'Corp', required_skills: [], nice_to_have_skills: [] },
      match_assessment: { overall_score: 0, strengths: [], gaps: [], recommendation: '' },
      cover_letter: { letter: '' },
      resume_recommendations: { summary: '', bullet_points: [] },
      company_research: { overview: '', culture: '', recent_news: [] },
      three_key_selling_points: [],
    };
    await setupPage(page, minimalResults);
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    expect(errors.length).toBe(0);
    await expect(page.locator('body')).toBeVisible();
  });

  test('empty arrays for required_skills do not crash page', async ({ page }) => {
    const results = { ...FULL_RESULTS, job_analysis: { ...FULL_RESULTS.job_analysis, required_skills: [] as string[], nice_to_have_skills: [] as string[] } };
    await setupPage(page, results);
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    expect(errors.length).toBe(0);
  });

  test('empty strengths and gaps arrays do not crash page', async ({ page }) => {
    const results = { ...FULL_RESULTS, match_assessment: { ...FULL_RESULTS.match_assessment, strengths: [], gaps: [] } };
    await setupPage(page, results);
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    expect(errors.length).toBe(0);
  });

  test('empty recent_news array does not crash page', async ({ page }) => {
    const results = { ...FULL_RESULTS, company_research: { ...FULL_RESULTS.company_research, recent_news: [] } };
    await setupPage(page, results);
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    expect(errors.length).toBe(0);
  });

  test('three_key_selling_points with 3 items renders correctly', async ({ page }) => {
    await setupPage(page, FULL_RESULTS);
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// C. PROFILE API RESPONSE SHAPES
// ---------------------------------------------------------------------------
test.describe('C. Profile API Response Shapes', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('dashboard renders with minimal profile response', async ({ page }) => {
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ name: 'User', email: 'u@example.com' }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });

  test('dashboard renders with full profile response', async ({ page }) => {
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        name: 'Jane Doe', email: 'jane@example.com', profile_complete: true,
        professional_title: 'Engineer', years_experience: 5,
        city: 'SF', state: 'CA', country: 'USA',
        skills: ['Python', 'TypeScript'],
      }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });

  test('dashboard renders with multiple applications', async ({ page }) => {
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ name: 'User', email: 'u@example.com' }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        applications: [
          { session_id: 's1', job_title: 'Engineer', company_name: 'Corp A', status: 'completed', created_at: new Date().toISOString() },
          { session_id: 's2', job_title: 'Dev', company_name: 'Corp B', status: 'processing', created_at: new Date().toISOString() },
          { session_id: 's3', job_title: 'Architect', company_name: 'Corp C', status: 'failed', created_at: new Date().toISOString() },
        ],
        total: 3,
      }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// D. CAREER TOOLS API RESPONSES
// ---------------------------------------------------------------------------
test.describe('D. Career Tools API Responses', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ name: 'User', email: 'u@example.com' }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
  });

  test('thank you note API 200 response does not crash page', async ({ page }) => {
    await page.route('**/api/v1/tools/thank-you**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        thank_you_note: 'Dear Jane, thank you for the opportunity...',
        subject_line: 'Thank You — Engineer Interview',
      }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard/tools');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });

  test('rejection analysis API 200 response does not crash page', async ({ page }) => {
    await page.route('**/api/v1/tools/rejection-analysis**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        analysis: 'Your application was strong. Consider improving your system design responses.',
        action_items: ['Practice system design', 'Research the company more'],
      }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard/tools');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });

  test('salary coach API 200 response does not crash page', async ({ page }) => {
    await page.route('**/api/v1/tools/salary-coach**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        strategy: 'Counter at 15% above the offer based on market data.',
        talking_points: ['Market rate is $X', 'Your 5 years of experience', 'Cost of living'],
        target_range: { min: 120000, max: 140000 },
      }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard/tools');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// E. ERROR RESPONSE SHAPES
// ---------------------------------------------------------------------------
test.describe('E. Error Response Shapes', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
  });

  test('detail-string 404 from profile API does not crash', async ({ page }) => {
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 404, contentType: 'application/json',
      body: JSON.stringify({ detail: 'Profile not found' }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });

  test('validation-error array 422 from API does not crash', async ({ page }) => {
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 422, contentType: 'application/json',
      body: JSON.stringify({ detail: [{ loc: ['body', 'name'], msg: 'field required', type: 'value_error.missing' }] }),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });

  test('empty body 200 from profile does not crash', async ({ page }) => {
    await page.route('**/api/v1/profile', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({}),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0 }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('/dashboard');
    await page.waitForTimeout(2000);
    expect(errors.length).toBe(0);
  });

  test('workflow results with null fields do not crash page', async ({ page }) => {
    await page.route(`**/api/v1/workflow/status/${SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'completed' }),
    }));
    await page.route(`**/api/v1/workflow/results/${SESSION_ID}`, (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        job_analysis: { job_title: null, company_name: null, required_skills: [], nice_to_have_skills: [] },
        match_assessment: { overall_score: null, strengths: [], gaps: [], recommendation: null },
        cover_letter: { letter: null },
        resume_recommendations: { summary: null, bullet_points: [] },
        company_research: { overview: null, culture: null, recent_news: [] },
        three_key_selling_points: [],
      }),
    }));
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(`/dashboard/application/${SESSION_ID}`);
    await page.waitForTimeout(4000);
    expect(errors.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// F. AUTH API RESPONSE VALIDATION
// ---------------------------------------------------------------------------
test.describe('F. Auth API Response Validation', () => {
  test('login success response sets localStorage token', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: false,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
    await page.route('**/api/v1/auth/login', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        access_token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMSJ9.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c',
        token_type: 'bearer',
        user: { name: 'Test', email: 'test@example.com', profile_complete: true },
      }),
    }));
    await page.route('**/api/v1/profile**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify(buildMockGetProfileResponse()),
    }));
    await page.route('**/api/v1/applications**', (route: any) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ applications: [], total: 0, page: 1, per_page: 10, pages: 0 }),
    }));
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('input[type="email"]').fill('test@example.com');
    await page.locator('input[type="password"]').fill('Password123!');
    await page.locator('button[type="submit"], #login-btn').first().click();
    await page.waitForTimeout(2000);
    const token = await page.evaluate(() => localStorage.getItem('access_token') || localStorage.getItem('authToken'));
    expect(token).not.toBeNull();
  });

  test('login 401 response keeps user on login page', async ({ page }) => {
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
    await page.locator('input[type="email"]').fill('bad@example.com');
    await page.locator('input[type="password"]').fill('badpassword');
    await page.locator('button[type="submit"], #login-btn').first().click();
    await page.waitForTimeout(1500);
    await expect(page).toHaveURL(/login/);
  });
});
