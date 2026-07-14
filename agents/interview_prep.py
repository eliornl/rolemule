"""
Agent for generating personalized interview preparation materials.
Generates unique content NOT covered by other agents: predicted questions,
answer frameworks using STAR method, how to address concerns, and logistics.

This agent is standalone and NOT part of the main LangGraph workflow.
It's called on-demand when a user requests interview preparation.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from utils.llm_client import get_llm_client, get_gemini_client  # test-patch alias
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import get_structured_logger

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# LLM Configuration
LLM_TEMPERATURE: float = 0.4  # Slightly creative for question generation
LLM_MAX_TOKENS: int = 16000  # Unified agent output cap

# =============================================================================
# PROMPTS
# =============================================================================

SYSTEM_CONTEXT: str = """You are an elite interview coach with 20+ years of experience helping candidates succeed in interviews across ALL industries worldwide.

## YOUR EXPERTISE INCLUDES:

**Interview Psychology:**
- You understand what interviewers REALLY want to hear (often different from the literal question)
- You know that interviews test communication and thinking, not just knowledge
- You can predict exactly which questions will be asked based on job requirements and company culture
- You understand the difference between screening calls, technical interviews, and final rounds

**Question Prediction Mastery:**
- You know the top 50 questions asked in every industry
- You can predict company-specific questions based on their values and culture
- You recognize which skill gaps will trigger probing questions
- You know behavioral questions test past behavior as predictor of future performance

**Answer Coaching:**
- You're an expert in the STAR method (Situation, Task, Action, Result)
- You know how to turn weaknesses into strengths without being fake
- You understand that specific stories beat generic claims every time
- You can help candidates articulate their value in memorable ways

**Strategic Preparation:**
- You know questions to ask that impress interviewers
- You understand salary negotiation psychology
- You know how to address concerns proactively before they're raised
- You understand that preparation reduces anxiety and improves performance

## YOUR PRINCIPLES:
- Generate SPECIFIC questions likely to be asked (not generic lists)
- Create answer frameworks using the candidate's ACTUAL experiences
- Address concerns the interviewer will have based on profile gaps
- Provide actionable, not theoretical, advice
- Be honest about weaknesses but always provide strategies to address them
- Remember: the goal is to help the candidate succeed while being authentic
- YEARS OF EXPERIENCE RULE: The "Years Experience" field is TOTAL career years — NEVER use it as domain-specific experience. When advising the candidate to highlight "X years of [skill/domain]", derive that number only from the relevant work history entries. If you cannot calculate domain-specific years from the work history, say "your experience with [skill]" without claiming a specific count.

## WHAT YOU DO NOT REPEAT:
- Do NOT repeat company information (already in company research)
- Do NOT list job requirements (already in job analysis)
- Do NOT analyze profile gaps (already in profile matching)
- Do NOT give resume advice (already in resume advisor)
- DO generate interview-specific content: questions, answers, strategies"""

INTERVIEW_PREP_PROMPT: str = """Generate comprehensive interview preparation materials for this candidate and job.

=== JOB INFORMATION ===
{job_info}

=== COMPANY RESEARCH ===
{company_info}

=== CANDIDATE PROFILE ===
{profile_info}

=== PROFILE MATCHING INSIGHTS ===
{matching_insights}

=== YOUR TASK ===
Generate personalized interview preparation that helps this specific candidate succeed in interviews for this specific job. Use their actual experiences to create answer frameworks.

IMPORTANT: Your response must be ONLY the JSON object below. No explanations, no markdown, no text before or after. Start with {{ and end with }}.

=== REQUIRED JSON OUTPUT FORMAT ===

{{
    "interview_process": {{
        "typical_rounds": [
            {{
                "round": 1,
                "type": "<Phone Screen | Technical | Behavioral | Panel | Case Study | etc.>",
                "duration": "<estimated duration>",
                "with": "<who they'll meet: Recruiter, Hiring Manager, Team Members, etc.>",
                "focus": "<what this round evaluates>",
                "tips": "<specific tip for this round>"
            }}
        ],
        "total_timeline": "<typical time from first interview to offer>",
        "preparation_time_needed": "<how long to prepare>",
        "format_prediction": "<virtual, onsite, or hybrid based on company/role>"
    }},
    
    "predicted_questions": {{
        "behavioral": [
            {{
                "question": "<specific behavioral question likely to be asked>",
                "why_likely": "<why this question based on job/company>",
                "your_story": {{
                    "use_this_experience": "<which experience from their profile to use>",
                    "situation": "<how to describe the situation>",
                    "task": "<what was the task/challenge>",
                    "action": "<what actions to highlight>",
                    "result": "<what results to emphasize>"
                }},
                "what_they_evaluate": "<what the interviewer is looking for>",
                "danger_zone": "<what NOT to say>"
            }}
        ],
        "technical": [
            {{
                "question": "<specific technical question based on job requirements>",
                "why_likely": "<why this will be asked>",
                "preparation_approach": "<how to prepare for this>",
                "key_points_to_cover": ["<point 1>", "<point 2>"],
                "follow_up_questions": ["<likely follow-up 1>"]
            }}
        ],
        "role_specific": [
            {{
                "question": "<question specific to this role/level>",
                "why_likely": "<context>",
                "answer_strategy": "<how to approach this>",
                "incorporate_your_experience": "<which experience to reference>"
            }}
        ],
        "company_specific": [
            {{
                "question": "<question about this specific company>",
                "why_likely": "<based on company values/culture>",
                "personalized_answer": "<answer incorporating research>"
            }}
        ]
    }},
    
    "addressing_concerns": [
        {{
            "concern": "<specific concern based on profile gaps>",
            "why_its_a_concern": "<what the interviewer might think>",
            "your_counter_narrative": "<the reframing strategy>",
            "talking_points": ["<specific point 1>", "<specific point 2>"],
            "proof_points_from_experience": ["<evidence from their background>"],
            "when_to_bring_up": "<proactively or only if asked>"
        }}
    ],
    
    "questions_for_them": {{
        "for_recruiter": [
            {{
                "question": "<question to ask recruiter>",
                "why_good": "<what it shows/reveals>",
                "listen_for": "<what their answer tells you>"
            }}
        ],
        "for_hiring_manager": [
            {{
                "question": "<question for hiring manager>",
                "why_good": "<demonstrates what>",
                "listen_for": "<red/green flags in answer>"
            }}
        ],
        "for_team_members": [
            {{
                "question": "<question for potential teammates>",
                "why_good": "<what it reveals>",
                "listen_for": "<what to notice>"
            }}
        ],
        "red_flag_questions": [
            {{
                "question": "<question to assess potential issues>",
                "when_to_ask": "<timing/context>",
                "what_youre_checking": "<concern being validated>"
            }}
        ]
    }},
    
    "logistics": {{
        "dress_code": "<recommendation based on company culture>",
        "what_to_bring": ["<item 1>", "<item 2>"],
        "timing": {{
            "arrive": "<when to arrive>",
            "expected_duration": "<how long to block>"
        }},
        "virtual_interview_tips": [
            "<tip 1 if virtual>",
            "<tip 2>"
        ],
        "post_interview": {{
            "thank_you_note": "<guidance on follow-up>",
            "follow_up_timeline": "<when to follow up if no response>"
        }}
    }},
    
    "quick_reference_card": {{
        "elevator_pitch": "<30-second pitch tailored to this role>",
        "three_key_selling_points": [
            "<selling point 1 with specific evidence>",
            "<selling point 2>",
            "<selling point 3>"
        ],
        "weakness_answer": {{
            "weakness": "<genuine but not damaging weakness>",
            "how_addressing": "<what you're doing about it>",
            "example": "<brief example>"
        }},
        "why_this_company": "<compelling, personalized answer>",
        "why_leaving_current": "<safe answer if applicable>",
        "salary_discussion": {{
            "anchor_range": "<suggested range to state>",
            "strategy": "<how to handle the conversation>",
            "deflection_phrase": "<what to say if asked too early>"
        }},
        "closing_statement": "<strong closing for end of interview>"
    }},
    
    "day_before_checklist": [
        "<preparation task 1>",
        "<preparation task 2>",
        "<preparation task 3>",
        "<preparation task 4>",
        "<preparation task 5>"
    ],
    
    "confidence_boosters": [
        "<reminder of strength 1>",
        "<reminder of strength 2>",
        "<reminder of achievement>"
    ]
}}

## GENERATION RULES:

1. **Use Their Actual Experiences**: For behavioral questions, reference specific jobs, projects, or achievements from their profile - don't make things up.

2. **Company-Specific Insights**: Use company research to predict questions about their values, challenges, and culture.

3. **Address Real Gaps**: Look at profile matching to identify concerns interviewers will have, then provide strategies to address them.

4. **Be Specific**: "Tell me about a time you led a project" is generic. "Tell me about leading a cross-functional initiative, given your experience at [Company X]" is specific.

5. **STAR Framework**: For behavioral questions, create complete STAR answers using their actual experiences.

6. **Balanced Questions**: Include questions that help the candidate evaluate if this is the right fit for them, not just impress the interviewer.

7. **Practical Logistics**: Dress code and timing should reflect the company culture from research.

8. **Quick Reference**: The quick_reference_card should be something they can review 5 minutes before walking in.

9. **Confidence Building**: End with genuine strengths to boost confidence.

10. **No Repetition**: Don't repeat information already available in job analysis, company research, or profile matching - focus on interview-specific preparation."""


class InterviewPrepAgent:
    """
    Generates personalized interview preparation materials.
    
    This agent is NOT part of the main LangGraph workflow - it's called on-demand
    when a user requests interview preparation for a completed application.
    
    It generates content that is UNIQUE and not covered by other agents:
    - Predicted interview questions (not just topics)
    - Answer frameworks using STAR method with user's actual experiences
    - How to address specific concerns from profile gaps
    - Questions to ask the interviewer
    - Interview logistics and preparation tips
    """

    def __init__(self) -> None:
        """Initialize Interview Prep Agent."""
        self.gemini_client = None
        self._current_user_api_key: Optional[str] = None

    async def generate(
        self,
        job_analysis: Dict[str, Any],
        company_research: Dict[str, Any],
        profile_matching: Dict[str, Any],
        user_profile: Dict[str, Any],
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate interview preparation materials.
        
        Args:
            job_analysis: Job analysis results from workflow
            company_research: Company research results from workflow
            profile_matching: Profile matching results (for gaps/concerns)
            user_profile: User's profile data
            user_api_key: Optional user API key (BYOK mode)
            model: Optional BYOK preferred Gemini model from Settings
            
        Returns:
            Interview preparation materials dictionary
            
        Raises:
            ValueError: If required data is missing
            Exception: If LLM generation fails
        """
        structured_logger.log_agent_start("interview_prep", None)
        start_time = datetime.now(timezone.utc)
        
        self._current_user_api_key = user_api_key
        self._current_llm_provider = llm_provider
        self.gemini_client = await get_llm_client()
        
        try:
            # Format inputs for LLM
            formatted_inputs = self._format_inputs(
                job_analysis, company_research, profile_matching, user_profile
            )
            
            # Build prompt
            prompt = INTERVIEW_PREP_PROMPT.format(**formatted_inputs)
            
            # Generate interview prep
            response = await self.gemini_client.generate(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=self._current_user_api_key,
                model=model,
                provider=getattr(self, "_current_llm_provider", None),
            )
            
            # Handle filtered response
            if response.get("filtered"):
                logger.warning("Interview prep response was filtered by safety settings")
                return self._create_filtered_result(response.get("response", ""))
            
            # Parse response
            response_text = response.get("response", "")
            result = parse_json_from_llm_response(response_text)
            
            if not result:
                logger.error("Failed to parse interview prep response as JSON")
                return self._create_parse_error_result(response_text)
            
            # Add metadata
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            duration_ms = processing_time * 1000
            result["generated_at"] = datetime.now(timezone.utc).isoformat()
            result["processing_time"] = processing_time
            result["version"] = 1
            
            structured_logger.log_agent_complete("interview_prep", None, duration_ms)
            return result
            
        except Exception as e:
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            duration_ms = processing_time * 1000
            structured_logger.log_agent_error("interview_prep", None, e, duration_ms)
            raise

    def _format_inputs(
        self,
        job_analysis: Dict[str, Any],
        company_research: Dict[str, Any],
        profile_matching: Dict[str, Any],
        user_profile: Dict[str, Any],
    ) -> Dict[str, str]:
        """
        Format all inputs for LLM prompt.
        
        Args:
            job_analysis: Job analysis data
            company_research: Company research data
            profile_matching: Profile matching data
            user_profile: User profile data
            
        Returns:
            Dictionary of formatted strings for prompt substitution
        """
        return {
            "job_info": self._format_job_info(job_analysis),
            "company_info": self._format_company_info(company_research),
            "profile_info": self._format_profile_info(user_profile),
            "matching_insights": self._format_matching_insights(profile_matching),
        }

    def _format_job_info(self, job: Dict[str, Any]) -> str:
        """Format job analysis for LLM."""
        if not job:
            return "No job analysis available."
        
        # Basic info
        sections = [f"""
### JOB OVERVIEW
- Title: {job.get('job_title', 'Not specified')}
- Company: {job.get('company_name', 'Not specified')}
- Location: {job.get('job_city', 'N/A')}, {job.get('job_state', 'N/A')}, {job.get('job_country', 'N/A')}
- Work Arrangement: {job.get('work_arrangement', 'Not specified')}
- Employment Type: {job.get('employment_type', 'Not specified')}
- Industry: {job.get('industry', 'Not specified')}
- Years Required: {job.get('years_experience_required', 'Not specified')}
"""]
        
        # Required skills
        required_skills = job.get('required_skills', [])
        if required_skills:
            sections.append(f"\n### REQUIRED SKILLS\n{', '.join(required_skills)}")
        
        # Soft skills
        soft_skills = job.get('soft_skills', [])
        if soft_skills:
            sections.append(f"\n### SOFT SKILLS\n{', '.join(soft_skills)}")
        
        # Responsibilities
        responsibilities = job.get('responsibilities', [])
        if responsibilities:
            resp_list = '\n'.join([f"- {r}" for r in responsibilities[:8]])
            sections.append(f"\n### KEY RESPONSIBILITIES\n{resp_list}")
        
        # Qualifications
        required_quals = job.get('required_qualifications', [])
        if required_quals:
            qual_list = '\n'.join([f"- {q}" for q in required_quals[:5]])
            sections.append(f"\n### REQUIRED QUALIFICATIONS\n{qual_list}")
        
        return ''.join(sections)

    def _format_company_info(self, company: Dict[str, Any]) -> str:
        """Format company research for LLM."""
        if not company:
            return "No company research available."
        
        sections = [f"""
### COMPANY BASICS
- Industry: {company.get('industry', 'N/A')}
- Size: {company.get('company_size', 'N/A')}
- Headquarters: {company.get('headquarters', 'N/A')}
"""]
        
        # Culture
        core_values = company.get('core_values', [])
        if core_values:
            sections.append(f"\n### CORE VALUES\n{', '.join(core_values[:5])}")
        
        work_environment = company.get('work_environment')
        if work_environment:
            sections.append(f"\n### WORK ENVIRONMENT\n{work_environment}")
        
        # Interview process (important for prep)
        interview_process = company.get('typical_interview_process', [])
        if interview_process:
            process_list = '\n'.join([f"- {step}" for step in interview_process])
            sections.append(f"\n### TYPICAL INTERVIEW PROCESS\n{process_list}")
        
        interview_format = company.get('interview_format')
        if interview_format:
            sections.append(f"\n### INTERVIEW FORMAT\n{interview_format}")
        
        # Application insights
        app_insights = company.get('application_insights', {})
        if app_insights:
            what_to_emphasize = app_insights.get('what_to_emphasize', [])
            if what_to_emphasize:
                sections.append(f"\n### WHAT TO EMPHASIZE\n{', '.join(what_to_emphasize)}")
            
            culture_fit = app_insights.get('culture_fit_signals', [])
            if culture_fit:
                sections.append(f"\n### CULTURE FIT SIGNALS\n{', '.join(culture_fit)}")
        
        return ''.join(sections)

    def _format_profile_info(self, profile: Dict[str, Any]) -> str:
        """Format user profile for LLM."""
        if not profile:
            return "No profile available."
        
        # Basic info
        sections = [f"""
### CANDIDATE BASICS
- Name: {profile.get('full_name', 'N/A')}
- Title: {profile.get('professional_title', 'N/A')}
- Years Experience: {profile.get('years_experience', 0)}
- Location: {profile.get('city', 'N/A')}, {profile.get('state', 'N/A')}, {profile.get('country', 'N/A')}
"""]
        
        # Summary
        summary = profile.get('summary')
        if summary:
            sections.append(f"\n### PROFESSIONAL SUMMARY\n{summary}")
        
        # Skills
        skills = profile.get('skills', [])
        if skills:
            sections.append(f"\n### SKILLS\n{', '.join(skills)}")
        
        # Work experience (crucial for STAR answers)
        work_exp = profile.get('work_experience', [])
        if work_exp:
            sections.append("\n### WORK EXPERIENCE (for STAR answers)")
            for i, exp in enumerate(work_exp[:4], 1):  # Limit to 4 most recent
                job_title = exp.get('job_title', 'N/A')
                company = exp.get('company', 'N/A')
                start = exp.get('start_date', 'N/A')
                end = exp.get('end_date', 'Present') if exp.get('is_current') else exp.get('end_date', 'N/A')
                description = exp.get('description', 'No description')
                
                sections.append(f"""
**Experience {i}: {job_title} at {company}**
- Duration: {start} to {end}
- Description: {description[:500]}
""")
        
        edu_rows = profile.get("education", []) or []
        if edu_rows:
            sections.append("\n### EDUCATION")
            for i, edu in enumerate(edu_rows[:4], 1):
                inst = edu.get("institution", "N/A")
                deg = edu.get("degree", "N/A")
                fos = edu.get("field_of_study") or ""
                start = edu.get("start_date", "N/A")
                end = (
                    "Present"
                    if edu.get("is_current")
                    else (edu.get("end_date") or "N/A")
                )
                line = f"**Education {i}: {deg} — {inst}** ({start} to {end})"
                if fos:
                    line += f"\n- Field: {fos}"
                sections.append(line)
        
        return ''.join(sections)

    def _format_matching_insights(self, matching: Dict[str, Any]) -> str:
        """Format profile matching insights for addressing concerns."""
        if not matching:
            return "No matching analysis available."
        
        sections = []
        
        # Executive summary
        exec_summary = matching.get('executive_summary', {})
        if exec_summary:
            sections.append(f"""
### OVERALL FIT
- Recommendation: {exec_summary.get('recommendation', 'N/A')}
- Fit Assessment: {exec_summary.get('fit_assessment', 'N/A')}
""")
        
        # Skills gaps (important for addressing concerns)
        qual_analysis = matching.get('qualification_analysis', {})
        skills_assessment = qual_analysis.get('skills_assessment', {})
        
        missing_skills = skills_assessment.get('missing_critical_skills', [])
        if missing_skills:
            skills_list = '\n'.join([
                f"- {s.get('skill', 'N/A')} ({s.get('importance', 'N/A')})"
                for s in missing_skills[:5]
            ])
            sections.append(f"\n### SKILL GAPS TO ADDRESS\n{skills_list}")
        
        # Experience gaps
        exp_assessment = qual_analysis.get('experience_assessment', {})
        years_eval = exp_assessment.get('years_evaluation', {})
        if years_eval:
            sections.append(f"""
### EXPERIENCE ASSESSMENT
- Candidate Years: {years_eval.get('candidate_years', 'N/A')}
- Required Years: {years_eval.get('required_years', 'N/A')}
- Assessment: {years_eval.get('assessment', 'N/A')}
""")
        
        # Deal breakers to address
        deal_breaker = matching.get('deal_breaker_analysis', {})
        found_breakers = deal_breaker.get('deal_breakers_found', [])
        if found_breakers:
            breakers_list = '\n'.join([
                f"- {b.get('issue', 'N/A')} ({b.get('severity', 'N/A')})"
                for b in found_breakers
            ])
            sections.append(f"\n### CONCERNS TO ADDRESS\n{breakers_list}")
        
        # Risk assessment
        risk = matching.get('risk_assessment', {})
        candidate_risks = risk.get('candidate_risks', [])
        if candidate_risks:
            risks_list = '\n'.join([
                f"- {r.get('risk', 'N/A')}"
                for r in candidate_risks[:3]
            ])
            sections.append(f"\n### EMPLOYER CONCERNS TO PROACTIVELY ADDRESS\n{risks_list}")
        
        # Strengths (for confidence)
        comp_positioning = matching.get('competitive_positioning', {})
        strengths = comp_positioning.get('strengths_vs_typical_applicant', [])
        if strengths:
            sections.append(f"\n### STRENGTHS TO LEVERAGE\n{', '.join(strengths)}")
        
        uvp = comp_positioning.get('unique_value_proposition')
        if uvp:
            sections.append(f"\n### UNIQUE VALUE PROPOSITION\n{uvp}")
        
        return ''.join(sections) if sections else "No specific matching insights available."

    def _create_filtered_result(self, message: str) -> Dict[str, Any]:
        """
        Create fallback result when content is filtered by safety settings.
        
        Args:
            message: Message from the safety filter
            
        Returns:
            Basic interview prep structure with filter notice
        """
        return {
            "interview_process": {
                "typical_rounds": [],
                "total_timeline": "Unable to generate - content filtered",
                "preparation_time_needed": "N/A",
                "format_prediction": "N/A"
            },
            "predicted_questions": {
                "behavioral": [],
                "technical": [],
                "role_specific": [],
                "company_specific": []
            },
            "addressing_concerns": [],
            "questions_for_them": {
                "for_recruiter": [],
                "for_hiring_manager": [],
                "for_team_members": [],
                "red_flag_questions": []
            },
            "logistics": {
                "dress_code": "Business casual recommended",
                "what_to_bring": ["Resume copies", "Notebook", "Pen"],
                "timing": {"arrive": "10 minutes early", "expected_duration": "1 hour"},
                "virtual_interview_tips": [],
                "post_interview": {"thank_you_note": "Send within 24 hours", "follow_up_timeline": "1 week"}
            },
            "quick_reference_card": {
                "elevator_pitch": "Content could not be generated due to filtering",
                "three_key_selling_points": [],
                "weakness_answer": {"weakness": "", "how_addressing": "", "example": ""},
                "why_this_company": "",
                "why_leaving_current": "",
                "salary_discussion": {"anchor_range": "", "strategy": "", "deflection_phrase": ""},
                "closing_statement": ""
            },
            "day_before_checklist": [
                "Review your resume",
                "Research the company",
                "Prepare questions to ask",
                "Plan your outfit",
                "Get a good night's sleep"
            ],
            "confidence_boosters": [],
            "filtered": True,
            "filter_message": message,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": 1
        }

    def _create_parse_error_result(self, raw_response: str = "") -> Dict[str, Any]:
        """
        Create fallback result when JSON parsing fails.
        
        Args:
            raw_response: The raw LLM response that couldn't be parsed
            
        Returns:
            Basic interview prep structure with parse error notice
        """
        return {
            "interview_process": {
                "typical_rounds": [],
                "total_timeline": "Unable to parse response",
                "preparation_time_needed": "N/A",
                "format_prediction": "N/A"
            },
            "predicted_questions": {
                "behavioral": [],
                "technical": [],
                "role_specific": [],
                "company_specific": []
            },
            "addressing_concerns": [],
            "questions_for_them": {
                "for_recruiter": [],
                "for_hiring_manager": [],
                "for_team_members": [],
                "red_flag_questions": []
            },
            "logistics": {
                "dress_code": "Business casual recommended",
                "what_to_bring": ["Resume copies", "Notebook", "Pen"],
                "timing": {"arrive": "10 minutes early", "expected_duration": "1 hour"},
                "virtual_interview_tips": ["Test your camera and microphone", "Find a quiet location"],
                "post_interview": {"thank_you_note": "Send within 24 hours", "follow_up_timeline": "1 week"}
            },
            "quick_reference_card": {
                "elevator_pitch": "Response parsing failed - please try regenerating",
                "three_key_selling_points": [],
                "weakness_answer": {"weakness": "", "how_addressing": "", "example": ""},
                "why_this_company": "",
                "why_leaving_current": "",
                "salary_discussion": {"anchor_range": "", "strategy": "", "deflection_phrase": ""},
                "closing_statement": ""
            },
            "day_before_checklist": [
                "Review your resume",
                "Research the company website",
                "Prepare 3-5 questions to ask",
                "Plan your outfit",
                "Get directions or test video setup"
            ],
            "confidence_boosters": [],
            "parse_error": True,
            "raw_response_preview": raw_response[:2000] if raw_response else "",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": 1
        }
