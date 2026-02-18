"""
Database bootstrap / connection helper.

- Keeps a cached connection settable via set_cached_connection().
- get_connection() will return the cached connection immediately if present.
- Supports user/password and wallet-based attempts (with retries).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

try:
    import oracledb
except Exception:  # pragma: no cover - oracledb may not be installed in all environments
    oracledb = None  # type: ignore

logger = logging.getLogger("db")

# Env vars
TNS_ADMIN = os.getenv("TNS_ADMIN")
WALLET_PASS = os.getenv("WALLET_PASS")
DB_DSN = os.getenv("DB_DSN")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Cached connection that can be set by the background connector.
_cached_conn: Optional["oracledb.Connection"] = None


def set_cached_connection(conn: Optional["oracledb.Connection"]) -> None:
    """Store a connection object to be returned by future get_connection() calls."""
    global _cached_conn
    _cached_conn = conn


def _get_cached_connection() -> Optional["oracledb.Connection"]:
    return _cached_conn


# Try to initialize the Oracle thick client if python-oracledb is available.
# If initialization fails (e.g. DPI-1047), we log a warning and continue (thin mode).
if oracledb is not None:
    try:
        if TNS_ADMIN:
            oracledb.init_oracle_client(config_dir=TNS_ADMIN)
            logger.info("Initialized Oracle thick client using TNS_ADMIN=%s", TNS_ADMIN)
        else:
            logger.debug(
                "TNS_ADMIN not set; skipping explicit oracledb.init_oracle_client() - using thin mode by default."
            )
    except Exception as e:
        logger.warning(
            "Could not initialize Oracle thick client (DPI-1047 or similar). Falling back to thin mode. Error: %s",
            e,
        )
else:
    logger.warning("python-oracledb is not installed; database helper functions will be limited.")


def _try_connect_with_kwargs(connect_kwargs: dict) -> Optional["oracledb.Connection"]:
    """
    Try oracledb.connect with connect_kwargs. If TypeError (unexpected kwarg),
    retry once without wallet-related kwargs.
    """
    try:
        conn = oracledb.connect(**connect_kwargs)
        return conn
    except TypeError as te:
        logger.debug("Connection rejected kwargs (%s). Retrying without wallet kwargs.", te)
        cleaned = {k: v for k, v in connect_kwargs.items() if k not in ("wallet_password", "wallet_location")}
        try:
            conn = oracledb.connect(**cleaned)
            return conn
        except Exception as e2:
            logger.exception("Connection attempt failed after retry without wallet kwargs: %s", e2)
            return None
    except Exception as e:
        logger.exception("Connection attempt failed: %s", e)
        return None


def get_connection(retries: int = 1, retry_delay: float = 2.0) -> Optional["oracledb.Connection"]:
    """
    Return a DB connection or None.

    - If a cached connection has been set via set_cached_connection(), return it immediately.
    - Otherwise attempt to connect according to environment vars.
    """
    # Return cached connection if present (fast, non-blocking).
    cached = _get_cached_connection()
    if cached is not None:
        return cached

    if oracledb is None:
        logger.debug("oracledb module not available; get_connection returning None")
        return None

    dsn = DB_DSN or os.getenv("DB_DSN")
    user = DB_USER or os.getenv("DB_USER")
    password = DB_PASSWORD or os.getenv("DB_PASSWORD")
    wallet_pass = WALLET_PASS or os.getenv("WALLET_PASS")
    tns_admin = TNS_ADMIN or os.getenv("TNS_ADMIN")

    if not dsn:
        logger.info("DB_DSN not set; skipping database connection.")
        return None

    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt < max(1, int(retries)):
        attempt += 1
        if user and password:
            connect_kwargs = {"user": user, "password": password, "dsn": dsn}
            if wallet_pass:
                connect_kwargs["wallet_password"] = wallet_pass
            logger.info("Attempting DB connection using user/password (attempt %d/%d) DSN=%s", attempt, retries, dsn)
            conn = _try_connect_with_kwargs(connect_kwargs)
            if conn:
                # Cache the connection for future fast returns.
                set_cached_connection(conn)
                logger.info("Successfully connected to Oracle DB using user/password (DSN=%s).", dsn)
                return conn
            last_exc = Exception("User/password connection failed (see logs).")
        else:
            if wallet_pass and tns_admin:
                connect_kwargs = {"dsn": dsn, "wallet_password": wallet_pass}
                logger.info(
                    "Attempting wallet-based DB connection (TNS_ADMIN=%s) (attempt %d/%d) DSN=%s",
                    tns_admin,
                    attempt,
                    retries,
                    dsn,
                )
                conn = _try_connect_with_kwargs(connect_kwargs)
                if conn:
                    set_cached_connection(conn)
                    logger.info("Successfully connected to Oracle DB using wallet auth (DSN=%s).", dsn)
                    return conn
                last_exc = Exception("Wallet-based connection failed (see logs).")
            else:
                logger.warning(
                    "DB_USER/DB_PASSWORD not provided and wallet information incomplete (TNS_ADMIN and WALLET_PASS required)."
                )
                return None

        # If we reach here and failed, sleep before next attempt (if applicable)
        if attempt < retries:
            logger.debug("Retrying DB connection after %.1fs...", retry_delay)
            time.sleep(retry_delay)

    logger.exception("All attempts to connect to Oracle DB failed (DSN=%s). Last error: %s", dsn, last_exc)
    return None
