"""
Retaliation Persistence — Save and Load Provocation Scores and History from Oracle DB

This module handles persistence for the retaliation system:
- User provocation scores
- Provocation history for score calculation
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Sequence

import db_layer

logger = logging.getLogger(__name__)


def load_provocation_scores() -> Dict[int, tuple[float, datetime]]:
    """
    Load provocation scores from database.
    Returns: {user_id: (score, last_updated)}
    """
    scores: Dict[int, tuple[float, datetime]] = {}
    
    try:
        rows = db_layer.fetch_all(
            "SELECT user_id, score, last_updated FROM honkbot_provocation_scores"
        )
        
        for user_id, score, last_updated in rows:
            user_id = int(user_id)
            score = float(score)
            
            # Convert Oracle TIMESTAMP to Python datetime
            if isinstance(last_updated, str):
                last_updated = datetime.fromisoformat(last_updated)
            
            # Ensure timezone-aware
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            
            scores[user_id] = (score, last_updated)
        
        logger.info(f"Loaded {len(scores)} provocation scores")
    except Exception as e:
        logger.error(f"Error loading provocation scores: {e}", exc_info=True)
    
    return scores


def save_provocation_score(user_id: int, score: float, last_updated: datetime) -> None:
    """Save a user's provocation score to database."""
    try:
        db_layer.upsert(
            "honkbot_provocation_scores",
            {"user_id": user_id},
            {
                "score": score,
                "last_updated": last_updated,
            }
        )
    except Exception as e:
        logger.error(f"Error saving provocation score: {e}", exc_info=True)


def delete_provocation_score(user_id: int) -> None:
    """Remove a user's provocation score from database."""
    try:
        db_layer.delete_rows("honkbot_provocation_scores", {"user_id": user_id})
    except Exception as e:
        logger.error(f"Error deleting provocation score: {e}", exc_info=True)


def load_provocation_history(user_id: int, limit: int = 10) -> List[dict]:
    """
    Load provocation history for a user.
    Returns list of history samples (most recent first).
    """
    history = []
    
    try:
        rows = db_layer.fetch_all(
            f"""
            SELECT content, mentions, created_at 
            FROM honkbot_provocation_history 
            WHERE user_id = :user_id 
            ORDER BY created_at DESC 
            FETCH FIRST {limit} ROWS ONLY
            """,
            {"user_id": user_id}
        )
        
        for content, mentions_json, created_at in rows:
            # Parse mentions JSON
            mentions = []
            if mentions_json:
                try:
                    mentions = json.loads(mentions_json)
                except Exception:
                    mentions = []
            
            # Convert timestamp
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            
            history.append({
                "content": str(content) if content else "",
                "mentions": mentions,
                "created_at": created_at,
            })
        
        logger.debug(f"Loaded {len(history)} history items for user {user_id}")
    except Exception as e:
        logger.error(f"Error loading provocation history: {e}", exc_info=True)
    
    return history


def save_provocation_history(user_id: int, content: str, mentions: Sequence[str], created_at: datetime) -> None:
    """Save a provocation history entry to database."""
    try:
        mentions_json = json.dumps(list(mentions))
        
        with db_layer.db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO honkbot_provocation_history (user_id, content, mentions, created_at) 
                VALUES (:user_id, :content, :mentions, :created_at)
                """,
                {
                    "user_id": user_id,
                    "content": content[:4000],  # Oracle VARCHAR2 limit
                    "mentions": mentions_json,
                    "created_at": created_at,
                }
            )
        
        # Keep history manageable - keep only last 100 entries per user
        with db_layer.db_cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM honkbot_provocation_history 
                WHERE user_id = :user_id 
                AND history_id NOT IN (
                    SELECT history_id FROM honkbot_provocation_history 
                    WHERE user_id = :user_id 
                    ORDER BY created_at DESC 
                    FETCH FIRST 100 ROWS ONLY
                )
                """,
                {"user_id": user_id}
            )
    except Exception as e:
        logger.error(f"Error saving provocation history: {e}", exc_info=True)


def cleanup_old_history(days: int = 30) -> None:
    """Remove provocation history older than specified days."""
    try:
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
        
        with db_layer.db_cursor() as cursor:
            cursor.execute(
                "DELETE FROM honkbot_provocation_history WHERE created_at < :cutoff",
                {"cutoff": cutoff_dt}
            )
            deleted = cursor.rowcount
        
        logger.info(f"Cleaned up {deleted} old provocation history entries")
    except Exception as e:
        logger.error(f"Error cleaning up history: {e}", exc_info=True)
