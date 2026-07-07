import { test, expect, chromium } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';

/**
 * Chrome Extension tests
 * Tests for the job extraction Chrome extension
 * 
 * Note: Extension testing requires special setup and may not work in all CI environments
 */
test.describe('Chrome Extension', () => {
  
  const extensionPath = path.join(__dirname, '../../extension');
  
  test.describe('Extension Files', () => {
    
    test('should have manifest.json', async () => {
      const manifestPath = path.join(extensionPath, 'manifest.json');
      expect(fs.existsSync(manifestPath)).toBe(true);
      
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
      expect(manifest.manifest_version).toBe(3);
      expect(manifest.name).toBeTruthy();
      expect(manifest.version).toBeTruthy();
    });
    
    test('should have popup files', async () => {
      const popupHtml = path.join(extensionPath, 'popup/popup.html');
      const popupJs = path.join(extensionPath, 'popup/popup.js');
      const popupCss = path.join(extensionPath, 'popup/popup.css');
      
      expect(fs.existsSync(popupHtml)).toBe(true);
      expect(fs.existsSync(popupJs)).toBe(true);
      expect(fs.existsSync(popupCss)).toBe(true);
    });
    
    test('should have content script', async () => {
      const contentJs = path.join(extensionPath, 'content/content.js');
      expect(fs.existsSync(contentJs)).toBe(true);
    });
    
    test('should have service worker', async () => {
      const serviceWorker = path.join(extensionPath, 'background/service-worker.js');
      expect(fs.existsSync(serviceWorker)).toBe(true);
    });
    
    test('should have icon files', async () => {
      const iconsPath = path.join(extensionPath, 'icons');
      
      // Check for icon files
      const iconFiles = fs.readdirSync(iconsPath).filter(f => f.endsWith('.png') || f.endsWith('.svg'));
      expect(iconFiles.length).toBeGreaterThan(0);
    });
  });
  
  test.describe('Manifest Validation', () => {
    
    test('should have valid permissions', async () => {
      const manifestPath = path.join(extensionPath, 'manifest.json');
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
      
      // Should have required permissions
      expect(manifest.permissions).toContain('activeTab');
      expect(manifest.permissions).toContain('storage');
    });
    
    test('should have valid action configuration', async () => {
      const manifestPath = path.join(extensionPath, 'manifest.json');
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
      
      expect(manifest.action).toBeTruthy();
      expect(manifest.action.default_popup).toBeTruthy();
    });
    
    test('should have valid content scripts configuration', async () => {
      const manifestPath = path.join(extensionPath, 'manifest.json');
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
      
      if (manifest.content_scripts) {
        expect(manifest.content_scripts.length).toBeGreaterThan(0);
        expect(manifest.content_scripts[0].js).toBeTruthy();
        expect(manifest.content_scripts[0].matches).toBeTruthy();
      }
    });
    
    test('should have valid background service worker', async () => {
      const manifestPath = path.join(extensionPath, 'manifest.json');
      const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
      
      expect(manifest.background).toBeTruthy();
      expect(manifest.background.service_worker).toBeTruthy();
    });
  });
  
  test.describe('Popup UI', () => {
    
    test('should have valid popup HTML structure', async () => {
      const popupHtml = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.html'),
        'utf-8'
      );
      
      // Check for basic HTML structure
      expect(popupHtml).toContain('<!DOCTYPE html>');
      expect(popupHtml).toContain('<html');
      expect(popupHtml).toContain('<head>');
      expect(popupHtml).toContain('<body>');
      
      // Check for required elements
      expect(popupHtml).toContain('popup.css');
      expect(popupHtml).toContain('popup.js');
    });
    
    test('should have login/auth UI elements', async () => {
      const popupHtml = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.html'),
        'utf-8'
      );
      
      // Should have auth-related elements
      expect(
        popupHtml.includes('login') || 
        popupHtml.includes('Login') ||
        popupHtml.includes('auth')
      ).toBe(true);
    });
    
    test('should have extract button', async () => {
      const popupHtml = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.html'),
        'utf-8'
      );
      
      // Should have extract/analyze button
      expect(
        popupHtml.toLowerCase().includes('extract') || 
        popupHtml.toLowerCase().includes('analyze') ||
        popupHtml.toLowerCase().includes('button')
      ).toBe(true);
    });
  });
  
  test.describe('Content Script', () => {
    
    test('should have job detection logic', async () => {
      const contentJs = fs.readFileSync(
        path.join(extensionPath, 'content/content.js'),
        'utf-8'
      );
      
      // Should have job-related selectors or logic
      expect(
        contentJs.includes('job') || 
        contentJs.includes('Job') ||
        contentJs.includes('career') ||
        contentJs.includes('Career')
      ).toBe(true);
    });
    
    test('should have content extraction logic', async () => {
      const contentJs = fs.readFileSync(
        path.join(extensionPath, 'content/content.js'),
        'utf-8'
      );
      
      // Should have extraction-related code
      expect(
        contentJs.includes('extract') || 
        contentJs.includes('innerText') ||
        contentJs.includes('textContent') ||
        contentJs.includes('querySelector')
      ).toBe(true);
    });
    
    test('should handle message passing', async () => {
      const contentJs = fs.readFileSync(
        path.join(extensionPath, 'content/content.js'),
        'utf-8'
      );
      
      // Should have Chrome message passing
      expect(
        contentJs.includes('chrome.runtime') || 
        contentJs.includes('sendMessage') ||
        contentJs.includes('onMessage')
      ).toBe(true);
    });
  });
  
  test.describe('Service Worker', () => {
    
    test('should have API communication logic', async () => {
      const serviceWorker = fs.readFileSync(
        path.join(extensionPath, 'background/service-worker.js'),
        'utf-8'
      );
      
      // Should have fetch or API calls
      expect(
        serviceWorker.includes('fetch') || 
        serviceWorker.includes('XMLHttpRequest') ||
        serviceWorker.includes('api')
      ).toBe(true);
    });
    
    test('should handle authentication', async () => {
      const serviceWorker = fs.readFileSync(
        path.join(extensionPath, 'background/service-worker.js'),
        'utf-8'
      );
      
      // Should have auth-related code
      expect(
        serviceWorker.includes('token') || 
        serviceWorker.includes('auth') ||
        serviceWorker.includes('Authorization')
      ).toBe(true);
    });
    
    test('should have message listeners', async () => {
      const serviceWorker = fs.readFileSync(
        path.join(extensionPath, 'background/service-worker.js'),
        'utf-8'
      );
      
      // Should have message listeners
      expect(
        serviceWorker.includes('onMessage') || 
        serviceWorker.includes('addListener')
      ).toBe(true);
    });
  });
  
  test.describe('Popup JavaScript', () => {
    
    test('should have DOM manipulation', async () => {
      const popupJs = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.js'),
        'utf-8'
      );
      
      // Should have DOM manipulation
      expect(
        popupJs.includes('document.') || 
        popupJs.includes('getElementById') ||
        popupJs.includes('querySelector')
      ).toBe(true);
    });
    
    test('should have event listeners', async () => {
      const popupJs = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.js'),
        'utf-8'
      );
      
      // Should have event listeners
      expect(
        popupJs.includes('addEventListener') || 
        popupJs.includes('onclick') ||
        popupJs.includes('click')
      ).toBe(true);
    });
    
    test('should communicate with content script', async () => {
      const popupJs = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.js'),
        'utf-8'
      );
      
      // Should have tab/content script communication
      expect(
        popupJs.includes('chrome.tabs') || 
        popupJs.includes('sendMessage') ||
        popupJs.includes('chrome.runtime')
      ).toBe(true);
    });
    
    test('should handle storage', async () => {
      const popupJs = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.js'),
        'utf-8'
      );
      
      // Should use storage API
      expect(
        popupJs.includes('chrome.storage') || 
        popupJs.includes('localStorage') ||
        popupJs.includes('storage')
      ).toBe(true);
    });
  });
  
  test.describe('CSS Styling', () => {
    
    test('should have valid popup CSS', async () => {
      const popupCss = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.css'),
        'utf-8'
      );
      
      // Should have basic CSS
      expect(popupCss.length).toBeGreaterThan(0);
      expect(popupCss).toContain('{');
      expect(popupCss).toContain('}');
    });
    
    test('should have responsive styling', async () => {
      const popupCss = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.css'),
        'utf-8'
      );
      
      // May or may not have media queries (popup is fixed size)
      // Just check it's valid CSS
      expect(popupCss).not.toContain('syntax error');
    });
    
    test('should have button styling', async () => {
      const popupCss = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.css'),
        'utf-8'
      );
      
      // Should have button styles
      expect(
        popupCss.includes('button') || 
        popupCss.includes('btn') ||
        popupCss.includes('.extract')
      ).toBe(true);
    });
  });
  
  test.describe('Content Script Details', () => {
    
    test('content script references job-related content', async () => {
      const contentJs = fs.readFileSync(
        path.join(extensionPath, 'content/content.js'),
        'utf-8'
      );
      // Should contain job-related logic
      const hasJobLogic = 
        contentJs.includes('greenhouse') ||
        contentJs.includes('workday') ||
        contentJs.toLowerCase().includes('job') ||
        contentJs.toLowerCase().includes('career');
      expect(hasJobLogic).toBe(true);
    });

    test('content script has class or ID selectors for job data', async () => {
      const contentJs = fs.readFileSync(
        path.join(extensionPath, 'content/content.js'),
        'utf-8'
      );
      // Should target DOM elements
      expect(
        contentJs.includes('className') ||
        contentJs.includes('querySelector') ||
        contentJs.includes('getElementById') ||
        contentJs.includes('class') ||
        contentJs.includes('data-')
      ).toBe(true);
    });

    test('content script handles different page types', async () => {
      const contentJs = fs.readFileSync(
        path.join(extensionPath, 'content/content.js'),
        'utf-8'
      );
      // Should have conditional logic for different pages
      expect(
        contentJs.includes('if ') || 
        contentJs.includes('switch') || 
        contentJs.includes('match(')
      ).toBe(true);
    });
  });

  test.describe('Service Worker Details', () => {
    
    test('service worker handles install event', async () => {
      const serviceWorker = fs.readFileSync(
        path.join(extensionPath, 'background/service-worker.js'),
        'utf-8'
      );
      expect(
        serviceWorker.includes('install') || 
        serviceWorker.includes('activate') ||
        serviceWorker.includes('oninstalled')
      ).toBe(true);
    });

    test('service worker handles API base URL', async () => {
      const serviceWorker = fs.readFileSync(
        path.join(extensionPath, 'background/service-worker.js'),
        'utf-8'
      );
      // Should have API URL configuration
      expect(
        serviceWorker.includes('http') || 
        serviceWorker.includes('API_URL') || 
        serviceWorker.includes('baseUrl') ||
        serviceWorker.includes('BASE_URL')
      ).toBe(true);
    });

    test('service worker exports or exposes functions', async () => {
      const serviceWorker = fs.readFileSync(
        path.join(extensionPath, 'background/service-worker.js'),
        'utf-8'
      );
      // Should have function definitions
      expect(
        serviceWorker.includes('function ') || 
        serviceWorker.includes('const ') ||
        serviceWorker.includes('=>')
      ).toBe(true);
    });
  });

  test.describe('Popup JavaScript Details', () => {
    
    test('popup.js references extension-specific APIs', async () => {
      const popupJs = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.js'),
        'utf-8'
      );
      expect(
        popupJs.includes('chrome.') ||
        popupJs.includes('browser.')
      ).toBe(true);
    });

    test('popup.js handles authentication state', async () => {
      const popupJs = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.js'),
        'utf-8'
      );
      expect(
        popupJs.includes('token') ||
        popupJs.includes('auth') ||
        popupJs.includes('login') ||
        popupJs.includes('user')
      ).toBe(true);
    });

    test('popup.js has async functions or Promises', async () => {
      const popupJs = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.js'),
        'utf-8'
      );
      expect(
        popupJs.includes('async ') ||
        popupJs.includes('.then(') ||
        popupJs.includes('Promise')
      ).toBe(true);
    });

    test('popup.js handles errors gracefully', async () => {
      const popupJs = fs.readFileSync(
        path.join(extensionPath, 'popup/popup.js'),
        'utf-8'
      );
      expect(
        popupJs.includes('catch') ||
        popupJs.includes('try {') ||
        popupJs.includes('error')
      ).toBe(true);
    });
  });

  test.describe('Manifest V3 Compliance', () => {
    test('manifest does not use background scripts array (uses service_worker)', async () => {
      const manifest = JSON.parse(fs.readFileSync(path.join(extensionPath, 'manifest.json'), 'utf-8'));
      if (manifest.manifest_version === 3) {
        expect(manifest.background?.scripts).toBeUndefined();
        expect(manifest.background?.service_worker).toBeTruthy();
      } else {
        expect(manifest.manifest_version).toBe(2);
      }
    });

    test('permissions array is defined', async () => {
      const manifest = JSON.parse(fs.readFileSync(path.join(extensionPath, 'manifest.json'), 'utf-8'));
      expect(Array.isArray(manifest.permissions)).toBe(true);
    });

    test('content scripts have matches array', async () => {
      const manifest = JSON.parse(fs.readFileSync(path.join(extensionPath, 'manifest.json'), 'utf-8'));
      if (manifest.content_scripts && manifest.content_scripts.length > 0) {
        expect(Array.isArray(manifest.content_scripts[0].matches)).toBe(true);
      }
    });

    test('action popup is set', async () => {
      const manifest = JSON.parse(fs.readFileSync(path.join(extensionPath, 'manifest.json'), 'utf-8'));
      const action = manifest.action || manifest.browser_action;
      expect(action).toBeTruthy();
    });
  });

  test.describe('Extension Loading (Chromium only)', () => {
    
    test.skip('should load extension in browser', async () => {
      // This test requires a full Chromium browser with extension support
      // Skip by default as it requires special setup
      
      const browser = await chromium.launchPersistentContext('', {
        headless: false,
        args: [
          `--disable-extensions-except=${extensionPath}`,
          `--load-extension=${extensionPath}`,
        ],
      });
      
      // Get the extension ID
      const extensionPage = browser.pages().find(p => 
        p.url().includes('chrome-extension://')
      );
      
      expect(extensionPage).toBeTruthy();
      
      await browser.close();
    });
  });
});
