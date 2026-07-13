"""
Salary Negotiation Coach Agent.
Generates personalized salary negotiation strategies and scripts.
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
LLM_TEMPERATURE = 0.6
LLM_MAX_TOKENS = 16000  # Unified agent output cap

# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SYSTEM_CONTEXT = """You are an expert salary negotiation coach with deep experience helping \
professionals at all levels secure better compensation packages. You understand market dynamics, \
negotiation psychology, and company perspectives. You write negotiation scripts that are \
word-for-word ready to say out loud — specific, assertive, and professional. \
NEVER use placeholder brackets like [X] or [your achievement] in any script. \
Every script line must be complete, natural-sounding prose tailored to the specific role and company.

YEARS OF EXPERIENCE RULE: The "Years of Experience" field is the candidate's TOTAL career years — NEVER use it as domain-specific experience in scripts. When referencing experience in a specific skill or domain (e.g. "X years of backend experience"), only do so if derivable from their actual work history. If uncertain, say "my experience in [skill]" without a specific year count."""

NEGOTIATION_PROMPT = """Generate a comprehensive salary negotiation strategy and scripts for this specific situation.

Job & Offer Details:
- Position: {job_title}
- Company: {company_name}
- Company Size: {company_size}
- Industry: {industry}
- Location: {location}
- Offered Base Salary: {offered_salary}
- Offered Benefits: {offered_benefits}

Candidate Profile:
- Years of Experience: {years_experience}
- Current/Previous Salary: {current_salary}
- Key Achievements: {achievements}
- Unique Value Propositions: {unique_value}
- Other Offers/Leverage: {other_offers}
- Urgency Level: {urgency}

Market Context:
- Target Salary Range: {target_range}
- Market Rate Information: {market_info}

Negotiation Parameters:
- Priority Areas: {priority_areas}
- Flexibility Areas: {flexibility_areas}
- Non-Negotiables: {non_negotiables}
- Negotiation Style Preference: {style_preference}

CRITICAL WRITING RULES — every rule is mandatory:
1. All script fields (opening, value_statement, counter_offer, closing, response_script) \
must be word-for-word ready to say. No placeholder text, no brackets like [X], \
no "mention your achievement here" style instructions.
2. Reference the actual company name ({company_name}) and role ({job_title}) in the scripts \
where natural — this makes them feel personal, not generic.
3. The recommended_target in market_analysis must be a specific dollar amount or range, \
not vague language like "market rate" — derive it from the offered salary and market context.
4. The walk_away_point must state specific conditions (e.g., concrete salary floor, \
equity threshold, timeline) — not vague advice.
5. Pushback scenarios must cover the 2-3 most likely objections for this specific \
company type and role, with a concrete response script for each.
6. Alternative asks must list realistic options with a specific dollar value or range.
7. MINIMUM ARRAY LENGTHS (non-negotiable): pushback_responses ≥ 3 items, \
alternative_asks ≥ 3 items, dos ≥ 4 items, donts ≥ 4 items.

Return your response as JSON with this exact structure:
{{
    "market_analysis": {{
        "salary_assessment": "Specific assessment of the offered salary vs market for this role/location",
        "market_position": "Where this offer falls — below/at/above market with context",
        "recommended_target": "Specific counter offer amount (e.g., $145,000)",
        "negotiation_room": "Estimated negotiation room with reasoning",
        "leverage_assessment": "Honest assessment of candidate's negotiating leverage"
    }},
    "strategy_overview": {{
        "approach": "Specific, named negotiation approach (2-3 sentences) tailored to this company",
        "key_messages": ["Concrete message 1", "Concrete message 2", "Concrete message 3"],
        "timing_recommendation": "Specific advice on when and how to initiate the conversation",
        "confidence_level": "HIGH / MEDIUM / LOW — with a one-sentence reason specific to this situation"
    }},
    "main_script": {{
        "opening": "Word-for-word opening line(s) — ready to say out loud, references the company/role",
        "value_statement": "Word-for-word value pitch — specific, no brackets, references their business impact",
        "counter_offer": "Word-for-word counter offer delivery — states specific number confidently",
        "closing": "Word-for-word closing — warm, collaborative, leaves the door open"
    }},
    "pushback_responses": [
        {{
            "scenario": "Specific pushback scenario title (e.g., 'Budget is frozen')",
            "response_script": "Word-for-word response — complete sentences, ready to say, no placeholders",
            "key_points": ["What this response accomplishes"]
        }}
    ],
    "alternative_asks": [
        {{
            "item": "Specific benefit to negotiate (e.g., Signing Bonus)",
            "value": "Dollar range (e.g., $10,000–$20,000)",
            "script": "Word-for-word ask for this alternative",
            "likelihood": "high/medium/low"
        }}
    ],
    "email_template": {{
        "subject": "Specific email subject line",
        "body": "Complete email body for written negotiation — no placeholders"
    }},
    "dos_and_donts": {{
        "dos": ["Specific, actionable do — tied to this situation"],
        "donts": ["Specific, consequential don't — tied to this situation"]
    }},
    "red_flags": ["Specific red flag that suggests walking away from this offer"],
    "walk_away_point": "Specific conditions: state the minimum salary, minimum equity %, and/or timeline that make this offer unacceptable — be quantitative",
    "final_tips": ["Concrete, situation-specific tip for closing the negotiation successfully"]
}}"""


# =============================================================================
# AGENT CLASS
# =============================================================================


class SalaryCoachAgent:
    """
    Agent for generating salary negotiation strategies and scripts.
    
    Provides personalized negotiation guidance based on job offer,
    candidate profile, and market conditions.
    """

    def __init__(self):
        """Initialize the SalaryCoachAgent."""
        self.gemini_client = None
        self._current_user_api_key: Optional[str] = None

    async def generate_strategy(
        self,
        job_title: str,
        company_name: str,
        offered_salary: str,
        years_experience: Optional[int] = None,
        additional_context: Optional[str] = None,
        location: Optional[str] = None,
        company_size: Optional[str] = None,
        industry: Optional[str] = None,
        offered_benefits: Optional[str] = None,
        current_salary: Optional[str] = None,
        achievements: Optional[List[str]] = None,
        unique_value: Optional[List[str]] = None,
        other_offers: Optional[str] = None,
        urgency: Optional[str] = None,
        target_range: Optional[str] = None,
        market_info: Optional[str] = None,
        priority_areas: Optional[List[str]] = None,
        flexibility_areas: Optional[List[str]] = None,
        non_negotiables: Optional[List[str]] = None,
        style_preference: Optional[str] = None,
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive salary negotiation strategy.
        
        Args:
            job_title: Position title
            company_name: Name of the company
            offered_salary: The salary offered
            years_experience: Years of relevant experience (optional, from profile)
            additional_context: Free-form additional info (target salary, achievements, etc.)
            location: Job location (for market context)
            company_size: Size of company (startup, mid-size, enterprise)
            industry: Industry sector
            offered_benefits: Description of offered benefits
            current_salary: Current or previous salary
            achievements: List of key achievements
            unique_value: List of unique value propositions
            other_offers: Description of other offers/leverage
            urgency: How urgently they need an answer
            target_range: Desired salary range
            market_info: Any market rate information
            priority_areas: What matters most to negotiate
            flexibility_areas: Where candidate can be flexible
            non_negotiables: Deal breakers
            style_preference: Preferred negotiation style
            user_api_key: Optional user API key for BYOK mode
            model: Optional BYOK preferred Gemini model from Settings
            
        Returns:
            Dict containing negotiation strategy and scripts
        """
        self._current_user_api_key = user_api_key
        self._current_user_model = model
        
        try:
            # Initialize Gemini client
            self.gemini_client = await get_gemini_client()
            
            # Format inputs with defaults
            location_str = location or "Not specified"
            company_size_str = company_size or "Not specified"
            industry_str = industry or "Not specified"
            offered_benefits_str = offered_benefits or "Standard benefits"
            current_salary_str = current_salary or "Not disclosed"
            achievements_str = ", ".join(achievements) if achievements else "Not specified"
            unique_value_str = ", ".join(unique_value) if unique_value else "Not specified"
            other_offers_str = other_offers or "None disclosed"
            urgency_str = urgency or "Normal timeline"
            target_range_str = target_range or "Market rate"
            market_info_str = market_info or "Use general market knowledge"
            priority_areas_str = ", ".join(priority_areas) if priority_areas else "Base salary"
            flexibility_areas_str = ", ".join(flexibility_areas) if flexibility_areas else "Open to discussion"
            non_negotiables_str = ", ".join(non_negotiables) if non_negotiables else "None specified"
            style_str = style_preference or "Professional and assertive"
            years_exp_str = str(years_experience) if years_experience is not None else "Not specified"
            
            # Add additional context if provided
            additional_info = ""
            if additional_context:
                additional_info = f"\n\nAdditional Context from Candidate:\n{additional_context}"
            
            # Build prompt
            prompt = NEGOTIATION_PROMPT.format(
                job_title=job_title,
                company_name=company_name,
                company_size=company_size_str,
                industry=industry_str,
                location=location_str,
                offered_salary=offered_salary,
                offered_benefits=offered_benefits_str,
                years_experience=years_exp_str,
                current_salary=current_salary_str,
                achievements=achievements_str,
                unique_value=unique_value_str,
                other_offers=other_offers_str,
                urgency=urgency_str,
                target_range=target_range_str,
                market_info=market_info_str,
                priority_areas=priority_areas_str,
                flexibility_areas=flexibility_areas_str,
                non_negotiables=non_negotiables_str,
                style_preference=style_str,
            ) + additional_info
            
            structured_logger.log_agent_start("salary_coach", None)
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
                structured_logger.log_agent_complete("salary_coach", None, duration_ms)
                return self._create_filtered_result(response.get("response", ""))
            
            response_text = response.get("response", "")
            
            # Parse JSON response
            parsed = parse_json_from_llm_response(response_text)
            
            if not parsed:
                logger.error("Failed to parse salary coach response: %s", sanitize_log_value(response_text[:200]))
                structured_logger.log_agent_error(
                    "salary_coach", None, 
                    Exception("JSON parse failed"), duration_ms
                )
                return self._create_parse_error_result(response_text, job_title)
            
            structured_logger.log_agent_complete("salary_coach", None, duration_ms)
            
            return {
                "market_analysis": parsed.get("market_analysis", {}),
                "strategy_overview": parsed.get("strategy_overview", {}),
                "main_script": parsed.get("main_script", {}),
                "pushback_responses": parsed.get("pushback_responses", []),
                "alternative_asks": parsed.get("alternative_asks", []),
                "email_template": parsed.get("email_template", {}),
                "dos_and_donts": parsed.get("dos_and_donts", {"dos": [], "donts": []}),
                "red_flags": parsed.get("red_flags", []),
                "walk_away_point": parsed.get("walk_away_point", ""),
                "final_tips": parsed.get("final_tips", []),
                "job_title": job_title,
                "company_name": company_name,
                "offered_salary": offered_salary,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0",
            }
            
        except Exception as e:
            logger.error("Salary negotiation strategy generation failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

    def _create_filtered_result(self, filter_message: str) -> Dict[str, Any]:
        """Create a result when content was filtered."""
        return {
            "market_analysis": {},
            "strategy_overview": {
                "approach": "Content generation was filtered",
                "key_messages": [],
                "timing_recommendation": "Please try again",
                "confidence_level": "low"
            },
            "main_script": {},
            "pushback_responses": [],
            "alternative_asks": [],
            "email_template": {},
            "dos_and_donts": {"dos": [], "donts": []},
            "red_flags": [],
            "walk_away_point": "",
            "final_tips": ["Please try again with different input"],
            "filtered": True,
            "filter_message": filter_message,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }

    def _create_parse_error_result(
        self, raw_response: str, job_title: str
    ) -> Dict[str, Any]:
        """Create a result when JSON parsing failed."""
        return {
            "market_analysis": {},
            "strategy_overview": {
                "approach": "See raw analysis below",
                "key_messages": [],
                "timing_recommendation": "Review the analysis",
                "confidence_level": "low"
            },
            "main_script": {
                "opening": raw_response[:2000] if len(raw_response) > 2000 else raw_response
            },
            "pushback_responses": [],
            "alternative_asks": [],
            "email_template": {},
            "dos_and_donts": {"dos": [], "donts": []},
            "red_flags": [],
            "walk_away_point": "",
            "final_tips": ["Review the raw analysis for guidance"],
            "job_title": job_title,
            "parse_error": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
        }
