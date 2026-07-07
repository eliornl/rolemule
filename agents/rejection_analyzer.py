"""
Rejection Analyzer Agent.
Analyzes job rejection emails and provides constructive feedback and improvement suggestions.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from utils.llm_client import get_gemini_client
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import get_structured_logger, sanitize_log_value

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

# LLM Configuration
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 16000  # Unified agent output cap

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SYSTEM_CONTEXT = """You are a supportive career coach with expertise in job searching and
professional development. Your role is to help job seekers learn from rejections, identify
improvement areas, and maintain motivation. You provide honest but encouraging feedback,
turning setbacks into learning opportunities.
NEVER use placeholder brackets like [Recruiter Name], [Your Name], [Company], [Position],
[Hiring Team], or any fill-in-the-blank markers. Write complete, ready-to-use text."""

REJECTION_ANALYSIS_PROMPT = """Analyze this job rejection email and provide constructive feedback.

Rejection Email:
{rejection_email}

Context:
- Job Title: {job_title}
- Company: {company_name}
- Interview Stage: {interview_stage}

Please analyze:
1. What the rejection language suggests about the decision
2. Any positive signals in the rejection (they kept your resume, encouraged future applications, etc.)
3. Potential areas for improvement based on the stage and language
4. Whether a follow-up is appropriate and professional

Be honest but encouraging. Focus on actionable growth opportunities.

CRITICAL WRITING RULES for the follow-up email (if follow_up_recommended is true):
1. NEVER write placeholder brackets such as [Recruiter Name], [Your Name], [Company], etc.
2. If a sender name appears in the rejection email, address them by FIRST NAME ONLY (e.g., "Hi Sarah,").
   If no name is available, open with "Dear Hiring Team," — write it exactly like that, not as a placeholder.
3. Close with "Best regards," on its own line. Do NOT add any name — the sender will sign it themselves.
4. Subject line format: "Re: {job_title} Application — {company_name}"
5. Keep the body under 120 words — gracious, brief, and professional.
6. Reference the specific company and role. No generic filler.
7. Provide follow_up_subject and follow_up_body as separate fields.

Return your response as JSON with this exact structure:
{{
    "analysis_summary": "2-3 sentence analysis specific to this rejection, company, and stage",
    "likely_reasons": ["specific reason 1", "specific reason 2", "specific reason 3"],
    "improvement_suggestions": ["actionable suggestion 1", "actionable suggestion 2", "actionable suggestion 3"],
    "positive_signals": ["specific positive signal 1", "specific positive signal 2"],
    "follow_up_recommended": true/false,
    "follow_up_subject": "Subject line if follow_up_recommended is true, null otherwise",
    "follow_up_body": "Email body if follow_up_recommended is true, null otherwise",
    "encouragement": "2-3 sentence encouragement specific to this situation and stage"
}}"""


# =============================================================================
# AGENT CLASS
# =============================================================================


class RejectionAnalyzerAgent:
    """
    Agent for analyzing job rejection emails and providing constructive feedback.
    
    Helps job seekers understand what might have happened, identify areas for
    improvement, and maintain motivation through the job search process.
    """

    def __init__(self):
        """Initialize the RejectionAnalyzerAgent."""
        self.gemini_client = None
        self._current_user_api_key: Optional[str] = None

    async def analyze(
        self,
        rejection_email: str,
        job_title: Optional[str] = None,
        company_name: Optional[str] = None,
        interview_stage: Optional[str] = None,
        user_api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze a rejection email and provide constructive feedback.
        
        Args:
            rejection_email: The text of the rejection email
            job_title: Optional job title applied for
            company_name: Optional company name
            interview_stage: Optional stage at which rejection occurred
            user_api_key: Optional user API key for BYOK mode
            
        Returns:
            Dict containing analysis_summary, likely_reasons, improvement_suggestions,
            positive_signals, follow_up_recommended, follow_up_template, encouragement
        """
        self._current_user_api_key = user_api_key
        
        try:
            # Initialize Gemini client
            self.gemini_client = await get_gemini_client()
            
            # Format optional inputs
            job_title_str = job_title if job_title else "Not specified"
            company_name_str = company_name if company_name else "Not specified"
            interview_stage_str = interview_stage if interview_stage else "Not specified"
            
            # Build prompt
            prompt = REJECTION_ANALYSIS_PROMPT.format(
                rejection_email=rejection_email,
                job_title=job_title_str,
                company_name=company_name_str,
                interview_stage=interview_stage_str,
            )
            
            structured_logger.log_agent_start("rejection_analyzer", None)
            start_time = datetime.now(timezone.utc)
            
            # Generate response
            response = await self.gemini_client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
            )
            
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            # Check for filtered content
            if response.get("filtered"):
                structured_logger.log_agent_complete("rejection_analyzer", None, duration_ms)
                return self._create_filtered_result(response.get("response", ""))
            
            response_text = response.get("response", "")
            
            # Parse JSON response
            parsed = parse_json_from_llm_response(response_text)
            
            if not parsed:
                logger.error("Failed to parse rejection analysis response: %s", sanitize_log_value(response_text[:200]))
                structured_logger.log_agent_error(
                    "rejection_analyzer", None,
                    Exception("JSON parse failed"), duration_ms
                )
                return self._create_parse_error_result(response_text)
            
            structured_logger.log_agent_complete("rejection_analyzer", None, duration_ms)
            
            return {
                "analysis_summary": parsed.get(
                    "analysis_summary",
                    "Unable to generate detailed analysis."
                ),
                "likely_reasons": parsed.get("likely_reasons", []),
                "improvement_suggestions": parsed.get("improvement_suggestions", []),
                "positive_signals": parsed.get("positive_signals", []),
                "follow_up_recommended": parsed.get("follow_up_recommended", False),
                "follow_up_subject": parsed.get("follow_up_subject"),
                "follow_up_body": parsed.get("follow_up_body"),
                "encouragement": parsed.get(
                    "encouragement",
                    "Every rejection brings you closer to the right opportunity. Keep going!"
                ),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
            }
            
        except Exception as e:
            logger.error("Rejection analysis failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

    def _create_filtered_result(self, filter_message: str) -> Dict[str, Any]:
        """Create a result when content was filtered."""
        return {
            "analysis_summary": "Content generation was filtered. Please try again.",
            "likely_reasons": [],
            "improvement_suggestions": [],
            "positive_signals": [],
            "follow_up_recommended": False,
            "follow_up_subject": None,
            "follow_up_body": None,
            "encouragement": "Keep your head up! The right opportunity is out there.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "filtered": True,
            "filter_message": filter_message,
            "version": "1.0",
        }

    def _create_parse_error_result(self, raw_response: str) -> Dict[str, Any]:
        """Create a result when JSON parsing failed."""
        return {
            "analysis_summary": raw_response if len(raw_response) < 500 else raw_response[:500],
            "likely_reasons": [],
            "improvement_suggestions": [],
            "positive_signals": [],
            "follow_up_recommended": False,
            "follow_up_subject": None,
            "follow_up_body": None,
            "encouragement": "Every rejection is a step closer to the right opportunity!",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parse_error": True,
            "version": "1.0",
        }
