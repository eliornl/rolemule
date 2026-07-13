"""
Follow-up Email Generator Agent.
Generates personalized follow-up emails for different stages of the job application process.
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

# Follow-up stages
FOLLOWUP_STAGES = [
    "after_application",
    "after_phone_screen",
    "after_interview",
    "after_final_round",
    "no_response",
    "after_rejection",
    "after_offer",
]

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SYSTEM_CONTEXT = """You are an expert career coach specializing in professional communication \
during the job search process. You write complete, polished follow-up emails that are \
ready to send immediately — no placeholders, no fill-in-the-blank markers, no brackets \
of any kind. Every email you produce is specific, confident, and leaves a lasting positive impression."""

FOLLOWUP_PROMPT = """Generate a complete, ready-to-send professional follow-up email for a job application.

Context:
- Stage: {stage}
- Company: {company_name}
- Position: {job_title}
- Contact Person: {contact_name} {contact_role}
- Days Since Last Contact: {days_since_contact}
- Previous Interactions: {previous_interactions}
- Key Points to Mention: {key_points}
- Sender's Name: {user_name}

Stage-Specific Guidelines:
{stage_guidelines}

CRITICAL WRITING RULES — every rule is mandatory:
1. Write a COMPLETE, polished email that is 100% ready to send. Zero placeholder text.
2. NEVER use square brackets like [mention X], [specific detail], [your achievement], \
or any fill-in-the-blank markers. If you do not have a specific detail, write naturally \
around the gap — omit the reference entirely rather than inserting a bracket.
3. Every sentence must be final, concrete prose. No example text, no italicised suggestions.
4. Keep the body under 150 words. Every sentence must earn its place.
5. Address the contact by FIRST NAME ONLY in the greeting (e.g., "Hi Jack," or "Dear Jack," — never use the full name like "Dear Jack Dennis,").
6. Sign off with "{user_name}" at the end.
7. Subject line must be specific to this role and company — not generic.
8. If Key Points to Mention are provided, weave them naturally into the email. \
If none are provided, draw on the company name and role to write something specific and genuine.

Return your response as JSON with this exact structure:
{{
    "subject_line": "Specific, role-focused subject line",
    "email_body": "Complete, polished email body — no placeholders whatsoever",
    "key_elements": ["What makes this email effective"],
    "tone": "professional/warm/enthusiastic/empathetic",
    "timing_advice": "Specific best time/day to send this email and why",
    "next_steps": "Specific action to take if no response within a defined timeframe",
    "alternative_subject": "Alternative subject line option"
}}"""

STAGE_GUIDELINES = {
    "after_application": """
- Purpose: Confirm application receipt and express interest
- Tone: Professional, enthusiastic
- Timing: 3-5 business days after applying
- Focus: Reiterate qualifications, show research about company
- Avoid: Being pushy, asking for timeline prematurely
""",
    "after_phone_screen": """
- Purpose: Thank them and reinforce fit
- Tone: Warm, professional
- Timing: Within 24 hours
- Focus: Reference specific points discussed, address any concerns
- Avoid: Repeating your entire resume
""",
    "after_interview": """
- Purpose: Express gratitude, reinforce interest
- Tone: Warm, enthusiastic
- Timing: Within 24 hours
- Focus: Reference memorable moments, address any questions left open
- Avoid: Being too casual or presumptuous
""",
    "after_final_round": """
- Purpose: Strong close, express commitment
- Tone: Confident, enthusiastic
- Timing: Within 24 hours
- Focus: Summarize why you're the ideal fit, express excitement
- Avoid: Pressuring for a decision
""",
    "no_response": """
- Purpose: Gentle check-in on status
- Tone: Understanding, professional
- Timing: 5-7 business days after expected response
- Focus: Brief, add value if possible, make it easy to respond
- Avoid: Guilt-tripping, being passive-aggressive
""",
    "after_rejection": """
- Purpose: Maintain relationship for future opportunities
- Tone: Gracious, professional
- Timing: Within 48 hours
- Focus: Thank them, ask for feedback (optional), express future interest
- Avoid: Arguing, being bitter, over-explaining
""",
    "after_offer": """
- Purpose: Express gratitude, clarify next steps
- Tone: Excited, professional
- Timing: Within 24 hours
- Focus: Thank them, confirm timeline for response, ask clarifying questions
- Avoid: Negotiating in this email (do that separately)
""",
}


# =============================================================================
# AGENT CLASS
# =============================================================================


class FollowUpGeneratorAgent:
    """
    Agent for generating follow-up emails at various stages of job applications.
    
    Supports multiple stages from initial application through offer,
    with stage-appropriate tone and content.
    """

    def __init__(self):
        """Initialize the FollowUpGeneratorAgent."""
        self.gemini_client = None
        self._current_user_api_key: Optional[str] = None

    async def generate(
        self,
        stage: str,
        company_name: str,
        job_title: str,
        contact_name: Optional[str] = None,
        contact_role: Optional[str] = None,
        days_since_contact: Optional[int] = None,
        previous_interactions: Optional[str] = None,
        key_points: Optional[List[str]] = None,
        user_name: Optional[str] = None,
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a follow-up email for a specific stage.
        
        Args:
            stage: Stage of follow-up (after_application, after_interview, etc.)
            company_name: Name of the company
            job_title: Position applied for
            contact_name: Optional name of contact person
            contact_role: Optional role of contact person
            days_since_contact: Optional days since last interaction
            previous_interactions: Optional description of previous interactions
            key_points: Optional list of key points to mention
            user_name: Optional user's name for sign-off
            user_api_key: Optional user API key for BYOK mode
            model: Optional BYOK preferred Gemini model from Settings
            
        Returns:
            Dict containing email content and guidance
        """
        self._current_user_api_key = user_api_key
        self._current_user_model = model
        
        # Validate stage
        if stage not in FOLLOWUP_STAGES:
            raise ValueError(f"Invalid stage. Must be one of: {FOLLOWUP_STAGES}")
        
        try:
            # Initialize Gemini client
            self.gemini_client = await get_gemini_client()
            
            # Format inputs
            contact_role_str = f"({contact_role})" if contact_role else ""
            days_str = f"{days_since_contact} days" if days_since_contact else "Not specified"
            interactions_str = previous_interactions if previous_interactions else "Initial contact"
            key_points_str = ", ".join(key_points) if key_points else "None specified"
            user_name_str = user_name if user_name else "[Your Name]"
            
            # Get stage guidelines
            stage_guidelines = STAGE_GUIDELINES.get(stage, "General follow-up")
            
            # Format stage for display
            stage_display = stage.replace("_", " ").title()
            
            # Build prompt
            prompt = FOLLOWUP_PROMPT.format(
                stage=stage_display,
                company_name=company_name,
                job_title=job_title,
                contact_name=contact_name or "Hiring Manager",
                contact_role=contact_role_str,
                days_since_contact=days_str,
                previous_interactions=interactions_str,
                key_points=key_points_str,
                user_name=user_name_str,
                stage_guidelines=stage_guidelines,
            )
            
            structured_logger.log_agent_start("followup_generator", None)
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
                structured_logger.log_agent_complete("followup_generator", None, duration_ms)
                return self._create_filtered_result(response.get("response", ""), stage)
            
            response_text = response.get("response", "")
            
            # Parse JSON response
            parsed = parse_json_from_llm_response(response_text)
            
            if not parsed:
                logger.error("Failed to parse follow-up response: %s", sanitize_log_value(response_text[:200]))
                structured_logger.log_agent_error(
                    "followup_generator", None, 
                    Exception("JSON parse failed"), duration_ms
                )
                return self._create_parse_error_result(response_text, stage, job_title)
            
            structured_logger.log_agent_complete("followup_generator", None, duration_ms)
            
            return {
                "subject_line": parsed.get(
                    "subject_line", 
                    f"Following up - {job_title} application"
                ),
                "email_body": parsed.get("email_body", ""),
                "key_elements": parsed.get("key_elements", []),
                "tone": parsed.get("tone", "professional"),
                "timing_advice": parsed.get("timing_advice", "Send during business hours"),
                "next_steps": parsed.get("next_steps", "Wait 5-7 days before following up again"),
                "alternative_subject": parsed.get("alternative_subject", ""),
                "stage": stage,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
            }
            
        except Exception as e:
            logger.error("Follow-up generation failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

    def _create_filtered_result(self, filter_message: str, stage: str) -> Dict[str, Any]:
        """Create a result when content was filtered."""
        return {
            "subject_line": "Following up on my application",
            "email_body": "Content generation was filtered. Please try again with different input.",
            "key_elements": [],
            "tone": "professional",
            "timing_advice": "Send during business hours",
            "next_steps": "Wait before following up again",
            "alternative_subject": "",
            "stage": stage,
            "filtered": True,
            "filter_message": filter_message,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }

    def _create_parse_error_result(
        self, raw_response: str, stage: str, job_title: str
    ) -> Dict[str, Any]:
        """Create a result when JSON parsing failed."""
        return {
            "subject_line": f"Following up - {job_title} application",
            "email_body": raw_response if len(raw_response) < 2000 else raw_response[:2000],
            "key_elements": [],
            "tone": "professional",
            "timing_advice": "Send during business hours",
            "next_steps": "Wait 5-7 days before following up again",
            "alternative_subject": "",
            "stage": stage,
            "parse_error": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }

    @staticmethod
    def get_available_stages() -> List[Dict[str, str]]:
        """Get list of available follow-up stages with descriptions."""
        return [
            {"id": "after_application", "name": "After Application", 
             "description": "Follow up after submitting your application"},
            {"id": "after_phone_screen", "name": "After Phone Screen",
             "description": "Thank you and follow up after initial phone call"},
            {"id": "after_interview", "name": "After Interview",
             "description": "Post-interview thank you and reinforcement"},
            {"id": "after_final_round", "name": "After Final Round",
             "description": "Strong close after final interview"},
            {"id": "no_response", "name": "No Response Check-in",
             "description": "Gentle check-in when you haven't heard back"},
            {"id": "after_rejection", "name": "After Rejection",
             "description": "Gracious response to maintain relationship"},
            {"id": "after_offer", "name": "After Offer",
             "description": "Acknowledge offer and clarify next steps"},
        ]
