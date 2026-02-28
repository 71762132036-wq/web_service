import os
from pathlib import Path

# Base data directory (inside backend)
DATA_DIR = str(Path(__file__).resolve().parent.parent / "data")
print(f"[BOOTSTRAP] DATA_DIR resolved to: {DATA_DIR}")

# ---------------------------------------------------------------------------
# Supabase — used by local /api/sync to pull data from the Render cron job
# ---------------------------------------------------------------------------
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://wxhhzedijpgzlukbvwia.supabase.co")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")  # Set via env var — never hardcode

# ---------------------------------------------------------------------------
# Upstox API credentials
# ---------------------------------------------------------------------------
CLIENT_ID = "f749999f-e82c-4443-9122-ac07d7a0f5d6"
CLIENT_SECRET = "sbt1wg4ean"
RURL = "https://127.0.0.1:8080/callback"
CODE = "UCeTCO"
ACCESS_TOKEN = (
    "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0TUNIUVAiLCJqdGkiOiI2OWExMDc5N2NhNmZlZDJkM2M0N2JlZjMiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzcyMTYwOTE5LCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NzIyMjk2MDB9.N7ldtaHPV3WcpEZY8lpLDJBx1ff5mb06KI3DiZ3FdI0"
)

# ---------------------------------------------------------------------------
# Upstox REST endpoint
# ---------------------------------------------------------------------------
API_URL = "https://api.upstox.com/v2/option/chain"

# ---------------------------------------------------------------------------
# Index definitions
# ---------------------------------------------------------------------------
INDICES: dict[str, dict] = {
    "Nifty": {
        "instrument_key": "NSE_INDEX|Nifty 50",
        "lot_size": 75,
        "expiry_type": "weekly",   # Tuesday
        "expiry_day": 1,
    },
    "BankNifty": {
        "instrument_key": "NSE_INDEX|Nifty Bank",
        "lot_size": 25,
        "expiry_type": "monthly",  # Last Tuesday of each month
        "expiry_day": 1,
    },
    "Sensex": {
        "instrument_key": "BSE_INDEX|SENSEX",
        "lot_size": 10,
        "expiry_type": "weekly",   # Thursday
        "expiry_day": 3,
    },
}

DEFAULT_INDEX = "Nifty"

# ---------------------------------------------------------------------------
# Display / calculation constants
# ---------------------------------------------------------------------------
GAMMA_CAGE_WIDTH = 4        # number of strikes around ATM
FILTER_STRIKES_RADIUS = 20 # ±N strikes around closest strike
CUTOFF_HOUR = 9             # 9 AM — roll to next expiry on expiry day at/after market open

# ---------------------------------------------------------------------------
# Auto-Fetch Configuration
# ---------------------------------------------------------------------------
AUTO_FETCH          = True  # Toggle background fetching
FETCH_INTERVAL_MINS = 15    # Interval in minutes

# ---------------------------------------------------------------------------
# Render Remote Collector
# ---------------------------------------------------------------------------
# Set to your deployed Render service URL, e.g. https://gc-gamma-collector.onrender.com
RENDER_API_URL: str = os.getenv("RENDER_API_URL", "")

