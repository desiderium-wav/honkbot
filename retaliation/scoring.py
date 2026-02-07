"""
Retaliation Scoring — Provocation Evaluation Logic

THIS MODULE DEFINES NO COMMANDS.

Responsibilities:
- Analyze messages, mentions, insults, and behavior
- Assign provocation scores to users
- Apply decay over time
- Flag thresholds for retaliation eligibility

This module contains scoring logic only.
It does not decide punishments or execute actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence


# ---------------------------
# Configuration & thresholds
# ---------------------------

@dataclass(frozen=True)
class Thresholds:
    warn: float = 6.0
    retaliate: float = 12.0
    severe: float = 18.0


@dataclass(frozen=True)
class ScoringConfig:
    # Content analysis
    base_insult: float = 2.0
    profanity: float = 1.2
    threat: float = 2.5
    all_caps_multiplier: float = 1.4
    exclamation_multiplier: float = 1.1

    # Mentions
    mention_direct: float = 1.5
    mention_group: float = 0.8

    # Repetition & escalation
    repetition: float = 1.0
    escalation: float = 2.0
    rapid_fire: float = 1.5

    # Decay
    half_life_seconds: float = 900.0  # 15 minutes

    thresholds: Thresholds = Thresholds()


# ---------------------------
# Data models
# ---------------------------

@dataclass(frozen=True)
class MessageEvent:
    """
    Minimal message representation for scoring.
    """
    author_id: str
    content: str
    mentions: Sequence[str]
    mention_everyone: bool = False
    mention_role: bool = False
    created_at: datetime = datetime.now(timezone.utc)


@dataclass(frozen=True)
class HistorySample:
    """
    Prior messages from the same author (most recent first preferred).
    """
    content: str
    created_at: datetime
    mentions: Sequence[str]


# ---------------------------
# Lexical heuristics
# ---------------------------

_INSULT_KEYWORDS = {
    "idiot", "moron", "stupid", "dumb", "loser", "trash", "garbage",
    "clown", "pathetic", "worthless", "useless", "shut up", "shutup",
}
_PROFANITY = {
    "fuck", "fucking", "shit", "bitch", "bastard", "asshole", "dick",
    "piss", "cunt",
}
_THREATS = {
    "kill", "hurt", "destroy", "ruin", "burn", "die", "dead",
    "dox", "doxx", "doxxing",
}


# ---------------------------
# Public API
# ---------------------------

def score_message(
    message: MessageEvent,
    history: Optional[Iterable[HistorySample]] = None,
    now: Optional[datetime] = None,
    config: ScoringConfig = ScoringConfig(),
) -> float:
    """
    Compute provocation score for a message event.
    """
    now = now or datetime.now(timezone.utc)
    history_list = list(history or [])

    base = (
        _score_content(message.content, config)
        + _score_mentions(message, config)
        + _score_repetition(message, history_list, config)
        + _score_escalation(message, history_list, config, now)
    )

    return max(0.0, base)


def apply_decay(
    score: float,
    last_updated: datetime,
    now: Optional[datetime] = None,
    config: ScoringConfig = ScoringConfig(),
) -> float:
    """
    Apply exponential decay to an existing provocation score.
    """
    now = now or datetime.now(timezone.utc)
    elapsed = max(0.0, (now - last_updated).total_seconds())
    if config.half_life_seconds <= 0:
        return score
    decay_factor = 0.5 ** (elapsed / config.half_life_seconds)
    return score * decay_factor


def meets_threshold(score: float, config: ScoringConfig = ScoringConfig()) -> bool:
    """
    True if score indicates retaliation eligibility.
    """
    return score >= config.thresholds.retaliate


def threshold_level(score: float, config: ScoringConfig = ScoringConfig()) -> str:
    """
    Returns severity label for downstream systems.
    """
    if score >= config.thresholds.severe:
        return "severe"
    if score >= config.thresholds.retaliate:
        return "retaliate"
    if score >= config.thresholds.warn:
        return "warn"
    return "none"


# ---------------------------
# Internal scoring helpers
# ---------------------------

def _score_content(content: str, config: ScoringConfig) -> float:
    text = content.lower()
    score = 0.0

    # keyword hits
    score += _keyword_hits(text, _INSULT_KEYWORDS) * config.base_insult
    score += _keyword_hits(text, _PROFANITY) * config.profanity
    score += _keyword_hits(text, _THREATS) * config.threat

    # intensity modifiers
    if _is_all_caps(content):
        score *= config.all_caps_multiplier
    if "!" in content:
        score *= config.exclamation_multiplier

    return score


def _score_mentions(message: MessageEvent, config: ScoringConfig) -> float:
    score = 0.0
    if message.mentions:
        score += len(message.mentions) * config.mention_direct
    if message.mention_everyone or message.mention_role:
        score += config.mention_group
    return score


def _score_repetition(
    message: MessageEvent,
    history: Sequence[HistorySample],
    config: ScoringConfig,
) -> float:
    """
    Penalize repeated content or repeated mentions in a short window.
    """
    if not history:
        return 0.0

    text = message.content.strip().lower()
    repeated = 0
    repeated_mentions = 0

    for sample in history[:5]:
        if sample.content.strip().lower() == text:
            repeated += 1
        if set(sample.mentions) & set(message.mentions):
            repeated_mentions += 1

    return (repeated + repeated_mentions) * config.repetition


def _score_escalation(
    message: MessageEvent,
    history: Sequence[HistorySample],
    config: ScoringConfig,
    now: datetime,
) -> float:
    """
    Detect rapid-fire insults or intensifying language over short intervals.
    """
    if not history:
        return 0.0

    recent_window = []
    for sample in history[:5]:
        age = (now - sample.created_at).total_seconds()
        if age <= 120:  # last 2 minutes
            recent_window.append(sample)

    if not recent_window:
        return 0.0

    current_hits = _keyword_hits(message.content.lower(), _INSULT_KEYWORDS | _PROFANITY | _THREATS)
    prior_hits = sum(
        _keyword_hits(s.content.lower(), _INSULT_KEYWORDS | _PROFANITY | _THREATS)
        for s in recent_window
    )

    escalation = 0.0
    if current_hits > 0 and prior_hits > 0:
        escalation += config.escalation

    if len(recent_window) >= 3:
        escalation += config.rapid_fire

    return escalation


def _keyword_hits(text: str, keywords: set[str]) -> int:
    return sum(1 for k in keywords if k in text)


def _is_all_caps(content: str) -> bool:
    letters = [c for c in content if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)
