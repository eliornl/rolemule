"""
Agent for generating intelligent resume optimization recommendations using LLM analysis.
Creates personalized, actionable resume advice by analyzing user profile against job requirements.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from workflows.state_schema import WorkflowState, ResumeRecommendationsResult
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

LLM_TEMPERATURE: float = 0.25  # Low for consistent, practical advice
LLM_MAX_TOKENS: int = 16000  # Aligned with unified agent output cap
LLM_TIMEOUT: float = 90.0  # Longer timeout for detailed analysis

# =============================================================================
# PROMPTS
# =============================================================================

SYSTEM_CONTEXT: str = """You are an elite resume strategist and ATS optimization expert with 20+ years of experience helping candidates land interviews at top companies.

## YOUR EXPERTISE:

**ATS Systems:**
- You know exactly how Applicant Tracking Systems parse and score resumes
- You understand keyword matching, density, and placement strategies
- You know which formats pass ATS and which get rejected

**Hiring Manager Psychology:**
- You know hiring managers spend only 6-7 seconds on initial resume scan
- You understand what makes them stop and read vs. move to the next resume
- You know the "F-pattern" reading behavior and design resumes accordingly

**Industry Knowledge:**
- You understand resume conventions vary by industry (tech vs. finance vs. healthcare)
- You know what keywords and phrases trigger interest in each field
- You recognize which achievements and metrics matter most by role

**Strategic Positioning:**
- You craft professional summaries that immediately communicate value
- You know how to frame experience gaps, career changes, and non-traditional backgrounds
- You transform job duties into achievement statements with measurable impact

## YOUR PRINCIPLES:
- Every recommendation must be SPECIFIC and ACTIONABLE
- Use ACTUAL details from the candidate's profile - never generic advice
- YEARS OF EXPERIENCE RULE: The "Years of Experience" field is TOTAL career years — NEVER use it as domain-specific experience. When claiming "X years of [skill/domain]", derive that number only from the relevant work history entries where that skill was actually used. If you cannot calculate it, say "experience with [skill]" without stating a specific year count.
- Prioritize changes by IMPACT - what will move the needle most?
- Consider both ATS optimization AND human reader appeal
- Be honest about weaknesses but always provide solutions"""

RESUME_ADVISOR_PROMPT: str = """Analyze this candidate's resume strategy for the target job and provide expert optimization recommendations.

=== CANDIDATE PROFILE ===
{user_profile}

=== TARGET JOB ===
{job_analysis}

=== MATCHING ANALYSIS ===
{profile_matching}

=== COMPANY CONTEXT ===
{company_context}

---

Analyze the candidate's fit and provide strategic resume recommendations. Output ONLY valid JSON with this exact structure:

{{
    "strategic_assessment": {{
        "current_competitiveness": "<How competitive is this candidate for THIS specific role? Be honest.>",
        "biggest_opportunity": "<Single biggest thing they can do to improve their chances>",
        "biggest_risk": "<Main concern a hiring manager might have>",
        "ats_pass_likelihood": "<HIGH | MEDIUM | LOW - will their resume pass ATS screening?>",
        "interview_likelihood": "<HIGH | MEDIUM | LOW - if a human sees it, will they interview?>"
    }},

    "professional_summary": {{
        "current_assessment": "<What's wrong with their current summary, if anything?>",
        "recommended_summary": "<Write an optimized 3-4 sentence professional summary tailored to THIS job. CRITICAL: use ONLY the exact 'Years of Experience' value from the candidate profile — never estimate, round up, or calculate a different number from their work history. Include key skills and value proposition.>",
        "key_elements_included": ["<keyword 1>", "<keyword 2>", "<specific achievement referenced>"]
    }},

    "experience_optimization": {{
        "prioritization_strategy": "<Which roles should be emphasized and why?>",
        "roles_to_highlight": [
            {{
                "role": "<job title from their experience>",
                "company": "<company name>",
                "why_relevant": "<why this role matters for the target job>",
                "bullet_point_suggestions": [
                    "<Rewritten achievement bullet with metrics - be specific using their actual experience>",
                    "<Another achievement bullet optimized for this job>",
                    "<Third achievement bullet>"
                ],
                "keywords_to_add": ["<keyword from job requirements to weave in>"]
            }}
        ],
        "roles_to_minimize": ["<role to de-emphasize>"],
        "experience_gap_strategy": "<How to address any experience gaps?>"
    }},

    "skills_section": {{
        "must_include_skills": [
            {{
                "skill": "<skill name>",
                "reason": "<why this is critical for ATS/hiring manager>",
                "where_to_demonstrate": "<which experience to link this to>"
            }}
        ],
        "skills_to_add": ["<skill they have but didn't list>"],
        "skills_to_remove_or_deprioritize": ["<skill that's irrelevant or hurts them>"],
        "recommended_skill_categories": {{
            "technical_skills": ["<skill1>", "<skill2>"],
            "soft_skills": ["<skill1>", "<skill2>"],
            "tools_technologies": ["<tool1>", "<tool2>"],
            "certifications": ["<cert1 if applicable>"]
        }}
    }},

    "ats_optimization": {{
        "critical_keywords_missing": [
            {{
                "keyword": "<exact keyword from job posting>",
                "importance": "<CRITICAL | HIGH | MEDIUM>",
                "where_to_add": "<specific section or bullet to add this>"
            }}
        ],
        "keyword_density_issues": "<Are any keywords over/under-used?>",
        "format_recommendations": [
            "<specific formatting tip for ATS compatibility>"
        ],
        "section_order_recommendation": ["<section1>", "<section2>", "<section3>", "<section4>"]
    }},

    "quick_wins": [
        {{
            "action": "<Specific, immediate action they can take>",
            "impact": "<HIGH | MEDIUM>",
            "time_to_implement": "<5 min | 15 min | 30 min | 1 hour>"
        }}
    ],

    "red_flags_to_fix": [
        {{
            "issue": "<Something that might concern a hiring manager>",
            "current_state": "<How it currently appears>",
            "recommended_fix": "<Exactly how to address it>"
        }}
    ],

    "final_checklist": {{
        "before_submitting": [
            "<Specific check #1>",
            "<Specific check #2>",
            "<Specific check #3>"
        ],
        "file_format": "<PDF or DOCX recommendation for this company/ATS>",
        "file_naming": "<Recommended file name format>"
    }},

    "confidence_score": {{
        "score": <0.0-1.0 - confidence these changes will improve their chances>,
        "reasoning": "<Why this confidence level?>"
    }}
}}

Remember: Be SPECIFIC. Use their ACTUAL experience, skills, and the EXACT job requirements. No generic advice."""


class ResumeAdvisorAgent:
    """
    Elite Resume Advisor Agent providing strategic, ATS-optimized resume recommendations.
    
    Uses expert LLM analysis to provide specific, actionable resume optimization advice
    tailored to the target job, leveraging profile matching insights and company context.
    """

    def __init__(self, gemini_client: Any) -> None:
        """
        Initialize Resume Advisor Agent.

        Args:
            gemini_client: Gemini client instance for LLM-powered analysis
        """
        if gemini_client is None:
            raise TypeError("gemini_client cannot be None")
        self.gemini_client: Any = gemini_client
        logger.info("Resume Advisor Agent initialized")

    async def process(self, state: WorkflowState) -> WorkflowState:
        """
        Process resume advisory analysis using expert LLM consultation.

        Args:
            state: Current workflow state containing all analysis results

        Returns:
            Updated workflow state with structured resume recommendations

        Raises:
            ValueError: If required data is missing
            Exception: If LLM generation fails
        """
        session_id = sanitize_log_value(str(state.get("session_id") or "unknown"))
        logger.info('Starting resume advisory for session %s', sanitize_log_value(session_id))
        start_time = datetime.now(timezone.utc)

        # Store user API key for use in LLM calls (BYOK mode)
        self._current_user_api_key = state.get("user_api_key")

        try:
            # Extract and validate required data
            user_profile: Dict[str, Any] = state.get("user_profile", {})
            job_analysis: Dict[str, Any] = state.get("job_analysis", {})
            profile_matching: Optional[Dict[str, Any]] = state.get("profile_matching")
            company_research: Optional[Dict[str, Any]] = state.get("company_research")
            prefs: Dict[str, Any] = state.get("workflow_preferences") or {}
            resume_length: str = prefs.get("resume_length", "concise")
            user_model: Optional[str] = prefs.get("preferred_model") if self._current_user_api_key else None

            if not user_profile:
                raise ValueError("User profile is required for resume advisory")
            if not job_analysis:
                raise ValueError("Job analysis is required for resume advisory")

            # Generate expert recommendations
            recommendations = await self._generate_recommendations(
                user_profile, job_analysis, profile_matching, company_research,
                resume_length=resume_length,
                user_model=user_model,
            )

            # Add processing metadata
            recommendations["processing_time"] = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds()
            recommendations["analysis_method"] = "EXPERT_LLM"

            # Create result object
            result = ResumeRecommendationsResult()
            result.comprehensive_advice = recommendations
            result.processing_time = recommendations["processing_time"]

            # Store in state
            state["resume_recommendations"] = result.to_dict()

            logger.info('Resume advisory completed for session %s', sanitize_log_value(session_id))

        except Exception as e:
            logger.error("Resume advisory failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

        return state

    async def _generate_recommendations(
        self,
        user_profile: Dict[str, Any],
        job_analysis: Dict[str, Any],
        profile_matching: Optional[Dict[str, Any]],
        company_research: Optional[Dict[str, Any]],
        resume_length: str = "concise",
        user_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate expert resume recommendations using LLM.

        Args:
            user_profile: User profile data
            job_analysis: Job analysis results
            profile_matching: Profile matching analysis
            company_research: Company research data

        Returns:
            Structured recommendations dictionary
        """
        logger.info("Generating expert resume recommendations")

        # Format all data for prompt
        formatted_profile = self._format_profile(user_profile)
        formatted_job = self._format_job(job_analysis)
        formatted_matching = self._format_matching(profile_matching)
        formatted_company = self._format_company(company_research)

        # Inject user-selected verbosity preference
        length_instruction = (
            "\n\nUSER PREFERENCE — DETAILED: Provide thorough rewrites and expanded explanations. "
            "For each role highlighted, supply 4-5 achievement bullets. Include detailed rationale "
            "for every keyword and section recommendation."
            if resume_length == "detailed"
            else
            "\n\nUSER PREFERENCE — CONCISE: Keep recommendations sharp and scannable. "
            "For each role highlighted, supply 2-3 tight achievement bullets. Prioritise the "
            "highest-impact changes only; omit minor or nice-to-have suggestions."
        )

        # Build prompt
        prompt = RESUME_ADVISOR_PROMPT.format(
            user_profile=formatted_profile,
            job_analysis=formatted_job,
            profile_matching=formatted_matching,
            company_context=formatted_company,
        ) + length_instruction

        # Call LLM
        try:
            response = await asyncio.wait_for(
                self.gemini_client.generate(
                    prompt=prompt,
                    system=SYSTEM_CONTEXT,
                    temperature=LLM_TEMPERATURE,
                    max_tokens=LLM_MAX_TOKENS,
                    user_api_key=self._current_user_api_key,
                    model=user_model,
                ),
                timeout=LLM_TIMEOUT,
            )

            if response.get("filtered"):
                logger.warning("Response was filtered")
                return self._create_fallback_result("Content was filtered by safety settings")

            response_text = response.get("response", "")
            result = parse_json_from_llm_response(response_text)

            if not result:
                logger.warning("Failed to parse JSON, returning raw response")
                return {
                    "raw_advice": response_text[:15000],
                    "parse_error": True,
                }

            return result

        except asyncio.TimeoutError:
            logger.error("LLM request timed out")
            return self._create_fallback_result("Request timed out")
        except Exception as e:
            logger.error("LLM request failed: %s", sanitize_log_value(str(e)), exc_info=True)
            return self._create_fallback_result(str(e))

    def _format_profile(self, profile: Dict[str, Any]) -> str:
        """Format user profile for LLM consumption."""
        sections = []

        # Basic info
        sections.append(f"Name: {profile.get('full_name', 'N/A')}")
        sections.append(f"Title: {profile.get('professional_title', 'N/A')}")
        sections.append(f"Years of Experience: {profile.get('years_experience', 0)}")

        location_parts = [
            profile.get("city", ""),
            profile.get("state", ""),
            profile.get("country", ""),
        ]
        location = ", ".join([p for p in location_parts if p])
        if location:
            sections.append(f"Location: {location}")

        # Constraints
        constraints = []
        if profile.get("is_student"):
            constraints.append("Currently a student")
        if profile.get("requires_visa_sponsorship"):
            constraints.append("Requires visa sponsorship")
        if profile.get("has_security_clearance"):
            constraints.append("Has security clearance")
        if constraints:
            sections.append(f"Special Considerations: {', '.join(constraints)}")

        # Summary
        if profile.get("summary"):
            sections.append(f"\nCurrent Professional Summary:\n{profile['summary']}")

        # Skills
        skills = profile.get("skills", [])
        if skills:
            sections.append(f"\nSkills: {', '.join(skills)}")

        # Experience
        work_exp = profile.get("work_experience", [])
        if work_exp:
            sections.append("\nWork Experience:")
            for i, exp in enumerate(work_exp, 1):
                title = exp.get("job_title", "N/A")
                company = exp.get("company", exp.get("company_name", "N/A"))
                start = exp.get("start_date", "N/A")
                end = exp.get("end_date", "Present")
                sections.append(f"\n{i}. {title} at {company} ({start} - {end})")
                if exp.get("description"):
                    sections.append(f"   {exp['description']}")

        edu_rows = profile.get("education", []) or []
        if edu_rows:
            sections.append("\nEducation:")
            for i, edu in enumerate(edu_rows, 1):
                deg = edu.get("degree", "N/A")
                inst = edu.get("institution", "N/A")
                start = edu.get("start_date", "N/A")
                end = edu.get("end_date", "Present") if edu.get("is_current") else edu.get("end_date", "N/A")
                fos = edu.get("field_of_study")
                line = f"\n{i}. {deg} — {inst} ({start} - {end})"
                if fos:
                    line += f" — Field: {fos}"
                sections.append(line)

        return "\n".join(sections)

    def _format_job(self, job: Dict[str, Any]) -> str:
        """Format job analysis for LLM consumption."""
        sections = []

        sections.append(f"Position: {job.get('job_title', 'N/A')}")
        sections.append(f"Company: {job.get('company_name', 'N/A')}")
        sections.append(f"Industry: {job.get('industry', 'N/A')}")

        location_parts = [
            job.get("job_city", ""),
            job.get("job_state", ""),
            job.get("job_country", ""),
        ]
        location = ", ".join([p for p in location_parts if p])
        if location:
            sections.append(f"Location: {location}")

        sections.append(f"Work Arrangement: {job.get('work_arrangement', 'N/A')}")
        sections.append(f"Experience Required: {job.get('years_experience_required', 'N/A')} years")

        # Skills
        required_skills = job.get("required_skills", [])
        if required_skills:
            sections.append(f"\nRequired Skills: {', '.join(required_skills)}")

        soft_skills = job.get("soft_skills", [])
        if soft_skills:
            sections.append(f"Soft Skills: {', '.join(soft_skills)}")

        # Qualifications
        required_quals = job.get("required_qualifications", [])
        if required_quals:
            sections.append("\nRequired Qualifications:")
            for q in required_quals:
                sections.append(f"  • {q}")

        preferred_quals = job.get("preferred_qualifications", [])
        if preferred_quals:
            sections.append("\nPreferred Qualifications:")
            for q in preferred_quals:
                sections.append(f"  • {q}")

        # ATS Keywords
        ats_keywords = job.get("ats_keywords", [])
        if ats_keywords:
            sections.append(f"\nATS Keywords: {', '.join(ats_keywords)}")

        return "\n".join(sections)

    def _format_matching(self, matching: Optional[Dict[str, Any]]) -> str:
        """Format profile matching analysis for LLM consumption."""
        if not matching:
            return "No matching analysis available"

        sections = []

        # Executive summary from new format
        exec_summary = matching.get("executive_summary", {})
        if exec_summary:
            sections.append(f"Overall Assessment: {exec_summary.get('fit_assessment', 'N/A')}")
            sections.append(f"Recommendation: {exec_summary.get('recommendation', 'N/A')}")
            sections.append(f"Verdict: {exec_summary.get('one_line_verdict', 'N/A')}")

        # Scores
        sections.append(f"\nQualification Score: {matching.get('qualification_score', 0):.2f}")
        sections.append(f"Preference Score: {matching.get('preference_score', 0):.2f}")
        sections.append(f"Overall Score: {matching.get('overall_score', 0):.2f}")

        # Skills analysis from new format
        qual_analysis = matching.get("qualification_analysis", {})
        skills_assessment = qual_analysis.get("skills_assessment", {})
        if skills_assessment:
            matched = skills_assessment.get("matched_skills", [])
            if matched:
                skill_names = [s.get("skill", s) if isinstance(s, dict) else s for s in matched[:10]]
                sections.append(f"\nMatched Skills: {', '.join(skill_names)}")

            missing = skills_assessment.get("missing_critical_skills", [])
            if missing:
                skill_names = [s.get("skill", s) if isinstance(s, dict) else s for s in missing[:10]]
                sections.append(f"Missing Skills: {', '.join(skill_names)}")

            hidden = skills_assessment.get("hidden_skills", [])
            if hidden:
                skill_names = [s.get("skill", s) if isinstance(s, dict) else s for s in hidden[:5]]
                sections.append(f"Hidden Skills (likely have): {', '.join(skill_names)}")

        # Application strategy from new format
        app_strategy = matching.get("application_strategy", {})
        if app_strategy:
            talking_points = app_strategy.get("key_talking_points", [])
            if talking_points:
                sections.append("\nKey Points to Emphasize:")
                for point in talking_points[:5]:
                    sections.append(f"  • {point}")

            concerns = app_strategy.get("address_these_concerns", [])
            if concerns:
                sections.append("\nConcerns to Address:")
                for concern in concerns[:3]:
                    if isinstance(concern, dict):
                        sections.append(f"  • {concern.get('concern', concern)}")
                    else:
                        sections.append(f"  • {concern}")

        return "\n".join(sections)

    def _format_company(self, company: Optional[Dict[str, Any]]) -> str:
        """Format company research for LLM consumption."""
        if not company:
            return "No company research available"

        sections = []

        if company.get("company_size"):
            sections.append(f"Company Size: {company['company_size']}")
        if company.get("industry"):
            sections.append(f"Industry: {company['industry']}")

        if company.get("mission_vision"):
            mission = company["mission_vision"]
            if len(mission) > 300:
                mission = mission[:300] + "..."
            sections.append(f"\nMission: {mission}")

        if company.get("core_values"):
            values = company["core_values"][:5]
            sections.append(f"Core Values: {', '.join(values)}")

        return "\n".join(sections) if sections else "Limited company information available"

    def _create_fallback_result(self, error_message: str) -> Dict[str, Any]:
        """Create fallback result on error."""
        return {
            "strategic_assessment": {
                "current_competitiveness": "Unable to assess due to error",
                "biggest_opportunity": "Please try again",
                "biggest_risk": error_message,
                "ats_pass_likelihood": "UNKNOWN",
                "interview_likelihood": "UNKNOWN",
            },
            "error": True,
            "error_message": error_message,
        }
