import os
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd

# Load .env from web_app folder (parent of backend)
env_file = Path("D:/Investments/Participant_Wise_OI/Analytical_App/gamma_stocks/GC_gamma/nifty/web_app/") / ".env"
load_dotenv(dotenv_path=env_file, encoding="utf-8-sig")

if os.getenv("ACCESS_TOKEN") is None and os.getenv("\ufeffACCESS_TOKEN"):
    os.environ["ACCESS_TOKEN"] = os.environ.pop("\ufeffACCESS_TOKEN")
# Base data directory (inside backend)
DATA_DIR = str(Path(__file__).resolve().parent.parent / "data")

# ---------------------------------------------------------------------------
# Supabase — used by local /api/sync to pull data from the Render cron job
# ---------------------------------------------------------------------------
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://wxhhzedijpgzlukbvwia.supabase.co")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind4aGh6ZWRpanBnemx1a2J2d2lhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyNzQyNzQsImV4cCI6MjA4Nzg1MDI3NH0.ynXWwZ3Tm6zz24qt8FShr0xsYP7gcw9TMqU868P8Qnw")  # Set via env var — never hardcode

# ---------------------------------------------------------------------------
# Upstox API credentials
# ---------------------------------------------------------------------------
CLIENT_ID = "f749999f-e82c-4443-9122-ac07d7a0f5d6"
CLIENT_SECRET = "sbt1wg4ean"
RURL = "https://127.0.0.1:8080/callback"
CODE = "UCeTCO"
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")

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
        "lot_size": 25,
        "expiry_type": "weekly",   # Tuesday
        "expiry_day": 1,
    },
    "BankNifty": {
        "instrument_key": "NSE_INDEX|Nifty Bank",
        "lot_size": 15,
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

# ---------------------------------------------------------------------------
# Stock definitions — loaded from stocks.csv
# ---------------------------------------------------------------------------
STOCKS: dict[str, dict] = {}
STOCKS_CSV_PATH = Path(__file__).resolve().parent.parent.parent / "stocks.csv"

if STOCKS_CSV_PATH.exists():
    import csv
    try:
        with open(STOCKS_CSV_PATH, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("Name")
                key = row.get("Key")
                if name and key:
                    # Sanitize name for use as a key (remove spaces/special chars if needed, but original name is fine for UI)
                    STOCKS[name] = {
                        "instrument_key": key,
                        "lot_size": 1, # Default lot size for now
                        "expiry_type": "monthly",
                        "expiry_day": 3, # Thursday for stocks
                    }
    except Exception:
        pass # Silently fail if stocks.csv missing, or use logging

DEFAULT_INDEX = "Nifty"

# ---------------------------------------------------------------------------
# Display / calculation constants
# ---------------------------------------------------------------------------
GAMMA_CAGE_WIDTH = 4        # number of strikes around ATM
FILTER_STRIKES_RADIUS = 20 # ±N strikes around closest strike
CUTOFF_HOUR = 16             # 4 PM — roll to next expiry on expiry day AFTER market close

# ---------------------------------------------------------------------------
# Auto-Fetch Configuration
# ---------------------------------------------------------------------------
AUTO_FETCH          = False   # Toggle background fetching
FETCH_INTERVAL_MINS = 1      # Interval in minutes

# Stock collection settings
FETCH_STOCKS     = True      # Whether to include stocks in the periodic fetcher
FETCH_ALL_STOCKS = True      # If True, fetch all 180+ stocks from stocks.csv
STOCKS_TO_FETCH  = ["RELIANCE", "TCS", "HDFCBANK", "INFY"] # Ignored if FETCH_ALL_STOCKS is True

# Market hours override
BYPASS_MARKET_HOURS = True   # If True, skip the market hours check in fetcher



