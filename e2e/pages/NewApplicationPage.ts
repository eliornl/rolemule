import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * New Application page object (job analysis workflow)
 */
export class NewApplicationPage extends BasePage {
  readonly url = '/dashboard/new-application';
  
  // Step 1 - Basic Info
  readonly jobTitleInput: Locator;
  readonly companyNameInput: Locator;
  readonly nextStepButton: Locator;
  
  // Step 2 - Input methods
  readonly urlInput: Locator;
  readonly textInput: Locator;
  readonly fileInput: Locator;
  
  // Tabs/toggle
  readonly urlTab: Locator;
  readonly textTab: Locator;
  readonly fileTab: Locator;
  
  // Actions
  readonly analyzeButton: Locator;
  readonly clearButton: Locator;
  
  // Progress
  readonly progressBar: Locator;
  readonly progressStatus: Locator;
  readonly agentStatus: Locator;
  readonly currentAgent: Locator;
  
  // Results
  readonly resultsSection: Locator;
  readonly matchScore: Locator;
  readonly jobTitle: Locator;
  readonly companyName: Locator;
  readonly coverLetterSection: Locator;
  readonly resumeAdviceSection: Locator;
  
  // Actions on results
  readonly viewDetailsButton: Locator;
  readonly copyButton: Locator;
  readonly downloadButton: Locator;
  readonly interviewPrepButton: Locator;
  
  constructor(page: Page) {
    super(page);
    
    // Step 1 - Basic Info
    this.jobTitleInput = page.locator('#jobTitleInput, #jobTitle, input[placeholder*="Job title"], input[placeholder*="Job Title"]');
    this.companyNameInput = page.locator('#companyNameInput, #companyName, input[placeholder*="Company"]');
    this.nextStepButton = page.locator('button:has-text("Next")');
    
    // Step 2 - Input methods
    this.urlInput = page.locator('#jobUrl');
    this.textInput = page.locator('#jobDescription');
    this.fileInput = page.locator('input[type="file"]');
    
    // Tabs (buttons that switch between input methods)
    this.urlTab = page.locator('.method-tab:has-text("URL"), button[onclick*="switchTab(\'url\')"]');
    this.textTab = page.locator('.method-tab:has-text("Manual"), .method-tab:has-text("Paste"), button[onclick*="switchTab(\'manual\')"]');
    this.fileTab = page.locator('.method-tab:has-text("File"), .method-tab:has-text("Upload"), button[onclick*="switchTab(\'file\')"]');
    
    // Actions
    this.analyzeButton = page.locator('button:has-text("Create Application"), button[onclick*="processApplication"], button:has-text("Analyze")');
    this.clearButton = page.locator('button:has-text("Clear"), button:has-text("Reset")');
    
    // Progress
    this.progressBar = page.locator('.progress-bar, .progress, [role="progressbar"]');
    this.progressStatus = page.locator('.progress-status, .status-message, [class*="status"]');
    this.agentStatus = page.locator('.agent-status, .workflow-status');
    this.currentAgent = page.locator('.current-agent, .active-agent');
    
    // Results
    this.resultsSection = page.locator('.results-section, .analysis-results, [class*="result"]');
    this.matchScore = page.locator('.match-score, .fit-score, [class*="score"]');
    this.jobTitle = page.locator('.job-title, [class*="title"]');
    this.companyName = page.locator('.company-name, [class*="company"]');
    this.coverLetterSection = page.locator('.cover-letter, [class*="cover-letter"]');
    this.resumeAdviceSection = page.locator('.resume-advice, [class*="resume"]');
    
    // Actions on results
    this.viewDetailsButton = page.locator('button:has-text("View Details"), button:has-text("View")');
    this.copyButton = page.locator('button:has-text("Copy"), .copy-btn');
    this.downloadButton = page.locator('button:has-text("Download"), .download-btn');
    this.interviewPrepButton = page.locator('button:has-text("Interview"), a:has-text("Interview")');
  }
  
  /**
   * Navigate to new application page
   */
  async navigate() {
    await this.goto(this.url);
    await this.waitForPageLoad();
  }
  
  /**
   * Complete Step 1 (Basic Info) and proceed to Step 2
   */
  async completeStep1(jobTitle: string = 'Software Engineer', companyName: string = 'Test Company') {
    if (await this.jobTitleInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await this.jobTitleInput.fill(jobTitle);
    }
    if (await this.companyNameInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await this.companyNameInput.fill(companyName);
    }
  }
  
  /**
   * Switch to URL input tab
   */
  async selectUrlInput() {
    // Try clicking the URL tab
    if (await this.urlTab.isVisible().catch(() => false)) {
      await this.urlTab.click();
    }
    await expect(this.urlInput).toBeVisible({ timeout: 5000 });
  }
  
  /**
   * Switch to text input tab
   */
  async selectTextInput() {
    // Try clicking the manual/text tab
    if (await this.textTab.isVisible().catch(() => false)) {
      await this.textTab.click();
      await this.page.waitForTimeout(300);
    }
    await expect(this.textInput).toBeVisible({ timeout: 5000 });
  }
  
  /**
   * Switch to file input tab
   */
  async selectFileInput() {
    if (await this.fileTab.isVisible().catch(() => false)) {
      await this.fileTab.click();
    }
    await expect(this.fileInput).toBeVisible({ timeout: 5000 });
  }
  
  /**
   * Submit job URL for analysis
   */
  async analyzeByUrl(url: string) {
    await this.selectUrlInput();
    await this.fillField(this.urlInput, url);
    await this.analyzeButton.click();
  }
  
  /**
   * Submit job text for analysis
   */
  async analyzeByText(text: string) {
    await this.selectTextInput();
    await this.fillField(this.textInput, text);
    await this.analyzeButton.click();
  }
  
  /**
   * Submit job file for analysis
   */
  async analyzeByFile(filePath: string) {
    await this.selectFileInput();
    await this.fileInput.setInputFiles(filePath);
    await this.analyzeButton.click();
  }
  
  /**
   * Wait for workflow to complete
   */
  async waitForCompletion(timeout: number = 120000) {
    // Wait for results to appear or error
    await expect(
      this.resultsSection.or(this.matchScore).or(this.page.locator('.error, .workflow-error'))
    ).toBeVisible({ timeout });
  }
  
  /**
   * Wait for specific agent to complete
   */
  async waitForAgent(agentName: string, timeout: number = 60000) {
    const completedAgent = this.page.locator(`[class*="completed"]:has-text("${agentName}")`);
    await expect(completedAgent).toBeVisible({ timeout });
  }
  
  /**
   * Get match score value
   */
  async getMatchScore(): Promise<number> {
    const scoreText = await this.matchScore.textContent();
    const match = scoreText?.match(/(\d+)/);
    return match ? parseInt(match[0]) : 0;
  }
  
  /**
   * Get current workflow status
   */
  async getStatus(): Promise<string> {
    return (await this.progressStatus.textContent()) || '';
  }
  
  /**
   * Get progress percentage
   */
  async getProgress(): Promise<number> {
    const style = await this.progressBar.getAttribute('style');
    const ariaValue = await this.progressBar.getAttribute('aria-valuenow');
    
    if (ariaValue) return parseInt(ariaValue);
    
    const widthMatch = style?.match(/width:\s*(\d+)/);
    return widthMatch ? parseInt(widthMatch[1]) : 0;
  }
  
  /**
   * Check if workflow completed successfully
   */
  async isCompleted(): Promise<boolean> {
    try {
      return await this.resultsSection.isVisible({ timeout: 5000 }) || 
             await this.matchScore.isVisible({ timeout: 5000 });
    } catch {
      return false;
    }
  }
  
  /**
   * Check if workflow failed
   */
  async hasFailed(): Promise<boolean> {
    return await this.page.locator('.error, .workflow-error, .failed').isVisible({ timeout: 2000 });
  }
  
  /**
   * Copy cover letter to clipboard
   */
  async copyCoverLetter() {
    await this.coverLetterSection.locator('.copy-btn, button:has-text("Copy")').click();
    await this.expectNotification('copied', 'success');
  }
  
  /**
   * Go to interview prep
   */
  async goToInterviewPrep() {
    await this.interviewPrepButton.click();
    await this.waitForURL(/interview-prep/);
  }
  
  /**
   * Full workflow test - analyze and wait for results
   */
  async analyzeJobAndWait(jobText: string, timeout: number = 120000): Promise<{
    matchScore: number;
    completed: boolean;
  }> {
    await this.analyzeByText(jobText);
    await this.waitForCompletion(timeout);
    
    const completed = await this.isCompleted();
    const matchScore = completed ? await this.getMatchScore() : 0;
    
    return { matchScore, completed };
  }
}
