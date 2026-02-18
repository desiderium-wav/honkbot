"""
Database bootstrap / connection helper.

This file attempts to initialize the Oracle "thick" client if available,
but will gracefully fall back to the python-oracledb "thin" mode if
thick client initialization fails (DPI-1047).

get_connection accepts retry parameters and supports:
 - User/password auth (DB_USER/DB_PASSWORD)
 - Wallet auth (TNS_ADMIN + WALLET_PASS) when user/password are not provided
It will try to pass the wallet password to the driver when available and
fall back if the driver does not accept that keyword.
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


# Try to initialize the Oracle thick client if python-oracledb is available.
# If initialization fails (e.g. DPI-1047), we log a warning and continue (thin mode).
if oracledb is not None:
    try:
        if TNS_ADMIN:
            # Only attempt init_oracle_client if TNS_ADMIN is set (wallets typically require it).
            oracledb.init_oracle_client(config_dir=TNS_ADMIN)
            logger.info("Initialized Oracle thick client using TNS_ADMIN=%s", TNS_ADMIN)
        else:
            logger.debug(
                "TNS_ADMIN not set; skipping explicit oracledb.init_oracle_client() - using thin mode by default."
            )
    except Exception as e:
        logger.warning(
            "Could not initialize Oracle thick client (DPI-1047 or similar). Falling back to python-oracledb thin mode. "
            "If you require the thick client, install Oracle Instant Client and set TNS_ADMIN appropriately. Error: %s",
            e,
        )
else:
    logger.warning("python-oracledb is not installed; database helper functions will be limited.")


def _try_connect_with_kwargs(connect_kwargs: dict) -> Optional["oracledb.Connection"]:
    """
    Try to call oracledb.connect with connect_kwargs. If the driver rejects
    unexpected kwargs (TypeError), retry by removing wallet-related kwargs.
    Returns a Connection or None.
    """
    try:
        conn = oracledb.connect(**connect_kwargs)
        return conn
    except TypeError as te:
        # Likely an unexpected kwarg (e.g., wallet_password not supported). Retry without wallet kwargs.
        # Remove any wallet-related keys and retry once.
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

    Parameters:
      - retries: number of attempts (>=1). If >1, the function will retry on failure.
      - retry_delay: seconds to wait between attempts.

    Environment variables used:
      - DB_DSN : DSN string (e.g. 'host:port/service_name' or TNS alias)
      - DB_USER
      - DB_PASSWORD
      - TNS_ADMIN (optional; used for wallets)
      - WALLET_PASS (optional; wallet password)

    Behavior:
      - If DB_DSN is not set, returns None.
      - If DB_USER and DB_PASSWORD are set, attempts user/password auth first.
      - If user/password are not set but WALLET_PASS and TNS_ADMIN are provided,
        attempts a wallet-based connect (best-effort).
    """
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

    # If we have user/password, prefer that path.
    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt < max(1, int(retries)):
        attempt += 1
        try:
            if user and password:
                # Build kwargs; include wallet_password if present (driver may accept it)
                connect_kwargs = {"user": user, "password": password, "dsn": dsn}
                if wallet_pass:
                    connect_kwargs["wallet_password"] = wallet_pass
                # Try connect (handles driver rejecting wallet kwargs internally)
                logger.info("Attempting DB connection using user/password (attempt %d/%d) DSN=%s", attempt, retries, dsn)
                conn = _try_connect_with_kwargs(connect_kwargs)
                if conn:
                    logger.info("Successfully connected to Oracle DB using user/password (DSN=%s).", dsn)
                    return conn
                else:
                    last_exc = Exception("User/password connection failed (see logs).")
            else:
                # No user/password provided. Try wallet-based connection if wallet info present.
                if wallet_pass and tns_admin:
                    # Try to use wallet auth — some drivers accept wallet_password at connect time.
                    connect_kwargs = {"dsn": dsn, "wallet_password": wallet_pass}
                    # Some environments require config_dir set via init_oracle_client; we already attempted that earlier if TNS_ADMIN set.
                    logger.info(
                        "Attempting wallet-based DB connection (TNS_ADMIN=%s) (attempt %d/%d) DSN=%s",
                        tns_admin,
                        attempt,
                        retries,
                        dsn,
                    )
                    conn = _try_connect_with_kwargs(connect_kwargs)
                    if conn:
                        logger.info("Successfully connected to Oracle DB using wallet auth (DSN=%s).", dsn)
                        return conn
                    else:
                        last_exc = Exception("Wallet-based connection failed (see logs).")
                else:
                    logger.warning(
                        "DB_USER/DB_PASSWORD not provided and wallet information incomplete (TNS_ADMIN and WALLET_PASS required)."
                    )
                    return None
        except Exception as e:
            last_exc = e
            logger.error("Failed to connect to Oracle DB (DSN=%s) on attempt %d/%d: %s", dsn, attempt, retries, e)
            if attempt < retries:
                time.sleep(retry_delay)

    logger.exception("All attempts to connect to Oracle DB failed (DSN=%s). Last error: %s", dsn, last_exc)
    return None
