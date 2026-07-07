import { Page, Route } from '@playwright/test';

/**
 * API Mocking utilities for comprehensive E2E testing
 * Allows testing full workflows without real backend/API keys
 */

// ============================================================================
// MOCK DATA
// ============================================================================

/**
 * Valid 3-part JWT for use in all mocked tests.
 * Client-side scripts validate token.split('.').length === 3 before storing;
 * using a bare string like 'mock-token' causes silent redirect to /auth/login.
 */
export const MOCK_JWT = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMSIsImV4cCI6OTk5OTk5OTk5OX0.fake_sig_for_testing';

export const mockUser = {
  id: 'mock-user-uuid-12345',
  email: 'mockuser@test.com',
  full_name: 'Mock Test User',
  profile_completed: true,
  email_verified: true,
  created_at: new Date().toISOString(),
};

export const mockProfile = {
  user_id: mockUser.id,
  full_name: 'Mock Test User',
  email: mockUser.email,
  city: 'San Francisco',
  state: 'CA',
  country: 'USA',
  professional_title: 'Senior Software Engineer',
  years_experience: 8,
  summary: 'Experienced software engineer with expertise in Python, JavaScript, and cloud technologies.',
  work_experience: [
    {
      company: 'TechCorp Inc',
      job_title: 'Senior Software Engineer',
      start_date: '2020-01',
      end_date: null,
      is_current: true,
      description: 'Led development of microservices architecture.',
    },
  ],
  skills: ['Python', 'JavaScript', 'TypeScript', 'React', 'Node.js', 'PostgreSQL', 'AWS'],
  education: [
    {
      institution: 'UC Berkeley',
      degree: 'BS Computer Science',
      field_of_study: 'Computer Science',
      start_date: '2012-09',
      end_date: '2016-05',
      is_current: false,
    },
  ],
  career_preferences: {
    min_salary: 150000,
    max_salary: 250000,
    job_types: ['full-time'],
    work_arrangements: ['remote', 'hybrid'],
  },
};

/**
 * Matches GET /api/v1/profile/ response shape (`user_info` + `profile_data` + `completion_status`).
 * Dashboard `loadUserData()` reads `completion_status.profile_completed`.
 */
export function buildMockGetProfileResponse(options: { profileCompleted?: boolean } = {}): Record<string, unknown> {
  const profileCompleted = options.profileCompleted !== false;
  const pct = profileCompleted ? 100 : 0;
  const sectionOk = profileCompleted;
  return {
    user_info: {
      id: mockUser.id,
      email: mockUser.email,
      full_name: mockUser.full_name,
      auth_method: 'email',
      profile_completed: profileCompleted,
      has_google_linked: false,
      has_password: true,
      created_at: mockUser.created_at,
      updated_at: mockUser.created_at,
      last_login: null,
    },
    profile_data: { ...mockProfile },
    completion_status: {
      basic_info: sectionOk,
      work_experience: sectionOk,
      education: sectionOk,
      skills_qualifications: sectionOk,
      career_preferences: sectionOk,
      completion_percentage: pct,
      profile_completed: profileCompleted,
    },
  };
}

/** True for GET exactly `/api/v1/profile` or `/api/v1/profile/` (not `/profile/status`, etc.). */
export function isProfileRootDocumentRequest(route: Route): boolean {
  if (route.request().method() !== 'GET') return false;
  const u = new URL(route.request().url());
  const path = u.pathname.replace(/\/$/, '') || '/';
  return path === '/api/v1/profile';
}

export const mockWorkflowSession = {
  session_id: 'mock-session-uuid-12345',
  user_id: mockUser.id,
  status: 'completed',
  workflow_phase: 'completed',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  agent_durations: {
    job_analyzer: 3500,
    profile_matching: 5200,
    company_research: 4800,
    resume_advisor: 4100,
    cover_letter_writer: 3900,
  },
};

export const mockJobAnalysis = {
  job_title: 'Senior Software Engineer',
  company_name: 'TechCorp Inc',
  location: 'San Francisco, CA',
  work_arrangement: 'Remote',
  salary_range: '$180,000 - $220,000',
  job_type: 'Full-time',
  experience_required: '5+ years',
  skills_required: ['Python', 'JavaScript', 'AWS', 'PostgreSQL'],
  skills_nice_to_have: ['Kubernetes', 'Machine Learning'],
  responsibilities: [
    'Design and implement scalable backend services',
    'Mentor junior developers',
    'Participate in code reviews',
  ],
  qualifications: [
    "Bachelor's degree in Computer Science",
    '5+ years of software engineering experience',
  ],
  benefits: ['Health insurance', '401k matching', 'Remote work'],
  company_description: 'TechCorp is a leading technology company.',
};

export const mockProfileMatching = {
  overall_score: 85,
  qualification_match: 90,
  skill_match: 88,
  experience_match: 82,
  preference_match: 80,
  gate_decision: 'proceed',
  executive_summary: 'Strong candidate with excellent technical skills matching the role requirements.',
  strengths: [
    'Strong Python and JavaScript experience',
    'Relevant cloud platform experience',
    'Leadership experience matches senior role',
  ],
  gaps: [
    'Limited Kubernetes experience',
    'No ML background mentioned',
  ],
  recommendations: [
    'Highlight cloud migration projects',
    'Emphasize team leadership experience',
  ],
};

export const mockCompanyResearch = {
  company_name: 'TechCorp Inc',
  industry: 'Technology',
  company_size: '500-1000 employees',
  founded: '2010',
  headquarters: 'San Francisco, CA',
  website: 'https://techcorp.example.com',
  culture: {
    values: ['Innovation', 'Collaboration', 'Growth'],
    work_environment: 'Fast-paced startup culture',
    diversity_initiatives: 'Strong DEI programs',
  },
  recent_news: [
    'Raised $50M Series C funding',
    'Expanded to European markets',
  ],
  interview_insights: [
    'Focus on system design questions',
    'Behavioral interviews emphasize teamwork',
  ],
  employee_satisfaction_rating: 4.2,
};

export const mockResumeAdvice = {
  overall_assessment: 'Strong resume that aligns well with the role.',
  key_recommendations: [
    {
      section: 'Summary',
      recommendation: 'Add specific metrics about team leadership',
      priority: 'high',
    },
    {
      section: 'Skills',
      recommendation: 'Add Kubernetes to skills section',
      priority: 'medium',
    },
  ],
  keywords_to_add: ['microservices', 'distributed systems', 'agile'],
  sections_to_emphasize: ['Technical Experience', 'Leadership'],
  formatting_suggestions: [
    'Keep to 2 pages maximum',
    'Use bullet points for achievements',
  ],
};

export const mockCoverLetter = {
  subject_line: 'Application for Senior Software Engineer Position',
  greeting: 'Dear Hiring Manager,',
  opening_paragraph: 'I am excited to apply for the Senior Software Engineer position at TechCorp Inc. With over 8 years of experience in software development and a proven track record of building scalable systems, I am confident I would be a valuable addition to your team.',
  body_paragraphs: [
    'In my current role at Tech Innovations Inc, I have led the development of microservices architecture that improved system performance by 40%. I have extensive experience with Python, JavaScript, and cloud technologies that directly align with your requirements.',
    'I am particularly drawn to TechCorp\'s commitment to innovation and your recent expansion into new markets. I believe my experience in scaling systems and mentoring teams would contribute to your continued growth.',
  ],
  closing_paragraph: 'I would welcome the opportunity to discuss how my skills and experience align with your needs. Thank you for considering my application.',
  signature: 'Sincerely,\nMock Test User',
  full_letter: '', // Will be constructed
};

export const mockInterviewPrep = {
  session_id: mockWorkflowSession.session_id,
  questions: {
    technical: [
      {
        question: 'Explain how you would design a distributed caching system.',
        guidance: 'Discuss cache invalidation, consistency, and scalability.',
        sample_answer: 'I would start by identifying the access patterns...',
      },
      {
        question: 'How do you handle database migrations in production?',
        guidance: 'Cover zero-downtime deployments and rollback strategies.',
        sample_answer: 'For production migrations, I follow a blue-green deployment...',
      },
    ],
    behavioral: [
      {
        question: 'Tell me about a time you had to mentor a struggling team member.',
        guidance: 'Use STAR method: Situation, Task, Action, Result.',
        sample_answer: 'In my previous role, I noticed a junior developer...',
      },
    ],
    company: [
      {
        question: 'Why do you want to work at TechCorp?',
        guidance: 'Reference company research and culture fit.',
        sample_answer: 'I\'m excited about TechCorp\'s focus on innovation...',
      },
    ],
    role: [
      {
        question: 'How would you approach leading a team of 5 engineers?',
        guidance: 'Discuss communication, delegation, and growth.',
        sample_answer: 'My leadership approach focuses on clear communication...',
      },
    ],
  },
  tips: [
    'Research the company thoroughly before the interview',
    'Prepare specific examples from your experience',
    'Ask thoughtful questions about the role and team',
  ],
};

export const mockToolResponses = {
  thankYou: {
    subject_line: 'Thank You for the Interview - Senior Software Engineer',
    email_body: 'Dear Sarah,\n\nThank you for taking the time to meet with me today...',
    key_points_referenced: ['Team structure discussion', 'Technical challenges'],
    tone: 'professional',
    generated_at: new Date().toISOString(),
  },
  
  rejectionAnalysis: {
    analysis_summary: 'The rejection appears to be due to strong competition rather than disqualification.',
    likely_reasons: ['Strong candidate pool', 'Slight experience gap in specific area'],
    improvement_suggestions: ['Gain more Kubernetes experience', 'Highlight leadership more'],
    positive_signals: ['They were impressed with technical skills'],
    follow_up_recommended: true,
    follow_up_template: 'Dear Hiring Team,\n\nThank you for the update...',
    encouragement: 'Remember that rejection is part of the process...',
    generated_at: new Date().toISOString(),
  },
  
  referenceRequest: {
    subject_line: 'Would You Be a Reference for Me?',
    email_body: 'Dear John,\n\nI hope this email finds you well...',
    talking_points: ['Remind them of key projects', 'Mention the target role'],
    follow_up_timeline: 'Follow up in 1 week if no response',
    tips: ['Send during business hours', 'Attach updated resume'],
    generated_at: new Date().toISOString(),
  },
  
  jobComparison: {
    executive_summary: 'Both jobs offer strong opportunities with different trade-offs.',
    recommended_job: 'Job 1',
    recommendation_confidence: 'high',
    recommendation_reasoning: 'Better alignment with remote preference and growth goals.',
    jobs_analysis: [
      {
        job_identifier: 'Job 1',
        title: 'Senior Engineer',
        company: 'Startup Inc',
        overall_score: 85,
        scores: {
          compensation: 80,
          career_growth: 90,
          work_life_balance: 85,
        },
        pros: ['Remote work', 'Equity upside'],
        cons: ['Startup risk'],
      },
    ],
    generated_at: new Date().toISOString(),
  },
  
  followUp: {
    subject_line: 'Following Up on Senior Engineer Application',
    email_body: 'Dear Jane,\n\nI wanted to follow up on my application...',
    key_elements: ['Adds value', 'Clear but gentle CTA'],
    tone: 'professional',
    timing_advice: 'Send Tuesday-Thursday morning',
    next_steps: 'Wait 5-7 days before following up again',
    generated_at: new Date().toISOString(),
  },
  
  salaryCoach: {
    market_analysis: {
      salary_assessment: 'The offer is 10-15% below market',
      market_position: 'Below market',
      recommended_target: '$165,000-$175,000',
      negotiation_room: 'Likely $10-20k room',
    },
    strategy_overview: {
      approach: 'Confident but collaborative negotiation',
      key_messages: ['Emphasize unique value', 'Reference market data'],
      timing_recommendation: 'Respond within 48 hours',
    },
    main_script: {
      opening: 'Thank you for the offer. I\'m excited about...',
      value_statement: 'Based on my experience with...',
      counter_offer: 'I was hoping we could discuss...',
      closing: 'I\'m confident we can find a number that works...',
    },
    generated_at: new Date().toISOString(),
  },
};

// ============================================================================
// MOCK SETUP FUNCTIONS
// ============================================================================

/**
 * Inject cookie consent into localStorage before page load.
 * Must include version:'1.0' — cookie-consent.js re-shows the banner
 * if the stored value lacks version, which overlays the page and blocks
 * all pointer events, breaking every subsequent test interaction.
 */
export async function setupCookieConsent(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('cookie_consent', JSON.stringify({
      essential: true,
      functional: true,
      analytics: false,
      version: '1.0',
      timestamp: new Date().toISOString(),
    }));
  });
}

/**
 * Inject a valid JWT auth token + cookie consent into localStorage
 * before page load. Use this for every test that navigates to an
 * authenticated (dashboard) page without going through the login form.
 */
export async function setupAuth(page: Page): Promise<void> {
  await page.addInitScript((token: string) => {
    localStorage.setItem('access_token', token);
    localStorage.setItem('authToken', token);
    localStorage.setItem('cookie_consent', JSON.stringify({
      essential: true,
      functional: true,
      analytics: false,
      version: '1.0',
      timestamp: new Date().toISOString(),
    }));
  }, MOCK_JWT);
}

/**
 * Setup all API mocks for comprehensive testing
 */
export async function setupAllMocks(
  page: Page,
  profileOptions?: ProfileMocksOptions,
): Promise<void> {
  await setupAuthMocks(page);
  await setupProfileMocks(page, profileOptions);
  await setupWorkflowMocks(page);
  await setupToolsMocks(page);
  await setupMiscMocks(page);
}

/**
 * Setup authentication API mocks
 */
export async function setupAuthMocks(page: Page): Promise<void> {
  // Login
  await page.route('**/api/v1/auth/login', async (route) => {
    const request = route.request();
    const body = request.postDataJSON();
    
    if (body?.email && body?.password) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: MOCK_JWT,
          token_type: 'bearer',
          user_id: mockUser.id,
          email: body.email,
          profile_completed: true,
        }),
      });
    } else {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid credentials' }),
      });
    }
  });
  
  // Register
  await page.route('**/api/v1/auth/register', async (route) => {
    const body = route.request().postDataJSON();
    
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: MOCK_JWT,
        token_type: 'bearer',
        user_id: mockUser.id,
        email: body?.email || mockUser.email,
        message: 'Registration successful',
      }),
    });
  });
  
  // Verify token
  await page.route('**/api/v1/auth/verify', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        valid: true,
        user_id: mockUser.id,
        email: mockUser.email,
      }),
    });
  });
  
  // Refresh token
  await page.route('**/api/v1/auth/refresh', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: MOCK_JWT,
        token_type: 'bearer',
      }),
    });
  });
  
  // Logout
  await page.route('**/api/v1/auth/logout', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Logged out successfully' }),
    });
  });
  
  // Password reset request
  await page.route('**/api/v1/auth/password-reset/request', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Password reset email sent' }),
    });
  });
  
  // Password reset confirm
  await page.route('**/api/v1/auth/password-reset/confirm', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Password reset successful' }),
    });
  });
  
  // Email verification
  await page.route('**/api/v1/auth/verify-email**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Email verified successfully' }),
    });
  });
  
  // Resend verification
  await page.route('**/api/v1/auth/resend-verification', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Verification email sent' }),
    });
  });
  
  // Google OAuth
  await page.route('**/api/v1/auth/google**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: MOCK_JWT,
        token_type: 'bearer',
        user_id: mockUser.id,
        email: mockUser.email,
        is_new_user: false,
      }),
    });
  });
}

/**
 * Options for {@link setupProfileMocks}.
 */
export type ProfileMocksOptions = {
  /** GET /api/v1/profile root — default fully complete (all five sections). */
  mockGetProfileCompleted?: boolean;
};

/**
 * Setup profile API mocks
 */
export async function setupProfileMocks(
  page: Page,
  options?: ProfileMocksOptions,
): Promise<void> {
  const getProfileCompleted = options?.mockGetProfileCompleted !== false;

  // GET /api/v1/profile/ — must match production shape (dashboard reads completion_status)
  await page.route('**/api/v1/profile**', async (route) => {
    if (!isProfileRootDocumentRequest(route)) {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        buildMockGetProfileResponse({ profileCompleted: getProfileCompleted }),
      ),
    });
  });
  
  // Update basic info
  await page.route('**/api/v1/profile/basic-info', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Basic info updated', ...mockProfile }),
    });
  });
  
  // Update work experience
  await page.route('**/api/v1/profile/work-experience', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Work experience updated' }),
    });
  });

  // Update education (profile setup step 3)
  await page.route('**/api/v1/profile/education', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Education updated' }),
    });
  });
  
  // Update skills (canonical path)
  await page.route('**/api/v1/profile/skills-qualifications', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Skills updated' }),
    });
  });
  
  // Update career preferences
  await page.route('**/api/v1/profile/career-preferences', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Career preferences updated' }),
    });
  });
  
  // Profile completion status (canonical endpoint)
  await page.route('**/api/v1/profile/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        profile_completed: true,
        completion_percentage: 100,
        completed_steps: [
          'basic_info',
          'work_experience',
          'education',
          'skills_qualifications',
          'career_preferences',
        ],
        missing_steps: [],
        next_step: null,
      }),
    });
  });

  // Legacy alias used by some tests — keep until callers migrate to /profile/status
  await page.route('**/api/v1/profile/completion-status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        profile_completed: true,
        completion_percentage: 100,
        missing_sections: [],
      }),
    });
  });
  
  // Parse resume
  await page.route('**/api/v1/profile/parse-resume', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: mockProfile,
        confidence: 'HIGH',
        processing_time: 1.5,
      }),
    });
  });
  
  // API key management
  await page.route('**/api/v1/profile/api-key**', async (route) => {
    const method = route.request().method();
    
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ has_key: true, key_configured: true }),
      });
    } else if (method === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'API key saved successfully' }),
      });
    } else if (method === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'API key deleted' }),
      });
    }
  });
  
  // Data export
  await page.route('**/api/v1/profile/export', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: mockUser,
        profile: mockProfile,
        applications: [],
        exported_at: new Date().toISOString(),
      }),
    });
  });
  
  // Delete account
  await page.route('**/api/v1/profile/delete-account', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'Account deleted successfully' }),
    });
  });
}

/**
 * Setup workflow API mocks
 */
export async function setupWorkflowMocks(page: Page): Promise<void> {
  // Start workflow
  await page.route('**/api/v1/workflow/start', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: mockWorkflowSession.session_id,
        status: 'started',
        message: 'Workflow started successfully',
      }),
    });
  });
  
  // Get workflow status
  await page.route('**/api/v1/workflow/status/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...mockWorkflowSession,
        job_analysis: mockJobAnalysis,
        profile_matching: mockProfileMatching,
        company_research: mockCompanyResearch,
        resume_advice: mockResumeAdvice,
        cover_letter: mockCoverLetter,
      }),
    });
  });
  
  // Get workflow results
  await page.route('**/api/v1/workflow/results/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        session_id: mockWorkflowSession.session_id,
        status: 'completed',
        job_analysis: mockJobAnalysis,
        profile_matching: mockProfileMatching,
        company_research: mockCompanyResearch,
        resume_advice: mockResumeAdvice,
        cover_letter: mockCoverLetter,
      }),
    });
  });
  
  // List workflow sessions
  await page.route('**/api/v1/workflow/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        sessions: [mockWorkflowSession],
        total: 1,
      }),
    });
  });
}

/**
 * Setup career tools API mocks
 */
export async function setupToolsMocks(page: Page): Promise<void> {
  // Thank you note
  await page.route('**/api/v1/tools/thank-you', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockToolResponses.thankYou),
    });
  });
  
  // Rejection analysis
  await page.route('**/api/v1/tools/rejection-analysis', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockToolResponses.rejectionAnalysis),
    });
  });
  
  // Reference request
  await page.route('**/api/v1/tools/reference-request', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockToolResponses.referenceRequest),
    });
  });
  
  // Job comparison
  await page.route('**/api/v1/tools/job-comparison', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockToolResponses.jobComparison),
    });
  });
  
  // Follow-up stages
  await page.route('**/api/v1/tools/followup-stages', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        stages: [
          { id: 'after_application', name: 'After Application' },
          { id: 'after_interview', name: 'After Interview' },
          { id: 'no_response', name: 'No Response' },
        ],
      }),
    });
  });
  
  // Follow-up generator
  await page.route('**/api/v1/tools/followup', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockToolResponses.followUp),
    });
  });
  
  // Salary coach
  await page.route('**/api/v1/tools/salary-coach', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockToolResponses.salaryCoach),
    });
  });
}

/**
 * Setup miscellaneous API mocks
 */
export async function setupMiscMocks(page: Page): Promise<void> {
  // Health check
  await page.route('**/api/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'healthy' }),
    });
  });
  
  // Applications list
  await page.route('**/api/v1/applications', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          applications: [
            {
              id: 'app-uuid-1',
              session_id: mockWorkflowSession.session_id,
              job_title: mockJobAnalysis.job_title,
              company_name: mockJobAnalysis.company_name,
              status: 'completed',
              match_score: mockProfileMatching.overall_score,
              created_at: new Date().toISOString(),
            },
          ],
          total: 1,
        }),
      });
    }
  });
  
  // Single application
  await page.route('**/api/v1/applications/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'app-uuid-1',
        session_id: mockWorkflowSession.session_id,
        job_title: mockJobAnalysis.job_title,
        company_name: mockJobAnalysis.company_name,
        status: 'completed',
        match_score: mockProfileMatching.overall_score,
        job_analysis: mockJobAnalysis,
        profile_matching: mockProfileMatching,
        cover_letter: mockCoverLetter,
        resume_advice: mockResumeAdvice,
      }),
    });
  });
  
  // Interview prep
  await page.route('**/api/v1/interview-prep/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(mockInterviewPrep),
    });
  });
  
  // Admin endpoints (for completeness)
  await page.route('**/api/v1/admin/**', async (route) => {
    await route.fulfill({
      status: 403,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Admin access required' }),
    });
  });
}

/**
 * Setup WebSocket mock
 */
export async function setupWebSocketMock(page: Page): Promise<void> {
  // Intercept WebSocket connection attempts
  await page.addInitScript(() => {
    class MockWebSocket {
      url: string;
      readyState: number = 1; // OPEN
      onopen: ((ev: Event) => void) | null = null;
      onmessage: ((ev: MessageEvent) => void) | null = null;
      onclose: ((ev: CloseEvent) => void) | null = null;
      onerror: ((ev: Event) => void) | null = null;
      
      constructor(url: string) {
        this.url = url;
        
        // Simulate connection
        setTimeout(() => {
          if (this.onopen) {
            this.onopen(new Event('open'));
          }
        }, 100);
        
        // Simulate workflow progress messages
        if (url.includes('/workflow/')) {
          const agents = ['job_analyzer', 'profile_matching', 'company_research', 'resume_advisor', 'cover_letter_writer'];
          let index = 0;
          
          const sendProgress = () => {
            if (index < agents.length && this.onmessage) {
              this.onmessage(new MessageEvent('message', {
                data: JSON.stringify({
                  type: 'agent_update',
                  agent_name: agents[index],
                  status: 'completed',
                  progress: ((index + 1) / agents.length) * 100,
                }),
              }));
              index++;
              
              if (index < agents.length) {
                setTimeout(sendProgress, 500);
              } else {
                // Send completion
                setTimeout(() => {
                  if (this.onmessage) {
                    this.onmessage(new MessageEvent('message', {
                      data: JSON.stringify({
                        type: 'workflow_complete',
                        status: 'completed',
                        match_score: 85,
                      }),
                    }));
                  }
                }, 500);
              }
            }
          };
          
          setTimeout(sendProgress, 500);
        }
      }
      
      send(data: string): void {
        console.log('MockWebSocket send:', data);
      }
      
      close(): void {
        this.readyState = 3; // CLOSED
        if (this.onclose) {
          this.onclose(new CloseEvent('close'));
        }
      }
    }
    
    (window as any).WebSocket = MockWebSocket;
  });
}

/**
 * Clear all mocks
 */
export async function clearAllMocks(page: Page): Promise<void> {
  await page.unrouteAll();
}
