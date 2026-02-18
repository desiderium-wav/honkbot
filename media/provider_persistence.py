"""
Media Provider Persistence — Save and Load Server Media Index from Oracle DB

This module handles persistence for media/providers.py ServerMediaProvider:
- Server-uploaded media URLs indexed by guild and keyword
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional

import db_layer

logger = logging.getLogger(__name__)


def load_server_media_index() -> Dict[int, Dict[str, List[str]]]:
    """
    Load server media index from database.
    Returns index structure: {guild_id: {keyword: [urls]}}
    """
    index: Dict[int, Dict[str, List[str]]] = {}
    
    try:
        rows = db_layer.fetch_all(
            "SELECT guild_id, keyword, media_url FROM honkbot_server_media ORDER BY guild_id, keyword"
        )
        
        for guild_id, keyword, media_url in rows:
            guild_id = int(guild_id)
            keyword = str(keyword).lower()
            media_url = str(media_url)
            
            guild_index = index.setdefault(guild_id, {})
            keyword_list = guild_index.setdefault(keyword, [])
            keyword_list.append(media_url)
        
        logger.info(f"Loaded server media index: {len(rows)} entries across {len(index)} guilds")
    except Exception as e:
        logger.error(f"Error loading server media index: {e}", exc_info=True)
    
    return index


def save_server_media(guild_id: int, keywords: Iterable[str], urls: Iterable[str]) -> None:
    """
    Save server media URLs for a guild.
    
    Args:
        guild_id: Discord guild ID
        keywords: Keywords associated with the media
        urls: Media URLs to save
    """
    try:
        url_list = list(urls)
        if not url_list:
            return
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            for url in url_list:
                with db_layer.db_cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO honkbot_server_media (guild_id, keyword, media_url) 
                        VALUES (:guild_id, :keyword, :url)
                        """,
                        {"guild_id": guild_id, "keyword": keyword_lower, "url": url}
                    )
        
        logger.debug(f"Saved {len(url_list)} media URLs for guild {guild_id}")
    except Exception as e:
        logger.error(f"Error saving server media: {e}", exc_info=True)


def delete_server_media(guild_id: int, keyword: Optional[str] = None, url: Optional[str] = None) -> int:
    """
    Delete server media entries.
    
    Args:
        guild_id: Discord guild ID
        keyword: Optional keyword filter
        url: Optional URL filter
    
    Returns:
        Number of entries deleted
    """
    try:
        where_parts = ["guild_id = :guild_id"]
        params = {"guild_id": guild_id}
        
        if keyword:
            where_parts.append("keyword = :keyword")
            params["keyword"] = keyword.lower()
        
        if url:
            where_parts.append("media_url = :url")
            params["url"] = url
        
        where_clause = " AND ".join(where_parts)
        
        with db_layer.db_cursor() as cursor:
            cursor.execute(f"DELETE FROM honkbot_server_media WHERE {where_clause}", params)
            deleted = cursor.rowcount
        
        logger.debug(f"Deleted {deleted} server media entries")
        return deleted
    except Exception as e:
        logger.error(f"Error deleting server media: {e}", exc_info=True)
        return 0
