"""
Database bootstrap / connection helper.

This file attempts to initialize the Oracle "thick" client if available,
but will gracefully fall back to the python-oracledb "thin" mode if
thick client initialization fails (DPI-1047).

get_connection now accepts retry parameters to match callers such as
db_layer.get_db_connection(retries=...).
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

logger = logging.getLogger(__name__)

# Optional TNS_ADMIN (wallet) directory — preserve existing env var behavior
TNS_ADMIN = os.getenv("TNS_ADMIN")

# Try to initialize the Oracle thick client if python-oracledb is available.
# If initialization fails (e.g. DPI-1047), we log a warning and continue.
if oracledb is not None:
    try:
        # Only attempt thick initialization if a TNS_ADMIN or explicit need is present.
        # If your code relies on the thick client for features like external auth or
        # certain wallet modes, keep TNS_ADMIN configured and install Instant Client.
        if TNS_ADMIN:
            oracledb.init_oracle_client(config_dir=TNS_ADMIN)
            logger.info("Initialized Oracle thick client using TNS_ADMIN=%s", TNS_ADMIN)
        else:
            # Avoid calling init_oracle_client without clear need (reduces DPI-1047 noise).
            logger.debug("TNS_ADMIN not set; skipping explicit oracledb.init_oracle_client() - using thin mode by default.")
    except Exception as e:
        # DPI-1047 or other init errors are caught here — continue in thin mode.
        logger.warning(
            "Could not initialize Oracle thick client (DPI-1047 or similar). "
            "Falling back to python-oracledb thin mode. If you require the thick client, "
            "install Oracle Instant Client and set TNS_ADMIN appropriately. Error: %s",
            e,
        )
else:
    logger.warning("python-oracledb is not installed; database helper functions will be limited.")


def get_connection(retries: int = 1, retry_delay: float = 2.0) -> Optional["oracledb.Connection"]:
    """
    Return a DB connection or None.

    Parameters:
      - retries: number of attempts (>=1). If >1, the function will retry on failure.
      - retry_delay: seconds to wait between attempts.

    Environment variables expected (common patterns):
      - DB_DSN : DSN string (e.g. 'host:port/service_name' or TNS alias)
      - DB_USER
      - DB_PASSWORD

    Returns:
      - oracledb.Connection on success
      - None if oracledb not installed, DB_DSN not set, credentials missing, or connection failed
    """
    if oracledb is None:
        logger.debug("oracledb module not available; get_connection returning None")
        return None

    dsn = os.getenv("DB_DSN")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not dsn:
        logger.info("DB_DSN not set; skipping database connection.")
        return None

    # If credentials are not provided, avoid calling oracledb.connect without them,
    # which results in DPY-4001: no credentials specified. If you use external auth
    # (OS authentication / wallet), set DB_USER/DB_PASSWORD appropriately or adapt this code.
    if not user or not password:
        logger.warning(
            "DB_USER or DB_PASSWORD not set (DB_DSN=%s). "
            "Not attempting DB connection. Set DB_USER/DB_PASSWORD in environment if a DB is required.",
            dsn,
        )
        return None

    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt < max(1, int(retries)):
        attempt += 1
        try:
            conn = oracledb.connect(user=user, password=password, dsn=dsn)
            logger.info("Successfully connected to Oracle DB (DSN=%s).", dsn)
            return conn
        except Exception as e:
            last_exc = e
            logger.error("Failed to connect to Oracle DB (DSN=%s) on attempt %d/%d: %s", dsn, attempt, retries, e)
            if attempt < retries:
                time.sleep(retry_delay)
    logger.exception("All attempts to connect to Oracle DB failed (DSN=%s). Last error: %s", dsn, last_exc)
    return None
