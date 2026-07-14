"""
Agent for generating personalized, compelling cover letters using expert LLM consultation.
Creates tailored cover letters by connecting candidate experience to job requirements and company culture.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from workflows.state_schema import WorkflowState, CoverLetterResult
from utils.llm_preferences import preferred_model_from_state
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

LLM_TEMPERATURE: float = 0.5  # Balanced: professional yet engaging
LLM_MAX_TOKENS: int = 16000  # Aligned with unified agent output cap
LLM_TIMEOUT: int = 60  # seconds

# =============================================================================
# PROMPTS
# =============================================================================

SYSTEM_CONTEXT: str = """You are an elite cover letter writer who has helped thousands of candidates land interviews at top companies including FAANG, Fortune 500, and high-growth startups.

## YOUR EXPERTISE:

**What Makes Cover Letters Work:**
- You know the difference between cover letters that get read and those that get skipped
- You understand that hiring managers spend only 30 seconds on most cover letters
- You know how to hook them in the first sentence and keep them reading
- You craft letters that feel personal, not templated
- You demonstrate DOMAIN KNOWLEDGE - if the job is in life sciences, you show curiosity about biology; if in fintech, you understand financial systems

**Strategic Storytelling:**
- You connect the candidate's experience to the company's SPECIFIC NEEDS from the job posting
- You address the TOP 3 requirements in the job description directly
- You turn achievements into compelling narratives that solve the company's problems
- You address concerns proactively without being defensive
- You show genuine interest by referencing specific company initiatives, products, or recent news

**Industry Awareness:**
- You know cover letter conventions vary by industry and company culture
- You adjust tone from formal (finance, law) to casual (startups, tech)
- You understand what different hiring managers care about
- You research and demonstrate knowledge of the SPECIFIC DOMAIN (healthcare, AI, manufacturing, etc.)

**What You MUST Avoid:**
- Generic opening lines ("I am writing to apply for...", "Forget incremental improvements...")
- Placeholder text like "[Today's Date]", "[Hiring Manager Name]", "[Company Address]"
- Repeating the resume verbatim
- Empty claims without evidence
- Desperation or over-qualification humility
- Walls of text - you use white space strategically
- Outdated references (check the date context provided)
- Generic statements that could apply to any job

## YOUR PRINCIPLES:
- First sentence must HOOK them with something SPECIFIC about the role or company
- Address the #1 job requirement in the first paragraph
- Every claim must have supporting evidence from their experience
- Show you know the company - reference their mission, recent news, or specific products
- Demonstrate genuine curiosity about the DOMAIN the job is in
- If there's a gap (like missing domain experience), acknowledge it briefly and pivot to transferable skills
- Be confident but not arrogant
- End with a specific, confident call to action
- Keep it to ONE PAGE (300-400 words max)
- NEVER include placeholder brackets - the letter must be ready to send
- YEARS OF EXPERIENCE RULE: The "Years of Experience" field is TOTAL career years — NEVER use it as domain-specific experience. When claiming "X years of [skill/domain]" in the letter, derive that number only from the relevant work history entries. If you cannot calculate it, say "experience with [skill]" without a specific year count."""

COVER_LETTER_PROMPT: str = """Write a compelling, personalized cover letter for this candidate applying to this specific job.

=== CANDIDATE ===
{user_profile}

=== TARGET JOB ===
{job_analysis}

=== STRATEGIC INSIGHTS (Use these to shape the narrative) ===
{profile_matching}

=== COMPANY CONTEXT (Reference specific details) ===
{company_context}

=== TODAY'S DATE ===
{today_date}

---

Write a cover letter that will make the hiring manager want to interview this candidate.

## CRITICAL REQUIREMENTS:

### 1. Opening Hook (MUST be unique and specific)
- First sentence must reference something SPECIFIC: a company product, recent news, or the exact problem this role solves
- NO generic openings like "I am excited to apply..." or "I am writing to express..."
- Example good opening: "When I saw that [Company] is building [specific thing from job posting], I knew my experience [specific match] could accelerate that work."
- The opening should make it clear you understand WHAT this job actually does

### 2. Address the Core Job Requirements
- Identify the TOP 3 requirements from the job posting
- Address each one with SPECIFIC evidence from the candidate's experience
- If the candidate lacks something important, briefly acknowledge and pivot to related strengths

### 3. Demonstrate Domain Understanding
- Show you understand the INDUSTRY/DOMAIN the job is in
- If it's a specialized field (life sciences, fintech, security, etc.), demonstrate curiosity or knowledge
- Use appropriate terminology from the job posting

### 4. Company-Specific Connection
- Reference the company's mission, values, or recent initiatives
- Show WHY this company specifically (not just any company)
- Connect your values to theirs

### 5. Confident Close
- End with a specific action you want to take (discussion, call, meeting)
- Express genuine enthusiasm without desperation

## FORMAT RULES (STRICT):
- Start directly with "Dear Hiring Manager," — or "Dear [Specific Name]," if a contact name is clearly stated in the job posting. Never use "Dear Hiring Team,"
- NO date header, NO address block, NO "[placeholder]" text of any kind
- The letter must be READY TO COPY AND PASTE - no fields to fill in
- 300-400 words maximum
- Sign off with the candidate's exact full name: {candidate_name} — nothing else on the closing line
- Professional but engaging tone

## TONE GUIDANCE:
{tone_guidance}

Write the complete cover letter now. Remember: NO PLACEHOLDERS, NO GENERIC OPENINGS, ADDRESS SPECIFIC JOB REQUIREMENTS:
"""

TONE_GUIDANCE = {
    "tech": "Professional but approachable. Tech companies appreciate authenticity and direct communication. Show technical credibility but also collaboration skills. Okay to show personality and genuine excitement about the technology.",
    "ai": "Intellectually curious and technically deep. AI companies value people who understand the nuances. Reference specific technical concepts from the job posting. Show you understand both the potential and limitations of AI.",
    "artificial intelligence": "Intellectually curious and technically deep. AI companies value people who understand the nuances. Reference specific technical concepts from the job posting. Show you understand both the potential and limitations of AI.",
    "machine learning": "Technically rigorous but practical. ML roles need people who can bridge research and production. Show you understand evaluation, deployment challenges, and real-world impact beyond just model accuracy.",
    "life sciences": "Scientific rigor meets practical impact. Demonstrate respect for the scientific method and domain expertise. Show curiosity about the biological/medical problems being solved. Emphasize collaboration with scientists and researchers.",
    "biotech": "Scientific rigor meets practical impact. Biotech values people who can communicate across disciplines. Show understanding that biology is complex and requires humility. Reference specific scientific challenges mentioned in the job.",
    "healthcare": "Warm yet professional. Emphasize patient outcomes, safety, and clinical excellence. Show you understand regulatory requirements and the stakes involved in healthcare decisions.",
    "finance": "Formal and precise. Emphasize analytical skills, attention to detail, risk awareness, and professionalism. Quantify achievements where possible.",
    "fintech": "Blend of financial rigor and tech innovation. Show you understand both regulatory constraints and user experience. Emphasize security awareness and scale thinking.",
    "startup": "Energetic and entrepreneurial. Show you can wear multiple hats, thrive in ambiguity, and move fast. Demonstrate ownership mentality and comfort with incomplete information.",
    "consulting": "Polished and articulate. Demonstrate strategic thinking, client focus, and ability to drive results. Show you can communicate complex ideas simply.",
    "research": "Intellectually humble and rigorous. Research organizations value depth over breadth. Show genuine curiosity and ability to think critically. Reference specific research areas mentioned.",
    "default": "Professional yet personable. Balance confidence with approachability. Show you understand the company's mission and can contribute immediately.",
}

# User-selected tone overrides — appended to (not replacing) industry guidance
USER_TONE_OVERRIDES: Dict[str, str] = {
    "professional": "",  # no override — let industry guidance fully control
    "conversational": (
        "\n\nUSER TONE PREFERENCE — CONVERSATIONAL: Write in a warm, natural, first-person voice. "
        "Use contractions (I've, I'm, we're). Avoid stiff corporate phrasing. Aim to sound like "
        "a smart colleague writing a candid note, not a formal applicant filling out a form."
    ),
    "enthusiastic": (
        "\n\nUSER TONE PREFERENCE — ENTHUSIASTIC: Bring genuine energy and passion. "
        "Express authentic excitement about this specific role and company — not just 'I am excited' "
        "but *why* you're excited. Let your motivation come through clearly without being over-the-top or desperate."
    ),
}


class CoverLetterWriterAgent:
    """
    Elite Cover Letter Writer Agent.

    Generates personalized, compelling cover letters using expert LLM consultation.
    Leverages profile matching insights to emphasize strengths and address concerns.
    """

    def __init__(self, gemini_client: Any) -> None:
        """
        Initialize the Cover Letter Writer Agent.

        Args:
            gemini_client: Gemini client instance for LLM communication

        Raises:
            TypeError: If gemini_client is None
        """
        if gemini_client is None:
            raise TypeError("gemini_client cannot be None")

        self.gemini_client = gemini_client
        logger.info("Cover Letter Writer Agent initialized")

    async def process(self, state: WorkflowState) -> WorkflowState:
        """
        Generate a personalized cover letter for the job application.

        Args:
            state: Current workflow state with all analysis results

        Returns:
            Updated workflow state with cover letter content

        Raises:
            ValueError: If required data is missing
            Exception: If cover letter generation fails
        """
        session_id = sanitize_log_value(str(state.get("session_id") or "unknown"))
        logger.info('Starting cover letter writing for session %s', sanitize_log_value(session_id))
        start_time = datetime.now(timezone.utc)

        # Store user API key for use in LLM calls (BYOK mode)
        self._current_user_api_key = state.get("user_api_key")
        self._current_llm_provider = state.get("llm_provider")

        try:
            # Extract required data
            user_profile: Dict[str, Any] = state.get("user_profile", {})
            job_analysis: Dict[str, Any] = state.get("job_analysis", {})
            profile_matching: Optional[Dict[str, Any]] = state.get("profile_matching")
            company_research: Optional[Dict[str, Any]] = state.get("company_research")
            prefs: Dict[str, Any] = state.get("workflow_preferences") or {}
            user_tone: str = prefs.get("cover_letter_tone", "professional")
            user_model: Optional[str] = preferred_model_from_state(
                state, self._current_user_api_key
            )

            # Validate
            if not user_profile:
                raise ValueError("User profile is required for cover letter writing")
            if not job_analysis:
                raise ValueError("Job analysis is required for cover letter writing")

            # Generate cover letter
            cover_letter_content = await self._generate_cover_letter(
                user_profile, job_analysis, profile_matching, company_research,
                user_tone=user_tone,
                user_model=user_model,
            )

            # Calculate processing time
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Create result
            result = CoverLetterResult(
                content=cover_letter_content,
                generated_at=datetime.now(timezone.utc).isoformat(),
                processing_time=processing_time,
            )

            # Store in state
            state["cover_letter"] = result.to_dict()

            logger.info("Cover letter writing completed successfully")

        except Exception as e:
            logger.error("Cover letter writing failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

        return state

    async def _generate_cover_letter(
        self,
        user_profile: Dict[str, Any],
        job_analysis: Dict[str, Any],
        profile_matching: Optional[Dict[str, Any]],
        company_research: Optional[Dict[str, Any]],
        user_tone: str = "professional",
        user_model: Optional[str] = None,
    ) -> str:
        """
        Generate personalized cover letter using expert LLM consultation.

        Args:
            user_profile: Candidate profile data
            job_analysis: Job analysis results
            profile_matching: Profile matching insights
            company_research: Company research data

        Returns:
            Complete cover letter content

        Raises:
            Exception: If LLM generation fails
        """
        logger.info("Generating cover letter with expert LLM consultation")

        # Format all inputs
        formatted_profile = self._format_profile(user_profile)
        formatted_job = self._format_job(job_analysis)
        formatted_matching = self._format_matching(profile_matching)
        formatted_company = self._format_company(company_research)

        # Determine tone based on industry - check multiple keywords
        industry = job_analysis.get("industry", "").lower()
        company_name = job_analysis.get("company_name", "").lower()
        job_title = job_analysis.get("job_title", "").lower()
        
        # Combine all context for better tone matching
        context = f"{industry} {company_name} {job_title}"
        
        tone = TONE_GUIDANCE.get("default")
        # Priority order for matching (more specific first)
        priority_keys = ["life sciences", "biotech", "ai", "artificial intelligence", "machine learning",
                        "fintech", "healthcare", "research", "finance", "consulting", "startup", "tech"]

        for key in priority_keys:
            if key in context:
                tone = TONE_GUIDANCE.get(key, tone)
                logger.info("Selected tone guidance for %r", sanitize_log_value(key))
                break

        # Append user-selected tone override on top of industry guidance
        tone_override = USER_TONE_OVERRIDES.get(user_tone, "")
        if tone_override:
            tone = (tone or "") + tone_override
            logger.info("Applied user tone override: %s", sanitize_log_value(user_tone))

        # Build prompt with today's date
        today = datetime.now().strftime("%B %d, %Y")
        
        candidate_name = user_profile.get("full_name") or ""
        prompt = COVER_LETTER_PROMPT.format(
            user_profile=formatted_profile,
            job_analysis=formatted_job,
            profile_matching=formatted_matching,
            company_context=formatted_company,
            tone_guidance=tone,
            today_date=today,
            candidate_name=candidate_name if candidate_name else "the candidate",
        )

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
                    provider=getattr(self, "_current_llm_provider", None),
                ),
                timeout=LLM_TIMEOUT,
            )

            if response.get("filtered"):
                logger.warning("Response was filtered by safety settings")
                return self._create_fallback_letter(user_profile, job_analysis)

            content = response.get("response", "").strip()
            if not content:
                    raise Exception("Empty response from LLM")

            return content

        except asyncio.TimeoutError:
            logger.error("LLM request timed out")
            raise Exception("Cover letter generation timed out")
        except Exception as e:
            logger.error("LLM request failed: %s", sanitize_log_value(str(e)), exc_info=True)
            raise

    def _format_profile(self, profile: Dict[str, Any]) -> str:
        """Format candidate profile for cover letter generation."""
        sections = []

        # Essential info
        name = profile.get("full_name", "Candidate")
        title = profile.get("professional_title", "Professional")
        years = profile.get("years_experience", 0)

        sections.append(f"Name: {name}")
        sections.append(f"Current Role: {title}")
        sections.append(f"Experience: {years} years")

        # Contact for letter header
        email = profile.get("email", "")
        if email:
            sections.append(f"Email: {email}")

        location_parts = [profile.get("city", ""), profile.get("state", "")]
        location = ", ".join([p for p in location_parts if p])
        if location:
            sections.append(f"Location: {location}")

        # Professional summary
        if profile.get("summary"):
            sections.append(f"\nProfessional Summary:\n{profile['summary']}")

        # Key skills
        skills = profile.get("skills", [])
        if skills:
            sections.append(f"\nKey Skills: {', '.join(skills[:15])}")

        # Recent experience (most important for cover letter)
        work_exp = profile.get("work_experience", [])
        if work_exp:
            sections.append("\nRecent Experience:")
            for exp in work_exp[:3]:  # Focus on last 3 roles
                title = exp.get("job_title", "N/A")
                company = exp.get("company", exp.get("company_name", "N/A"))
                sections.append(f"\n• {title} at {company}")
                if exp.get("description"):
                    # Include full description for context
                    desc = exp["description"]
                    if len(desc) > 500:
                        desc = desc[:500] + "..."
                    sections.append(f"  {desc}")

        edu_rows = profile.get("education", []) or []
        if edu_rows:
            sections.append("\nEducation:")
            for edu in edu_rows[:3]:
                inst = edu.get("institution", "N/A")
                deg = edu.get("degree", "N/A")
                fos = edu.get("field_of_study")
                extra = f", {fos}" if fos else ""
                sections.append(f"\n• {deg} at {inst}{extra}")

        return "\n".join(sections)

    def _format_job(self, job: Dict[str, Any]) -> str:
        """Format job information for cover letter generation."""
        sections = []

        sections.append(f"Position: {job.get('job_title', 'N/A')}")
        sections.append(f"Company: {job.get('company_name', 'N/A')}")
        sections.append(f"Industry: {job.get('industry', 'N/A')}")

        location_parts = [job.get("job_city", ""), job.get("job_state", "")]
        location = ", ".join([p for p in location_parts if p])
        if location:
            sections.append(f"Location: {location}")

        sections.append(f"Work Arrangement: {job.get('work_arrangement', 'N/A')}")

        # Key requirements - these are CRITICAL for the cover letter
        required_skills = job.get("required_skills", [])
        if required_skills:
            sections.append("\n*** KEY TECHNICAL SKILLS REQUIRED (address these!): ***")
            sections.append(f"{', '.join(required_skills[:12])}")

        soft_skills = job.get("soft_skills", [])
        if soft_skills:
            sections.append(f"\nSoft Skills They Want: {', '.join(soft_skills[:6])}")

        # Qualifications - most important for cover letter targeting
        required_quals = job.get("required_qualifications", [])
        if required_quals:
            sections.append("\n*** TOP REQUIREMENTS FROM JOB POSTING (address top 3!): ***")
            for i, q in enumerate(required_quals[:7], 1):
                qual_text = q if isinstance(q, str) else q.get('qualification', str(q))
                sections.append(f"  {i}. {qual_text}")

        # Responsibilities - what the job actually does
        responsibilities = job.get("responsibilities", [])
        if responsibilities:
            sections.append("\nWhat This Role Does (for context):")
            for r in responsibilities[:5]:
                sections.append(f"  • {r}")

        # Preferred qualifications - bonus points if candidate has these
        preferred = job.get("preferred_qualifications", [])
        if preferred:
            sections.append("\nNice-to-Have (mention if candidate has):")
            for p in preferred[:4]:
                pref_text = p if isinstance(p, str) else p.get('qualification', str(p))
                sections.append(f"  • {pref_text}")

        # Years of experience required
        years = job.get("years_experience_required")
        if years:
            sections.append(f"\nExperience Level: {years}+ years")

        # Team context
        team_info = job.get("team_info")
        if team_info:
            sections.append(f"\nTeam Context: {team_info}")

        return "\n".join(sections)

    def _format_matching(self, matching: Optional[Dict[str, Any]]) -> str:
        """Format matching insights for cover letter strategy."""
        if not matching:
            return "No matching analysis available - write a general strong cover letter"

        sections = []

        # Executive summary
        exec_summary = matching.get("executive_summary", {})
        if exec_summary:
            recommendation = exec_summary.get("recommendation", "N/A")
            verdict = exec_summary.get("one_line_verdict", "")
            fit_assessment = exec_summary.get("fit_assessment", "")
            sections.append(f"Match Level: {recommendation}")
            if verdict:
                sections.append(f"One-Line Assessment: {verdict}")
            if fit_assessment:
                sections.append(f"Detailed Fit: {fit_assessment}")

        # Overall scores
        qual_score = matching.get('qualification_score', matching.get('final_scores', {}).get('qualification_score', 0))
        sections.append(f"\nQualification Score: {qual_score:.2f}/1.0")

        # Key strengths to emphasize (from new format)
        qual_analysis = matching.get("qualification_analysis", {})
        skills_assessment = qual_analysis.get("skills_assessment", {})
        if skills_assessment:
            matched = skills_assessment.get("matched_skills", [])
            if matched:
                sections.append("\n*** STRENGTHS TO HIGHLIGHT (use these!): ***")
                for skill in matched[:6]:
                    if isinstance(skill, dict):
                        skill_name = skill.get("skill", "")
                        evidence = skill.get("evidence", "")
                        strength = skill.get("strength", "")
                        sections.append(f"  • {skill_name} ({strength})")
                        if evidence:
                            sections.append(f"    Evidence: {evidence[:100]}")
                    else:
                        sections.append(f"  • {skill}")

            # Missing critical skills - address these proactively
            missing = skills_assessment.get("missing_critical_skills", [])
            if missing:
                sections.append("\n*** GAPS TO ADDRESS PROACTIVELY: ***")
                for gap in missing[:3]:
                    if isinstance(gap, dict):
                        skill_name = gap.get("skill", "")
                        importance = gap.get("importance", "")
                        can_learn = gap.get("can_learn_quickly", False)
                        sections.append(f"  • {skill_name} ({importance})")
                        if can_learn:
                            sections.append("    → Note: Can be learned quickly - mention willingness to learn")
                    else:
                        sections.append(f"  • {gap}")

            # Hidden skills they may not realize they have
            hidden = skills_assessment.get("hidden_skills", [])
            if hidden:
                sections.append("\nHidden Skills to Mention:")
                for h in hidden[:3]:
                    if isinstance(h, dict):
                        sections.append(f"  • {h.get('skill', '')} - {h.get('reasoning', '')[:80]}")
                    else:
                        sections.append(f"  • {h}")

        # Application strategy insights
        app_strategy = matching.get("application_strategy", {})
        if app_strategy:
            talking_points = app_strategy.get("key_talking_points", [])
            if talking_points:
                sections.append("\n*** KEY TALKING POINTS (weave into letter): ***")
                for point in talking_points[:5]:
                    sections.append(f"  • {point}")

            concerns = app_strategy.get("address_these_concerns", [])
            if concerns:
                sections.append("\n*** CONCERNS TO ADDRESS (briefly acknowledge, then pivot): ***")
                for concern in concerns[:3]:
                    if isinstance(concern, dict):
                        issue = concern.get("concern", "")
                        fix = concern.get("how_to_address", "")
                        sections.append(f"  • Issue: {issue}")
                        if fix:
                            sections.append(f"    → Strategy: {fix}")
                    else:
                        sections.append(f"  • {concern}")

            cover_angle = app_strategy.get("cover_letter_angle", "")
            if cover_angle:
                sections.append(f"\n*** RECOMMENDED NARRATIVE ANGLE: ***\n{cover_angle}")

        # Competitive positioning
        competitive = matching.get("competitive_positioning", {})
        if competitive:
            unique_value = competitive.get("unique_value_proposition", "")
            if unique_value:
                sections.append(f"\n*** YOUR UNIQUE VALUE PROPOSITION (emphasize!): ***\n{unique_value}")
            
            strengths_vs_typical = competitive.get("strengths_vs_typical_applicant", [])
            if strengths_vs_typical:
                sections.append("\nHow You Stand Out vs. Other Applicants:")
                for s in strengths_vs_typical[:3]:
                    sections.append(f"  • {s}")

        # Risk assessment - what to be careful about
        risk = matching.get("risk_assessment", {})
        if risk:
            red_flags = risk.get("red_flags_for_candidate", [])
            if red_flags:
                sections.append("\nPotential Red Flags (don't dwell on these):")
                for r in red_flags[:2]:
                    sections.append(f"  • {r}")

        return "\n".join(sections)

    def _format_company(self, company: Optional[Dict[str, Any]]) -> str:
        """Format company information for personalization."""
        if not company:
            return "Limited company information - focus on role and general industry knowledge"

        sections = []

        if company.get("company_size"):
            sections.append(f"Company Size: {company['company_size']}")

        if company.get("industry"):
            sections.append(f"Industry: {company['industry']}")

        # Mission/vision for alignment - CRITICAL for cover letter
        if company.get("mission_vision"):
            mission = company["mission_vision"]
            if len(mission) > 500:
                mission = mission[:500] + "..."
            sections.append(f"\n*** COMPANY MISSION (reference this!): ***\n{mission}")

        # Core values for cultural fit messaging
        if company.get("core_values"):
            values = company["core_values"][:6]
            sections.append(f"\n*** COMPANY VALUES (align with these!): ***\n{', '.join(values)}")

        # What they look for in candidates
        app_insights = company.get("application_insights", {})
        what_to_emphasize = app_insights.get("what_to_emphasize", company.get("what_to_emphasize", []))
        if what_to_emphasize:
            sections.append("\n*** WHAT THEY LOOK FOR IN CANDIDATES: ***")
            for item in what_to_emphasize[:4]:
                sections.append(f"  • {item}")

        # Culture fit signals
        culture_signals = app_insights.get("culture_fit_signals", [])
        if culture_signals:
            sections.append("\nHow to Show Culture Fit:")
            for signal in culture_signals[:3]:
                sections.append(f"  • {signal}")

        # Recent news for personalization hooks
        if company.get("recent_news"):
            news = company["recent_news"]
            if isinstance(news, list) and news:
                sections.append("\n*** RECENT NEWS (great for personalization!): ***")
                for item in news[:3]:
                    if isinstance(item, dict):
                        headline = item.get("headline", item.get("title", ""))
                        summary = item.get("summary", "")
                        if headline:
                            sections.append(f"  • {headline}")
                            if summary:
                                sections.append(f"    ({summary[:150]})")
                    elif isinstance(item, str):
                        sections.append(f"  • {item[:150]}")

        # Key products or services
        overview = company.get("company_overview", {})
        products = overview.get("key_products_services", [])
        if products:
            sections.append(f"\nKey Products/Services: {', '.join(products[:4])}")

        # Competitive advantages
        landscape = company.get("competitive_landscape", {})
        advantages = landscape.get("competitive_advantages", company.get("competitive_advantages", []))
        if advantages:
            sections.append(f"\nTheir Strengths: {', '.join(advantages[:3])}")

        return "\n".join(sections) if sections else "Limited company information available"

    def _create_fallback_letter(
        self, profile: Dict[str, Any], job: Dict[str, Any]
    ) -> str:
        """Create a basic fallback cover letter if LLM fails."""
        name = profile.get("full_name", "Candidate")
        title = profile.get("professional_title", "professional")
        company = job.get("company_name", "your organization")
        position = job.get("job_title", "this role")
        years = profile.get("years_experience", 0)
        skills = profile.get("skills", [])[:5]
        skills_text = ", ".join(skills) if skills else "relevant technical skills"

        years_text = f"{years} years of" if years else "extensive"

        return f"""Dear Hiring Manager,

The {position} role at {company} caught my attention because it aligns well with my background in {title.lower()} work. With {years_text} experience and proficiency in {skills_text}, I am confident I can contribute to your team's success.

Throughout my career, I have focused on delivering impactful results and collaborating effectively with cross-functional teams. I am particularly drawn to {company}'s mission and would welcome the opportunity to bring my skills and enthusiasm to this role.

I would be glad to discuss how my background aligns with your needs. Thank you for considering my application.

{name}

---
Note: This is a simplified template generated because the full AI analysis was unavailable. Consider customizing further before submitting."""
