/**
 * @smoke Job Finder CTA is present on the dashboard (mocked auth).
 */
import { test, expect } from '@playwright/test';
import { setupAuth, setupAllMocks } from '../utils/api-mocks';

test.describe('Job Finder @smoke', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await setupAllMocks(page);
  });

  test('dashboard shows Find jobs action', async ({ page }) => {
    await page.goto('/dashboard');
    const link = page.locator('a[href="/dashboard/find-jobs"]');
    await expect(link.first()).toBeVisible({ timeout: 15000 });
  });
});
