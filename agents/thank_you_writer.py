"""
Thank You Note Writer Agent.
Generates personalized thank you emails after job interviews.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

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

SYSTEM_CONTEXT = """You are an expert career coach specializing in professional communication.
You help job seekers write compelling, personalized thank you notes that leave a positive
impression after interviews. Your emails are professional yet warm, concise, and memorable.
NEVER use placeholder brackets like [Your Name], [Company], [Date], or any fill-in-the-blank
markers. Write complete, polished emails that are ready to send immediately."""

THANK_YOU_PROMPT = """Generate a professional thank you note email for a job interview.

Context:
- Interviewer: {interviewer_name}{interviewer_role}
- Interview Type: {interview_type}
- Company: {company_name}
- Position: {job_title}
- Key Discussion Points: {discussion_points}
- Additional Notes: {additional_notes}

CRITICAL WRITING RULES (violating any of these is unacceptable):
1. NEVER write placeholder brackets such as [Your Name], [Name], [Company], [Position], etc.
   Every word must be concrete and ready to send.
2. Subject line format: "Thank you: {job_title} Interview — {company_name}"
   Do NOT append the sender's name to the subject line.
3. Address the interviewer by FIRST NAME ONLY (e.g., "Hi Mati," not "Dear Mati Breski,").
4. Close the email with "Best regards," on its own line. Do NOT add any name below it —
   the sender will sign it themselves.
5. Keep the body under 150 words.
6. Reference the specific discussion points provided. If none were given, draw on the
   company name and role to write something concrete and genuine.
7. Reiterate authentic enthusiasm for the specific role at the specific company.

Return your response as JSON with this exact structure:
{{
    "subject_line": "Thank you: {job_title} Interview — {company_name}",
    "email_body": "Full email body with proper greeting and sign-off",
    "key_points_referenced": ["point 1", "point 2"],
    "tone": "professional/warm/enthusiastic"
}}"""


# =============================================================================
# AGENT CLASS
# =============================================================================


class ThankYouWriterAgent:
    """
    Agent for generating personalized thank you notes after job interviews.
    
    Uses LLM to create professional, contextual thank you emails that 
    reference specific discussion points and demonstrate genuine interest.
    """

    def __init__(self):
        """Initialize the ThankYouWriterAgent."""
        self.gemini_client = None
        self._current_user_api_key: Optional[str] = None

    async def generate(
        self,
        interviewer_name: str,
        interview_type: str,
        company_name: str,
        job_title: str,
        interviewer_role: Optional[str] = None,
        key_discussion_points: Optional[List[str]] = None,
        additional_notes: Optional[str] = None,
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a personalized thank you note.
        
        Args:
            interviewer_name: Name of the interviewer
            interview_type: Type of interview (phone, video, onsite, etc.)
            company_name: Name of the company
            job_title: Position applied for
            interviewer_role: Optional role/title of interviewer
            key_discussion_points: Optional list of topics discussed
            additional_notes: Optional additional context
            user_api_key: Optional user API key for BYOK mode
            model: Optional BYOK preferred Gemini model from Settings
            
        Returns:
            Dict containing subject_line, email_body, key_points_referenced, tone
        """
        self._current_user_api_key = user_api_key
        self._current_user_model = model
        
        try:
            # Initialize Gemini client
            self.gemini_client = await get_gemini_client()
            
            # Format inputs
            interviewer_role_str = f" ({interviewer_role})" if interviewer_role else ""
            discussion_points_str = (
                ", ".join(key_discussion_points) 
                if key_discussion_points 
                else "General interview discussion"
            )
            additional_notes_str = additional_notes if additional_notes else "None"
            
            # Build prompt
            prompt = THANK_YOU_PROMPT.format(
                interviewer_name=interviewer_name,
                interviewer_role=interviewer_role_str,
                interview_type=interview_type,
                company_name=company_name,
                job_title=job_title,
                discussion_points=discussion_points_str,
                additional_notes=additional_notes_str,
            )
            
            structured_logger.log_agent_start("thank_you_writer", None)
            start_time = datetime.now(timezone.utc)
            
            # Generate response
            response = await self.gemini_client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
                model=self._current_user_model,
            )
            
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            # Check for filtered content
            if response.get("filtered"):
                structured_logger.log_agent_complete("thank_you_writer", None, duration_ms)
                return self._create_filtered_result(response.get("response", ""))
            
            response_text = response.get("response", "")
            
            # Parse JSON response
            parsed = parse_json_from_llm_response(response_text)
            
            if not parsed:
                logger.error("Failed to parse thank you note response: %s", sanitize_log_value(response_text[:200]))
                structured_logger.log_agent_error(
                    "thank_you_writer", None, 
                    Exception("JSON parse failed"), duration_ms
                )
                return self._create_parse_error_result(response_text, job_title)
            
            structured_logger.log_agent_complete("thank_you_writer", None, duration_ms)
            
            return {
                "subject_line": parsed.get(
                    "subject_line", 
                    f"Thank you for the interview - {job_title}"
                ),
                "email_body": parsed.get("email_body", ""),
                "key_points_referenced": parsed.get("key_points_referenced", []),
                "tone": parsed.get("tone", "professional"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
            }
            
        except Exception as e:
            logger.error("Thank you note generation failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

    def _create_filtered_result(self, filter_message: str) -> Dict[str, Any]:
        """Create a result when content was filtered."""
        return {
            "subject_line": "Thank you for the interview",
            "email_body": "Content generation was filtered. Please try again with different input.",
            "key_points_referenced": [],
            "tone": "professional",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "filtered": True,
            "filter_message": filter_message,
            "version": "1.0",
        }

    def _create_parse_error_result(
        self, raw_response: str, job_title: str
    ) -> Dict[str, Any]:
        """Create a result when JSON parsing failed."""
        return {
            "subject_line": f"Thank you for the interview - {job_title}",
            "email_body": raw_response if len(raw_response) < 2000 else raw_response[:2000],
            "key_points_referenced": [],
            "tone": "professional",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parse_error": True,
            "version": "1.0",
        }
