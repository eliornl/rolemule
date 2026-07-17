import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for RoleMule E2E tests.
 * 
 * Run all tests: npx playwright test
 * Run specific file: npx playwright test e2e/tests/auth.spec.ts
 * Run in UI mode: npx playwright test --ui
 * Run headed: npx playwright test --headed
 * Debug: npx playwright test --debug
 * 
 * CI/CD Optimizations:
 * - Smoke tests: SMOKE=1 npx playwright test (runs ~30 critical tests in ~3 min)
 * - Full suite with sharding: npx playwright test --shard=1/4
 * - Parallel workers enabled in CI for speed
 */

// Determine if running smoke tests only
const isSmoke = !!process.env.SMOKE;
const isCI = !!process.env.CI;
const isMockedE2E = !!(process.env.SKIP_SERVER || process.env.SMOKE);

export default defineConfig({
  // Test directory
  testDir: './tests',
  
  // Output directory for test artifacts
  outputDir: './test-results',
  
  // Run tests in parallel
  fullyParallel: true,
  
  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: isCI,
  
  // Retry failed tests - fewer retries in smoke mode for speed
  retries: isSmoke ? 0 : (isCI ? 1 : 1),
  
  // Workers: Playwright tests are I/O bound, so we can use more workers than CPUs
  // GitHub Actions: use 10 workers (tests wait on network/DB, not CPU)
  // Local: use 6 workers (balance between speed and resource usage)
  workers: isSmoke ? 4 : (isMockedE2E ? (isCI ? 10 : 6) : (isCI ? 4 : 3)),
  
  // Reporter configuration - minimal in CI smoke for speed
  reporter: isSmoke 
    ? [['list'], ...(isCI ? [['github'] as const] : [])]
    : [
        ['html', { outputFolder: './playwright-report' }],
        ['list'],
        ...(isCI ? [['github'] as const] : []),
      ],
  
  // Global test timeout - live-server profile setup needs more than 20s under load
  timeout: isSmoke ? 45000 : 30000,
  
  // Expect timeout
  expect: {
    timeout: isSmoke ? 3000 : 5000,
  },
  
  // Shared settings for all projects
  use: {
    // Base URL for the application
    baseURL: process.env.BASE_URL || 'http://localhost:8000',
    
    // No trace in CI (expensive) - only when debugging locally
    trace: process.env.DEBUG ? 'on' : 'off',
    
    // Screenshots only on failure, skip in smoke for speed
    screenshot: isSmoke ? 'off' : 'only-on-failure',
    
    // No video in CI (very expensive)
    video: process.env.DEBUG ? 'on-first-retry' : 'off',
    
    // Browser context options
    viewport: { width: 1280, height: 720 },
    
    // Ignore HTTPS errors for local development
    ignoreHTTPSErrors: true,
    
    // Action timeout - shorter for smoke
    actionTimeout: isSmoke ? 5000 : 10000,
    
    // Navigation timeout - shorter for smoke
    navigationTimeout: isSmoke ? 10000 : 15000,
  },
  
  // Configure projects for different browsers
  projects: [
    // Setup project - runs before all tests to create auth state
    {
      name: 'setup',
      testDir: '.',
      testMatch: /global\.setup\.ts/,
    },
    
    // Desktop Chrome (primary)
    {
      name: 'chromium',
      use: { 
        ...devices['Desktop Chrome'],
      },
      dependencies: ['setup'],
    },
    
    // Desktop Firefox
    {
      name: 'firefox',
      use: { 
        ...devices['Desktop Firefox'],
      },
      dependencies: ['setup'],
    },
    
    // Desktop Safari
    {
      name: 'webkit',
      use: { 
        ...devices['Desktop Safari'],
      },
      dependencies: ['setup'],
    },
    
    // Mobile Chrome
    {
      name: 'mobile-chrome',
      use: { 
        ...devices['Pixel 5'],
      },
      dependencies: ['setup'],
    },
    
    // Mobile Safari
    {
      name: 'mobile-safari',
      use: { 
        ...devices['iPhone 12'],
      },
      dependencies: ['setup'],
    },
    
    // Extension tests (no server needed)
    {
      name: 'extension',
      testMatch: /extension\.spec\.ts/,
      use: { 
        ...devices['Desktop Chrome'],
      },
      // No dependencies - doesn't need setup or server
    },
  ],
  
  // Web server configuration - start app before tests
  // Set to undefined to skip auto-start (use running server)
  webServer: process.env.SKIP_SERVER ? undefined : {
    command: 'cd .. && uvicorn main:app --host 0.0.0.0 --port 8000',
    url: 'http://localhost:8000/health',
    // Default: start a dedicated server with TESTING=true. Reuse only when explicitly
    // requested (dev server must also be started with TESTING=true / make start-local).
    reuseExistingServer: !!process.env.REUSE_DEV_SERVER,
    timeout: 120000,
    env: {
      DATABASE_URL: process.env.DATABASE_URL ?? 'postgresql+asyncpg://applypilot:applypilot@localhost:5432/applypilot',
      REDIS_URL: process.env.REDIS_URL ?? 'redis://localhost:6379/0',
      TESTING: 'true',
      DEBUG: 'true',
      DISABLE_EMAIL_VERIFICATION: 'true',
      ALLOWED_HOSTS: 'localhost,127.0.0.1',
      CORS_ORIGINS: 'http://localhost:8000',
      ...(process.env.JWT_SECRET ? { JWT_SECRET: process.env.JWT_SECRET } : {}),
      ...(process.env.ENCRYPTION_KEY ? { ENCRYPTION_KEY: process.env.ENCRYPTION_KEY } : {}),
    },
  },
});
