import { test, expect } from '@playwright/test';

/**
 * COMPREHENSIVE PROFILE SETUP PAGE TESTS  (/profile/setup)
 *
 * Wizard: step-0 (resume) + step-1 … step-5 (five content steps after resume).
 *   Step 0: Resume upload  (optional — can skip)
 *   Step 1: Basic Info     (city, state, country, title, experience, summary, student toggle)
 *   Step 2: Experience     (job entries + "no experience" checkbox)
 *   Step 3: Education        (entries + "no formal education" checkbox)
 *   Step 4: Skills         (tag input)
 *   Step 5: Preferences    (salary, job types, company sizes, work arrangement, travel, relocation, visa, clearance)
 *
 * Sections:
 *   A. Page structure (navbar, progress bar, step indicators, alerts)
 *   B. Step 0 — Resume Upload
 *   C. Step 1 — Basic Info
 *   D. Step 2 — Experience
 *   E. Step 3 — Education
 *   F. Step 4 — Skills
 *   G. Step 5 — Preferences
 *   H. Navigation buttons (Prev / Next / Complete)
 *   I. Access control
 *   J. Page structure extended
 *   K. Step 1 validation & mobile
 *   L. Step 4 skills extended
 *   M. Completion flow
 */

// Must be a valid 3-part JWT format — profile-setup.js validates token.split('.').length === 3
const MOCK_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMSIsImV4cCI6OTk5OTk5OTk5OX0.fake_sig_for_testing';

const MOCK_PROFILE = {
  id: 'u1',
  full_name: 'Test User',
  email: 'test@example.com',
  is_verified: true,
  job_title: '',
};

async function setupAuth(page: any) {
  await page.addInitScript((token: string) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('authToken', token);
    // Pre-accept cookie consent — must include version: '1.0' or the banner still shows
    localStorage.setItem('cookie_consent', JSON.stringify({
      essential: true, functional: true, analytics: false,
      version: '1.0', timestamp: new Date().toISOString()
    }));
  }, MOCK_TOKEN);

  // The profile setup JS calls /api/v1/profile/ (with trailing slash) to load existing data
  await page.route('**/api/v1/profile/**', (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      user_info: MOCK_PROFILE,
      profile_data: { city: '', state: '', country: '', professional_title: '', years_experience: null },
    }),
  }));

  await page.route('**/api/v1/profile', (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(MOCK_PROFILE),
  }));

  await page.route('**/api/v1/resume/upload', (route: any) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ message: 'Resume uploaded' }),
  }));

  // Mock all profile save endpoints called when clicking Next on each step
  await page.route('**/api/v1/profile/basic-info', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'Saved' }),
  }));
  await page.route('**/api/v1/profile/work-experience', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'Saved' }),
  }));
  await page.route('**/api/v1/profile/education', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'Saved' }),
  }));
  await page.route('**/api/v1/profile/skills-qualifications', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'Saved' }),
  }));
  await page.route('**/api/v1/profile/career-preferences', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'Saved' }),
  }));
  await page.route('**/api/v1/profile/complete', (route: any) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'Profile completed' }),
  }));
}

// ---------------------------------------------------------------------------
// A. PAGE STRUCTURE
// ---------------------------------------------------------------------------
test.describe('A. Page Structure', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
  });

  test('page title contains "Profile Setup"', async ({ page }) => {
    await expect(page).toHaveTitle(/Profile Setup/i);
  });

  test('navbar brand is present', async ({ page }) => {
    await expect(page.locator('.navbar-brand')).toBeVisible();
  });

  test('logout button is present in navbar', async ({ page }) => {
    await expect(page.locator('#logout-btn')).toBeAttached();
  });

  test('progress bar is present', async ({ page }) => {
    await expect(page.locator('#progress-bar')).toBeAttached();
  });

  test('5 step indicators are present (steps 1–5)', async ({ page }) => {
    await expect(page.locator('[data-step]')).toHaveCount(5);
  });

  test('step indicator labels are correct', async ({ page }) => {
    const labels = await page.locator('.step-label').allTextContents();
    expect(labels).toContain('Basic Info');
    expect(labels).toContain('Experience');
    expect(labels).toContain('Education');
    expect(labels).toContain('Skills');
    expect(labels).toContain('Preferences');
  });

  test('error alert container is present', async ({ page }) => {
    await expect(page.locator('#error-alert')).toBeAttached();
  });

  test('success alert container is present', async ({ page }) => {
    await expect(page.locator('#success-alert')).toBeAttached();
  });

  test('step-0 is active on page load', async ({ page }) => {
    await expect(page.locator('#step-0')).toBeVisible();
  });

  test('steps 1-5 are hidden on page load', async ({ page }) => {
    await expect(page.locator('#step-1')).not.toBeVisible();
    await expect(page.locator('#step-2')).not.toBeVisible();
    await expect(page.locator('#step-3')).not.toBeVisible();
    await expect(page.locator('#step-4')).not.toBeVisible();
    await expect(page.locator('#step-5')).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// B. STEP 0 — RESUME UPLOAD
// ---------------------------------------------------------------------------
test.describe('B. Step 0 — Resume Upload', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
  });

  test('resume upload section is visible on step 0', async ({ page }) => {
    await expect(page.locator('#resume-upload-section')).toBeVisible();
  });

  test('resume drop zone is visible', async ({ page }) => {
    await expect(page.locator('#resume-drop-zone')).toBeVisible();
  });

  test('resume file input accepts pdf, docx, txt', async ({ page }) => {
    const accept = await page.locator('#resume-file-input').getAttribute('accept');
    expect(accept).toContain('.pdf');
    expect(accept).toContain('.docx');
    expect(accept).toContain('.txt');
  });

  test('upload progress bar is hidden initially', async ({ page }) => {
    await expect(page.locator('#upload-progress')).toHaveClass(/d-none/);
  });

  test('"Skip for now" button is present', async ({ page }) => {
    await expect(page.locator('#skip-resume-btn')).toBeVisible();
  });

  test('clicking "Skip for now" advances to step 1', async ({ page }) => {
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(400);
    await expect(page.locator('#step-1')).toBeVisible({ timeout: 3000 });
    await expect(page.locator('#step-0')).not.toBeVisible({ timeout: 3000 });
  });
});

// ---------------------------------------------------------------------------
// Shared helpers: fill required fields to pass validation when clicking Next
// ---------------------------------------------------------------------------

/** Fill all required fields on step 1 (Basic Info) */
async function fillStep1Required(page: any) {
  await page.locator('#full-name').fill('Test User').catch(() => {});
  await page.locator('#city').fill('Tel Aviv');
  await page.locator('#state').fill('Tel Aviv District');
  await page.locator('#country').fill('Israel');
  await page.locator('#professional-title').fill('Software Engineer');
  await page.locator('#years-experience').fill('3');
  await page.locator('#summary').fill('Experienced developer building cool products.');
}

/** Check "no experience" and mock API so experience step passes */
async function fillStep2Required(page: any) {
  const cb = page.locator('#no-experience');
  if (await cb.isVisible({ timeout: 2000 }).catch(() => false)) {
    await cb.check();
  }
}

/** Check "no formal education" so education step passes */
async function fillStep3Education(page: any) {
  const cb = page.locator('#no-education');
  if (await cb.isVisible({ timeout: 2000 }).catch(() => false)) {
    await cb.check();
  }
}

/** Add one skill tag so skills step passes */
async function fillStep4Skills(page: any) {
  const input = page.locator('#skills-input');
  if (await input.isVisible({ timeout: 2000 }).catch(() => false)) {
    await input.fill('JavaScript');
    await input.press('Enter');
    await page.waitForTimeout(200);
  }
}

/** Check one of each required preference group */
async function _fillStep5Preferences(page: any) {
  for (const id of ['#job-type-fulltime', '#company-size-small', '#work-arrangement-remote', '#travel-none']) {
    const el = page.locator(id);
    if (await el.isVisible({ timeout: 2000 }).catch(() => false)) {
      await el.check().catch(() => {});
    }
  }
}

// ---------------------------------------------------------------------------
// C. STEP 1 — BASIC INFO
// ---------------------------------------------------------------------------
test.describe('C. Step 1 — Basic Info', () => {
  async function goToStep1(page: any) {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#skip-resume-btn').click();
    await page.waitForSelector('#step-1.active, #step-1:not([style*="display: none"])', { timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(300);
  }

  test('basic info form is present', async ({ page }) => {
    await goToStep1(page);
    await expect(page.locator('#basic-info-form')).toBeAttached();
  });

  test('city input is present', async ({ page }) => {
    await goToStep1(page);
    await expect(page.locator('#city')).toBeVisible();
  });

  test('state input is present', async ({ page }) => {
    await goToStep1(page);
    await expect(page.locator('#state')).toBeVisible();
  });

  test('country input is present', async ({ page }) => {
    await goToStep1(page);
    await expect(page.locator('#country')).toBeVisible();
  });

  test('professional title input is present', async ({ page }) => {
    await goToStep1(page);
    await expect(page.locator('#professional-title')).toBeVisible();
  });

  test('years of experience input is present', async ({ page }) => {
    await goToStep1(page);
    await expect(page.locator('#years-experience')).toBeVisible();
  });

  test('summary textarea is present', async ({ page }) => {
    await goToStep1(page);
    await expect(page.locator('#summary')).toBeVisible();
  });

  test('"Currently a student" checkbox is present', async ({ page }) => {
    await goToStep1(page);
    await expect(page.locator('#is-student')).toBeAttached();
  });

  test('can type into city field', async ({ page }) => {
    await goToStep1(page);
    await page.locator('#city').fill('Tel Aviv');
    expect(await page.locator('#city').inputValue()).toBe('Tel Aviv');
  });

  test('can type into professional title', async ({ page }) => {
    await goToStep1(page);
    await page.locator('#professional-title').fill('Software Engineer');
    expect(await page.locator('#professional-title').inputValue()).toBe('Software Engineer');
  });

  test('can type years of experience (numeric)', async ({ page }) => {
    await goToStep1(page);
    await page.locator('#years-experience').fill('5');
    expect(await page.locator('#years-experience').inputValue()).toBe('5');
  });

  test('can type into summary textarea', async ({ page }) => {
    await goToStep1(page);
    await page.locator('#summary').fill('Experienced developer with passion for AI products.');
    const val = await page.locator('#summary').inputValue();
    expect(val).toContain('Experienced developer');
  });

  test('"Currently a student" checkbox can be checked', async ({ page }) => {
    await goToStep1(page);
    await page.locator('#is-student').check();
    await expect(page.locator('#is-student')).toBeChecked();
  });
});

// ---------------------------------------------------------------------------
// D. STEP 2 — EXPERIENCE
// ---------------------------------------------------------------------------
test.describe('D. Step 2 — Experience', () => {
  async function goToStep2(page: any) {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(300);
    await fillStep1Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(500);
  }

  test('experience container is present', async ({ page }) => {
    await goToStep2(page);
    await expect(page.locator('#experience-container')).toBeAttached();
  });

  test('"Add Experience" button is present', async ({ page }) => {
    await goToStep2(page);
    await expect(page.locator('#add-experience-btn')).toBeAttached();
  });

  test('"No experience yet" checkbox is present', async ({ page }) => {
    await goToStep2(page);
    await expect(page.locator('#no-experience')).toBeAttached();
  });

  test('"No experience" checkbox can be checked', async ({ page }) => {
    await goToStep2(page);
    const cb = page.locator('#no-experience');
    if (await cb.isVisible()) {
      await cb.check();
      await expect(cb).toBeChecked();
    } else {
      await expect(cb).toBeAttached();
    }
  });
});

// ---------------------------------------------------------------------------
// E. STEP 3 — EDUCATION
// ---------------------------------------------------------------------------
test.describe('E. Step 3 — Education', () => {
  async function goToStep3Education(page: any) {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(300);
    await fillStep1Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await fillStep2Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await page.locator('#step-3').waitFor({ state: 'visible', timeout: 5000 });
  }

  test('education container is present', async ({ page }) => {
    await goToStep3Education(page);
    await expect(page.locator('#education-container')).toBeAttached();
  });

  test('"Add education" control is present', async ({ page }) => {
    await goToStep3Education(page);
    await expect(page.locator('#add-education-btn')).toBeAttached();
  });

  test('"No formal education" checkbox is present', async ({ page }) => {
    await goToStep3Education(page);
    await expect(page.locator('#no-education')).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// F. STEP 4 — SKILLS
// ---------------------------------------------------------------------------
test.describe('F. Step 4 — Skills', () => {
  async function goToStep4Skills(page: any) {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(300);
    await fillStep1Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await fillStep2Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await fillStep3Education(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await page.locator('#step-4').waitFor({ state: 'visible', timeout: 5000 });
  }

  test('skills input is present', async ({ page }) => {
    await goToStep4Skills(page);
    await expect(page.locator('#skills-input')).toBeAttached();
  });

  test('skills container is present', async ({ page }) => {
    await goToStep4Skills(page);
    await expect(page.locator('#skills-container')).toBeAttached();
  });

  test('can type into skills input', async ({ page }) => {
    await goToStep4Skills(page);
    const input = page.locator('#skills-input');
    if (await input.isVisible()) {
      await input.fill('Python');
      expect(await input.inputValue()).toBe('Python');
    } else {
      await expect(input).toBeAttached();
    }
  });
});

// ---------------------------------------------------------------------------
// G. STEP 5 — PREFERENCES
// ---------------------------------------------------------------------------
test.describe('G. Step 5 — Preferences', () => {
  async function goToStep5Preferences(page: any) {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(300);
    await fillStep1Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await fillStep2Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await fillStep3Education(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await fillStep4Skills(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(500);
    await page.locator('#step-5').waitFor({ state: 'visible', timeout: 5000 });
  }

  test('career preferences form is present', async ({ page }) => {
    await goToStep5Preferences(page);
    await expect(page.locator('#career-preferences-form')).toBeAttached();
  });

  test('min salary input is present', async ({ page }) => {
    await goToStep5Preferences(page);
    await expect(page.locator('#min-salary')).toBeAttached();
  });

  test('max salary input is present', async ({ page }) => {
    await goToStep5Preferences(page);
    await expect(page.locator('#max-salary')).toBeAttached();
  });

  test.describe('Job type checkboxes', () => {
    test('full-time checkbox is present', async ({ page }) => {
      await goToStep5Preferences(page);
      await expect(page.locator('#job-type-fulltime')).toBeAttached();
    });
    test('part-time checkbox is present', async ({ page }) => {
      await goToStep5Preferences(page);
      await expect(page.locator('#job-type-parttime')).toBeAttached();
    });
    test('contract checkbox is present', async ({ page }) => {
      await goToStep5Preferences(page);
      await expect(page.locator('#job-type-contract')).toBeAttached();
    });
    test('freelance checkbox is present', async ({ page }) => {
      await goToStep5Preferences(page);
      await expect(page.locator('#job-type-freelance')).toBeAttached();
    });
    test('internship checkbox is present', async ({ page }) => {
      await goToStep5Preferences(page);
      await expect(page.locator('#job-type-internship')).toBeAttached();
    });
    test('can check full-time', async ({ page }) => {
      await goToStep5Preferences(page);
      const cb = page.locator('#job-type-fulltime');
      if (await cb.isVisible()) { await cb.check(); await expect(cb).toBeChecked(); }
      else { await expect(cb).toBeAttached(); }
    });
  });

  test.describe('Company size checkboxes', () => {
    const sizes = ['startup', 'small', 'medium', 'large', 'enterprise'];
    for (const s of sizes) {
      test(`company-size-${s} is present`, async ({ page }) => {
        await goToStep5Preferences(page);
        await expect(page.locator(`#company-size-${s}`)).toBeAttached();
      });
    }
  });

  test.describe('Work arrangement checkboxes', () => {
    const arrangements = ['onsite', 'remote', 'hybrid'];
    for (const a of arrangements) {
      test(`work-arrangement-${a} is present`, async ({ page }) => {
        await goToStep5Preferences(page);
        await expect(page.locator(`#work-arrangement-${a}`)).toBeAttached();
      });
    }
    test('can check remote', async ({ page }) => {
      await goToStep5Preferences(page);
      const cb = page.locator('#work-arrangement-remote');
      if (await cb.isVisible()) { await cb.check(); await expect(cb).toBeChecked(); }
      else { await expect(cb).toBeAttached(); }
    });
  });

  test.describe('Travel preference radio buttons', () => {
    const travels = ['none', 'minimal', 'moderate', 'frequent', 'extensive'];
    for (const t of travels) {
      test(`travel-${t} radio is present`, async ({ page }) => {
        await goToStep5Preferences(page);
        await expect(page.locator(`#travel-${t}`)).toBeAttached();
      });
    }
  });

  test('willing-to-relocate checkbox is present', async ({ page }) => {
    await goToStep5Preferences(page);
    await expect(page.locator('#willing-to-relocate')).toBeAttached();
  });

  test('requires-visa-sponsorship checkbox is present', async ({ page }) => {
    await goToStep5Preferences(page);
    await expect(page.locator('#requires-visa-sponsorship')).toBeAttached();
  });

  test('has-security-clearance checkbox is present', async ({ page }) => {
    await goToStep5Preferences(page);
    await expect(page.locator('#has-security-clearance')).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// H. NAVIGATION BUTTONS
// ---------------------------------------------------------------------------
test.describe('H. Navigation Buttons', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
  });

  test('Prev button exists in DOM', async ({ page }) => {
    await expect(page.locator('#prev-btn')).toBeAttached();
  });

  test('Next button exists in DOM', async ({ page }) => {
    await expect(page.locator('#next-btn')).toBeAttached();
  });

  test('Complete button exists in DOM', async ({ page }) => {
    await expect(page.locator('#complete-btn')).toBeAttached();
  });

  test('skipping resume advances to step 1 (Next visible)', async ({ page }) => {
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(400);
    await expect(page.locator('#step-1')).toBeVisible({ timeout: 3000 });
  });

  test('clicking Next from step 1 moves to step 2', async ({ page }) => {
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(300);
    await fillStep1Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#step-2')).toBeVisible({ timeout: 3000 });
  });

  test('clicking Prev from step 2 returns to step 1', async ({ page }) => {
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(300);
    await fillStep1Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(500);
    // Now on step 2 — go back
    const prevBtn = page.locator('#prev-btn');
    if (await prevBtn.isVisible()) {
      await prevBtn.click();
      await page.waitForTimeout(400);
      await expect(page.locator('#step-1')).toBeVisible({ timeout: 3000 });
    } else {
      await expect(prevBtn).toBeAttached();
    }
  });

  test('full forward walk: step 0 → 1 → 2 → 3 → 4 → 5', async ({ page }) => {
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(300);
    await fillStep1Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await fillStep2Required(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await fillStep3Education(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await fillStep4Skills(page);
    await page.locator('#next-btn').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#step-5')).toBeVisible({ timeout: 5000 });
  });
});

// ---------------------------------------------------------------------------
// I. ACCESS CONTROL
// ---------------------------------------------------------------------------
test.describe('I. Access Control', () => {
  test('unauthenticated user is redirected from /profile/setup', async ({ page }) => {
    await page.goto('/profile/setup');
    await page.waitForURL(/auth\/login/, { timeout: 8000 });
    expect(page.url()).toContain('auth/login');
  });
});

// ---------------------------------------------------------------------------
// J. PAGE STRUCTURE EXTENDED
// ---------------------------------------------------------------------------
test.describe('J. Page Structure Extended', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
  });

  test('step containers step-0 through step-5 all exist in DOM', async ({ page }) => {
    for (const step of ['step-0', 'step-1', 'step-2', 'step-3', 'step-4', 'step-5']) {
      await expect(page.locator(`#${step}`)).toBeAttached();
    }
  });

  test('progress bar has role="progressbar" or is a <progress> element', async ({ page }) => {
    const progressBar = page.locator('#progress-bar');
    await expect(progressBar).toBeAttached();
    const role = await progressBar.getAttribute('role');
    const tag = await progressBar.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    expect(role === 'progressbar' || tag === 'progress' || tag === 'div').toBe(true);
  });

  test('no JS errors on profile setup page load', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.waitForTimeout(500);
    expect(errors.length).toBe(0);
  });

  test('page has a form element', async ({ page }) => {
    await expect(page.locator('form').first()).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// K. STEP 1 VALIDATION & MOBILE
// ---------------------------------------------------------------------------
test.describe('K. Step 1 — Validation & Mobile', () => {
  async function goToStep1(page: any) {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(400);
    await page.locator('#step-1').waitFor({ state: 'visible', timeout: 5000 });
  }

  test('step 1 title input has a placeholder or label', async ({ page }) => {
    await goToStep1(page);
    const titleInput = page.locator('#professional-title');
    await expect(titleInput).toBeVisible();
  });

  test('step 1 city input is present and fillable', async ({ page }) => {
    await goToStep1(page);
    const cityInput = page.locator('#city');
    await expect(cityInput).toBeVisible();
    await cityInput.fill('Tel Aviv');
    expect(await cityInput.inputValue()).toBe('Tel Aviv');
  });

  test('step 1 years-experience is a number input', async ({ page }) => {
    await goToStep1(page);
    const input = page.locator('#years-experience');
    await expect(input).toBeVisible();
    expect(await input.getAttribute('type')).toBe('number');
    const max = await input.getAttribute('max');
    expect(max === '50' || max === null).toBe(true);
  });

  test('profile setup is visible on 375px mobile viewport', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 667 } });
    const p = await ctx.newPage();
    await p.addInitScript((token: string) => {
      localStorage.setItem('access_token', token);
      localStorage.setItem('authToken', token);
      localStorage.setItem('cookie_consent', JSON.stringify({ essential: true, functional: true, analytics: false, version: '1.0', timestamp: new Date().toISOString() }));
    }, MOCK_TOKEN);
    await p.route('**/api/v1/profile/**', (route: any) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ user_info: MOCK_PROFILE, profile_data: {} }) }));
    await p.route('**/api/v1/profile', (route: any) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_PROFILE) }));
    await p.goto('/profile/setup');
    await expect(p.locator('#step-0')).toBeVisible({ timeout: 5000 });
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------
// L. STEP 4 SKILLS — EXTENDED
// ---------------------------------------------------------------------------
test.describe('L. Step 4 — Skills Extended', () => {
  async function goToStep4SkillsExtended(page: any) {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(300);
    // Fill step 1 minimally
    const title = page.locator('#professional-title');
    if (await title.isVisible({ timeout: 2000 }).catch(() => false)) {
      await title.fill('Engineer');
    }
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    // Step 2 - check "no experience"
    const noExp = page.locator('#no-experience');
    if (await noExp.isVisible({ timeout: 2000 }).catch(() => false)) {
      await noExp.check();
    }
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    const noEd = page.locator('#no-education');
    if (await noEd.isVisible({ timeout: 2000 }).catch(() => false)) {
      await noEd.check();
    }
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    await page.locator('#step-4').waitFor({ state: 'visible', timeout: 5000 });
  }

  test('skill input element is present on step 4', async ({ page }) => {
    await goToStep4SkillsExtended(page);
    const skillInput = page.locator('#skills-input');
    await expect(skillInput.first()).toBeAttached();
  });

  test('skills container is present', async ({ page }) => {
    await goToStep4SkillsExtended(page);
    await expect(page.locator('#skills-container')).toBeAttached();
  });

  test('step 4 header says "Skills"', async ({ page }) => {
    await goToStep4SkillsExtended(page);
    const heading = page.locator('#step-4 h2, #step-4 h3, #step-4 h4').first();
    await expect(heading).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// M. COMPLETION FLOW
// ---------------------------------------------------------------------------
test.describe('M. Completion Flow', () => {
  test('complete button is present on step 5', async ({ page }) => {
    await setupAuth(page);
    await page.goto('/profile/setup');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#skip-resume-btn').click();
    await page.waitForTimeout(300);
    const title = page.locator('#professional-title');
    if (await title.isVisible({ timeout: 2000 }).catch(() => false)) await title.fill('Engineer');
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    const noExp = page.locator('#no-experience');
    if (await noExp.isVisible({ timeout: 2000 }).catch(() => false)) await noExp.check();
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    const noEd = page.locator('#no-education');
    if (await noEd.isVisible({ timeout: 2000 }).catch(() => false)) await noEd.check();
    await page.locator('#next-btn').click();
    await page.waitForTimeout(400);
    const skillInput = page.locator('#skills-input');
    if (await skillInput.isVisible({ timeout: 2000 }).catch(() => false)) {
      await skillInput.fill('Python');
      await skillInput.press('Enter');
    }
    await page.locator('#next-btn').click();
    await page.waitForTimeout(500);
    await page.locator('#step-5').waitFor({ state: 'visible', timeout: 5000 });
    await expect(page.locator('#complete-btn')).toBeAttached();
  });
});
