"""
Retaliation Engine — Autonomous Punishment Execution

THIS MODULE DEFINES AUTONOMOUS TRIGGERS (NO USER COMMANDS).

Responsibilities:
- Observe provocation scores
- Consult Goose Brain state
- Factor honk counters into escalation severity
- Select appropriate retaliation actions
- Trigger Honkify, HonkLocks, media actions, voice actions, Takeovers, or DMs
- Avoid repetition and excessive spam

This system escalates behavior, not fairness. 
This module is invoked automatically by message listeners
or background decision loops.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from retaliation import scoring

logger = logging.getLogger(__name__)

# In-memory score cache: {user_id: (score, last_updated)}
_provocation_scores: Dict[int, tuple[float, datetime]] = {}


def initialize() -> None:
    """Load persisted provocation scores on startup."""
    global _provocation_scores
    try:
        from retaliation import persistence
        _provocation_scores = persistence.load_provocation_scores()
        logger.info("Retaliation engine initialized")
    except Exception as e:
        logger.error(f"Error initializing retaliation engine: {e}", exc_info=True)


def get_provocation_score(user_id: int, apply_decay: bool = True) -> float:
    """
    Get current provocation score for a user.
    Optionally apply decay based on time elapsed.
    """
    if user_id not in _provocation_scores:
        return 0.0
    
    score, last_updated = _provocation_scores[user_id]
    
    if apply_decay:
        now = datetime.now(timezone.utc)
        score = scoring.apply_decay(score, last_updated, now)
    
    return score


def update_provocation_score(
    user_id: int,
    message_content: str,
    mentions: list[str],
    mention_everyone: bool = False,
    mention_role: bool = False,
) -> float:
    """
    Update provocation score for a user based on a message.
    Returns the new score.
    """
    from retaliation import persistence
    
    # Get existing score with decay
    current_score = get_provocation_score(user_id, apply_decay=True)
    
    # Create message event
    now = datetime.now(timezone.utc)
    message_event = scoring.MessageEvent(
        author_id=str(user_id),
        content=message_content,
        mentions=mentions,
        mention_everyone=mention_everyone,
        mention_role=mention_role,
        created_at=now,
    )
    
    # Load history for context
    history_data = persistence.load_provocation_history(user_id, limit=5)
    history_samples = [
        scoring.HistorySample(
            content=h["content"],
            created_at=h["created_at"],
            mentions=h["mentions"],
        )
        for h in history_data
    ]
    
    # Score the message
    message_score = scoring.score_message(message_event, history_samples, now)
    
    # Update total score
    new_score = current_score + message_score
    _provocation_scores[user_id] = (new_score, now)
    
    # Persist
    try:
        persistence.save_provocation_score(user_id, new_score, now)
        persistence.save_provocation_history(user_id, message_content, mentions, now)
    except Exception as e:
        logger.error(f"Error persisting provocation data: {e}")
    
    return new_score


def reset_provocation_score(user_id: int) -> None:
    """Reset a user's provocation score."""
    from retaliation import persistence
    
    _provocation_scores.pop(user_id, None)
    
    try:
        persistence.delete_provocation_score(user_id)
    except Exception as e:
        logger.error(f"Error deleting provocation score: {e}")


def get_guild_provocation(guild_id: int) -> float:
    """
    Get aggregate provocation level for a guild.
    Used by decision loop to factor into chaos calculations.
    """
    # Simple implementation: return max score across all users with decay applied
    # Could be enhanced with guild-specific logic
    if not _provocation_scores:
        return 0.0
    
    now = datetime.now(timezone.utc)
    decayed_scores = []
    for user_id, (score, last_updated) in _provocation_scores.items():
        decayed_score = scoring.apply_decay(score, last_updated, now)
        decayed_scores.append(decayed_score)
    
    return max(decayed_scores) if decayed_scores else 0.0

