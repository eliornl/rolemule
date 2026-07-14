"""
Job Comparison Agent.
Compares multiple jobs side-by-side to help users decide which to pursue.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from utils.llm_client import get_llm_client, get_gemini_client  # test-patch alias
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import get_structured_logger, sanitize_log_value

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

# LLM Configuration
LLM_TEMPERATURE = 0.5
LLM_MAX_TOKENS = 16000  # Unified agent output cap

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SYSTEM_CONTEXT = """You are an expert career advisor specializing in helping job seekers 
make informed decisions about job opportunities. You analyze multiple job opportunities 
objectively and provide clear, actionable comparisons based on various factors including 
compensation, growth potential, work-life balance, and career trajectory.

YEARS OF EXPERIENCE RULE: The "Years of Experience" field is the candidate's TOTAL career years — NEVER use it as domain-specific experience. When referencing experience in a specific skill or domain, only do so if it can be derived from their actual work history. If uncertain, say "experience with [skill]" without claiming a specific year count."""

COMPARISON_PROMPT = """Compare the following job opportunities and help the user decide which to pursue.

{jobs_section}

User Profile Context:
- Career Goals: {career_goals}
- Top Priorities: {priorities}
- Years of Experience: {experience_years}
- Preferred Work Style: {work_style}
- Location Preference: {location_preference}
- Salary Expectations: {salary_expectations}

Analyze each job across these dimensions:
1. Compensation & Benefits (salary, equity, perks)
2. Career Growth (promotion potential, learning opportunities)
3. Work-Life Balance (flexibility, expected hours, remote options)
4. Company Stability & Culture (company size, stability, culture fit)
5. Role Fit (skills match, responsibilities, challenge level)
6. Long-term Career Impact (resume building, industry reputation)

CRITICAL: Never use "Job 1", "Job 2", "Job 3" anywhere in your response.
Refer to each job by its JOB TITLE (e.g., "Founding Engineer", "Applied AI Engineer").
If two jobs share the same title, use "Title at Company" (e.g., "SWE at Google" vs "SWE at Meta").
This applies to every field: job_identifier, recommended_job, decision_factors winner,
questions_to_ask prefixes, comparison_matrix values, and final_advice.

Return your analysis as JSON with this exact structure:
{{
    "executive_summary": "2-3 sentence summary using job titles, not job numbers",
    "recommended_job": "Job title (e.g. 'Founding Engineer') or 'No clear winner'",
    "recommendation_confidence": "high" or "medium" or "low",
    "recommendation_reasoning": "Why this role is recommended",
    "jobs_analysis": [
        {{
            "job_identifier": "Job title — or 'Title at Company' if two titles are identical — NEVER 'Job 1'",
            "title": "Job title",
            "company": "Full company name",
            "overall_score": 85,
            "scores": {{
                "compensation": 80,
                "career_growth": 90,
                "work_life_balance": 75,
                "company_culture": 85,
                "role_fit": 88,
                "career_impact": 82
            }},
            "pros": ["pro 1", "pro 2", "pro 3"],
            "cons": ["con 1", "con 2"],
            "ideal_for": "Type of candidate this job is ideal for",
            "concerns": ["Any red flags or concerns"]
        }}
    ],
    "comparison_matrix": {{
        "best_compensation": "Job title",
        "best_growth": "Job title",
        "best_balance": "Job title",
        "best_culture": "Job title",
        "best_fit": "Job title"
    }},
    "decision_factors": [
        {{
            "factor": "Factor name",
            "importance": "high/medium/low",
            "winner": "Job title (e.g. 'Founding Engineer') — NEVER 'Job 1'",
            "explanation": "Why this role wins on this factor"
        }}
    ],
    "questions_to_ask": ["To [job title]: specific question — use job titles not job numbers"],
    "final_advice": "Final advice using job titles throughout, never job numbers"
}}"""

JOB_TEMPLATE = """
--- Job {index} (refer to this job as "{title}" throughout your response; if another job has the same title, use "{title} at {company}") ---
Title: {title}
Company: {company}
Location: {location}
Salary Range: {salary}
Job Type: {job_type}
Remote Policy: {remote_policy}
Description/Requirements:
{description}
"""


# =============================================================================
# AGENT CLASS
# =============================================================================


class JobComparisonAgent:
    """
    Agent for comparing multiple job opportunities side-by-side.
    
    Analyzes jobs across multiple dimensions and provides objective
    comparison with recommendations based on user priorities.
    """

    def __init__(self):
        """Initialize the JobComparisonAgent."""
        self.gemini_client = None
        self._current_user_api_key: Optional[str] = None

    async def compare(
        self,
        jobs: List[Dict[str, Any]],
        user_context: Optional[Dict[str, Any]] = None,
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare multiple job opportunities.
        
        Args:
            jobs: List of job dictionaries with title, company, location, 
                  salary, job_type, remote_policy, description
            user_context: Optional dict with career_goals, priorities, 
                         experience_years, work_style, location_preference,
                         salary_expectations
            user_api_key: Optional user API key for BYOK mode
            model: Optional BYOK preferred Gemini model from Settings
            
        Returns:
            Dict containing comparison analysis and recommendation
        """
        self._current_user_api_key = user_api_key
        self._current_llm_provider = llm_provider
        self._current_user_model = model
        
        if len(jobs) < 2:
            raise ValueError("At least 2 jobs required for comparison")
        if len(jobs) > 3:
            raise ValueError("Maximum 3 jobs can be compared at once")
        
        try:
            # Initialize Gemini client
            self.gemini_client = await get_llm_client()
            
            # Build jobs section
            jobs_section = ""
            for i, job in enumerate(jobs, 1):
                jobs_section += JOB_TEMPLATE.format(
                    index=i,
                    title=job.get("title", "Not specified"),
                    company=job.get("company", "Not specified"),
                    location=job.get("location", "Not specified"),
                    salary=job.get("salary", "Not specified"),
                    job_type=job.get("job_type", "Full-time"),
                    remote_policy=job.get("remote_policy", "Not specified"),
                    description=job.get("description", "No description provided")[:5000],
                )
            
            # Extract user context
            ctx = user_context or {}
            career_goals = ctx.get("career_goals", "Not specified")
            priorities = ctx.get("priorities", "Not specified")
            experience_years = ctx.get("experience_years", "Not specified")
            work_style = ctx.get("work_style", "Not specified")
            location_preference = ctx.get("location_preference", "Flexible")
            salary_expectations = ctx.get("salary_expectations", "Not specified")
            
            # Build prompt
            prompt = COMPARISON_PROMPT.format(
                jobs_section=jobs_section,
                career_goals=career_goals,
                priorities=priorities,
                experience_years=experience_years,
                work_style=work_style,
                location_preference=location_preference,
                salary_expectations=salary_expectations,
            )
            
            structured_logger.log_agent_start("job_comparison", None)
            start_time = datetime.now(timezone.utc)
            
            # Generate response
            response = await self.gemini_client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
                model=self._current_user_model,
                provider=getattr(self, "_current_llm_provider", None),
            )
            
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            # Check for filtered content
            if response.get("filtered"):
                structured_logger.log_agent_complete("job_comparison", None, duration_ms)
                return self._create_filtered_result(response.get("response", ""))
            
            response_text = response.get("response", "")
            
            # Parse JSON response
            parsed = parse_json_from_llm_response(response_text)
            
            if not parsed:
                logger.error("Failed to parse job comparison response: %s", sanitize_log_value(response_text[:200]))
                structured_logger.log_agent_error(
                    "job_comparison", None, 
                    Exception("JSON parse failed"), duration_ms
                )
                return self._create_parse_error_result(response_text, jobs)
            
            structured_logger.log_agent_complete("job_comparison", None, duration_ms)
            
            return {
                "executive_summary": parsed.get("executive_summary", ""),
                "recommended_job": parsed.get("recommended_job", "No clear winner"),
                "recommendation_confidence": parsed.get("recommendation_confidence", "medium"),
                "recommendation_reasoning": parsed.get("recommendation_reasoning", ""),
                "jobs_analysis": parsed.get("jobs_analysis", []),
                "comparison_matrix": parsed.get("comparison_matrix", {}),
                "decision_factors": parsed.get("decision_factors", []),
                "questions_to_ask": parsed.get("questions_to_ask", []),
                "final_advice": parsed.get("final_advice", ""),
                "jobs_compared": len(jobs),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
            }
            
        except Exception as e:
            logger.error("Job comparison failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

    def _create_filtered_result(self, filter_message: str) -> Dict[str, Any]:
        """Create a result when content was filtered."""
        return {
            "executive_summary": "Content generation was filtered.",
            "recommended_job": "Unable to determine",
            "recommendation_confidence": "low",
            "recommendation_reasoning": "Analysis could not be completed due to content filtering.",
            "jobs_analysis": [],
            "comparison_matrix": {},
            "decision_factors": [],
            "questions_to_ask": [],
            "final_advice": "Please try again with different job descriptions.",
            "filtered": True,
            "filter_message": filter_message,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }

    def _create_parse_error_result(
        self, raw_response: str, jobs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create a result when JSON parsing failed."""
        return {
            "executive_summary": "Analysis completed but formatting error occurred.",
            "recommended_job": "See raw analysis",
            "recommendation_confidence": "low",
            "recommendation_reasoning": raw_response[:2000] if len(raw_response) > 2000 else raw_response,
            "jobs_analysis": [],
            "comparison_matrix": {},
            "decision_factors": [],
            "questions_to_ask": [],
            "final_advice": "Review the raw analysis above for insights.",
            "jobs_compared": len(jobs),
            "parse_error": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }
