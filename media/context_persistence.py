"""
Media Context Persistence — Save and Load Conversation Context from Oracle DB

This module handles persistence for media/context.py:
- Message history
- Keyword counts
- Learned keywords
- Keyword-to-topic mappings
"""

from __future__ import annotations

import logging
from collections import Counter, deque
from datetime import datetime
from typing import Dict, Set

import db_layer

logger = logging.getLogger(__name__)


def load_context_state(analyzer) -> None:
    """
    Load context state from database into a ContextAnalyzer instance.
    Called on bot startup.
    """
    try:
        _load_messages(analyzer)
        _load_keywords(analyzer)
        _load_learned_keywords(analyzer)
        _load_keyword_topics(analyzer)
        logger.info("Successfully loaded context state from database")
    except Exception as e:
        logger.error(f"Error loading context state: {e}", exc_info=True)


def _load_messages(analyzer) -> None:
    """Load recent messages into history."""
    # Load last N messages (matching max_history)
    rows = db_layer.fetch_all(
        f"""
        SELECT message_timestamp, author, content 
        FROM honkbot_context_messages 
        ORDER BY message_id DESC 
        FETCH FIRST {analyzer.max_history} ROWS ONLY
        """,
        {}
    )
    
    # Reverse to get chronological order
    for message_timestamp, author, content in reversed(rows):
        # Convert Oracle TIMESTAMP to Python datetime
        if isinstance(message_timestamp, str):
            timestamp = datetime.fromisoformat(message_timestamp)
        else:
            timestamp = message_timestamp
        
        from media.context import MessageEvent
        event = MessageEvent(timestamp=timestamp, author=str(author), content=str(content))
        analyzer._history.append(event)
    
    logger.debug(f"Loaded {len(rows)} message history items")


def _load_keywords(analyzer) -> None:
    """Load keyword counts."""
    rows = db_layer.fetch_all("SELECT keyword, keyword_count FROM honkbot_context_keywords")
    
    for keyword, count in rows:
        analyzer._keyword_counts[str(keyword)] = int(count)
    
    logger.debug(f"Loaded {len(rows)} keyword counts")


def _load_learned_keywords(analyzer) -> None:
    """Load learned keywords."""
    rows = db_layer.fetch_all("SELECT keyword FROM honkbot_learned_keywords")
    
    for (keyword,) in rows:
        analyzer.learned_keywords.add(str(keyword))
    
    logger.debug(f"Loaded {len(rows)} learned keywords")


def _load_keyword_topics(analyzer) -> None:
    """Load keyword-to-topic mappings."""
    rows = db_layer.fetch_all("SELECT keyword, topic FROM honkbot_keyword_topics")
    
    for keyword, topic in rows:
        analyzer.keyword_topics[str(keyword)] = str(topic)
    
    logger.debug(f"Loaded {len(rows)} keyword topics")


def save_message(author: str, content: str, timestamp: datetime) -> None:
    """Save a message to database."""
    try:
        with db_layer.db_cursor() as cursor:
            cursor.execute(
                "INSERT INTO honkbot_context_messages (message_timestamp, author, content) VALUES (:ts, :author, :content)",
                {"ts": timestamp, "author": author, "content": content}
            )
        
        # Keep table size manageable - delete old messages beyond reasonable limit
        with db_layer.db_cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM honkbot_context_messages 
                WHERE message_id NOT IN (
                    SELECT message_id FROM honkbot_context_messages 
                    ORDER BY message_id DESC 
                    FETCH FIRST 1000 ROWS ONLY
                )
                """
            )
    except Exception as e:
        logger.error(f"Error saving message: {e}", exc_info=True)


def save_keywords(keyword_counts: Counter) -> None:
    """Save all keyword counts to database."""
    try:
        # Clear and rewrite for simplicity
        with db_layer.db_cursor() as cursor:
            cursor.execute("DELETE FROM honkbot_context_keywords")
        
        for keyword, count in keyword_counts.items():
            if count > 0:
                db_layer.upsert(
                    "honkbot_context_keywords",
                    {"keyword": keyword},
                    {"keyword_count": count}
                )
    except Exception as e:
        logger.error(f"Error saving keywords: {e}", exc_info=True)


def save_learned_keywords(learned_keywords: Set[str]) -> None:
    """Save learned keywords to database."""
    try:
        # Clear and rewrite
        with db_layer.db_cursor() as cursor:
            cursor.execute("DELETE FROM honkbot_learned_keywords")
        
        for keyword in learned_keywords:
            with db_layer.db_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO honkbot_learned_keywords (keyword) VALUES (:keyword)",
                    {"keyword": keyword}
                )
    except Exception as e:
        logger.error(f"Error saving learned keywords: {e}", exc_info=True)


def save_keyword_topics(keyword_topics: Dict[str, str]) -> None:
    """Save keyword-to-topic mappings to database."""
    try:
        # Only save custom mappings (not defaults)
        from media.context import DEFAULT_KEYWORD_TOPICS
        
        # Clear existing
        with db_layer.db_cursor() as cursor:
            cursor.execute("DELETE FROM honkbot_keyword_topics")
        
        for keyword, topic in keyword_topics.items():
            # Skip default mappings
            if DEFAULT_KEYWORD_TOPICS.get(keyword) == topic:
                continue
            
            with db_layer.db_cursor() as cursor:
                cursor.execute(
                    "INSERT INTO honkbot_keyword_topics (keyword, topic) VALUES (:keyword, :topic)",
                    {"keyword": keyword, "topic": topic}
                )
    except Exception as e:
        logger.error(f"Error saving keyword topics: {e}", exc_info=True)


def persist_context_snapshot(analyzer) -> None:
    """
    Persist current context snapshot periodically.
    Should be called after significant changes or on a timer.
    """
    try:
        save_keywords(analyzer._keyword_counts)
        save_learned_keywords(analyzer.learned_keywords)
        save_keyword_topics(analyzer.keyword_topics)
    except Exception as e:
        logger.error(f"Error persisting context snapshot: {e}", exc_info=True)
