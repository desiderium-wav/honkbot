"""
Database Access Layer — Shared DB Connection Management and Helpers

This module provides:
- Connection pooling and management
- Helper functions for common DB operations
- Schema initialization
- Graceful reconnection handling

All persistence modules should use this layer instead of direct db.py calls.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

import oracledb

from db import get_connection

logger = logging.getLogger(__name__)

# Global connection reference for reuse
_connection: Optional[oracledb.Connection] = None


def get_db_connection(retries: int = 3) -> oracledb.Connection:
    """
    Get a database connection with automatic reconnection.
    Reuses existing connection if available and healthy.
    """
    global _connection
    
    if _connection is not None:
        try:
            # Test connection health with a simple query
            with _connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM DUAL")
            return _connection
        except Exception as e:
            logger.warning(f"Existing connection unhealthy: {e}, reconnecting...")
            try:
                _connection.close()
            except Exception:
                pass
            _connection = None
    
    # Create new connection
    _connection = get_connection(retries=retries)
    return _connection


def close_connection() -> None:
    """Close the global connection if it exists."""
    global _connection
    if _connection is not None:
        try:
            _connection.close()
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
        finally:
            _connection = None


@contextmanager
def db_cursor():
    """
    Context manager for database cursors with automatic error handling.
    
    Usage:
        with db_cursor() as cursor:
            cursor.execute("SELECT * FROM table")
            rows = cursor.fetchall()
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}", exc_info=True)
        raise
    finally:
        cursor.close()


def execute_ddl(ddl_statements: List[str]) -> None:
    """
    Execute DDL statements (CREATE TABLE, etc.)
    Ignores "table already exists" errors.
    """
    with db_cursor() as cursor:
        for ddl in ddl_statements:
            try:
                cursor.execute(ddl)
                logger.info(f"Executed DDL: {ddl[:60]}...")
            except oracledb.DatabaseError as e:
                error_obj, = e.args
                # ORA-00955: name is already used by an existing object
                if error_obj.code == 955:
                    logger.debug(f"Object already exists: {ddl[:60]}...")
                else:
                    raise


def upsert(
    table: str,
    key_columns: Dict[str, Any],
    value_columns: Dict[str, Any],
) -> None:
    """
    Insert or update a row based on key columns.
    
    Args:
        table: Table name
        key_columns: Columns that identify the row (WHERE clause)
        value_columns: Columns to set (SET clause for UPDATE, values for INSERT)
    """
    all_columns = {**key_columns, **value_columns}
    
    # Try UPDATE first
    set_clause = ", ".join(f"{col} = :{col}" for col in value_columns.keys())
    where_clause = " AND ".join(f"{col} = :{col}" for col in key_columns.keys())
    
    update_sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
    
    with db_cursor() as cursor:
        cursor.execute(update_sql, all_columns)
        
        # If no rows updated, INSERT
        if cursor.rowcount == 0:
            columns = ", ".join(all_columns.keys())
            placeholders = ", ".join(f":{col}" for col in all_columns.keys())
            insert_sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            cursor.execute(insert_sql, all_columns)


def fetch_one(query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Tuple]:
    """Execute a query and return one row."""
    with db_cursor() as cursor:
        cursor.execute(query, params or {})
        return cursor.fetchone()


def fetch_all(query: str, params: Optional[Dict[str, Any]] = None) -> List[Tuple]:
    """Execute a query and return all rows."""
    with db_cursor() as cursor:
        cursor.execute(query, params or {})
        return cursor.fetchall()


def delete_rows(table: str, where_columns: Dict[str, Any]) -> int:
    """
    Delete rows from a table based on WHERE conditions.
    Returns number of rows deleted.
    """
    where_clause = " AND ".join(f"{col} = :{col}" for col in where_columns.keys())
    delete_sql = f"DELETE FROM {table} WHERE {where_clause}"
    
    with db_cursor() as cursor:
        cursor.execute(delete_sql, where_columns)
        return cursor.rowcount


def initialize_schema() -> None:
    """
    Initialize all database tables for HonkBot persistence.
    Called once on bot startup.
    """
    ddl_statements = [
        # State/Memory tables
        """
        CREATE TABLE honkbot_user_honk_counts (
            user_id NUMBER PRIMARY KEY,
            honk_count NUMBER NOT NULL
        )
        """,
        """
        CREATE TABLE honkbot_channel_honk_activity (
            channel_id NUMBER PRIMARY KEY,
            activity_count NUMBER NOT NULL
        )
        """,
        """
        CREATE TABLE honkbot_cooldowns (
            cooldown_key VARCHAR2(100),
            target_id NUMBER,
            until_timestamp NUMBER NOT NULL,
            PRIMARY KEY (cooldown_key, target_id)
        )
        """,
        """
        CREATE TABLE honkbot_takeover_thresholds (
            channel_id NUMBER PRIMARY KEY,
            threshold_value NUMBER NOT NULL
        )
        """,
        """
        CREATE TABLE honkbot_recent_actions (
            user_id NUMBER,
            action_name VARCHAR2(200),
            action_timestamp NUMBER NOT NULL,
            PRIMARY KEY (user_id, action_name, action_timestamp)
        )
        """,
        """
        CREATE TABLE honkbot_honklocks (
            user_id NUMBER PRIMARY KEY,
            locked_at NUMBER NOT NULL
        )
        """,
        """
        CREATE TABLE honkbot_echolocks (
            user_id NUMBER PRIMARY KEY,
            locked_at NUMBER NOT NULL
        )
        """,
        """
        CREATE TABLE honkbot_safety_state (
            guild_id NUMBER PRIMARY KEY,
            enabled NUMBER(1) NOT NULL,
            channel_exclusions CLOB,
            immunity_roles CLOB,
            module_toggles CLOB,
            cooldowns CLOB
        )
        """,
        """
        CREATE TABLE honkbot_global_state (
            state_key VARCHAR2(100) PRIMARY KEY,
            state_value VARCHAR2(1000)
        )
        """,
        
        # Media/Context tables
        """
        CREATE TABLE honkbot_context_messages (
            message_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            message_timestamp TIMESTAMP NOT NULL,
            author VARCHAR2(200) NOT NULL,
            content CLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE honkbot_context_keywords (
            keyword VARCHAR2(200) PRIMARY KEY,
            keyword_count NUMBER NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE honkbot_learned_keywords (
            keyword VARCHAR2(200) PRIMARY KEY,
            learned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE honkbot_keyword_topics (
            keyword VARCHAR2(200) PRIMARY KEY,
            topic VARCHAR2(100) NOT NULL
        )
        """,
        
        # Media/Providers tables
        """
        CREATE TABLE honkbot_server_media (
            media_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            guild_id NUMBER NOT NULL,
            keyword VARCHAR2(200) NOT NULL,
            media_url VARCHAR2(2000) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX idx_server_media_guild_keyword 
        ON honkbot_server_media(guild_id, keyword)
        """,
        
        # Retaliation tables
        """
        CREATE TABLE honkbot_provocation_scores (
            user_id NUMBER PRIMARY KEY,
            score NUMBER NOT NULL,
            last_updated TIMESTAMP NOT NULL
        )
        """,
        """
        CREATE TABLE honkbot_provocation_history (
            history_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id NUMBER NOT NULL,
            content VARCHAR2(4000),
            mentions CLOB,
            created_at TIMESTAMP NOT NULL
        )
        """,
        """
        CREATE INDEX idx_provocation_history_user 
        ON honkbot_provocation_history(user_id, created_at DESC)
        """,
    ]
    
    execute_ddl(ddl_statements)
    logger.info("Database schema initialized successfully")
