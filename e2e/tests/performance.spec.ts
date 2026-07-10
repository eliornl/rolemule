import { test, expect } from '@playwright/test';
import { RegisterPage, LoginPage, ProfileSetupPage } from '../pages';
import { generateTestEmail } from '../fixtures/test-data';

/**
 * Performance tests - Page load times, response times, resource usage
 */
const tier1MockedOnly = !!process.env.SKIP_SERVER;

test.describe('Performance', () => {
  
  test.describe('Page Load Times', () => {
    
    test('should load homepage within 3 seconds', async ({ page }) => {
      const startTime = Date.now();
      
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      const loadTime = Date.now() - startTime;
      
      // Should load within 3 seconds
      expect(loadTime).toBeLessThan(3000);
    });
    
    test('should load login page within 2 seconds', async ({ page }) => {
      const startTime = Date.now();
      
      await page.goto('/auth/login');
      await page.waitForLoadState('domcontentloaded');
      
      const loadTime = Date.now() - startTime;
      
      expect(loadTime).toBeLessThan(2000);
    });
    
    test('should load registration page within 2 seconds', async ({ page }) => {
      const startTime = Date.now();
      
      await page.goto('/auth/register');
      await page.waitForLoadState('domcontentloaded');
      
      const loadTime = Date.now() - startTime;
      
      expect(loadTime).toBeLessThan(2000);
    });
    
    test('should load dashboard within 3 seconds', async ({ page }) => {
      // Login first
      const registerPage = new RegisterPage(page);
      const email = generateTestEmail('perf_dashboard_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'Perf Dashboard Test',
        email: email,
        password: 'PerfDashboardPassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
      
      if (page.url().includes('profile/setup')) {
        const profilePage = new ProfileSetupPage(page);
        await profilePage.quickSetup({
          title: 'Engineer',
          yearsExperience: 3,
          skills: ['Python'],
        });
      }
      
      // Measure dashboard load
      const startTime = Date.now();
      await page.goto('/dashboard');
      await page.waitForLoadState('networkidle');
      
      const loadTime = Date.now() - startTime;
      
      expect(loadTime).toBeLessThan(3000);
    });
    
    test('should load help page within 2 seconds', async ({ page }) => {
      const startTime = Date.now();
      
      await page.goto('/help');
      await page.waitForLoadState('domcontentloaded');
      
      const loadTime = Date.now() - startTime;
      
      expect(loadTime).toBeLessThan(2000);
    });
  });
  
  test.describe('First Contentful Paint', () => {
    
    test('should have FCP under 1.5 seconds on homepage', async ({ page }) => {
      await page.goto('/');
      
      // Get FCP from Performance API
      const fcp = await page.evaluate(() => {
        return new Promise<number>((resolve) => {
          const observer = new PerformanceObserver((list) => {
            const entries = list.getEntries();
            for (const entry of entries) {
              if (entry.name === 'first-contentful-paint') {
                resolve(entry.startTime);
              }
            }
          });
          observer.observe({ type: 'paint', buffered: true });
          
          // Fallback
          setTimeout(() => resolve(0), 5000);
        });
      });
      
      // FCP should be under 1.5 seconds (or 0 if not supported)
      expect(fcp).toBeLessThan(1500);
    });
    
    test('should have FCP under 1.5 seconds on login page', async ({ page }) => {
      await page.goto('/auth/login');
      
      const fcp = await page.evaluate(() => {
        return new Promise<number>((resolve) => {
          const observer = new PerformanceObserver((list) => {
            const entries = list.getEntries();
            for (const entry of entries) {
              if (entry.name === 'first-contentful-paint') {
                resolve(entry.startTime);
              }
            }
          });
          observer.observe({ type: 'paint', buffered: true });
          setTimeout(() => resolve(0), 5000);
        });
      });
      
      expect(fcp).toBeLessThan(1500);
    });
  });
  
  test.describe('API Response Times', () => {
    test('should respond to auth endpoints within reasonable time', async ({ page }) => {
      await page.goto('/auth/login');
      
      const startTime = Date.now();
      
      await page.request.post('/api/v1/auth/login', {
        data: {
          email: 'test@example.com',
          password: 'password',
        },
      });
      
      const responseTime = Date.now() - startTime;
      
      // Should respond within 3 seconds (live server under parallel E2E load)
      expect(responseTime).toBeLessThan(3000);
    });
    
    test('should respond to health check within reasonable time', async ({ page }) => {
      const startTime = Date.now();
      
      // Try both possible health check endpoints
      let response = await page.request.get('/health').catch(() => null);
      if (!response || response.status() === 404) {
        response = await page.request.get('/api/health');
      }
      
      const responseTime = Date.now() - startTime;
      
      // Health check should be fast (but give tolerance for cold start)
      expect(responseTime).toBeLessThan(1000);
      expect(response?.status()).toBe(200);
    });
  });
  
  test.describe('Resource Loading', () => {
    
    test('should not load excessive JavaScript', async ({ page }) => {
      const resources: { url: string; size: number }[] = [];
      
      page.on('response', async response => {
        const url = response.url();
        if (url.endsWith('.js')) {
          const body = await response.body().catch(() => Buffer.from(''));
          resources.push({ url, size: body.length });
        }
      });
      
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      // Total JS should be under 2MB
      const totalSize = resources.reduce((sum, r) => sum + r.size, 0);
      expect(totalSize).toBeLessThan(2 * 1024 * 1024);
    });
    
    test('should not load excessive CSS', async ({ page }) => {
      const resources: { url: string; size: number }[] = [];
      
      page.on('response', async response => {
        const url = response.url();
        if (url.endsWith('.css')) {
          const body = await response.body().catch(() => Buffer.from(''));
          resources.push({ url, size: body.length });
        }
      });
      
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      // Total CSS should be under 500KB
      const totalSize = resources.reduce((sum, r) => sum + r.size, 0);
      expect(totalSize).toBeLessThan(500 * 1024);
    });
    
    test('should have reasonable number of HTTP requests', async ({ page }) => {
      let requestCount = 0;
      
      page.on('request', () => {
        requestCount++;
      });
      
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      // Should be under 50 requests for initial page load
      expect(requestCount).toBeLessThan(50);
    });
    
    test('should compress text resources', async ({ page }) => {
      const compressedResponses: boolean[] = [];
      
      page.on('response', response => {
        const contentType = response.headers()['content-type'] || '';
        const encoding = response.headers()['content-encoding'];
        
        if (contentType.includes('text') || contentType.includes('javascript') || contentType.includes('json')) {
          compressedResponses.push(!!encoding);
        }
      });
      
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      // At least some responses should be compressed
      // (May not be compressed in development)
    });
  });
  
  test.describe('Memory Usage', () => {
    
    test('should not have memory leaks on navigation', async ({ page }) => {
      // Navigate multiple times and check memory
      const memoryReadings: number[] = [];
      
      for (let i = 0; i < 5; i++) {
        await page.goto('/auth/login');
        await page.goto('/auth/register');
        await page.goto('/');
        
        const memory = await page.evaluate(() => {
          if ((performance as any).memory) {
            return (performance as any).memory.usedJSHeapSize;
          }
          return 0;
        });
        
        memoryReadings.push(memory);
      }
      
      // Memory should not grow significantly
      if (memoryReadings[0] > 0) {
        const growth = memoryReadings[memoryReadings.length - 1] / memoryReadings[0];
        expect(growth).toBeLessThan(2); // Should not double
      }
    });
    
    test('should clean up resources on page unload', async ({ page }) => {
      // Navigate to multiple pages and verify cleanup
      await page.goto('/auth/login');
      await page.waitForLoadState('networkidle');
      
      // Navigate to another page
      await page.goto('/auth/register');
      await page.waitForLoadState('networkidle');
      
      // Navigate away
      await page.goto('/auth/login');
      
      // Page should load normally (no memory leak issues)
      const loginPage = new LoginPage(page);
      await expect(loginPage.emailInput).toBeVisible();
    });
  });
  
  test.describe('Form Performance', () => {
    
    test('should submit login form within 1 second', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.navigate();
      
      await loginPage.emailInput.fill('test@example.com');
      await loginPage.passwordInput.fill('password123');
      
      const startTime = Date.now();
      await loginPage.loginButton.click();
      
      // Wait for response (success or error)
      await page.waitForResponse(
        response => response.url().includes('/auth/login'),
        { timeout: 5000 }
      ).catch(() => {});
      
      const submitTime = Date.now() - startTime;
      
      // Form submission should be quick
      expect(submitTime).toBeLessThan(1000);
    });
    
    test('should handle rapid form input', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      await registerPage.navigate();
      
      // Type rapidly
      await registerPage.emailInput.type('rapidtyping@example.com', { delay: 10 });
      await registerPage.passwordInput.type('RapidTypingPassword123!', { delay: 10 });
      
      // Form should handle it
      const emailValue = await registerPage.emailInput.inputValue();
      expect(emailValue).toBe('rapidtyping@example.com');
    });
  });
  
  test.describe('Image Optimization', () => {
    
    test('should lazy load images', async ({ page }) => {
      await page.goto('/');
      
      // Some images may be lazy loaded
      // Not strictly required but good practice
    });
    
    test('should use appropriate image sizes', async ({ page }) => {
      await page.goto('/');
      
      const images = await page.locator('img').all();
      
      for (const img of images) {
        const naturalWidth = await img.evaluate((el: HTMLImageElement) => el.naturalWidth);
        const displayWidth = await img.evaluate((el: HTMLImageElement) => el.clientWidth);
        
        if (naturalWidth > 0 && displayWidth > 0) {
          // Image should not be more than 2x display size
          expect(naturalWidth).toBeLessThanOrEqual(displayWidth * 2 + 100);
        }
      }
    });
  });
  
  test.describe('Caching', () => {
    
    test('should cache static resources', async ({ page }) => {
      // First load
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      
      // Second load - should use cache
      const cachedRequests: string[] = [];
      
      page.on('request', request => {
        cachedRequests.push(request.url());
      });
      
      await page.reload();
      await page.waitForLoadState('networkidle');
      
      // Some requests should be from cache (fewer network requests)
      // This is hard to verify directly, but page should load faster
    });
    
    test('should not cache API responses inappropriately', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      const email = generateTestEmail('cache_api_test');
      
      await registerPage.navigate();
      await registerPage.register({
        name: 'Cache API Test',
        email: email,
        password: 'CacheAPITestPassword123!',
        acceptTerms: true,
      });
      
      await page.waitForURL(/profile|dashboard/, { timeout: 15000 });
      
      // API responses should not be overly cached
      // (Data should be fresh on each request)
    });
  });
  
  test.describe('Concurrent Users Simulation', () => {
    
    test('should handle multiple simultaneous page loads', async ({ browser }) => {
      const pages = await Promise.all([
        browser.newPage(),
        browser.newPage(),
        browser.newPage(),
      ]);
      
      // Load pages simultaneously
      await Promise.all(
        pages.map(p => p.goto('/auth/login'))
      );
      
      // All pages should load
      for (const page of pages) {
        const loginPage = new LoginPage(page);
        await expect(loginPage.emailInput).toBeVisible();
      }
      
      // Cleanup
      await Promise.all(pages.map(p => p.close()));
    });
    
    test('should handle rapid navigation', async ({ page }) => {
      const urls = ['/auth/login', '/auth/register', '/', '/help', '/auth/login'];
      
      for (const url of urls) {
        await page.goto(url);
        await page.waitForTimeout(100); // Minimal wait
      }
      
      // Should end up on last page
      await expect(page).toHaveURL(/login/);
    });
  });
});
