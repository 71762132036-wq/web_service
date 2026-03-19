"""
Upstox API service — fetches option chain data and manages file I/O.
Ported from streamlit_app/modules/api_client.py
"""

from __future__ import annotations
import calendar
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional, Tuple, List, Union

import pandas as pd
import requests
import logging

logger = logging.getLogger(__name__)

from core.config import ACCESS_TOKEN, API_URL, CUTOFF_HOUR, DATA_DIR, INDICES


# ---------------------------------------------------------------------------
# Expiry date helpers
# ---------------------------------------------------------------------------

def get_next_expiry(index_name: str, indices: dict = None) -> str:
    """Return next expiry date (YYYY-MM-DD) fetching from Upstox API.
    
    If the API fails, it falls back to the old calculation logic (IST-aware).
    For stocks, it fetches expiries for a representative liquid stock (RELIANCE)
    if the index_name is not in the primary index set.
    """
    import zoneinfo
    ist = zoneinfo.ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    today = now.date()
    
    if indices is None:
        from core.config import INDICES, STOCKS
        indices = {**INDICES, **STOCKS}

    index_config = indices.get(index_name)
    if not index_config:
        raise ValueError(f"Unknown index/stock: {index_name}")

    # 1. Resolve Instrument Key for expiry lookup
    # Indices use their own, stocks use RELIANCE as proxy for general equity derivatives series
    lookup_key = index_config["instrument_key"]
    if index_name not in ["Nifty", "BankNifty", "Sensex"]:
        lookup_key = "NSE_EQ|RELIANCE" # Standard proxy for stock derivatives expiries

    # 2. Try fetching from API
    api_expiries = get_active_expiries(lookup_key)
    if api_expiries:
        # Find first expiry >= today (after cutoff, strictly > today if today is expiry)
        for exp_str in api_expiries:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            if exp_date > today:
                return exp_str
            if exp_date == today:
                if now.hour < CUTOFF_HOUR:
                    return exp_str
                # else: continue to next one
        
        # If all API expiries passed, return the last one as a last resort
        return api_expiries[-1]

    # 3. Fallback: Calculation (Existing Logic)
    logger.info("[EXPIRY-FALLBACK] Falling back to calculation for %s", index_name)
    expiry_type = index_config["expiry_type"]
    expiry_day = index_config.get("expiry_day", 1)  # Default to 1 for stocks

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

    elif expiry_type == "monthly_last_tuesday":
        year, month = now.year, now.month

        def last_tuesday(y: int, m: int):
            _, last = calendar.monthrange(y, m)
            d = datetime(y, m, last)
            while d.weekday() != 1:  # Tuesday = 1
                d -= timedelta(days=1)
            return d.date()

        expiry_date = last_tuesday(year, month)

        if expiry_date == today and now.hour >= CUTOFF_HOUR:
            month += 1
            if month == 13:
                month, year = 1, year + 1
            expiry_date = last_tuesday(year, month)
        elif expiry_date < today:
            month += 1
            if month == 13:
                month, year = 1, year + 1
            expiry_date = last_tuesday(year, month)
    else:
        expiry_date = today

    return expiry_date.strftime("%Y-%m-%d")


def get_active_expiries(instrument_key: str) -> List[str]:
    """Fetch active expiry dates from Upstox for a given instrument."""
    url = "https://api.upstox.com/v2/option/contract"
    params = {"instrument_key": instrument_key}
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json().get("data", [])
        # Extract unique nested expiry dates and sort them
        expiries = sorted(list(set(item.get("expiry") for item in data if item.get("expiry"))))
        return expiries
    except Exception as exc:
        logger.error("[EXPIRY-API-ERROR] Failed to fetch expiries for %s: %s", instrument_key, exc)
        return []


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------

def fetch_option_chain_data(
    index_name: str = "Nifty", expiry_date: Optional[str] = None, indices: Optional[dict] = None
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Fetch live option chain from Upstox.

    All time-based logic inside this module is now IST-aware to match the
    remote collector and avoid data skew when the backend is running on a
    machine configured with UTC or another timezone.
    """
    if indices is None:
        from core.config import INDICES
        indices = INDICES

    index_config = indices.get(index_name)
    if not index_config:
        return None, f"Unknown index/stock: {index_name}"

    if expiry_date is None:
        expiry_date = get_next_expiry(index_name, indices)

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
        # 1. Try explicit expiry first
        response = requests.get(API_URL, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        option_data = data.get("data", [])

        if not option_data:
            # 2. Fallback A: Auto-discovery (Nearest Expiry)
            # sometimes the calculated expiry is slightly off (e.g. holidays), 
            # so try fetching without an explicit expiry to let Upstox decide.
            logger.info("[EXPIRY FALLBACK] No data for %s, trying auto-discovery (no expiry_date param)...", expiry_date)
            params_auto = {"instrument_key": index_config["instrument_key"]}
            try:
                resp_auto = requests.get(API_URL, params=params_auto, headers=headers, timeout=15)
                resp_auto.raise_for_status()
                auto_data = resp_auto.json().get("data", [])
                if auto_data:
                    option_data = auto_data
                    expiry_date = auto_data[0].get("expiry", expiry_date) # Update with what we found
                    logger.info("[EXPIRY FALLBACK] Success via auto-discovery: %s", expiry_date)
            except Exception: pass

        if not option_data:
            # 3. Fallback B: Holiday Resilience (+/- 1 day)
            from datetime import datetime as _dt
            _orig = _dt.strptime(expiry_date, "%Y-%m-%d").date()
            holiday_candidates = [
                (_orig - timedelta(days=1)).strftime("%Y-%m-%d"),
                (_orig + timedelta(days=1)).strftime("%Y-%m-%d")
            ]
            for hc in holiday_candidates:
                logger.debug("[EXPIRY FALLBACK] Trying holiday candidate: %s", hc)
                params["expiry_date"] = hc
                try:
                    resp_h = requests.get(API_URL, params=params, headers=headers, timeout=15)
                    resp_h.raise_for_status()
                    h_data = resp_h.json().get("data", [])
                    if h_data:
                        option_data = h_data
                        expiry_date = hc
                        logger.info("[EXPIRY FALLBACK] Success via holiday shift: %s", hc)
                        break
                except Exception: continue

        if not option_data:
            # 4. Fallback C: Existing week/month shifts (Deep fallbacks)
            index_config = indices.get(index_name, {})
            expiry_type = index_config.get("expiry_type", "")
            fallback_dates = []
            
            # Generate candidate expiries to try (go backwards first, then forwards)
            if expiry_type == "weekly":
                from datetime import datetime as _dt
                _orig = _dt.strptime(expiry_date, "%Y-%m-%d").date()
                # Try previous week first, then next week
                fallback_dates = [
                    (_orig - timedelta(days=7)).strftime("%Y-%m-%d"),
                    (_orig + timedelta(days=7)).strftime("%Y-%m-%d"),
                ]
            elif expiry_type == "monthly" or expiry_type == "monthly_last_tuesday":
                # For monthly stocks, try previous month and next month
                import calendar as cal
                _orig = datetime.strptime(expiry_date, "%Y-%m-%d").date()
                
                # Previous month
                if _orig.month == 1:
                    prev_m, prev_y = 12, _orig.year - 1
                else:
                    prev_m, prev_y = _orig.month - 1, _orig.year
                
                # Next month
                if _orig.month == 12:
                    next_m, next_y = 1, _orig.year + 1
                else:
                    next_m, next_y = _orig.month + 1, _orig.year
                
                if expiry_type == "monthly_last_tuesday":
                    def last_tuesday(y: int, m: int):
                        _, last = cal.monthrange(y, m)
                        d = datetime(y, m, last)
                        while d.weekday() != 1:
                            d -= timedelta(days=1)
                        return d.date()
                    
                    prev_expiry = last_tuesday(prev_y, prev_m).strftime("%Y-%m-%d")
                    next_expiry = last_tuesday(next_y, next_m).strftime("%Y-%m-%d")
                else:
                    def last_weekday(y: int, m: int, wd: int):
                        _, last = cal.monthrange(y, m)
                        d = datetime(y, m, last)
                        while d.weekday() != wd:
                            d -= timedelta(days=1)
                        return d.date()
                    
                    day = index_config.get("expiry_day", 4)  # Default to Friday(4)
                    prev_expiry = last_weekday(prev_y, prev_m, day).strftime("%Y-%m-%d")
                    next_expiry = last_weekday(next_y, next_m, day).strftime("%Y-%m-%d")
                
                fallback_dates = [prev_expiry, next_expiry]
            
            # Try deep fallback expiries
            for fallback_date in fallback_dates:
                if fallback_date == expiry_date:
                    continue
                logger.debug("[EXPIRY FALLBACK] Trying deep candidate: %s", fallback_date)
                params["expiry_date"] = fallback_date
                try:
                    response2 = requests.get(API_URL, params=params, headers=headers, timeout=15)
                    response2.raise_for_status()
                    option_data = response2.json().get("data", [])
                    if option_data:
                        expiry_date = fallback_date
                        logger.info("[EXPIRY FALLBACK] Success with %s", fallback_date)
                        break
                except Exception:
                    continue
            
            if not option_data:
                return None, f"No option chain data available for {index_name} on {expiry_date} or nearby expiries"

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
    """Keep only ±filter_radius strikes around the spot price.

    Use the median spot across all rows rather than the first row. The API
    sometimes returns slightly different underlying_spot_price values per
    strike, and relying on the first row could pick the wrong centre, leading
    to inconsistent strike subsets between live fetch and scheduled collector.
    """
    # use median to be robust to small per-row variations
    ltp = float(df["Spot"].median())
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

def save_data(df: pd.DataFrame, index_name: str, data_dir: Optional[str] = None, timestamp_str: Optional[str] = None) -> str:
    """Save DataFrame → data/<INDEX>/<EXPIRY>/<TIMESTAMP>.parquet"""
    try:
        if data_dir is None:
            data_dir = DATA_DIR
        
        if "expiry" not in df.columns:
            raise KeyError(f"'expiry' column not found in DataFrame. Available columns: {list(df.columns)}")
        
        if df.empty:
            raise ValueError("DataFrame is empty, cannot save")
        
        expiry_date = df["expiry"].iloc[0]
        folder = Path(data_dir) / index_name / expiry_date
        folder.mkdir(parents=True, exist_ok=True)

        # 1. Resolve Timestamp (Deterministic for batch-locking, or now() for ad-hoc)
        if timestamp_str:
            timestamp = timestamp_str
        else:
            ist = ZoneInfo("Asia/Kolkata")
            timestamp = datetime.now(ist).strftime("%d_%H%M%S")
            
        filepath = folder / f"{timestamp}.parquet"
        df.to_parquet(filepath, engine="pyarrow", index=False)
        
        return str(filepath)
    
    except Exception as exc:
        error_msg = f"save_data FAILED for {index_name}: {type(exc).__name__}: {exc}"
        logger.error("[ERROR-SAVE] %s", error_msg)
        raise Exception(error_msg) from exc


def load_data_file(filepath: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Load a Parquet file into a DataFrame."""
    try:
        df = pd.read_parquet(filepath, engine="pyarrow")
        return df, None
    except Exception as exc:  # noqa: BLE001
        return None, f"Error loading file: {exc}"


def get_available_files(index_name: str, data_dir: Optional[str] = None) -> dict:
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
                csv_files = sorted(expiry_folder.glob("*.parquet"), reverse=True)
                if csv_files:
                    files_dict[expiry_folder.name] = [f.name for f in csv_files]

    # Legacy structure: data/EXPIRY/ (Nifty only, backward compat)
    if index_name == "Nifty" and data_path.exists():
        for expiry_folder in data_path.iterdir():
            if expiry_folder.is_dir() and expiry_folder.name not in files_dict:
                try:
                    datetime.strptime(expiry_folder.name, "%Y-%m-%d")
                    csv_files = sorted(expiry_folder.glob("*.parquet"), reverse=True)
                    if csv_files:
                        files_dict[expiry_folder.name] = [f.name for f in csv_files]
                except ValueError:
                    pass

    return files_dict
