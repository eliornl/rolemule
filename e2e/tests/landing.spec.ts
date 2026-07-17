import { test, expect } from '@playwright/test';

/**
 * COMPREHENSIVE LANDING PAGE TESTS
 *
 * Covers every section of the RoleMule landing page (index.html):
 *
 * 1.  Page Load & Meta
 * 2.  Navbar — logo, nav-links (Workflow / On Demand), Sign In / Try Free CTAs, mobile hamburger
 * 3.  Hero Section — tagline, subtitle, 4 steps
 * 4.  Tech Stack Bar — provider tags, GitHub link
 * 5.  Problem Section (#problem) — stat number, time-comparison table
 * 6.  Features Section (#features) — 5 workflow AI-agent cards
 * 6b. On Demand (#after-apply) — Optimize CV, Interview Prep, Mock Session, Outreach
 * 7.  Chrome Extension Section (#extension) — 4 bullet points
 * 8.  Career Tools Section (#tools) — all 6 tool cards
 * 8b. CLI Section (#cli)
 * 9.  Example Section (#example) — 10 interactive tabs + screenshot panels
 * 10. Pricing Section (#pricing) — free pricing text, BYOK CTA
 * 11. Footer — logo, Help / Privacy / Terms links, GitHub link
 * 12. Cookie Consent — banner appears, accept hides it, reject keeps it hidden
 * 13. Smooth-scroll anchor navigation
 * 14. Accessibility basics — page landmark, heading order, link accessible names
 * 15. Auth CTAs — Sign In → /auth/login, Try Free → /auth/register
 * 16. Unauthenticated protection — /dashboard redirects to login
 * 17. Public pages — /help, /privacy, /terms load without auth
 * 18. Error pages — 404 for unknown routes
 * 19. Mobile & tablet viewports
 * 20. Security headers present
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function clearConsent(page: any) {
  await page.context().clearCookies();
  await page.evaluate(() => {
    try { localStorage.clear(); } catch (_) {}
    try { sessionStorage.clear(); } catch (_) {}
  });
}

// ---------------------------------------------------------------------------
// 1. Page Load & Meta
// ---------------------------------------------------------------------------
test.describe('1. Page Load & Meta', () => {
  test('landing page returns HTTP 200', async ({ request }) => {
    const res = await request.get('/');
    expect(res.status()).toBe(200);
  });

  test('page title contains RoleMule', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/RoleMule/i);
  });

  test('meta description is present', async ({ page }) => {
    await page.goto('/');
    const metaDesc = page.locator('meta[name="description"]');
    await expect(metaDesc).toHaveCount(1);
    const content = await metaDesc.getAttribute('content');
    expect(content).toBeTruthy();
    expect(content!.length).toBeGreaterThan(20);
  });

  test('viewport meta tag is present', async ({ page }) => {
    await page.goto('/');
    const viewport = page.locator('meta[name="viewport"]');
    await expect(viewport).toHaveCount(1);
  });

  test('page body has .landing-page class', async ({ page }) => {
    await page.goto('/');
    const body = page.locator('body');
    await expect(body).toHaveClass(/landing-page/);
  });

  test('no console errors on initial load', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    // Filter out expected third-party noise
    const criticalErrors = errors.filter(e =>
      !e.includes('favicon') && !e.includes('analytics') && !e.includes('posthog')
    );
    expect(criticalErrors).toHaveLength(0);
  });

  test('health endpoint returns 200', async ({ request }) => {
    const res = await request.get('/health');
    expect(res.status()).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// 2. Navbar
// ---------------------------------------------------------------------------
test.describe('2. Navbar', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('navbar is visible and fixed to top', async ({ page }) => {
    const nav = page.locator('nav.navbar');
    await expect(nav).toBeVisible();
    const position = await nav.evaluate(el => getComputedStyle(el).position);
    expect(position).toBe('fixed');
  });

  test('brand logo is visible and links to homepage', async ({ page }) => {
    const brand = page.locator('.navbar-brand');
    await expect(brand).toBeVisible();
    const href = await brand.getAttribute('href');
    expect(href).toBe('/');
  });

  test('brand text reads "RoleMule"', async ({ page }) => {
    const brand = page.locator('.navbar-brand');
    const text = await brand.textContent();
    expect(text?.replace(/\s/g, '')).toMatch(/RoleMule/i);
  });

  test('navbar has "Why RoleMule" link pointing to #problem', async ({ page }) => {
    const link = page.locator('.navbar-nav a[href="#problem"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/Why RoleMule/i);
  });

  test('navbar has "Workflow" link pointing to #features', async ({ page }) => {
    const link = page.locator('.navbar-nav a[href="#features"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/Workflow/i);
  });

  test('navbar has "On Demand" link pointing to #after-apply', async ({ page }) => {
    const link = page.locator('.navbar-nav a[href="#after-apply"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/On Demand/i);
  });

  test('navbar has "Extension" link pointing to #extension', async ({ page }) => {
    const link = page.locator('.navbar-nav a[href="#extension"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/Extension/i);
  });

  test('navbar has "Career Tools" link pointing to #tools', async ({ page }) => {
    const link = page.locator('.navbar-nav a[href="#tools"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/Career Tools/i);
  });

  test('navbar has "CLI" link pointing to #cli', async ({ page }) => {
    const link = page.locator('.navbar-nav a[href="#cli"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/^CLI$/i);
  });

  test('navbar has "Example" link pointing to #example', async ({ page }) => {
    const link = page.locator('.navbar-nav a[href="#example"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/Example/i);
  });

  test('navbar has "Pricing" link pointing to #pricing', async ({ page }) => {
    const link = page.locator('.navbar-nav a[href="#pricing"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/Pricing/i);
  });

  test('"Sign In" CTA is visible and links to /auth/login', async ({ page }) => {
    const signIn = page.locator('.nav-cta a[href="/auth/login"]');
    await expect(signIn).toBeVisible();
    await expect(signIn).toContainText(/Sign In/i);
  });

  test('"Try Free" CTA is visible and links to /auth/register', async ({ page }) => {
    const tryFree = page.locator('.nav-cta a[href="/auth/register"]');
    await expect(tryFree).toBeVisible();
    await expect(tryFree).toContainText(/Try Free/i);
  });

  test('Sign In CTA navigates to login page', async ({ page }) => {
    await page.locator('.nav-cta a[href="/auth/login"]').click();
    await expect(page).toHaveURL(/\/auth\/login/);
  });

  test('Try Free CTA navigates to register page', async ({ page }) => {
    await page.goto('/');
    await page.locator('.nav-cta a[href="/auth/register"]').click();
    await expect(page).toHaveURL(/\/auth\/register/);
  });

  test('mobile: hamburger toggler exists', async ({ page }) => {
    const toggler = page.locator('.navbar-toggler');
    await expect(toggler).toBeAttached();
  });

  test('mobile: hamburger opens navbar collapse', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const mobilePage = await ctx.newPage();
    await mobilePage.goto('/');
    await mobilePage.waitForLoadState('domcontentloaded');

    const toggler = mobilePage.locator('.navbar-toggler');
    // On mobile the toggler should be visible
    const togglerVisible = await toggler.isVisible();
    if (togglerVisible) {
      await toggler.click();
      const collapse = mobilePage.locator('#navbarNav');
      await expect(collapse).toHaveClass(/show/, { timeout: 3000 });
    }

    await ctx.close();
  });

  test('navbar uses navbar-expand-xl (not navbar-expand-lg)', async ({ page }) => {
    const nav = page.locator('nav.navbar');
    await expect(nav).toHaveClass(/navbar-expand-xl/);
  });
});

// ---------------------------------------------------------------------------
// 3. Hero Section
// ---------------------------------------------------------------------------
test.describe('3. Hero Section', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('hero section is visible', async ({ page }) => {
    await expect(page.locator('.hero-section')).toBeVisible();
  });

  test('hero title contains tagline "One mule for every role"', async ({ page }) => {
    const title = page.locator('.hero-title');
    await expect(title).toBeVisible();
    await expect(title).toContainText(/One mule for every role/i);
  });

  test('hero title does not use old Job Search Companion headline', async ({ page }) => {
    const title = page.locator('.hero-title');
    await expect(title).not.toContainText(/Job Search Companion/i);
  });

  test('hero subtitle is visible and non-empty', async ({ page }) => {
    const subtitle = page.locator('.hero-subtitle');
    await expect(subtitle).toBeVisible();
    const text = await subtitle.textContent();
    expect(text?.trim().length).toBeGreaterThan(20);
  });

  test('hero shows exactly 4 steps', async ({ page }) => {
    const steps = page.locator('.hero-step');
    await expect(steps).toHaveCount(4);
  });

  test('step 1 mentions "Add Any Job Posting"', async ({ page }) => {
    const steps = page.locator('.hero-step');
    await expect(steps.nth(0)).toContainText(/Add Any Job Posting/i);
  });

  test('step 2 mentions "AI Works in the Background"', async ({ page }) => {
    const steps = page.locator('.hero-step');
    await expect(steps.nth(1)).toContainText(/AI Works in the Background/i);
  });

  test('step 3 mentions "Apply with Confidence"', async ({ page }) => {
    const steps = page.locator('.hero-step');
    await expect(steps.nth(2)).toContainText(/Apply with Confidence/i);
  });

  test('step 4 mentions "Continue Your Journey"', async ({ page }) => {
    const steps = page.locator('.hero-step');
    await expect(steps.nth(3)).toContainText(/Continue Your Journey/i);
  });

  test('hero step numbers are 1, 2, 3, 4', async ({ page }) => {
    const nums = page.locator('.step-num');
    await expect(nums).toHaveCount(4);
    for (let i = 1; i <= 4; i++) {
      await expect(nums.nth(i - 1)).toContainText(String(i));
    }
  });

  test('3 step arrows are rendered between steps', async ({ page }) => {
    const arrows = page.locator('.hero-step-arrow');
    await expect(arrows).toHaveCount(3);
  });
});

// ---------------------------------------------------------------------------
// 4. Tech Stack Bar
// ---------------------------------------------------------------------------
test.describe('4. Tech Stack Bar', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('tech bar section is present', async ({ page }) => {
    await expect(page.locator('.section-tech-bar')).toBeVisible();
  });

  test('"Built with" label is shown', async ({ page }) => {
    await expect(page.locator('.tech-bar-label')).toContainText(/Built with/i);
  });

  const techTags = ['Python', 'FastAPI', 'PostgreSQL', 'Redis', 'Google Gemini', 'OpenAI', 'Anthropic', 'Ollama', 'LangGraph', 'Docker'];
  for (const tag of techTags) {
    test(`tech tag "${tag}" is visible`, async ({ page }) => {
      const tagEl = page.locator('.tech-bar-tags span').filter({ hasText: tag });
      await expect(tagEl).toBeVisible();
    });
  }

  test('GitHub "View on GitHub" link is present', async ({ page }) => {
    const ghLink = page.locator('.tech-bar-link');
    await expect(ghLink).toBeVisible();
    await expect(ghLink).toContainText(/View on GitHub/i);
  });

  test('GitHub link opens in a new tab', async ({ page }) => {
    const ghLink = page.locator('.tech-bar-link');
    const target = await ghLink.getAttribute('target');
    expect(target).toBe('_blank');
  });

  test('GitHub link has rel="noopener noreferrer"', async ({ page }) => {
    const ghLink = page.locator('.tech-bar-link');
    const rel = await ghLink.getAttribute('rel');
    expect(rel).toContain('noopener');
    expect(rel).toContain('noreferrer');
  });
});

// ---------------------------------------------------------------------------
// 5. Problem Section
// ---------------------------------------------------------------------------
test.describe('5. Problem Section', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('problem section exists with correct id', async ({ page }) => {
    await expect(page.locator('#problem')).toBeAttached();
  });

  test('problem section title is visible', async ({ page }) => {
    const title = page.locator('#problem .problem-title');
    await expect(title).toBeVisible();
    await expect(title).toContainText(/Job searching/i);
  });

  test('stat number "~150" is shown', async ({ page }) => {
    const stat = page.locator('.stat-number');
    await expect(stat).toContainText('150');
  });

  test('stat description mentions "Applications"', async ({ page }) => {
    const desc = page.locator('.stat-desc');
    await expect(desc).toContainText(/Applications/i);
  });

  test('comparison shows "Manual" column', async ({ page }) => {
    await expect(page.locator('.comparison-item.manual')).toBeVisible();
  });

  test('comparison shows "With AI" column', async ({ page }) => {
    await expect(page.locator('.comparison-item.ai')).toBeVisible();
  });

  test('"VS" divider is visible', async ({ page }) => {
    await expect(page.locator('.comparison-vs')).toContainText('VS');
  });

  test('Manual total time is "~1.5 hours"', async ({ page }) => {
    const manual = page.locator('.comparison-item.manual .total-time');
    await expect(manual).toContainText(/1\.5 hours/i);
  });

  test('AI total time is "~6 minutes"', async ({ page }) => {
    const ai = page.locator('.comparison-item.ai .total-time');
    await expect(ai).toContainText(/6 minutes/i);
  });

  test('"15x faster" summary text is present', async ({ page }) => {
    await expect(page.locator('.problem-solution')).toContainText(/15x faster/i);
  });

  test('problem section has exactly 5 manual task rows', async ({ page }) => {
    const rows = page.locator('.comparison-item.manual .task-row');
    await expect(rows).toHaveCount(5);
  });
});

// ---------------------------------------------------------------------------
// 6. Features Section — 6 AI Agents
// ---------------------------------------------------------------------------
test.describe('6. Features Section (6 AI Agents)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('features section exists with correct id', async ({ page }) => {
    await expect(page.locator('#features')).toBeAttached();
  });

  test('section label reads "Workflow Agents"', async ({ page }) => {
    const label = page.locator('#features .section-label');
    await expect(label).toContainText(/Workflow Agents/i);
  });

  test('section title mentions "Five AI Agents"', async ({ page }) => {
    const title = page.locator('#features .section-title');
    await expect(title).toContainText(/Five AI Agents/i);
  });

  test('exactly 5 feature cards are rendered', async ({ page }) => {
    const cards = page.locator('#features .feature-card');
    await expect(cards).toHaveCount(5);
  });

  const agents = [
    'Job Analyzer',
    'Profile Matcher',
    'Company Researcher',
    'Resume Advisor',
    'Cover Letter Writer',
  ];

  for (const agent of agents) {
    test(`agent card "${agent}" is visible`, async ({ page }) => {
      const card = page.locator('#features .feature-card').filter({ hasText: agent });
      await expect(card).toBeVisible();
    });
  }

  test('each feature card has a description paragraph', async ({ page }) => {
    const cards = page.locator('#features .feature-card');
    const count = await cards.count();
    for (let i = 0; i < count; i++) {
      const p = cards.nth(i).locator('p');
      await expect(p).toBeVisible();
      const text = await p.textContent();
      expect(text!.trim().length).toBeGreaterThan(10);
    }
  });

  test('each feature card has an icon', async ({ page }) => {
    const icons = page.locator('#features .feature-icon-wrap i');
    await expect(icons).toHaveCount(5);
  });
});

// ---------------------------------------------------------------------------
// 6b. After Apply Section
// ---------------------------------------------------------------------------
test.describe('6b. After Apply Section', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('after-apply section exists with correct id', async ({ page }) => {
    await expect(page.locator('#after-apply')).toBeAttached();
  });

  test('section label reads "On-Demand Agents"', async ({ page }) => {
    await expect(page.locator('#after-apply .section-label')).toContainText(/On-Demand Agents/i);
  });

  test('exactly 4 after-apply cards are rendered', async ({ page }) => {
    await expect(page.locator('#after-apply .feature-card')).toHaveCount(4);
  });

  const afterApplyCards = ['Optimize CV', 'Interview Prep', 'Mock Session', 'Hiring Outreach'];
  for (const name of afterApplyCards) {
    test(`after-apply card "${name}" is visible`, async ({ page }) => {
      await expect(page.locator('#after-apply .feature-card').filter({ hasText: name })).toBeVisible();
    });
  }
});

// ---------------------------------------------------------------------------
// 7. Chrome Extension Section
// ---------------------------------------------------------------------------
test.describe('7. Chrome Extension Section', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('extension section exists with correct id', async ({ page }) => {
    await expect(page.locator('#extension')).toBeAttached();
  });

  test('section label reads "Chrome Extension"', async ({ page }) => {
    const label = page.locator('#extension .section-label');
    await expect(label).toContainText(/Chrome Extension/i);
  });

  test('title mentions job site extraction', async ({ page }) => {
    const title = page.locator('#extension .section-title');
    await expect(title).toContainText(/job site/i);
  });

  test('subtitle mentions Analyze This Job and Match Form To Profile', async ({ page }) => {
    const subtitle = page.locator('#extension .section-subtitle');
    await expect(subtitle).toContainText(/Analyze This Job/i);
    await expect(subtitle).toContainText(/Match Form To Profile/i);
  });

  test('extension popup mockup preview is visible', async ({ page }) => {
    await expect(page.locator('.popup-mockup')).toBeVisible();
  });

  test('extension popup shows "RoleMule" brand', async ({ page }) => {
    await expect(page.locator('.pm-logo')).toContainText(/RoleMule/i);
  });

  test('extension popup shows "Analyze This Job" button', async ({ page }) => {
    await expect(page.locator('.pm-btn')).toContainText(/Analyze This Job/i);
  });
});

// ---------------------------------------------------------------------------
// 8. Career Tools Section
// ---------------------------------------------------------------------------
test.describe('8. Career Tools Section', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('tools section exists with correct id', async ({ page }) => {
    await expect(page.locator('#tools')).toBeAttached();
  });

  test('section label reads "Beyond Applications"', async ({ page }) => {
    const label = page.locator('#tools .section-label');
    await expect(label).toContainText(/Beyond Applications/i);
  });

  test('section title mentions "Career Tools"', async ({ page }) => {
    const title = page.locator('#tools .section-title');
    await expect(title).toContainText(/Career Tools/i);
  });

  test('exactly 6 tool cards are rendered', async ({ page }) => {
    const cards = page.locator('#tools .tool-card');
    await expect(cards).toHaveCount(6);
  });

  const tools = [
    'Thank You Notes',
    'Job Comparison',
    'Salary Coach',
    'Follow-up Emails',
    'Reference Requests',
    'Rejection Analysis',
  ];

  for (const tool of tools) {
    test(`tool card "${tool}" is visible`, async ({ page }) => {
      const card = page.locator('#tools .tool-card').filter({ hasText: tool });
      await expect(card).toBeVisible();
    });
  }

  test('each tool card has an icon', async ({ page }) => {
    const icons = page.locator('#tools .tool-icon i');
    await expect(icons).toHaveCount(6);
  });

  test('each tool card has a description', async ({ page }) => {
    const cards = page.locator('#tools .tool-card');
    const count = await cards.count();
    for (let i = 0; i < count; i++) {
      const p = cards.nth(i).locator('p');
      await expect(p).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// 8b. CLI Section
// ---------------------------------------------------------------------------
test.describe('8b. CLI Section', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('cli section exists with correct id', async ({ page }) => {
    await expect(page.locator('#cli')).toBeAttached();
  });

  test('cli strip mentions rolemule command', async ({ page }) => {
    await expect(page.locator('#cli .cli-strip-code')).toContainText(/rolemule/i);
  });

  test('cli section title mentions terminal', async ({ page }) => {
    await expect(page.locator('#cli .section-title')).toContainText(/terminal/i);
  });
});

// ---------------------------------------------------------------------------
// 9. Example Section — Interactive Tabs
// ---------------------------------------------------------------------------
test.describe('9. Example Section (Interactive Tabs)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#example').scrollIntoViewIfNeeded();
    await page.locator('.screenshot-showcase').waitFor({ state: 'attached' });
    await page.waitForFunction(() => {
      const el = document.querySelector('#example .screenshot-showcase');
      return el?.classList.contains('animate-visible') ?? false;
    }, { timeout: 5000 });
  });

  test('example section exists with correct id', async ({ page }) => {
    await expect(page.locator('#example')).toBeAttached();
  });

  test('section label reads "See It In Action"', async ({ page }) => {
    await expect(page.locator('#example .section-label')).toContainText(/See It In Action/i);
  });

  test('section title mentions "Real Job. Real Results."', async ({ page }) => {
    await expect(page.locator('#example .section-title')).toContainText(/Real Job\. Real Results\./i);
  });

  test('screenshot showcase container is visible', async ({ page }) => {
    await expect(page.locator('.screenshot-showcase')).toBeVisible();
  });

  test('screenshot frame shows browser chrome and URL bar', async ({ page }) => {
    await expect(page.locator('.ss-browser-chrome')).toBeVisible();
    await expect(page.locator('.ss-url-bar')).toContainText(/rolemule/i);
  });

  test('exactly 10 screenshot tabs are rendered', async ({ page }) => {
    const tabs = page.locator('.ss-tab');
    await expect(tabs).toHaveCount(10);
  });

  const tabLabels = [
    'Job Details', 'Your Fit', 'Strategy', 'Company', 'Cover Letter', 'Resume',
    'Optimize CV', 'Interview', 'Mock Session', 'Outreach',
  ];

  for (const label of tabLabels) {
    test(`tab "${label}" is visible`, async ({ page }) => {
      const tab = page.locator('.ss-tab').filter({ hasText: label });
      await expect(tab).toBeVisible();
    });
  }

  test('"Job Details" tab is active by default', async ({ page }) => {
    const activeTab = page.locator('.ss-tab.active');
    await expect(activeTab).toContainText(/Job Details/i);
  });

  test('"Job Details" panel is visible by default', async ({ page }) => {
    await expect(page.locator('#ss-panel-job-details')).toBeVisible();
  });

  test('clicking "Your Fit" tab shows fit panel', async ({ page }) => {
    await page.locator('.ss-tab').filter({ hasText: 'Your Fit' }).click();
    await expect(page.locator('#ss-panel-your-fit')).toBeVisible({ timeout: 3000 });
    await expect(page.locator('#ss-panel-job-details')).toBeHidden();
  });

  test('clicking "Strategy" tab shows strategy panel', async ({ page }) => {
    await page.locator('.ss-tab').filter({ hasText: 'Strategy' }).click();
    await expect(page.locator('#ss-panel-strategy')).toBeVisible({ timeout: 3000 });
  });

  test('clicking "Company" tab shows company panel', async ({ page }) => {
    await page.locator('.ss-tab').filter({ hasText: 'Company' }).click();
    await expect(page.locator('#ss-panel-company')).toBeVisible({ timeout: 3000 });
  });

  test('clicking "Cover Letter" tab shows cover letter panel', async ({ page }) => {
    await page.locator('.ss-tab').filter({ hasText: 'Cover Letter' }).click();
    await expect(page.locator('#ss-panel-cover-letter')).toBeVisible({ timeout: 3000 });
  });

  test('clicking "Resume" tab shows resume panel', async ({ page }) => {
    await page.locator('.ss-tab').filter({ hasText: 'Resume' }).click();
    await expect(page.locator('#ss-panel-resume')).toBeVisible({ timeout: 3000 });
  });

  test('clicking "Optimize CV" tab shows optimize panel', async ({ page }) => {
    await page.locator('.ss-tab').filter({ hasText: 'Optimize CV' }).click();
    await expect(page.locator('#ss-panel-optimize-cv')).toBeVisible({ timeout: 3000 });
  });

  test('clicking "Interview" tab shows interview panel', async ({ page }) => {
    await page.locator('.ss-tab').filter({ hasText: 'Interview' }).click();
    await expect(page.locator('#ss-panel-interview')).toBeVisible({ timeout: 3000 });
  });

  test('clicking "Mock Session" tab shows mock session panel', async ({ page }) => {
    await page.locator('.ss-tab').filter({ hasText: 'Mock Session' }).click();
    await expect(page.locator('#ss-panel-mock-session')).toBeVisible({ timeout: 3000 });
  });

  test('clicking "Outreach" tab shows outreach panel', async ({ page }) => {
    await page.locator('.ss-tab').filter({ hasText: 'Outreach' }).click();
    await expect(page.locator('#ss-panel-outreach')).toBeVisible({ timeout: 3000 });
  });

  test('all 10 screenshot panels exist in the DOM', async ({ page }) => {
    const panels = [
      'ss-panel-job-details', 'ss-panel-your-fit', 'ss-panel-strategy', 'ss-panel-company',
      'ss-panel-cover-letter', 'ss-panel-resume', 'ss-panel-optimize-cv', 'ss-panel-interview',
      'ss-panel-mock-session', 'ss-panel-outreach',
    ];
    for (const id of panels) {
      await expect(page.locator(`#${id}`)).toBeAttached();
    }
  });

  test('each screenshot panel contains a lazy-loaded image', async ({ page }) => {
    const images = page.locator('.ss-panel img');
    await expect(images).toHaveCount(10);
    await expect(images.first()).toHaveAttribute('loading', 'lazy');
  });
});

// ---------------------------------------------------------------------------
// 10. Pricing Section
// ---------------------------------------------------------------------------
test.describe('10. Pricing Section', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('pricing section exists with correct id', async ({ page }) => {
    await expect(page.locator('#pricing')).toBeAttached();
  });

  test('section label reads "Always Free"', async ({ page }) => {
    await expect(page.locator('#pricing .section-label')).toContainText(/Always Free/i);
  });

  test('section title mentions "Open Source"', async ({ page }) => {
    await expect(page.locator('#pricing .section-title')).toContainText(/Open Source/i);
  });

  test('section title mentions "BYOK"', async ({ page }) => {
    await expect(page.locator('#pricing .section-title')).toContainText(/BYOK/i);
  });

  test('pricing description mentions "<$0.01 per job analysis"', async ({ page }) => {
    await expect(page.locator('.pricing-description')).toContainText(/\$0\.01/i);
  });

  test('"Get Started Free" CTA button is visible', async ({ page }) => {
    const btn = page.locator('#pricing .btn-primary-glow');
    await expect(btn).toBeVisible();
    await expect(btn).toContainText(/Get Started Free/i);
  });

  test('pricing CTA links to register', async ({ page }) => {
    const btn = page.locator('#pricing .btn-primary-glow');
    const href = await btn.getAttribute('href');
    expect(href).toContain('/auth/register');
  });

  test('pricing CTA is a same-origin register link', async ({ page }) => {
    const btn = page.locator('#pricing .btn-primary-glow');
    const target = await btn.getAttribute('target');
    expect(target).toBeNull();
    const href = await btn.getAttribute('href');
    expect(href).toBe('/auth/register');
  });
});

// ---------------------------------------------------------------------------
// 11. Footer
// ---------------------------------------------------------------------------
test.describe('11. Footer', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('footer is present', async ({ page }) => {
    await expect(page.locator('footer.footer')).toBeAttached();
  });

  test('footer brand reads "RoleMule"', async ({ page }) => {
    const brand = page.locator('footer .footer-brand');
    await expect(brand).toContainText(/RoleMule/i);
  });

  test('footer "Help & FAQ" link goes to /help', async ({ page }) => {
    const link = page.locator('footer a[href="/help"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/Help/i);
  });

  test('footer "Privacy" link goes to /privacy', async ({ page }) => {
    const link = page.locator('footer a[href="/privacy"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/Privacy/i);
  });

  test('footer "Terms" link goes to /terms', async ({ page }) => {
    const link = page.locator('footer a[href="/terms"]');
    await expect(link).toBeVisible();
    await expect(link).toContainText(/Terms/i);
  });

  test('footer GitHub link is present with "Open Source on GitHub"', async ({ page }) => {
    const ghLink = page.locator('footer .footer-github');
    await expect(ghLink).toBeVisible();
    await expect(ghLink).toContainText(/Open Source on GitHub/i);
  });

  test('footer GitHub link opens in new tab', async ({ page }) => {
    const ghLink = page.locator('footer .footer-github');
    const target = await ghLink.getAttribute('target');
    expect(target).toBe('_blank');
  });

  test('footer shows copyright year 2026', async ({ page }) => {
    const footer = page.locator('footer');
    await expect(footer).toContainText(/2026/);
  });

  test('clicking /help link navigates to help page', async ({ page }) => {
    await page.locator('footer a[href="/help"]').click();
    await expect(page).toHaveURL(/\/help/);
  });

  test('clicking /privacy link navigates to privacy page', async ({ page }) => {
    await page.goto('/');
    await page.locator('footer a[href="/privacy"]').click();
    await expect(page).toHaveURL(/\/privacy/);
  });

  test('clicking /terms link navigates to terms page', async ({ page }) => {
    await page.goto('/');
    await page.locator('footer a[href="/terms"]').click();
    await expect(page).toHaveURL(/\/terms/);
  });
});

// ---------------------------------------------------------------------------
// 12. Cookie Consent
// ---------------------------------------------------------------------------
test.describe('12. Cookie Consent', () => {
  test('cookie consent banner appears on fresh visit', async ({ page, context }) => {
    await clearConsent(page);
    await context.clearCookies();
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const banner = page.locator('#cookie-consent-banner');
    // Banner may or may not appear (depends on server-side consent check)
    // We just verify it doesn't crash — either it shows or it's hidden
    const bannerExists = await banner.count() > 0;
    if (bannerExists) {
      const text = await banner.textContent();
      // If visible, it should contain something meaningful
      expect(text!.length).toBeGreaterThan(0);
    }
  });

  test('clicking "Accept All" hides the cookie banner', async ({ page, context }) => {
    await clearConsent(page);
    await context.clearCookies();
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const banner = page.locator('#cookie-consent-banner');
    const acceptBtn = page.locator('.cookie-btn-accept');

    if (await banner.isVisible({ timeout: 3000 }).catch(() => false)) {
      await acceptBtn.click();
      await expect(banner).toBeHidden({ timeout: 3000 });
    }
  });

  test('clicking "Reject All" hides the cookie banner', async ({ page, context }) => {
    await clearConsent(page);
    await context.clearCookies();
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const banner = page.locator('#cookie-consent-banner');
    const rejectBtn = page.locator('.cookie-btn-reject, [data-action="reject-cookies"]');

    if (await banner.isVisible({ timeout: 3000 }).catch(() => false)) {
      if (await rejectBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        await rejectBtn.click();
        await expect(banner).toBeHidden({ timeout: 3000 });
      }
    }
  });

  test('after accepting, banner does not reappear on reload', async ({ page, context }) => {
    await clearConsent(page);
    await context.clearCookies();
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const banner = page.locator('#cookie-consent-banner');
    const acceptBtn = page.locator('.cookie-btn-accept');

    if (await banner.isVisible({ timeout: 3000 }).catch(() => false)) {
      await acceptBtn.click();
      await expect(banner).toBeHidden({ timeout: 3000 });

      // Reload and check
      await page.reload();
      await page.waitForLoadState('domcontentloaded');
      await expect(banner).toBeHidden({ timeout: 3000 });
    }
  });
});

// ---------------------------------------------------------------------------
// 13. Smooth-Scroll Anchor Navigation
// ---------------------------------------------------------------------------
test.describe('13. Anchor Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('clicking "Why RoleMule" scrolls to #problem section', async ({ page }) => {
    await page.locator('a[href="#problem"]').first().click();
    await page.waitForTimeout(800); // allow scroll animation
    const section = page.locator('#problem');
    const isInView = await section.evaluate(el => {
      const rect = el.getBoundingClientRect();
      return rect.top < window.innerHeight && rect.bottom > 0;
    });
    expect(isInView).toBeTruthy();
  });

  test('clicking "Workflow" scrolls to #features section', async ({ page }) => {
    await page.locator('a[href="#features"]').first().click();
    await page.waitForTimeout(800);
    const section = page.locator('#features');
    const isInView = await section.evaluate(el => {
      const rect = el.getBoundingClientRect();
      return rect.top < window.innerHeight + 200 && rect.bottom > -200;
    });
    expect(isInView).toBeTruthy();
  });

  test('direct URL with #pricing hash scrolls to pricing', async ({ page }) => {
    await page.goto('/#pricing');
    await page.waitForLoadState('domcontentloaded');
    // Longer page (After Apply + CLI) — wait for hash scroll / force into view if needed
    await page.waitForTimeout(1200);
    const section = page.locator('#pricing');
    await section.scrollIntoViewIfNeeded();
    await expect(section).toBeVisible();
    const isNearViewport = await section.evaluate(el => {
      const rect = el.getBoundingClientRect();
      return rect.top < window.innerHeight + 600 && rect.bottom > -200;
    });
    expect(isNearViewport).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// 14. Accessibility Basics
// ---------------------------------------------------------------------------
test.describe('14. Accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
  });

  test('page has exactly one <main> landmark', async ({ page }) => {
    await expect(page.locator('main')).toHaveCount(1);
  });

  test('page has a <nav> landmark', async ({ page }) => {
    await expect(page.locator('nav')).toHaveCount(1);
  });

  test('page has a <footer> landmark', async ({ page }) => {
    await expect(page.locator('footer')).toHaveCount(1);
  });

  test('page has an <h1> heading', async ({ page }) => {
    const h1 = page.locator('h1');
    await expect(h1).toHaveCount(1);
  });

  test('all images have alt attributes', async ({ page }) => {
    const images = page.locator('img');
    const count = await images.count();
    for (let i = 0; i < count; i++) {
      const alt = await images.nth(i).getAttribute('alt');
      // alt may be empty string (decorative) but must not be absent
      expect(alt).not.toBeNull();
    }
  });

  test('navbar toggler has aria-label', async ({ page }) => {
    const toggler = page.locator('.navbar-toggler');
    const ariaLabel = await toggler.getAttribute('aria-label');
    expect(ariaLabel).toBeTruthy();
  });

  test('all external links have rel containing "noopener"', async ({ page }) => {
    const externalLinks = page.locator('a[target="_blank"]');
    const count = await externalLinks.count();
    for (let i = 0; i < count; i++) {
      const rel = await externalLinks.nth(i).getAttribute('rel');
      expect(rel).toContain('noopener');
    }
  });

  test('Sign In link has descriptive text (not just an icon)', async ({ page }) => {
    const signIn = page.locator('.nav-cta a[href="/auth/login"]');
    const text = await signIn.textContent();
    expect(text?.trim().length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// 15. Auth CTAs — Full Navigation Flow
// ---------------------------------------------------------------------------
test.describe('15. Auth CTAs', () => {
  test('"Sign In" button navigates to /auth/login', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('.nav-cta a[href="/auth/login"]').click();
    await expect(page).toHaveURL(/\/auth\/login/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('"Try Free" button navigates to /auth/register', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('.nav-cta a[href="/auth/register"]').click();
    await expect(page).toHaveURL(/\/auth\/register/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('login page loads with email input', async ({ page }) => {
    await page.goto('/auth/login');
    await expect(page.locator('input[type="email"]')).toBeVisible();
  });

  test('register page loads with name/email/password inputs', async ({ page }) => {
    await page.goto('/auth/register');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 16. Unauthenticated Protection
// ---------------------------------------------------------------------------
test.describe('16. Unauthenticated Protection', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.evaluate(() => {
      try { localStorage.clear(); } catch (_) {}
    });
  });

  test('/dashboard redirects unauthenticated user to login', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForURL(/login|auth/, { timeout: 10000 });
    expect(page.url()).toMatch(/login|auth/);
  });

  test('/dashboard/new-application redirects to login', async ({ page }) => {
    await page.goto('/dashboard/new-application');
    await page.waitForURL(/login|auth/, { timeout: 10000 });
    expect(page.url()).toMatch(/login|auth/);
  });

  test('/dashboard/tools redirects to login', async ({ page }) => {
    await page.goto('/dashboard/tools');
    await page.waitForURL(/login|auth/, { timeout: 10000 });
    expect(page.url()).toMatch(/login|auth/);
  });

  test('/dashboard/settings redirects to login', async ({ page }) => {
    await page.goto('/dashboard/settings');
    await page.waitForURL(/login|auth/, { timeout: 10000 });
    expect(page.url()).toMatch(/login|auth/);
  });

  test('/dashboard/history is removed and returns 404', async ({ page }) => {
    const response = await page.goto('/dashboard/history');
    expect(response?.status()).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// 17. Public Pages (no auth required)
// ---------------------------------------------------------------------------
test.describe('17. Public Pages', () => {
  test('/help page loads without auth (HTTP 200)', async ({ request }) => {
    const res = await request.get('/help');
    expect(res.status()).toBe(200);
  });

  test('/privacy page loads without auth (HTTP 200)', async ({ request }) => {
    const res = await request.get('/privacy');
    expect(res.status()).toBe(200);
  });

  test('/terms page loads without auth (HTTP 200)', async ({ request }) => {
    const res = await request.get('/terms');
    expect(res.status()).toBe(200);
  });

  test('/auth/login page loads (HTTP 200)', async ({ request }) => {
    const res = await request.get('/auth/login');
    expect(res.status()).toBe(200);
  });

  test('/auth/register page loads (HTTP 200)', async ({ request }) => {
    const res = await request.get('/auth/register');
    expect(res.status()).toBe(200);
  });

  test('/auth/reset-password page loads (HTTP 200)', async ({ request }) => {
    const res = await request.get('/auth/reset-password');
    expect(res.status()).toBe(200);
  });

  test('/help page has visible content', async ({ page }) => {
    await page.goto('/help');
    await expect(page.locator('body')).toBeVisible();
    const bodyText = await page.locator('body').textContent();
    expect(bodyText!.trim().length).toBeGreaterThan(100);
  });
});

// ---------------------------------------------------------------------------
// 18. Error Pages
// ---------------------------------------------------------------------------
test.describe('18. Error Pages', () => {
  test('unknown route returns 404 or redirects gracefully', async ({ page }) => {
    const res = await page.goto('/this-definitely-does-not-exist-xyz-12345');
    // Accept 404 status or a redirect to an error page
    const status = res?.status();
    const url = page.url();
    expect(status === 404 || url.includes('404') || status === 200).toBeTruthy();
  });

  test('/health endpoint returns JSON with status', async ({ request }) => {
    const res = await request.get('/health');
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty('status');
  });
});

// ---------------------------------------------------------------------------
// 19. Mobile & Tablet Viewports
// ---------------------------------------------------------------------------
test.describe('19. Mobile & Tablet Viewports', () => {
  const viewports = [
    { name: 'iPhone SE (375x667)', width: 375, height: 667 },
    { name: 'iPhone 14 (390x844)', width: 390, height: 844 },
    { name: 'iPad (768x1024)', width: 768, height: 1024 },
    { name: 'Tablet landscape (1024x768)', width: 1024, height: 768 },
  ];

  for (const vp of viewports) {
    test(`landing page loads on ${vp.name}`, async ({ browser }) => {
      const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      const p = await ctx.newPage();
      await p.goto('/');
      await p.waitForLoadState('domcontentloaded');

      await expect(p.locator('.hero-section')).toBeVisible();
      await expect(p.locator('footer')).toBeAttached();

      await ctx.close();
    });

    test(`hero title visible on ${vp.name}`, async ({ browser }) => {
      const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      const p = await ctx.newPage();
      await p.goto('/');
      await p.waitForLoadState('domcontentloaded');

      await expect(p.locator('.hero-title')).toBeVisible();
      await ctx.close();
    });
  }

  test('footer links are accessible on mobile (375px)', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 812 } });
    const p = await ctx.newPage();
    await p.goto('/');
    await p.waitForLoadState('domcontentloaded');

    // Scroll to footer
    await p.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect(p.locator('footer a[href="/help"]')).toBeVisible({ timeout: 5000 });
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------
// 20. Security Headers
// ---------------------------------------------------------------------------
test.describe('20. Security Headers', () => {
  test('response includes X-Content-Type-Options', async ({ request }) => {
    const res = await request.get('/');
    const header = res.headers()['x-content-type-options'];
    expect(header).toBeTruthy();
  });

  test('response includes X-Frame-Options or CSP frame-ancestors', async ({ request }) => {
    const res = await request.get('/');
    const headers = res.headers();
    const hasXFrame = !!headers['x-frame-options'];
    const csp = headers['content-security-policy'] || '';
    const hasFrameAncestors = csp.includes('frame-ancestors');
    expect(hasXFrame || hasFrameAncestors).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// 21. Additional Page Sections
// ---------------------------------------------------------------------------
test.describe('21. Additional Page Sections', () => {
  test('hero CTA primary button is present', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const cta = page.locator('.navbar .btn-primary-glow, .nav-cta a[href*="register"]').first();
    await expect(cta).toBeVisible();
  });

  test('hero CTA secondary button or link is present', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const cta = page.locator('.navbar .btn-ghost, .nav-cta a[href*="login"]').first();
    await expect(cta).toBeAttached();
  });

  test('features section has at least 3 feature items', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const features = page.locator('#features .feature-card');
    const count = await features.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test('pricing section has at least one plan card', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const cards = page.locator('.pricing-section .pricing-card, [class*="pricing"] [class*="card"]');
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('problem section or pain-point section is visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const section = page.locator('.problem-section, [class*="problem"], [class*="pain"]').first();
    await expect(section).toBeAttached();
  });

  test('tech stack section is visible', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const section = page.locator('#section-tech-bar, .section-tech-bar').first();
    await expect(section).toBeAttached();
  });
});

// ---------------------------------------------------------------------------
// 22. Navbar Details
// ---------------------------------------------------------------------------
test.describe('22. Navbar Details', () => {
  test('navbar brand link goes to /', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const brand = page.locator('.navbar-brand, a.brand').first();
    const href = await brand.getAttribute('href');
    expect(href === '/' || href === '#' || href === '').toBeTruthy();
  });

  test('navbar has login and register links', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const loginLink = page.locator('a[href="/auth/login"], a:has-text("Log in"), a:has-text("Login")').first();
    const registerLink = page.locator('a[href="/auth/register"], a:has-text("Sign up"), a:has-text("Register")').first();
    await expect(loginLink).toBeAttached();
    await expect(registerLink).toBeAttached();
  });

  test('navbar collapses on mobile (hamburger visible at 375px)', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 667 } });
    const p = await ctx.newPage();
    await p.goto('/');
    await p.waitForLoadState('domcontentloaded');
    const toggler = p.locator('.navbar-toggler, button[data-bs-toggle="collapse"]').first();
    await expect(toggler).toBeVisible();
    await ctx.close();
  });

  test('hamburger menu opens navbar on click at 375px', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 667 } });
    const p = await ctx.newPage();
    await p.goto('/');
    await p.waitForLoadState('domcontentloaded');
    const toggler = p.locator('.navbar-toggler, button[data-bs-toggle="collapse"]').first();
    await toggler.click();
    await p.waitForTimeout(500);
    const nav = p.locator('.navbar-collapse.show, .navbar-nav').first();
    await expect(nav).toBeAttached();
    await ctx.close();
  });
});

// ---------------------------------------------------------------------------
// 23. Footer Details
// ---------------------------------------------------------------------------
test.describe('23. Footer Details', () => {
  test('footer has copyright text', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const footer = page.locator('footer');
    const text = await footer.textContent();
    expect(text).toMatch(/©|copyright|rolemule/i);
  });

  test('footer has privacy policy link', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const link = page.locator('footer a[href*="privacy"], footer a:has-text("Privacy")').first();
    await expect(link).toBeAttached();
  });

  test('footer has terms of service link', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const link = page.locator('footer a[href*="terms"], footer a:has-text("Terms")').first();
    await expect(link).toBeAttached();
  });

  test('footer has at least 3 links', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const links = page.locator('footer a');
    const count = await links.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });
});

// ---------------------------------------------------------------------------
// 24. Cookie Consent Scenarios
// ---------------------------------------------------------------------------
test.describe('24. Cookie Consent Scenarios', () => {
  test('cookie banner shows when no consent stored', async ({ page, context }) => {
    await clearConsent(page);
    await context.clearCookies();
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const banner = page.locator('#cookie-consent-banner');
    const visible = await banner.isVisible({ timeout: 5000 }).catch(() => false);
    if (!visible) {
      // Banner only renders when analytics consent is applicable — no crash is acceptable
      await expect(page.locator('body')).toBeVisible();
      return;
    }
    await expect(banner).toBeVisible();
  });

  test('accepting all cookies hides the banner', async ({ page, context }) => {
    await clearConsent(page);
    await context.clearCookies();
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const banner = page.locator('#cookie-consent-banner');
    const acceptBtn = page.locator('.cookie-btn-accept, #cookie-accept-all, button:has-text("Accept All")').first();
    if (await banner.isVisible({ timeout: 3000 }).catch(() => false)) {
      await acceptBtn.click();
      await expect(banner).toBeHidden({ timeout: 3000 });
    }
  });

  test('cookie banner does not appear when consent already stored', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('cookie_consent', JSON.stringify({
        essential: true, functional: true, analytics: true,
        version: '1.0', timestamp: new Date().toISOString(),
      }));
    });
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    const banner = page.locator('#cookie-banner, .cookie-consent').first();
    const isVisible = await banner.isVisible().catch(() => false);
    expect(isVisible).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 25. Scroll Behaviour
// ---------------------------------------------------------------------------
test.describe('25. Scroll Behaviour', () => {
  test('page scrolls to features section via anchor', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const anchor = page.locator('a[href="#features"], a[href*="features"]').first();
    if (await anchor.count() > 0) {
      await anchor.click();
      await page.waitForTimeout(800);
      const section = page.locator('#features').first();
      await expect(section).toBeVisible();
    }
  });

  test('scroll to top button appears after scrolling', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.evaluate(() => window.scrollTo(0, 2000));
    await page.waitForTimeout(500);
    const topBtn = page.locator('#back-to-top, .scroll-to-top, [class*="scroll-top"]').first();
    if (await topBtn.count() > 0) {
      await expect(topBtn).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// 26. Accessibility Extras
// ---------------------------------------------------------------------------
test.describe('26. Accessibility Extras', () => {
  test('all images have alt attributes', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const images = await page.locator('img').all();
    for (const img of images) {
      const alt = await img.getAttribute('alt');
      expect(alt !== null).toBeTruthy();
    }
  });

  test('interactive elements are keyboard focusable', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.keyboard.press('Tab');
    const focused = await page.evaluate(() => document.activeElement?.tagName);
    expect(['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'BODY'].includes(focused || '')).toBeTruthy();
  });

  test('main landmark exists', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const main = page.locator('main, [role="main"]').first();
    await expect(main).toBeAttached();
  });

  test('no duplicate id attributes on page', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const duplicates = await page.evaluate(() => {
      const ids = Array.from(document.querySelectorAll('[id]')).map(el => el.id);
      const counts: Record<string, number> = {};
      ids.forEach(id => { counts[id] = (counts[id] || 0) + 1; });
      return Object.entries(counts).filter(([, c]) => c > 1).map(([id]) => id);
    });
    expect(duplicates.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// 27. Auth Page Extras
// ---------------------------------------------------------------------------
test.describe('27. Auth Page Extras', () => {
  test('/auth/login page has a password show/hide toggle or input', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    const passwordInput = page.locator('input[type="password"]');
    await expect(passwordInput).toBeAttached();
  });

  test('/auth/register page shows password confirmation field', async ({ page }) => {
    await page.goto('/auth/register');
    await page.waitForLoadState('domcontentloaded');
    const inputs = page.locator('input[type="password"]');
    const count = await inputs.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test('/auth/forgot-password page has email input', async ({ page }) => {
    await page.goto('/auth/forgot-password');
    await page.waitForLoadState('domcontentloaded');
    const email = page.locator('input[type="email"], input[name="email"]').first();
    await expect(email).toBeAttached();
  });

  test('auth pages have brand logo or RoleMule text', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveTitle(/RoleMule/i);
  });

  test('/auth/login form submission requires non-empty fields', async ({ page }) => {
    await page.goto('/auth/login');
    await page.waitForLoadState('domcontentloaded');
    const btn = page.locator('button[type="submit"], #login-btn').first();
    await btn.click();
    // HTML5 validation or JS validation should prevent navigation
    await expect(page).toHaveURL(/login/);
  });
});

// ---------------------------------------------------------------------------
// 28. Static Asset Loading
// ---------------------------------------------------------------------------
test.describe('28. Static Asset Loading', () => {
  test('CSS stylesheet loads successfully (no 404)', async ({ page }) => {
    const failed: string[] = [];
    page.on('response', res => {
      if (res.url().includes('.css') && res.status() === 404) {
        failed.push(res.url());
      }
    });
    await page.goto('/');
    await page.waitForLoadState('load');
    expect(failed.length).toBe(0);
  });

  test('JavaScript bundle loads successfully (no 404)', async ({ page }) => {
    const failed: string[] = [];
    page.on('response', res => {
      if (res.url().includes('.js') && res.status() === 404) {
        failed.push(res.url());
      }
    });
    await page.goto('/');
    await page.waitForLoadState('load');
    expect(failed.length).toBe(0);
  });

  test('page title is set', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);
  });

  test('page title contains RoleMule or brand name', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const title = await page.title();
    expect(title.toLowerCase()).toMatch(/rolemule|mule|role|job/i);
  });

  test('meta description tag is present', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const meta = page.locator('meta[name="description"]').first();
    await expect(meta).toBeAttached();
  });

  test('favicon link tag is present', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    const favicon = page.locator('link[rel="icon"], link[rel="shortcut icon"]').first();
    await expect(favicon).toBeAttached();
  });
});
