"""
Database bootstrap / connection helper.

This file attempts to initialize the Oracle "thick" client if available,
but will now gracefully fall back to the python-oracledb "thin" mode if
thick client initialization fails (DPI-1047).  The get_connection()
helper attempts to open a database connection if DB_DSN (or DB_USER/DB_PASSWORD)
are provided in the environment; otherwise it returns None.

"""

from __future__ import annotations

import logging
import os
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
            # Attempting init_oracle_client without args may raise DPI-1047 if no client is present;
            # we avoid calling it when TNS_ADMIN is not set to reduce spurious errors.
            # This means we'll continue in thin mode (default) unless the environment explicitly
            # requests thick initialization.
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


def get_connection() -> Optional["oracledb.Connection"]:
    """
    Return a DB connection or None.

    Environment variables expected (common patterns):
      - DB_DSN : DSN string (e.g. 'host:port/service_name' or TNS name)
      - DB_USER
      - DB_PASSWORD

    If DB_DSN is not set, this returns None (no DB configured).
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

    try:
        # python-oracledb uses thin mode by default. If thick client init succeeded above,
        # this will use thick behavior where appropriate.
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        logger.info("Successfully connected to Oracle DB (DSN=%s).", dsn)
        return conn
    except Exception as e:
        logger.exception("Failed to connect to Oracle DB (DSN=%s): %s", dsn, e)
        return None
