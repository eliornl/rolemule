/**
 * Migrated from ui/static/js/types.js
 * Behavior preserved 1:1. Typed gradually; @ts-nocheck until fully annotated.
 */
// @ts-nocheck
/**
 * @fileoverview Shared TypeScript-compatible JSDoc type definitions for the ApplyPilot frontend.
 * These types provide IDE autocomplete and type checking without requiring TypeScript compilation.
 */

// =============================================================================
// API RESPONSE TYPES
// =============================================================================

/**
 * @typedef {Object} ApiResponse
 * @property {boolean} [success] - Whether the request was successful
 * @property {string} [message] - Response message
 * @property {string} [error] - Error message if failed
 * @property {string} [redirect] - URL to redirect to after success
 */

/**
 * @typedef {Object} AuthResponse
 * @property {string} access_token - JWT access token
 * @property {string} token_type - Token type (e.g., "bearer")
 * @property {number} [expires_in] - Token expiration time in seconds
 * @property {User} [user] - User data
 */

/**
 * @typedef {Object} PaginatedResponse
 * @property {number} page - Current page number
 * @property {number} per_page - Items per page
 * @property {number} total - Total number of items
 * @property {number} total_pages - Total number of pages
 * @property {boolean} has_prev - Whether there is a previous page
 * @property {boolean} has_next - Whether there is a next page
 */

// =============================================================================
// USER TYPES
// =============================================================================

/**
 * @typedef {Object} User
 * @property {string} id - User UUID
 * @property {string} email - User email address
 * @property {string} full_name - User's full name
 * @property {boolean} profile_completed - Whether profile setup is complete
 * @property {number} profile_completion_percentage - Profile completion percentage (0-100)
 * @property {string} [created_at] - ISO timestamp of account creation
 * @property {string} [last_login] - ISO timestamp of last login
 */

/**
 * @typedef {Object} UserProfile
 * @property {string} [id] - Profile UUID
 * @property {string} [user_id] - Associated user UUID
 * @property {string} [full_name] - User's full name
 * @property {string} [email] - User's email
 * @property {string} [phone] - User's phone number
 * @property {string} [location] - User's location
 * @property {string} [city] - User's city
 * @property {string} [state] - User's state/province
 * @property {string} [country] - User's country
 * @property {string} [professional_title] - Professional title
 * @property {string} [professional_summary] - Professional summary
 * @property {number} [years_experience] - Years of experience
 * @property {string} [summary] - Professional summary (alternate)
 * @property {string} [profile_url] - Professional profile URL
 * @property {string} [github_url] - GitHub profile URL
 * @property {string} [portfolio_url] - Portfolio URL
 * @property {string} [resume_url] - Resume file URL
 * @property {boolean} [is_student] - Whether user is a student
 * @property {boolean} [actively_searching] - Whether actively searching for jobs
 * @property {WorkExperience[]} [experience] - Work experience history
 * @property {WorkExperience[]} [work_experience] - Work history (alternate)
 * @property {Education[]} [education] - Education history
 * @property {Certification[]} [certifications] - Certifications
 * @property {string[]} [skills] - List of skills
 * @property {string[]} [technical_skills] - Technical skills
 * @property {string[]} [soft_skills] - Soft skills
 * @property {string[]} [industry_knowledge] - Industry knowledge areas
 * @property {string[]} [tools_technologies] - Tools and technologies
 * @property {string[]} [desired_job_titles] - Desired job titles
 * @property {string[]} [desired_industries] - Desired industries
 * @property {string[]} [desired_locations] - Desired work locations
 * @property {SalaryRange} [salary_range] - Desired salary range
 * @property {SalaryRange} [desired_salary_range] - Desired salary (alternate)
 * @property {string[]} [desired_company_sizes] - Preferred company sizes
 * @property {string[]} [job_types] - Preferred job types
 * @property {string[]} [work_arrangements] - Preferred work arrangements
 * @property {boolean} [willing_to_relocate] - Willingness to relocate
 * @property {boolean} [requires_visa_sponsorship] - Needs visa sponsorship
 * @property {boolean} [has_security_clearance] - Has security clearance
 * @property {string} [max_travel_preference] - Maximum travel preference
 */

/**
 * @typedef {Object} Education
 * @property {string} institution - Institution name
 * @property {string} degree - Degree obtained
 * @property {string} [field] - Field of study (resume parser / legacy)
 * @property {string} [field_of_study] - Field of study (profile API)
 * @property {string} [location] - Institution location
 * @property {string} [start_date] - Start date (YYYY-MM)
 * @property {string} [end_date] - End date (YYYY-MM)
 * @property {boolean} [is_current] - Currently enrolled
 * @property {boolean} [current] - Legacy: currently studying
 * @property {number} [gpa] - Grade point average
 */

/**
 * @typedef {Object} Certification
 * @property {string} name - Certification name
 * @property {string} issuer - Issuing organization
 * @property {string} [issue_date] - Issue date
 * @property {string} [expiry_date] - Expiration date
 * @property {boolean} [no_expiry] - Whether certification doesn't expire
 * @property {string} [credential_id] - Credential ID
 * @property {string} [credential_url] - Credential verification URL
 */

/**
 * @typedef {Object} WorkExperience
 * @property {string} company - Company name
 * @property {string} title - Job title
 * @property {string} [start_date] - Start date (YYYY-MM format)
 * @property {string} [end_date] - End date (YYYY-MM format or "Present")
 * @property {boolean} [is_current] - Whether this is the current job
 * @property {string} [description] - Role description
 * @property {string[]} [achievements] - Key achievements
 */

/**
 * @typedef {Object} SalaryRange
 * @property {number} [min] - Minimum salary
 * @property {number} [max] - Maximum salary
 * @property {string} [currency] - Currency code (e.g., "USD")
 * @property {string} [period] - Pay period (e.g., "yearly", "hourly")
 */

// =============================================================================
// WORKFLOW TYPES
// =============================================================================

/**
 * @typedef {'initialized' | 'in_progress' | 'awaiting_confirmation' | 'completed' | 'failed'} WorkflowStatus
 */

/**
 * @typedef {'initialization' | 'job_analysis' | 'profile_matching' | 'company_research' | 'document_generation' | 'completed' | 'error'} WorkflowPhase
 */

/**
 * @typedef {'pending' | 'running' | 'completed' | 'failed'} AgentStatus
 */

/**
 * @typedef {Object} WorkflowSession
 * @property {string} id - Session UUID
 * @property {string} session_id - Session identifier
 * @property {string} user_id - User UUID
 * @property {WorkflowStatus} workflow_status - Current workflow status
 * @property {WorkflowPhase} current_phase - Current workflow phase
 * @property {string} [current_agent] - Currently running agent
 * @property {Object<string, AgentStatus>} [agent_status] - Status of each agent
 * @property {string[]} [completed_agents] - List of completed agents
 * @property {string[]} [failed_agents] - List of failed agents
 * @property {string[]} [error_messages] - Error messages
 * @property {string[]} [warning_messages] - Warning messages
 * @property {string} [job_title] - Job title being applied for
 * @property {string} [company_name] - Company name
 * @property {string} [created_at] - ISO timestamp
 * @property {string} [updated_at] - ISO timestamp
 */

/**
 * @typedef {Object} WorkflowListResponse
 * @property {WorkflowSession[]} sessions - List of workflow sessions
 * @property {number} page - Current page
 * @property {number} per_page - Items per page
 * @property {number} total - Total items
 * @property {number} total_pages - Total pages
 */

/**
 * @typedef {Object} WorkflowStatusResponse
 * @property {string} session_id - Session identifier
 * @property {WorkflowStatus} workflow_status - Current status
 * @property {WorkflowPhase} current_phase - Current phase
 * @property {number} progress_percentage - Progress (0-100)
 * @property {string} [current_agent] - Currently running agent
 * @property {Object<string, AgentStatus>} [agent_status] - Agent statuses
 * @property {string[]} [completed_agents] - Completed agents
 * @property {boolean} [requires_confirmation] - Whether user confirmation is needed
 */

/**
 * @typedef {Object} WorkflowResults
 * @property {string} session_id - Session identifier
 * @property {JobAnalysis} [job_analysis] - Job analysis results
 * @property {ProfileMatching} [profile_matching] - Profile matching results
 * @property {CompanyResearch} [company_research] - Company research results
 * @property {ResumeRecommendations} [resume_recommendations] - Resume advice
 * @property {CoverLetter} [cover_letter] - Generated cover letter
 */

// =============================================================================
// AGENT RESULT TYPES
// =============================================================================

/**
 * @typedef {Object} JobAnalysis
 * @property {string} [company_name] - Company name
 * @property {string} [job_title] - Job title
 * @property {string} [location] - Job location
 * @property {string} [work_arrangement] - Remote/hybrid/onsite
 * @property {string[]} [required_skills] - Required skills
 * @property {string[]} [preferred_skills] - Preferred skills
 * @property {string[]} [requirements] - Job requirements
 * @property {string[]} [responsibilities] - Job responsibilities
 * @property {SalaryRange} [salary_range] - Salary information
 * @property {string} [experience_level] - Required experience level
 */

/**
 * @typedef {Object} ProfileMatching
 * @property {ExecutiveSummary} [executive_summary] - Match summary
 * @property {FinalScores} [final_scores] - Match scores
 * @property {string[]} [strengths] - Candidate strengths
 * @property {string[]} [gaps] - Skill/experience gaps
 * @property {string[]} [recommendations] - Improvement recommendations
 */

/**
 * @typedef {Object} ExecutiveSummary
 * @property {string} recommendation - AI recommendation (STRONG_MATCH, GOOD_MATCH, etc.)
 * @property {string} [summary] - Summary text
 * @property {string[]} [key_points] - Key points
 */

/**
 * @typedef {Object} FinalScores
 * @property {number} overall_fit - Overall fit score (0-1)
 * @property {number} [skills_match] - Skills match score
 * @property {number} [experience_match] - Experience match score
 * @property {number} [preference_match] - Preference match score
 */

/**
 * @typedef {Object} CompanyResearch
 * @property {string} [company_overview] - Company overview
 * @property {string} [culture] - Company culture
 * @property {string} [recent_news] - Recent news
 * @property {string[]} [competitors] - Competitor companies
 * @property {string[]} [interview_tips] - Interview preparation tips
 */

/**
 * @typedef {Object} ResumeRecommendations
 * @property {string} [content] - Resume advice content
 * @property {string[]} [keywords] - Keywords to include
 * @property {string[]} [improvements] - Suggested improvements
 * @property {string[]} [achievements_to_highlight] - Achievements to emphasize
 */

/**
 * @typedef {Object} CoverLetter
 * @property {string} [content] - Cover letter content
 * @property {string} [format] - Format (text, markdown, etc.)
 */

// =============================================================================
// APPLICATION TYPES
// =============================================================================

/**
 * @typedef {'draft' | 'processing' | 'completed' | 'failed' | 'applied' | 'interview' | 'rejected' | 'accepted'} ApplicationStatus
 */

/**
 * @typedef {Object} JobApplication
 * @property {string} id - Application UUID
 * @property {string} user_id - User UUID
 * @property {string} [session_id] - Associated workflow session ID
 * @property {string} [job_title] - Job title
 * @property {string} [company_name] - Company name
 * @property {string} [job_url] - Original job posting URL
 * @property {number} [match_score] - Match score (0-1)
 * @property {ApplicationStatus} status - Application status
 * @property {string} [applied_date] - Date applied
 * @property {string} [response_date] - Date of response
 * @property {string} [notes] - User notes
 * @property {string} created_at - Creation timestamp
 * @property {string} updated_at - Last update timestamp
 */

// =============================================================================
// WEBSOCKET MESSAGE TYPES
// =============================================================================

/**
 * @typedef {'connected' | 'pong' | 'agent_update' | 'phase_change' | 'workflow_complete' | 'workflow_error' | 'gate_decision'} WebSocketMessageType
 */

/**
 * @typedef {Object} WebSocketMessage
 * @property {WebSocketMessageType} type - Message type
 * @property {string} [session_id] - Associated session ID
 * @property {Object} [data] - Message payload
 * @property {string} [message] - Human-readable message
 * @property {string} timestamp - ISO timestamp
 */

/**
 * @typedef {Object} AgentUpdateData
 * @property {string} agent - Agent name
 * @property {AgentStatus} status - Agent status
 * @property {string} [message] - Status message
 */

/**
 * @typedef {Object} PhaseChangeData
 * @property {WorkflowPhase} phase - New phase
 * @property {number} progress - Progress percentage
 */

/**
 * @typedef {Object} GateDecisionData
 * @property {number} match_score - Match score (0-1)
 * @property {string} recommendation - AI recommendation
 * @property {boolean} requires_confirmation - Whether confirmation is needed
 */

// =============================================================================
// UI COMPONENT TYPES
// =============================================================================

/**
 * @typedef {'success' | 'error' | 'warning' | 'info'} NotificationType
 */

/**
 * @typedef {Object} ModalOptions
 * @property {'sm' | 'lg' | 'xl'} [size] - Modal size
 * @property {string} [footer] - Footer HTML content
 */

/**
 * @typedef {Object} ApiCallOptions
 * @property {Object<string, string>} [headers] - Additional headers
 * @property {boolean} [skipTokenRefresh] - Skip automatic token refresh
 */

// =============================================================================
// GLOBAL DECLARATIONS
// =============================================================================

/**
 * @typedef {Object} AppInstance
 * @property {function(string, NotificationType): void} showNotification - Show notification
 * @property {function(string, string, Object): Promise<any>} apiCall - Make API call
 * @property {function(): void} [logout] - Logout user
 * @property {function(): Promise<void>} [refreshToken] - Refresh auth token
 */

/**
 * Global window extensions
 * @global
 */

// Extend window with app-specific globals
// @ts-ignore - Extending window object for app globals
if (typeof window !== "undefined") {
  /** @type {AppInstance|undefined} */
  window.app = window.app;
  /** @type {ProfileManager|undefined} */
  window.profileManager = window.profileManager;
}

// Export empty object to make this a module (for ES modules compatibility)
export {};

