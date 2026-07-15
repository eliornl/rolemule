"""
Conversational mock interview agent (HR / Pro / Manager styles).

Standalone on-demand agent — not part of the LangGraph workflow.
Uses the user's BYOK LLM. English only in v1.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from utils.llm.speak_stream import SpeakFieldStreamer
from utils.llm_client import get_gemini_client  # noqa: F401  # test-patch alias
from utils.llm_parsing import parse_json_from_llm_response
from utils.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

LLM_TEMPERATURE: float = 0.55
LLM_MAX_TOKENS: int = 16000

SpeakDeltaCallback = Callable[[str], Awaitable[None]]

VALID_STYLES = frozenset({"hr", "pro", "manager"})
HISTORY_CAP = 5
MAX_PROMPT_TURNS = 6

STYLE_PACKS: Dict[str, str] = {
    "hr": (
        "You are a senior recruiter running a realistic first-round screen. "
        "Sound warm, organized, and lightly evaluative — never stiff or scripted. "
        "Probe motivation, communication, culture fit, resume walkthrough, "
        "logistics, and light compensation expectations. "
        "Prefer behavioral and company-fit questions. "
        "If answers are vague, ask for one concrete example — not a lecture."
    ),
    "pro": (
        "You are a senior peer / specialist interviewer judging craft depth. "
        "Sound sharp, curious, and respectful — like a strong IC who has done this work. "
        "Probe role-specific skills, past evidence, tradeoffs, and problem-solving for THIS job. "
        "Prefer technical and role-specific questions. "
        "Push for specificity (numbers, systems, decisions) without being hostile."
    ),
    "manager": (
        "You are the hiring manager deciding if this person can own outcomes on your team. "
        "Sound calm, direct, and practical. "
        "Probe ownership, prioritization, collaboration, impact, judgment, and team fit for THIS role. "
        "Prefer role-specific and behavioral ownership questions. "
        "Ask how they would handle real constraints — ambiguity, conflict, tradeoffs."
    ),
}

SYSTEM_CONTEXT: str = """You are a world-class mock interviewer for ApplyPilot practice sessions.

You run interviews the way top hiring teams do: natural conversation, one focused ask at a time,
and follow-ups that react to what the candidate just said — never a generic quiz script.

## INTERVIEW CRAFT
- Stay strictly in character for the assigned interviewer style.
- Speak in clear English only. Spoken lines are SHORT (max ~60 words). One question at a time.
- Sound human: contractions are fine; avoid corporate fluff, markdown, bullets, or emoji in "speak".
- Never invent a different job title or company than provided.
- Never use bracket placeholders like [Name] or [Company] in "speak".
- Ground every follow-up in the candidate's latest answer (quote a detail, then probe).
- Calibrate difficulty to the role seniority implied by the job + profile — not beginner, not unrealistically senior.
- Prefer questions from prep notes when they fit the style; otherwise invent grounded questions from the job.
- Do NOT lecture, summarize the job back to them, or give coaching inside "speak". Coaching belongs only in "tip".
- YEARS OF EXPERIENCE RULE: total career years is NOT domain tenure — never invent domain year counts.

## TIME COACHING (hard rules)
- If seconds_remaining is between 61 and 120: this is the last full question (or a brief closing example).
- If seconds_remaining is between 31 and 60: ask for a short 30–60 second summary of their strongest fit.
- If seconds_remaining <= 30 or time is up: wrap_up politely — no new topics.

## SCORING CALIBRATION (when scoring)
- 9–10: specific, structured, role-relevant evidence with clear impact
- 7–8: solid answer with a real example; minor gaps
- 5–6: partial / generic; missing structure or evidence
- 1–4: vague, off-topic, or avoids the question
Be fair but not soft. Empty fluff never scores above 5.

## OUTPUT
- Return ONLY valid JSON matching the requested schema. No markdown fences, no preamble.
"""

OPEN_PROMPT: str = """Open a realistic mock interview practice session.

Style: {style}
Style instructions: {style_pack}
Duration minutes: {duration_minutes}
STAR coach mode: {star_coach}

=== JOB ===
{job_info}

=== COMPANY ===
{company_info}

=== CANDIDATE ===
{profile_info}

=== MATCH NOTES ===
{matching_insights}

=== PREP QUESTIONS (prefer these when relevant to style) ===
{prep_questions}

Opening quality bar:
- Brief greeting that names the role/company when known, then ONE first question.
- First question should feel like a real screen for this style (not "tell me about yourself" unless HR and no better opener fits).
- Build a short plan of 3–5 topics you intend to cover for this duration (ids q1, q2, …).

Return ONLY JSON:
{{
  "speak": "Brief greeting + first interview question (plain text, no markdown)",
  "act": "next_question",
  "plan": [
    {{"id": "q1", "category": "behavioral|technical|role_specific|company_specific", "goal": "short goal"}}
  ],
  "running_notes": []
}}
"""

TURN_PROMPT: str = """Continue the mock interview. Stay in character.

Style: {style}
Style instructions: {style_pack}
Seconds remaining: {seconds_remaining}
Time coaching: {time_coaching}
STAR coach mode: {star_coach}
Already covered plan ids: {covered_ids}

=== JOB (compact) ===
{job_info}

=== RECENT TURNS ===
{recent_turns}

=== CANDIDATE ANSWER (latest) ===
{transcript}

=== PLAN / NOTES ===
{plan_notes}

Decide act:
- follow_up — answer was thin, missing evidence, or (if STAR coach ON) missing Situation/Action/Result; ask ONE short probe
- next_question — answer was sufficient; move to a new plan topic
- wrap_up — time up, coverage enough, or seconds_remaining <= 30 (MUST wrap_up if <= 30)

Speak quality bar:
- React to something specific they said, then ask the next question or probe.
- Do not repeat their answer back at length.
- Do not put tips, scores, or meta commentary in "speak".

Scoring: score ONLY the latest candidate answer (content / structure / clarity).
If any score is <= 5, set "tip" to one concrete coaching line for the UI (empty string if scores are strong).
When you finish a plan topic, include its id in covered_plan_ids.
Keep running_notes short (what you learned / what to probe next).

Return ONLY JSON:
{{
  "speak": "Your next spoken line (plain text)",
  "act": "follow_up|next_question|wrap_up",
  "scores": {{
    "content": 1-10,
    "structure": 1-10,
    "clarity": 1-10
  }},
  "tip": "Optional one-line coaching tip for the candidate UI (empty string if none)",
  "covered_plan_ids": ["q1"],
  "running_notes": ["short note"]
}}
"""

DEBRIEF_PROMPT: str = """Produce a world-class scored debrief for this mock interview.

Style: {style}
Style instructions: {style_pack}

=== JOB ===
{job_info}

=== FULL TRANSCRIPT ===
{transcript_full}

Weight feedback for this style:
- hr: communication, fit, consistency, clarity of motivation
- pro: depth, evidence, skill signal, problem-solving rigor
- manager: judgment, ownership, prioritization, role match

Debrief quality bar:
- overall_score and dimension scores must match the transcript (no grade inflation).
- strengths / improvements: 3 specific bullets each, tied to what they said — not generic advice.
- weakest_answer_rewrite: a stronger model answer in first person for their weakest turn (plain text, ~80–140 words), using STAR when relevant.
- summary: 2–3 sentences a hiring coach would say out loud after the practice.

Return ONLY JSON:
{{
  "overall_score": 1-10,
  "scores": {{
    "content": 1-10,
    "structure": 1-10,
    "clarity": 1-10,
    "role_fit": 1-10,
    "style_focus": 1-10
  }},
  "strengths": ["...", "...", "..."],
  "improvements": ["...", "...", "..."],
  "weakest_answer_rewrite": "A stronger model answer for the weakest turn",
  "summary": "2-3 sentence overall summary"
}}
"""


def _compact_dict(data: Optional[Dict[str, Any]], keys: List[str], limit: int = 1200) -> str:
    if not data:
        return "(none)"
    parts: List[str] = []
    for key in keys:
        val = data.get(key)
        if val is None or val == "" or val == {} or val == []:
            continue
        parts.append(f"{key}: {val}")
    text = "\n".join(parts)
    return text[:limit] if len(text) > limit else text


def _extract_prep_questions(interview_prep: Optional[Dict[str, Any]], style: str) -> str:
    if not interview_prep:
        return "(none — invent grounded questions from job/profile)"
    pq = interview_prep.get("predicted_questions") or {}
    buckets: List[str]
    if style == "hr":
        buckets = ["behavioral", "company_specific"]
    elif style == "pro":
        buckets = ["technical", "role_specific"]
    else:
        buckets = ["role_specific", "behavioral"]
    lines: List[str] = []
    for bucket in buckets:
        items = pq.get(bucket) or []
        if not isinstance(items, list):
            continue
        for item in items[:4]:
            if isinstance(item, dict):
                q = item.get("question")
                if q:
                    lines.append(f"[{bucket}] {q}")
            elif isinstance(item, str):
                lines.append(f"[{bucket}] {item}")
    return "\n".join(lines) if lines else "(none)"


def _format_turns(turns: List[Dict[str, Any]], limit: int = MAX_PROMPT_TURNS) -> str:
    recent = turns[-limit:] if turns else []
    if not recent:
        return "(none yet)"
    lines = []
    for t in recent:
        role = t.get("role", "?")
        text = (t.get("text") or "")[:500]
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _safe_score(value: Any, default: int = 5) -> int:
    """Clamp LLM score fields to 1–10; tolerate non-numeric junk."""
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(1, min(10, n))


def _time_coaching(seconds_remaining: int) -> str:
    if seconds_remaining <= 0:
        return "Time is up — wrap_up only."
    if seconds_remaining <= 30:
        return "MUST wrap_up now. Thank them briefly."
    if seconds_remaining <= 60:
        return "Ask for a short 30–60 second closing summary of their strongest fit, then prepare to wrap."
    if seconds_remaining <= 120:
        return "Say this is the last full question (or a brief closing example). Do not open a big new topic."
    return "Normal pacing — continue the interview."


def _normalize_plan(plan: Any) -> List[Dict[str, Any]]:
    if not isinstance(plan, list):
        return []
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(plan[:8]):
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or f"q{i + 1}").strip() or f"q{i + 1}"
        cat = str(item.get("category") or "behavioral").strip().lower()
        if cat not in ("behavioral", "technical", "role_specific", "company_specific"):
            cat = "behavioral"
        goal = str(item.get("goal") or "").strip()[:200]
        out.append({"id": pid, "category": cat, "goal": goal})
    return out


def _normalize_covered_ids(raw: Any, plan: List[Dict[str, Any]]) -> List[str]:
    valid = {str(p.get("id")) for p in plan if p.get("id")}
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        pid = str(item or "").strip()
        if pid and pid in valid and pid not in out:
            out.append(pid)
    return out


def _tip_from_scores(tip: Any, scores: Dict[str, int]) -> str:
    text = str(tip or "").strip()
    if text:
        return text[:240]
    vals = [scores.get("content", 5), scores.get("structure", 5), scores.get("clarity", 5)]
    if min(vals) <= 5:
        if scores.get("structure", 5) <= 5:
            return "Try a clearer structure: situation → what you did → the result."
        if scores.get("content", 5) <= 5:
            return "Add one concrete example or metric to strengthen this answer."
        return "Slow down and finish one clear point before moving on."
    return ""


class MockInterviewAgent:
    """Adaptive mock interviewer for HR / Pro / Manager styles."""

    def __init__(self) -> None:
        self.gemini_client = None
        self._current_user_api_key: Optional[str] = None

    async def _generate_json(
        self,
        prompt: str,
        *,
        user_api_key: Optional[str],
        model: Optional[str],
        llm_provider: Optional[str],
    ) -> Dict[str, Any]:
        self.gemini_client = await get_gemini_client()
        response = await self.gemini_client.generate(
            prompt=prompt,
            system=SYSTEM_CONTEXT,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            user_api_key=user_api_key,
            provider=llm_provider,
            model=model,
        )
        if response.get("filtered"):
            return {
                "error": "filtered",
                "speak": "I need to pause this practice session. Please try again.",
                "act": "wrap_up",
            }
        raw = response.get("response", "") or ""
        return self._parse_raw_json(raw)

    def _parse_raw_json(self, raw: str) -> Dict[str, Any]:
        parsed = parse_json_from_llm_response(raw)
        if not parsed or not isinstance(parsed, dict):
            logger.warning(
                "Mock interview JSON parse failed: %s",
                sanitize_log_value(raw[:200]),
            )
            return {
                "error": "parse_error",
                "speak": "Thanks for that answer. Let's wrap up this practice for now.",
                "act": "wrap_up",
            }
        return parsed

    async def _generate_json_streaming(
        self,
        prompt: str,
        *,
        user_api_key: Optional[str],
        model: Optional[str],
        llm_provider: Optional[str],
        on_speak_delta: Optional[SpeakDeltaCallback] = None,
    ) -> Dict[str, Any]:
        """
        Stream model tokens, emit speak deltas, then parse full JSON.

        Falls back to non-streaming generate on stream failure.
        """
        self.gemini_client = await get_gemini_client()
        if on_speak_delta is None or not hasattr(self.gemini_client, "generate_stream"):
            return await self._generate_json(
                prompt,
                user_api_key=user_api_key,
                model=model,
                llm_provider=llm_provider,
            )

        streamer = SpeakFieldStreamer()
        parts: List[str] = []
        try:
            async for chunk in self.gemini_client.generate_stream(
                prompt=prompt,
                system=SYSTEM_CONTEXT,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                user_api_key=user_api_key,
                provider=llm_provider,
                model=model,
            ):
                if not chunk:
                    continue
                parts.append(chunk)
                delta = streamer.feed(chunk)
                if delta:
                    try:
                        await on_speak_delta(delta)
                    except Exception:
                        logger.debug(
                            "Mock interview speak delta callback failed",
                            exc_info=True,
                        )
            raw = "".join(parts)
            if not raw.strip():
                raise RuntimeError("empty stream")
            return self._parse_raw_json(raw)
        except Exception as stream_err:
            logger.warning(
                "Mock interview stream failed, falling back: %s",
                sanitize_log_value(str(stream_err)),
            )
            return await self._generate_json(
                prompt,
                user_api_key=user_api_key,
                model=model,
                llm_provider=llm_provider,
            )

    async def open_session(
        self,
        *,
        style: str,
        duration_minutes: int,
        job_analysis: Optional[Dict[str, Any]] = None,
        company_research: Optional[Dict[str, Any]] = None,
        profile_matching: Optional[Dict[str, Any]] = None,
        user_profile: Optional[Dict[str, Any]] = None,
        interview_prep: Optional[Dict[str, Any]] = None,
        star_coach: bool = False,
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        on_speak_delta: Optional[SpeakDeltaCallback] = None,
    ) -> Dict[str, Any]:
        """
        Open a mock interview and return the first interviewer utterance.

        Returns:
            Dict with speak, act, plan, running_notes
        """
        style = (style or "").lower().strip()
        if style not in VALID_STYLES:
            style = "hr"
        style_pack = STYLE_PACKS[style]
        job_info = _compact_dict(
            job_analysis,
            ["job_title", "company_name", "required_skills", "responsibilities", "required_qualifications"],
        )
        company_info = _compact_dict(
            company_research,
            ["company_name", "overview", "culture_and_values", "interview_intelligence"],
        )
        profile_info = _compact_dict(
            user_profile,
            ["full_name", "professional_title", "years_experience", "summary", "skills", "work_experience"],
            limit=2000,
        )
        matching = _compact_dict(
            profile_matching,
            ["executive_summary", "qualification_breakdown", "competitive_positioning"],
        )
        prep_q = _extract_prep_questions(interview_prep, style)
        prompt = OPEN_PROMPT.format(
            style=style,
            style_pack=style_pack,
            duration_minutes=duration_minutes,
            star_coach="ON" if star_coach else "OFF",
            job_info=job_info,
            company_info=company_info,
            profile_info=profile_info,
            matching_insights=matching,
            prep_questions=prep_q,
        )
        if on_speak_delta is not None:
            result = await self._generate_json_streaming(
                prompt,
                user_api_key=user_api_key,
                model=model,
                llm_provider=llm_provider,
                on_speak_delta=on_speak_delta,
            )
        else:
            result = await self._generate_json(
                prompt,
                user_api_key=user_api_key,
                model=model,
                llm_provider=llm_provider,
            )
        speak = str(result.get("speak") or "").strip()
        if not speak:
            speak = "Thanks for joining. Tell me a bit about yourself and why you're interested in this role."
        plan = _normalize_plan(result.get("plan"))
        notes = result.get("running_notes") if isinstance(result.get("running_notes"), list) else []
        out = {
            "speak": speak,
            "act": result.get("act") or "next_question",
            "plan": plan,
            "running_notes": notes,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        if result.get("error"):
            out["error"] = result["error"]
        return out

    async def next_turn(
        self,
        *,
        style: str,
        seconds_remaining: int,
        transcript: str,
        turns: List[Dict[str, Any]],
        plan: List[Dict[str, Any]],
        running_notes: List[Any],
        covered_plan_ids: Optional[List[str]] = None,
        star_coach: bool = False,
        job_analysis: Optional[Dict[str, Any]] = None,
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None,
        on_speak_delta: Optional[SpeakDeltaCallback] = None,
    ) -> Dict[str, Any]:
        """
        Score the latest answer and produce the next interviewer act.

        Returns:
            Dict with speak, act, scores, tip, covered_plan_ids, running_notes
        """
        style = (style or "").lower().strip()
        if style not in VALID_STYLES:
            style = "hr"
        plan_norm = _normalize_plan(plan)
        covered = list(covered_plan_ids or [])
        if seconds_remaining <= 0:
            return {
                "speak": "We're out of time. Thanks for practicing — I'll share feedback next.",
                "act": "wrap_up",
                "scores": {"content": 5, "structure": 5, "clarity": 5},
                "tip": "",
                "covered_plan_ids": covered,
                "running_notes": list(running_notes or []),
            }
        style_pack = STYLE_PACKS[style]
        job_info = _compact_dict(
            job_analysis,
            ["job_title", "company_name", "required_skills", "responsibilities"],
            limit=800,
        )
        plan_notes = f"plan={plan_norm}\nnotes={running_notes}"
        prompt = TURN_PROMPT.format(
            style=style,
            style_pack=style_pack,
            seconds_remaining=max(0, int(seconds_remaining)),
            time_coaching=_time_coaching(seconds_remaining),
            star_coach="ON" if star_coach else "OFF",
            covered_ids=", ".join(covered) if covered else "(none yet)",
            job_info=job_info,
            recent_turns=_format_turns(turns),
            transcript=(transcript or "")[:4000],
            plan_notes=plan_notes[:1500],
        )
        if on_speak_delta is not None:
            result = await self._generate_json_streaming(
                prompt,
                user_api_key=user_api_key,
                model=model,
                llm_provider=llm_provider,
                on_speak_delta=on_speak_delta,
            )
        else:
            result = await self._generate_json(
                prompt,
                user_api_key=user_api_key,
                model=model,
                llm_provider=llm_provider,
            )
        if result.get("error"):
            return {
                "error": result["error"],
                "speak": str(result.get("speak") or "").strip()
                or "I need a moment — please try submitting that answer again.",
                "act": "next_question",
                "scores": {"content": 5, "structure": 5, "clarity": 5},
                "tip": "",
                "covered_plan_ids": covered,
                "running_notes": list(running_notes or []),
            }
        act = str(result.get("act") or "next_question").lower().strip()
        if act not in ("follow_up", "next_question", "wrap_up"):
            act = "next_question"
        if seconds_remaining <= 30:
            act = "wrap_up"
        speak = str(result.get("speak") or "").strip()
        if not speak:
            if act == "wrap_up":
                speak = "Thanks — that was helpful."
            elif seconds_remaining <= 60:
                speak = "In about a minute, what's the strongest reason you're a fit for this role?"
            elif seconds_remaining <= 120:
                speak = "Last full question — can you share one brief example that shows your impact?"
            else:
                speak = "Can you share a specific example of that?"
        scores = {
            "content": _safe_score((result.get("scores") or {}).get("content") if isinstance(result.get("scores"), dict) else None),
            "structure": _safe_score((result.get("scores") or {}).get("structure") if isinstance(result.get("scores"), dict) else None),
            "clarity": _safe_score((result.get("scores") or {}).get("clarity") if isinstance(result.get("scores"), dict) else None),
        }
        new_covered = _normalize_covered_ids(result.get("covered_plan_ids"), plan_norm)
        merged_covered = list(covered)
        for pid in new_covered:
            if pid not in merged_covered:
                merged_covered.append(pid)
        tip = _tip_from_scores(result.get("tip"), scores)
        notes = result.get("running_notes") if isinstance(result.get("running_notes"), list) else list(running_notes or [])
        return {
            "speak": speak,
            "act": act,
            "scores": scores,
            "tip": tip,
            "covered_plan_ids": merged_covered,
            "running_notes": notes,
        }

    async def debrief(
        self,
        *,
        style: str,
        turns: List[Dict[str, Any]],
        job_analysis: Optional[Dict[str, Any]] = None,
        user_api_key: Optional[str] = None,
        model: Optional[str] = None,
        llm_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate end-of-session scored debrief.

        Returns:
            Debrief dict with overall_score, strengths, improvements, etc.
        """
        style = (style or "").lower().strip()
        if style not in VALID_STYLES:
            style = "hr"
        style_pack = STYLE_PACKS[style]
        job_info = _compact_dict(
            job_analysis,
            ["job_title", "company_name", "required_skills"],
            limit=800,
        )
        transcript_full = _format_turns(turns, limit=40)
        prompt = DEBRIEF_PROMPT.format(
            style=style,
            style_pack=style_pack,
            job_info=job_info,
            transcript_full=transcript_full[:8000],
        )
        result = await self._generate_json(
            prompt,
            user_api_key=user_api_key,
            model=model,
            llm_provider=llm_provider,
        )
        scores = result.get("scores") if isinstance(result.get("scores"), dict) else {}
        strengths = result.get("strengths") if isinstance(result.get("strengths"), list) else []
        improvements = result.get("improvements") if isinstance(result.get("improvements"), list) else []
        return {
            "overall_score": _safe_score(result.get("overall_score")),
            "scores": {
                "content": _safe_score(scores.get("content")),
                "structure": _safe_score(scores.get("structure")),
                "clarity": _safe_score(scores.get("clarity")),
                "role_fit": _safe_score(scores.get("role_fit")),
                "style_focus": _safe_score(scores.get("style_focus")),
            },
            "strengths": [str(s) for s in strengths[:5]],
            "improvements": [str(s) for s in improvements[:5]],
            "weakest_answer_rewrite": str(result.get("weakest_answer_rewrite") or ""),
            "summary": str(result.get("summary") or ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
