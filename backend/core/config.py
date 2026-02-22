"""Core configuration — indices, API credentials, and app-wide constants."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Upstox API credentials
# ---------------------------------------------------------------------------
CLIENT_ID = "f749999f-e82c-4443-9122-ac07d7a0f5d6"
CLIENT_SECRET = "sbt1wg4ean"
RURL = "https://127.0.0.1:8080/callback"
CODE = "UCeTCO"
ACCESS_TOKEN = (
    "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0TUNIUVAiLCJqdGkiOiI2OTliMDVjYWU5NDI5NTAwMGE0MzJkZmEiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzcxNzY3MjQyLCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NzE3OTc2MDB9.lyA85iSewdiOG92MNASfQ1Cw7XGA7lr4k89rp3FGIWc"
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
CUTOFF_HOUR = 17            # 5 PM — roll to next expiry after this hour
