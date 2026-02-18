import os
import oracledb
from dotenv import load_dotenv
import time

load_dotenv()

TNS_ADMIN = os.getenv("TNS_ADMIN")
oracledb.init_oracle_client(config_dir=TNS_ADMIN)

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
WALLET_PASS = os.getenv("WALLET_PASS")
DSN = "discorddb_tp"

def get_connection(retries=3, delay=5):
    """
    Returns a live Oracle DB connection
    Retries on failure.
    """
    for attempt in range(retries):
        try:
            conn = oracledb.connect(
                user=DB_USER,
                password=DB_PASS,
                wallet_location=TNS_ADMIN,
                wallet_password=WALLET_PASS
            )
            return conn
        except oracledb.DatabaseError as e:
            print(f"DB Connection Failed (attempt {attempt+1}): {e}")
            time.sleep(delay)
    raise RuntimeError("Failed to connect to the database after multiple attempts.")

if __name__ == "__main__":
    conn = get_connection()
    print("Connected to the database.")
    conn.close()
