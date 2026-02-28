"""
Upstox API service — fetches option chain data and manages file I/O.
Ported from streamlit_app/modules/api_client.py
"""

from __future__ import annotations
import calendar
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, List

import pandas as pd
import requests

from core.config import ACCESS_TOKEN, API_URL, CUTOFF_HOUR, DATA_DIR, INDICES


# ---------------------------------------------------------------------------
# Expiry date helpers
# ---------------------------------------------------------------------------

def get_next_expiry(index_name: str) -> str:
    """Return next expiry date (YYYY-MM-DD) based on index rules."""
    index_config = INDICES.get(index_name)
    if not index_config:
        raise ValueError(f"Unknown index: {index_name}")

    now = datetime.now()
    today = now.date()
    expiry_type = index_config["expiry_type"]
    expiry_day = index_config["expiry_day"]

    if expiry_type == "weekly":
        days_until = (expiry_day - now.weekday()) % 7
        expiry_date = (now + timedelta(days=days_until)).date()

        if expiry_date == today and now.hour >= CUTOFF_HOUR:
            expiry_date += timedelta(days=7)
        elif expiry_date < today:
            expiry_date += timedelta(days=7)

    elif expiry_type == "monthly":
        year, month = now.year, now.month

        def last_weekday(y: int, m: int, weekday: int):
            _, last = calendar.monthrange(y, m)
            d = datetime(y, m, last)
            while d.weekday() != weekday:
                d -= timedelta(days=1)
            return d.date()

        expiry_date = last_weekday(year, month, expiry_day)

        if expiry_date == today and now.hour >= CUTOFF_HOUR:
            month += 1
            if month == 13:
                month, year = 1, year + 1
            expiry_date = last_weekday(year, month, expiry_day)
        elif expiry_date < today:
            month += 1
            if month == 13:
                month, year = 1, year + 1
            expiry_date = last_weekday(year, month, expiry_day)
    else:
        expiry_date = today

    return expiry_date.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------

def fetch_option_chain_data(
    index_name: str = "Nifty", expiry_date: str | None = None
) -> tuple[pd.DataFrame | None, str | None]:
    """
    Fetch option chain from Upstox API.

    Returns:
        (DataFrame, None) on success, (None, error_message) on failure.
    """
    index_config = INDICES.get(index_name)
    if not index_config:
        return None, f"Unknown index: {index_name}"

    if expiry_date is None:
        expiry_date = get_next_expiry(index_name)

    params = {
        "instrument_key": index_config["instrument_key"],
        "expiry_date": expiry_date,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }

    try:
        response = requests.get(API_URL, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        option_data = data.get("data", [])
        if not option_data:
            # Fallback: on expiry day the API may no longer serve today's expiry.
            # Automatically retry with +7 days for weekly, next month for monthly.
            index_config = INDICES.get(index_name, {})
            if index_config.get("expiry_type") == "weekly":
                from datetime import datetime as _dt
                _orig = _dt.strptime(expiry_date, "%Y-%m-%d").date()
                _next = _orig + timedelta(days=7)
                fallback_date = _next.strftime("%Y-%m-%d")
                print(f"[EXPIRY FALLBACK] No data for {expiry_date}, retrying with {fallback_date}")
                params["expiry_date"] = fallback_date
                response2 = requests.get(API_URL, params=params, headers=headers, timeout=15)
                response2.raise_for_status()
                option_data = response2.json().get("data", [])
                if not option_data:
                    return None, f"No data for {expiry_date} or {fallback_date}"
                # Patch expiry_date for correct folder naming
                expiry_date = fallback_date
            else:
                return None, "No data received from API"

        records = []
        for item in option_data:
            record = {
                "Strike": item.get("strike_price"),
                "Gamma": item["call_options"]["option_greeks"].get("gamma"),
                "Call_OI": item["call_options"]["market_data"].get("oi"),
                "Put_OI": item["put_options"]["market_data"].get("oi"),
                "Spot": item.get("underlying_spot_price"),
                "expiry": item.get("expiry"),
                "PCR": item.get("pcr"),
                "call_ltp": item["call_options"]["market_data"].get("ltp"),
                "call_oi": item["call_options"]["market_data"].get("oi"),
                "call_iv": item["call_options"]["option_greeks"].get("iv"),
                "call_delta": item["call_options"]["option_greeks"].get("delta"),
                "call_gamma": item["call_options"]["option_greeks"].get("gamma"),
                "call_theta": item["call_options"]["option_greeks"].get("theta"),
                "call_vega": item["call_options"]["option_greeks"].get("vega"),
                "call_vanna": item["call_options"]["option_greeks"].get("vanna"),
                "call_charm": item["call_options"]["option_greeks"].get("charm"),
                "call_pop": item["call_options"]["option_greeks"].get("pop"),
                "call_vol": item["call_options"]["market_data"].get("volume"),
                "call_close": item["call_options"]["market_data"].get("close"),
                "call_bid_price": item["call_options"]["market_data"].get("bid_price"),
                "call_bid_qty": item["call_options"]["market_data"].get("bid_qty"),
                "call_ask_price": item["call_options"]["market_data"].get("ask_price"),
                "call_ask_qty": item["call_options"]["market_data"].get("ask_qty"),
                "call_prev_oi": item["call_options"]["market_data"].get("prev_oi"),
                "call_oi_chg": (item["call_options"]["market_data"].get("oi") or 0) - (item["call_options"]["market_data"].get("prev_oi") or 0),

                "put_ltp": item["put_options"]["market_data"].get("ltp"),
                "put_oi": item["put_options"]["market_data"].get("oi"),
                "put_iv": item["put_options"]["option_greeks"].get("iv"),
                "put_delta": item["put_options"]["option_greeks"].get("delta"),
                "put_gamma": item["put_options"]["option_greeks"].get("gamma"),
                "put_theta": item["put_options"]["option_greeks"].get("theta"),
                "put_vega": item["put_options"]["option_greeks"].get("vega"),
                "put_vanna": item["put_options"]["option_greeks"].get("vanna"),
                "put_charm": item["put_options"]["option_greeks"].get("charm"),
                "put_pop": item["put_options"]["option_greeks"].get("pop"),
                "put_vol": item["put_options"]["market_data"].get("volume"),
                "put_close": item["put_options"]["market_data"].get("close"),
                "put_bid_price": item["put_options"]["market_data"].get("bid_price"),
                "put_bid_qty": item["put_options"]["market_data"].get("bid_qty"),
                "put_ask_price": item["put_options"]["market_data"].get("ask_price"),
                "put_ask_qty": item["put_options"]["market_data"].get("ask_qty"),
                "put_prev_oi": item["put_options"]["market_data"].get("prev_oi"),
                "put_oi_chg": (item["put_options"]["market_data"].get("oi") or 0) - (item["put_options"]["market_data"].get("prev_oi") or 0),
            }
            records.append(record)

        df = pd.DataFrame(records).sort_values("Strike").reset_index(drop=True)
        return df, None

    except requests.exceptions.RequestException as exc:
        return None, f"API Error: {exc}"
    except Exception as exc:  # noqa: BLE001
        return None, f"Data Processing Error: {exc}"


# ---------------------------------------------------------------------------
# Strike filtering
# ---------------------------------------------------------------------------

def filter_near_strikes(df: pd.DataFrame, filter_radius: int = 20) -> pd.DataFrame:
    """Keep only ±filter_radius strikes around the spot price."""
    ltp = df["Spot"].iloc[0]
    all_strikes = sorted(df["Strike"].unique())
    closest = min(all_strikes, key=lambda x: abs(x - ltp))
    idx = all_strikes.index(closest)

    low = max(idx - filter_radius, 0)
    high = min(idx + filter_radius, len(all_strikes))
    selected = all_strikes[low:high]

    return df[df["Strike"].isin(selected)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_data(df: pd.DataFrame, index_name: str, data_dir: str | None = None) -> str:
    """Save DataFrame → data/<INDEX>/<EXPIRY>/<TIMESTAMP>.csv"""
    if data_dir is None:
        data_dir = DATA_DIR
    expiry_date = df["expiry"].iloc[0]
    folder = Path(data_dir) / index_name / expiry_date
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%d_%H%M%S")
    filepath = folder / f"{timestamp}.csv"
    
    print(f"[DEBUG] Saving data. data_dir={data_dir}, target_file={filepath}")
    
    df.to_csv(filepath, index=False)
    return str(filepath)


def load_data_file(filepath: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load a CSV file into a DataFrame."""
    try:
        df = pd.read_csv(filepath)
        return df, None
    except Exception as exc:  # noqa: BLE001
        return None, f"Error loading file: {exc}"


def get_available_files(index_name: str, data_dir: str | None = None) -> dict:
    """
    Return dict of { expiry_date: [filename, ...] } for the given index.
    Supports both new structure (data/INDEX/EXPIRY/) and old (data/EXPIRY/).
    """
    if data_dir is None:
        data_dir = DATA_DIR
    files_dict = {}
    data_path = Path(data_dir)

    # New structure: data/INDEX/EXPIRY/
    index_path = data_path / index_name
    if index_path.exists():
        for expiry_folder in index_path.iterdir():
            if expiry_folder.is_dir():
                csv_files = sorted(expiry_folder.glob("*.csv"), reverse=True)
                if csv_files:
                    files_dict[expiry_folder.name] = [f.name for f in csv_files]

    # Legacy structure: data/EXPIRY/ (Nifty only, backward compat)
    if index_name == "Nifty" and data_path.exists():
        for expiry_folder in data_path.iterdir():
            if expiry_folder.is_dir() and expiry_folder.name not in files_dict:
                try:
                    datetime.strptime(expiry_folder.name, "%Y-%m-%d")
                    csv_files = sorted(expiry_folder.glob("*.csv"), reverse=True)
                    if csv_files:
                        files_dict[expiry_folder.name] = [f.name for f in csv_files]
                except ValueError:
                    pass

    return files_dict
