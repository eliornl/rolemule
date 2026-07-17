"""
Text Processing Utilities

Provides text processing functions for similarity calculation, skill extraction,
and other text analysis operations used across RoleMule.
"""

from difflib import SequenceMatcher
import re

MAX_LENGTH: int = 10000


def clean_text(text: str) -> str:
    """
    Clean and normalize text content for processing.

    Args:
        text: Raw text content to clean

    Returns:
        str: Cleaned and normalized text
    """
    # Input validation
    if not text.strip():
        return ""

    try:
        # Remove extra whitespace
        cleaned: str = re.sub(r"\s+", " ", text)

        # Remove special characters that might interfere with processing
        cleaned: str = re.sub(r"[\r\n\t]+", " ", cleaned)

        # Remove HTML tags if present (improved regex)
        cleaned: str = re.sub(r"<[^<>]*>", "", cleaned)

        # Remove any remaining HTML entities
        cleaned: str = re.sub(r"&[a-zA-Z0-9#]+;", " ", cleaned)

        # Normalize whitespace
        cleaned: str = cleaned.strip()

        return cleaned
    except Exception:
        # Fallback to basic cleaning if regex fails
        return text.strip() if text else ""


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two text strings using sequence matching.

    Args:
        text1: First text string
        text2: Second text string

    Returns:
        float: Similarity score between 0.0 and 1.0
    """
    # Handle empty strings
    if not text1.strip() and not text2.strip():
        return 1.0  # Both empty strings are identical
    if not text1.strip() or not text2.strip():
        return 0.0  # One empty, one not

    try:
        # Normalize texts - lowercase and remove extra whitespace
        text1_norm: str = " ".join(text1.lower().split())
        text2_norm: str = " ".join(text2.lower().split())

        # Handle very long texts by truncating for performance
        if len(text1_norm) > MAX_LENGTH:
            text1_norm: str = text1_norm[:MAX_LENGTH]
        if len(text2_norm) > MAX_LENGTH:
            text2_norm: str = text2_norm[:MAX_LENGTH]

        # Use SequenceMatcher for similarity calculation
        similarity: float = SequenceMatcher(None, text1_norm, text2_norm).ratio()

        return similarity
    except Exception:
        # Fallback to basic comparison if SequenceMatcher fails
        return 1.0 if text1.strip().lower() == text2.strip().lower() else 0.0
