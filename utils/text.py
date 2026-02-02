"""
Text Utilities — Shared Message Processing Helpers

THIS MODULE DEFINES NO COMMANDS.

Provides reusable helpers for:
- Mock casing
- Word replacement
- Tokenization
- Safe text mutation

Used by lock systems and context analysis.
"""

from __future__ import annotations

import re
from typing import Iterable, List

__all__ = [
    "mock_case",
    "tokenize",
    "contains_token",
    "replace_token",
    "honk_replace",
    "normalize_whitespace",
    "safe_truncate",
]

# Splits into "word" tokens and single punctuation tokens, ignoring whitespace.
_TOKEN_RE = re.compile(r"[A-Za-z0-9']+|[^\w\s]")


def tokenize(text: str) -> List[str]:
    """
    Tokenize text into words and punctuation. Whitespace is not returned.
    Deterministic and lightweight; safe for inspection and replacement.
    """
    return _TOKEN_RE.findall(text)


def contains_token(text: str, token: str, *, case_sensitive: bool = False) -> bool:
    """
    Return True if a token is present in the tokenized text.
    """
    if not case_sensitive:
        token = token.lower()
        return any(t.lower() == token for t in tokenize(text))
    return token in tokenize(text)


def replace_token(
    text: str,
    token: str,
    replacement: str,
    *,
    case_sensitive: bool = False,
) -> str:
    """
    Replace whole-token occurrences with a replacement string.
    Respects word boundaries using token inspection rather than substring replace.
    """

    def _match(tok: str) -> bool:
        return tok == token if case_sensitive else tok.lower() == token.lower()

    parts: List[str] = []
    for part in re.split(r"(\s+)", text):
        if part.isspace() or not part:
            parts.append(part)
            continue

        # Replace on token basis within this chunk (preserving punctuation).
        tokens = _TOKEN_RE.findall(part)
        rebuilt = []
        idx = 0
        for t in tokens:
            # Find t's position in part to preserve original separators.
            start = part.find(t, idx)
            if start == -1:
                continue
            rebuilt.append(part[idx:start])
            rebuilt.append(replacement if _match(t) else t)
            idx = start + len(t)
        rebuilt.append(part[idx:])
        parts.append("".join(rebuilt))

    return "".join(parts)


def honk_replace(
    text: str,
    target: str,
    *,
    honk: str = "honk",
    case_sensitive: bool = False,
) -> str:
    """
    Replace a target token with a honk-like word.
    """
    return replace_token(text, target, honk, case_sensitive=case_sensitive)


def mock_case(text: str, *, start_upper: bool = False) -> str:
    """
    Alternates casing across letters in the text, leaving non-letters intact.
    Deterministic: starts with upper or lower based on start_upper.
    """
    result = []
    upper = start_upper
    for ch in text:
        if ch.isalpha():
            result.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            result.append(ch)
    return "".join(result)


def normalize_whitespace(text: str) -> str:
    """
    Collapse all whitespace runs to a single space and strip ends.
    """
    return " ".join(text.split())


def safe_truncate(text: str, max_length: int, *, ellipsis: str = "…") -> str:
    """
    Truncate text to max_length, appending ellipsis if truncation occurs.
    If max_length is too small for ellipsis, returns a clipped ellipsis.
    """
    if max_length < 0:
        raise ValueError("max_length must be non-negative")
    if len(text) <= max_length:
        return text
    if max_length == 0:
        return ""
    if len(ellipsis) >= max_length:
        return ellipsis[:max_length]
    return text[: max_length - len(ellipsis)] + ellipsis
