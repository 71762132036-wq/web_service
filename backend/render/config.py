"""
config.py — Environment-based configuration for the Render collector service.
All secrets are injected as environment variables on the Render dashboard.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]

# ---------------------------------------------------------------------------
# Upstox API
# ---------------------------------------------------------------------------
API_URL = "https://api.upstox.com/v2/option/chain"

# Token is persisted in Supabase and updated via POST /set-token.
# On first deploy you may also set it here as a fallback env var.
UPSTOX_ACCESS_TOKEN: str = os.getenv("UPSTOX_ACCESS_TOKEN", "")

# ---------------------------------------------------------------------------
# Collection schedule
# ---------------------------------------------------------------------------
COLLECT_INTERVAL_MINS: int = int(os.getenv("COLLECT_INTERVAL_MINS", "15"))
FILTER_STRIKES_RADIUS: int = int(os.getenv("FILTER_STRIKES_RADIUS", "20"))

# Market hours (IST) — Mon–Fri only
MARKET_OPEN_H,  MARKET_OPEN_M  = 9,  30
MARKET_CLOSE_H, MARKET_CLOSE_M = 15, 30

# ---------------------------------------------------------------------------
# Index definitions (mirrors backend/core/config.py)
# ---------------------------------------------------------------------------
INDICES: dict = {
    "Nifty": {
        "instrument_key": "NSE_INDEX|Nifty 50",
        "lot_size": 75,
        "expiry_type": "weekly",
        "expiry_day": 1,   # Tuesday
    },
    "BankNifty": {
        "instrument_key": "NSE_INDEX|Nifty Bank",
        "lot_size": 25,
        "expiry_type": "monthly",
        "expiry_day": 1,   # Last Tuesday of month
    },
    "Sensex": {
        "instrument_key": "BSE_INDEX|SENSEX",
        "lot_size": 10,
        "expiry_type": "weekly",
        "expiry_day": 3,   # Thursday
    },
}

CUTOFF_HOUR: int = 9   # Roll to next expiry at/after 9 AM on expiry day
