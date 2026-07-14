"""
Reference Request Writer Agent.
Generates professional emails requesting someone to be a job reference.
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
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 16000  # Unified agent output cap

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SYSTEM_CONTEXT = """You are an expert career coach specializing in professional networking
and communication. You help job seekers craft thoughtful, respectful reference requests that
maintain professional relationships while effectively asking for support. Your emails balance
professionalism with warmth and make it easy for the reference to say yes (or gracefully decline).
NEVER use placeholder brackets like [Your Name], [Reference Name], [Company], [Position], or
any fill-in-the-blank markers. Write complete, ready-to-send text."""

REFERENCE_REQUEST_PROMPT = """Generate a professional email requesting someone to be a job reference.

Context:
- Reference Name: {reference_name}
- Relationship: {reference_relationship}
- Company Worked Together: {reference_company}
- Target Position: {target_job_title}
- Target Company: {target_company}
- Key Accomplishments to Highlight: {key_accomplishments}
- Time Since Last Contact: {time_since_contact}
- Sender Name: {user_name}

CRITICAL WRITING RULES (violating any of these is unacceptable):
1. NEVER write placeholder brackets such as [Your Name], [Reference Name], [Company], etc.
   Every word must be concrete and ready to send.
2. Address the reference by FIRST NAME ONLY (e.g., "Hi Hadar," not "Dear Hadar Smith,").
3. Close with "Best regards," on its own line. Do NOT add a name below it — the sender
   will sign it themselves.
4. Keep the body under 200 words — warm, personal, and concise.
5. Reference the specific company and role they're applying for. No generic filler.
6. If accomplishments are provided, weave them naturally into the email.
7. If time since last contact is long (1+ year), open with a brief genuine reconnect line.

Return your response as JSON with this exact structure:
{{
    "subject_line": "Subject line for the email",
    "email_body": "Full email body with proper greeting and sign-off (no name after Best regards,)",
    "talking_points": ["Specific point they could mention about you", "Another concrete accomplishment"],
    "follow_up_timeline": "Specific timeframe to follow up (e.g., '5-7 business days')",
    "tips": ["Concrete tip for the reference request process", "Another helpful tip"]
}}"""


# =============================================================================
# AGENT CLASS
# =============================================================================


class ReferenceRequestWriterAgent:
    """
    Agent for generating professional reference request emails.
    
    Creates thoughtful, respectful requests that maintain professional 
    relationships while effectively asking for support in the job search.
    """

    def __init__(self):
        """Initialize the ReferenceRequestWriterAgent."""
        self.gemini_client = None
        self._current_user_api_key: Optional[str] = None

    async def generate(
        self,
        reference_name: str,
        reference_relationship: str,
        reference_company: Optional[str] = None,
        years_worked_together: Optional[int] = None,
        target_job_title: Optional[str] = None,
        target_company: Optional[str] = None,
        key_accomplishments: Optional[List[str]] = None,
        time_since_contact: Optional[str] = None,
        user_name: Optional[str] = None,
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a professional reference request email.
        
        Args:
            reference_name: Name of the person to request as reference
            reference_relationship: Relationship (former manager, colleague, etc.)
            reference_company: Optional company where you worked together
            years_worked_together: Optional years of working together
            target_job_title: Optional job title you're applying for
            target_company: Optional company you're applying to
            key_accomplishments: Optional list of accomplishments to highlight
            time_since_contact: Optional time since last contact
            user_name: Optional sender's name
            user_api_key: Optional user API key for BYOK mode
            model: Optional BYOK preferred Gemini model from Settings
            
        Returns:
            Dict containing subject_line, email_body, talking_points,
            follow_up_timeline, tips
        """
        self._current_user_api_key = user_api_key
        self._current_llm_provider = llm_provider
        self._current_user_model = model
        
        try:
            # Initialize Gemini client
            self.gemini_client = await get_llm_client()
            
            # Format optional inputs
            reference_company_str = reference_company if reference_company else "Not specified"
            target_job_str = target_job_title if target_job_title else "Not specified"
            target_company_str = target_company if target_company else "Not specified"
            accomplishments_str = (
                ", ".join(key_accomplishments) 
                if key_accomplishments 
                else "Not specified"
            )
            time_since_str = time_since_contact if time_since_contact else "Not specified"
            user_name_str = user_name if user_name else "the applicant"
            
            # Build prompt
            prompt = REFERENCE_REQUEST_PROMPT.format(
                reference_name=reference_name,
                reference_relationship=reference_relationship,
                reference_company=reference_company_str,
                target_job_title=target_job_str,
                target_company=target_company_str,
                key_accomplishments=accomplishments_str,
                time_since_contact=time_since_str,
                user_name=user_name_str,
            )
            
            structured_logger.log_agent_start("reference_request_writer", None)
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
                structured_logger.log_agent_complete("reference_request_writer", None, duration_ms)
                return self._create_filtered_result(response.get("response", ""), target_job_str)
            
            response_text = response.get("response", "")
            
            # Parse JSON response
            parsed = parse_json_from_llm_response(response_text)
            
            if not parsed:
                logger.error(
                    "Failed to parse reference request response: %s",
                    sanitize_log_value(response_text[:200]),
                )
                structured_logger.log_agent_error(
                    "reference_request_writer", None,
                    Exception("JSON parse failed"), duration_ms
                )
                return self._create_parse_error_result(response_text, target_job_str)
            
            structured_logger.log_agent_complete("reference_request_writer", None, duration_ms)
            
            return {
                "subject_line": parsed.get(
                    "subject_line",
                    f"Reference Request - {target_job_str}"
                ),
                "email_body": parsed.get("email_body", ""),
                "talking_points": parsed.get("talking_points", []),
                "follow_up_timeline": parsed.get(
                    "follow_up_timeline",
                    "Follow up in 1 week if no response"
                ),
                "tips": parsed.get("tips", []),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
            }
            
        except Exception as e:
            logger.error("Reference request generation failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

    def _create_filtered_result(
        self, filter_message: str, target_job: str
    ) -> Dict[str, Any]:
        """Create a result when content was filtered."""
        return {
            "subject_line": f"Reference Request - {target_job}",
            "email_body": "Content generation was filtered. Please try again with different input.",
            "talking_points": [],
            "follow_up_timeline": "Follow up in 1 week if no response",
            "tips": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "filtered": True,
            "filter_message": filter_message,
            "version": "1.0",
        }

    def _create_parse_error_result(
        self, raw_response: str, target_job: str
    ) -> Dict[str, Any]:
        """Create a result when JSON parsing failed."""
        return {
            "subject_line": f"Reference Request - {target_job}",
            "email_body": raw_response if len(raw_response) < 2000 else raw_response[:2000],
            "talking_points": [],
            "follow_up_timeline": "Follow up in 1 week if no response",
            "tips": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "parse_error": True,
            "version": "1.0",
        }
