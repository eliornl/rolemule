"""
Utility functions for parsing structured data from LLM responses.
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional, Match

logger = logging.getLogger(__name__)


def _fix_json_strings(text: str) -> str:
    """
    Escape literal control characters (newlines, tabs, carriage returns) that
    appear inside JSON string values.

    LLMs frequently output literal newlines inside JSON strings, which is
    invalid JSON and causes json.loads() to raise "Unterminated string".
    This function walks the text character-by-character and replaces them
    with their JSON escape sequences only when inside a string value.

    Args:
        text: Raw JSON-like text from the LLM

    Returns:
        Text with control characters inside strings properly escaped
    """
    result: List[str] = []
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == "\\" and in_string:
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch == "\n":
            result.append("\\n")
        elif in_string and ch == "\r":
            result.append("\\r")
        elif in_string and ch == "\t":
            result.append("\\t")
        else:
            result.append(ch)

    return "".join(result)


def _repair_truncated_json(text: str) -> str:
    """
    Attempt to repair JSON that was truncated mid-generation by the LLM.

    After fixing literal control characters, closes any unclosed string value
    and then closes unclosed arrays/objects in reverse order so json.loads()
    can parse whatever data was produced before truncation.

    Args:
        text: Possibly-truncated JSON-like text from the LLM

    Returns:
        Repaired text that may be parseable by json.loads()
    """
    fixed = _fix_json_strings(text)

    result: List[str] = []
    stack: List[str] = []
    in_string = False
    escape_next = False

    for ch in fixed:
        result.append(ch)
        if escape_next:
            escape_next = False
        elif ch == "\\" and in_string:
            escape_next = True
        elif ch == '"':
            in_string = not in_string
        elif not in_string:
            if ch in "{[":
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()

    # Close any unclosed string
    if in_string:
        result.append('"')

    # Remove trailing commas before closing (common LLM artifact)
    repaired = "".join(result).rstrip()
    repaired = re.sub(r",\s*$", "", repaired)

    # Close unclosed structures in reverse order
    for open_ch in reversed(stack):
        repaired += "}" if open_ch == "{" else "]"

    return repaired


def _try_parse(text: str) -> Optional[Dict[str, Any]]:
    """Try raw → fix control chars → repair truncation, return first success."""
    for candidate in (text, _fix_json_strings(text), _repair_truncated_json(text)):
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            logger.debug("JSON parse candidate failed", exc_info=True)
    return None


def parse_json_from_llm_response(response: Any) -> Dict[str, Any]:
    """
    Parse JSON from LLM response in various formats.

    Attempts three increasingly aggressive recovery strategies:
    1. Raw parse
    2. Fix literal control characters inside strings
    3. Repair truncated JSON (close open strings and brackets)

    Args:
        response: LLM response (may be dict with 'response' key or direct string)

    Returns:
        Parsed JSON data as dictionary, or empty dict if all strategies fail
    """
    response_text: str = (
        response.get("response", response) if isinstance(response, dict) else response
    )

    # Strategy 1: JSON fenced in triple backticks
    json_match: Optional[Match[str]] = re.search(
        r"```json\s*([\s\S]*?)\s*```", response_text
    )
    if json_match:
        result = _try_parse(json_match.group(1).strip())
        if result is not None:
            return result

    # Strategy 2: largest {...} block in the response
    json_match = re.search(r"(\{[\s\S]*\})", response_text)
    if json_match:
        result = _try_parse(json_match.group(1).strip())
        if result is not None:
            return result

    # Strategy 3: entire response text (handles truncated JSON with no closing })
    # Find the first { and try to repair everything from there
    start = response_text.find("{")
    if start != -1:
        result = _try_parse(response_text[start:])
        if result is not None:
            return result

    logger.warning("Failed to parse AI response as JSON after all repair attempts")
    logger.debug("Raw LLM response (first 500 chars): %s", response_text[:500])
    return {}
