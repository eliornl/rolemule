import { Page, Locator } from '@playwright/test';
import { BasePage } from './BasePage';

/**
 * Career Tools page object
 */
export class ToolsPage extends BasePage {
  readonly url = '/dashboard/tools';
  
  // Tool tabs - use nav-link class which is the actual element
  readonly thankYouTab: Locator;
  readonly rejectionTab: Locator;
  readonly referenceTab: Locator;
  readonly comparisonTab: Locator;
  readonly followUpTab: Locator;
  readonly salaryTab: Locator;
  
  // Tool sections
  readonly thankYouSection: Locator;
  readonly rejectionSection: Locator;
  readonly referenceSection: Locator;
  readonly comparisonSection: Locator;
  readonly followupSection: Locator;
  readonly salarySection: Locator;
  
  // Common elements
  readonly generateButton: Locator;
  readonly outputSection: Locator;
  readonly copyButton: Locator;
  readonly loadingIndicator: Locator;
  readonly loadingOverlay: Locator;
  readonly errorMessage: Locator;
  readonly alertContainer: Locator;
  
  // Thank You form
  readonly interviewerNameInput: Locator;
  readonly interviewTypeSelect: Locator;
  readonly companyNameInput: Locator;
  readonly jobTitleInput: Locator;
  readonly discussionPointsInput: Locator;
  readonly thankYouOutput: Locator;
  
  // Rejection form
  readonly rejectionEmailInput: Locator;
  readonly interviewStageSelect: Locator;
  readonly rejectionOutput: Locator;
  
  // Reference form
  readonly referenceNameInput: Locator;
  readonly relationshipSelect: Locator;
  readonly targetJobInput: Locator;
  readonly targetCompanyInput: Locator;
  readonly referenceOutput: Locator;
  
  // Job comparison form
  readonly addJobButton: Locator;
  readonly jobInputs: Locator;
  readonly job1TitleInput: Locator;
  readonly job1CompanyInput: Locator;
  readonly job2TitleInput: Locator;
  readonly job2CompanyInput: Locator;
  readonly comparisonOutput: Locator;
  
  // Follow-up form
  readonly followUpStageSelect: Locator;
  readonly contactNameInput: Locator;
  readonly daysSinceContactInput: Locator;
  readonly followupCompanyInput: Locator;
  readonly followupJobTitleInput: Locator;
  readonly followupOutput: Locator;
  
  // Salary coach form
  readonly currentSalaryInput: Locator;
  readonly offeredSalaryInput: Locator;
  readonly experienceInput: Locator;
  readonly achievementsInput: Locator;
  readonly salaryJobTitleInput: Locator;
  readonly salaryCompanyInput: Locator;
  readonly salaryOutput: Locator;
  
  constructor(page: Page) {
    super(page);
    
    // Tabs - match the actual nav links in the HTML
    this.thankYouTab = page.locator('.nav-link:has-text("Thank You")');
    this.rejectionTab = page.locator('.nav-link:has-text("Rejection")');
    this.referenceTab = page.locator('.nav-link:has-text("Reference")');
    this.comparisonTab = page.locator('.nav-link:has-text("Compare")');
    this.followUpTab = page.locator('.nav-link:has-text("Follow")');
    this.salaryTab = page.locator('.nav-link:has-text("Salary")');
    
    // Tool sections by ID
    this.thankYouSection = page.locator('#thankYouSection');
    this.rejectionSection = page.locator('#rejectionSection');
    this.referenceSection = page.locator('#referenceSection');
    this.comparisonSection = page.locator('#comparisonSection');
    this.followupSection = page.locator('#followupSection');
    this.salarySection = page.locator('#salarySection');
    
    // Common
    this.generateButton = page.locator('.tool-section.active button[type="submit"]');
    this.outputSection = page.locator('.output-card:visible');
    this.copyButton = page.locator('.copy-btn:visible');
    this.loadingIndicator = page.locator('.spinner-border');
    this.loadingOverlay = page.locator('#loadingOverlay');
    this.errorMessage = page.locator('.alert-danger');
    this.alertContainer = page.locator('#alertContainer');
    
    // Thank You form fields
    this.interviewerNameInput = page.locator('#interviewerName');
    this.interviewTypeSelect = page.locator('#interviewType');
    this.companyNameInput = page.locator('#companyName');
    this.jobTitleInput = page.locator('#jobTitle');
    this.discussionPointsInput = page.locator('#discussionPoints');
    this.thankYouOutput = page.locator('#thankYouOutput');
    
    // Rejection form fields
    this.rejectionEmailInput = page.locator('#rejectionEmail');
    this.interviewStageSelect = page.locator('#interviewStage');
    this.rejectionOutput = page.locator('#rejectionOutput');
    
    // Reference form fields
    this.referenceNameInput = page.locator('#referenceName');
    this.relationshipSelect = page.locator('#referenceRelationship');
    this.targetJobInput = page.locator('#targetJobTitle');
    this.targetCompanyInput = page.locator('#targetCompany');
    this.referenceOutput = page.locator('#referenceOutput');
    
    // Job comparison form fields
    this.addJobButton = page.locator('button:has-text("Add")');
    this.jobInputs = page.locator('.card');
    this.job1TitleInput = page.locator('#job1Title');
    this.job1CompanyInput = page.locator('#job1Company');
    this.job2TitleInput = page.locator('#job2Title');
    this.job2CompanyInput = page.locator('#job2Company');
    this.comparisonOutput = page.locator('#comparisonOutput');
    
    // Follow-up form fields
    this.followUpStageSelect = page.locator('#followupStage');
    this.contactNameInput = page.locator('#followupContactName');
    this.daysSinceContactInput = page.locator('#followupDays');
    this.followupCompanyInput = page.locator('#followupCompany');
    this.followupJobTitleInput = page.locator('#followupJobTitle');
    this.followupOutput = page.locator('#followupOutput');
    
    // Salary coach form fields
    this.currentSalaryInput = page.locator('#currentSalary');
    this.offeredSalaryInput = page.locator('#offeredSalary');
    this.experienceInput = page.locator('#yearsExperience');
    this.achievementsInput = page.locator('#achievements');
    this.salaryJobTitleInput = page.locator('#salaryJobTitle');
    this.salaryCompanyInput = page.locator('#salaryCompany');
    this.salaryOutput = page.locator('#salaryOutput');
  }
  
  /**
   * Navigate to tools page
   */
  async navigate() {
    await this.goto(this.url);
    await this.waitForPageLoad();
    // Wait for the tools nav to be visible
    await this.page.waitForSelector('.tools-nav', { timeout: 10000 });
  }
  
  /**
   * Select a tool tab using JavaScript to trigger the onclick handler
   */
  async selectTool(tool: 'thank-you' | 'rejection' | 'reference' | 'comparison' | 'followup' | 'salary') {
    // Map test tool names to the actual JavaScript function parameter names
    const toolNameMap: Record<string, string> = {
      'thank-you': 'thankYou',
      'rejection': 'rejection',
      'reference': 'reference',
      'comparison': 'comparison',
      'followup': 'followup',
      'salary': 'salary',
    };
    
    const sectionMap: Record<string, Locator> = {
      'thank-you': this.thankYouSection,
      'rejection': this.rejectionSection,
      'reference': this.referenceSection,
      'comparison': this.comparisonSection,
      'followup': this.followupSection,
      'salary': this.salarySection,
    };
    
    const jsToolName = toolNameMap[tool];
    
    // Call the showTool function directly via JavaScript
    await this.page.evaluate((toolName) => {
      (window as any).showTool?.(toolName);
    }, jsToolName);
    
    // Wait for the section to become active
    await sectionMap[tool].waitFor({ state: 'visible', timeout: 5000 });
    await this.page.waitForTimeout(300);
  }
  
  /**
   * Generate thank you note
   */
  async generateThankYouNote(data: {
    interviewerName: string;
    interviewType: string;
    companyName: string;
    jobTitle: string;
    discussionPoints?: string;
  }) {
    await this.selectTool('thank-you');
    
    await this.interviewerNameInput.fill(data.interviewerName);
    await this.interviewTypeSelect.selectOption(data.interviewType);
    await this.companyNameInput.fill(data.companyName);
    await this.jobTitleInput.fill(data.jobTitle);
    
    if (data.discussionPoints) {
      await this.discussionPointsInput.fill(data.discussionPoints);
    }
    
    await this.page.locator('#thankYouSubmit').click();
    await this.waitForOutput(this.thankYouOutput);
  }
  
  /**
   * Analyze rejection email
   */
  async analyzeRejection(data: {
    rejectionEmail: string;
    jobTitle?: string;
    companyName?: string;
    stage?: string;
  }) {
    await this.selectTool('rejection');
    
    await this.rejectionEmailInput.fill(data.rejectionEmail);
    
    if (data.jobTitle) {
      await this.page.locator('#rejectionJobTitle').fill(data.jobTitle);
    }
    if (data.companyName) {
      await this.page.locator('#rejectionCompany').fill(data.companyName);
    }
    if (data.stage) {
      await this.interviewStageSelect.selectOption(data.stage);
    }
    
    await this.page.locator('#rejectionSubmit').click();
    await this.waitForOutput(this.rejectionOutput);
  }
  
  /**
   * Generate reference request
   */
  async generateReferenceRequest(data: {
    referenceName: string;
    relationship: string;
    targetJob?: string;
    targetCompany?: string;
  }) {
    await this.selectTool('reference');
    
    await this.referenceNameInput.fill(data.referenceName);
    await this.relationshipSelect.selectOption(data.relationship);
    
    if (data.targetJob) {
      await this.targetJobInput.fill(data.targetJob);
    }
    if (data.targetCompany) {
      await this.targetCompanyInput.fill(data.targetCompany);
    }
    
    await this.page.locator('#referenceSubmit').click();
    await this.waitForOutput(this.referenceOutput);
  }
  
  /**
   * Compare jobs
   */
  async compareJobs(data: {
    job1: { title: string; company: string };
    job2: { title: string; company: string };
  }) {
    await this.selectTool('comparison');
    
    await this.job1TitleInput.fill(data.job1.title);
    await this.job1CompanyInput.fill(data.job1.company);
    await this.job2TitleInput.fill(data.job2.title);
    await this.job2CompanyInput.fill(data.job2.company);
    
    await this.page.locator('#comparisonForm button[type="submit"]').click();
    await this.waitForOutput(this.comparisonOutput);
  }
  
  /**
   * Generate follow-up email
   */
  async generateFollowUp(data: {
    stage: string;
    companyName: string;
    jobTitle: string;
    contactName?: string;
    daysSinceContact?: number;
  }) {
    await this.selectTool('followup');
    
    await this.followUpStageSelect.selectOption(data.stage);
    await this.followupCompanyInput.fill(data.companyName);
    await this.followupJobTitleInput.fill(data.jobTitle);
    
    if (data.contactName) {
      await this.contactNameInput.fill(data.contactName);
    }
    if (data.daysSinceContact) {
      await this.daysSinceContactInput.fill(data.daysSinceContact.toString());
    }
    
    await this.page.locator('#followupForm button[type="submit"]').click();
    await this.waitForOutput(this.followupOutput);
  }
  
  /**
   * Get salary coaching
   */
  async getSalaryCoaching(data: {
    jobTitle: string;
    companyName: string;
    offeredSalary: string;
    yearsExperience: number;
    currentSalary?: string;
    achievements?: string;
  }) {
    await this.selectTool('salary');
    
    await this.salaryJobTitleInput.fill(data.jobTitle);
    await this.salaryCompanyInput.fill(data.companyName);
    await this.offeredSalaryInput.fill(data.offeredSalary);
    await this.experienceInput.fill(data.yearsExperience.toString());
    
    if (data.currentSalary) {
      await this.currentSalaryInput.fill(data.currentSalary);
    }
    if (data.achievements) {
      await this.achievementsInput.fill(data.achievements);
    }
    
    await this.page.locator('#salaryForm button[type="submit"]').click();
    await this.waitForOutput(this.salaryOutput);
  }
  
  /**
   * Wait for output to appear
   */
  async waitForOutput(outputLocator?: Locator, timeout: number = 60000) {
    // Wait for loading overlay to hide
    await this.loadingOverlay.waitFor({ state: 'hidden', timeout: timeout }).catch(() => {});
    
    if (outputLocator) {
      await outputLocator.waitFor({ state: 'visible', timeout });
    }
  }
  
  /**
   * Check if output is displayed
   */
  async hasOutput(): Promise<boolean> {
    return await this.outputSection.isVisible({ timeout: 2000 }).catch(() => false);
  }
  
  /**
   * Get output text
   */
  async getOutputText(): Promise<string> {
    return (await this.outputSection.textContent()) || '';
  }
  
  /**
   * Copy output to clipboard
   */
  async copyOutput() {
    await this.copyButton.click();
  }
  
  /**
   * Check for error
   */
  async hasError(): Promise<boolean> {
    return await this.errorMessage.isVisible({ timeout: 2000 }).catch(() => false);
  }
  
  /**
   * Get error message
   */
  async getErrorMessage(): Promise<string> {
    return (await this.errorMessage.textContent()) || '';
  }
  
  /**
   * Get the active tool section
   */
  async getActiveSection(): Promise<Locator> {
    return this.page.locator('.tool-section.active');
  }
  
  /**
   * Check if a specific tool section is active
   */
  async isToolActive(tool: 'thank-you' | 'rejection' | 'reference' | 'comparison' | 'followup' | 'salary'): Promise<boolean> {
    const sectionMap: Record<string, Locator> = {
      'thank-you': this.thankYouSection,
      'rejection': this.rejectionSection,
      'reference': this.referenceSection,
      'comparison': this.comparisonSection,
      'followup': this.followupSection,
      'salary': this.salarySection,
    };
    const section = sectionMap[tool];
    const hasActiveClass = await section.evaluate((el) => el.classList.contains('active'));
    return hasActiveClass;
  }
}
