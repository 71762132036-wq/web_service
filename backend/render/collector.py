"""
collector.py — Standalone Upstox option chain fetcher for the Render service.
Mirrors the logic in backend/services/upstox_service.py, but is fully
self-contained so the Render service has no dependency on the local app.
"""
from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Expiry helpers
# ---------------------------------------------------------------------------

def get_next_expiry(index_name: str, indices: dict, cutoff_hour: int = 9) -> str:
    """Return next expiry date (YYYY-MM-DD) based on index rules."""
    index_config = indices.get(index_name)
    if not index_config:
        raise ValueError(f"Unknown index: {index_name}")

    now = datetime.now()
    today = now.date()
    expiry_type = index_config["expiry_type"]
    expiry_day  = index_config["expiry_day"]

    if expiry_type == "weekly":
        days_until = (expiry_day - now.weekday()) % 7
        expiry_date = (now + timedelta(days=days_until)).date()

        if expiry_date == today and now.hour >= cutoff_hour:
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

        if expiry_date <= today and now.hour >= cutoff_hour:
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

def fetch_option_chain(
    index_name: str,
    access_token: str,
    api_url: str,
    indices: dict,
    cutoff_hour: int = 9,
    expiry_date: Optional[str] = None,
) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Fetch option chain from Upstox API.
    Returns (DataFrame, None) on success, (None, error_message) on failure.
    """
    index_config = indices.get(index_name)
    if not index_config:
        return None, f"Unknown index: {index_name}"

    if expiry_date is None:
        expiry_date = get_next_expiry(index_name, indices, cutoff_hour)

    params = {
        "instrument_key": index_config["instrument_key"],
        "expiry_date":    expiry_date,
    }
    headers = {
        "Content-Type":  "application/json",
        "Accept":        "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        raw = resp.json()

        option_data = raw.get("data", [])

        # Expiry-day fallback: retry with +7 days for weekly index
        if not option_data and index_config.get("expiry_type") == "weekly":
            fallback = (
                datetime.strptime(expiry_date, "%Y-%m-%d") + timedelta(days=7)
            ).strftime("%Y-%m-%d")
            logger.info("[EXPIRY FALLBACK] No data for %s, retrying %s", expiry_date, fallback)
            params["expiry_date"] = fallback
            resp2 = requests.get(api_url, params=params, headers=headers, timeout=15)
            resp2.raise_for_status()
            option_data = resp2.json().get("data", [])
            if not option_data:
                return None, f"No data for {expiry_date} or {fallback}"
            expiry_date = fallback

        if not option_data:
            return None, "No data received from API"

        records = []
        for item in option_data:
            co = item["call_options"]
            po = item["put_options"]
            records.append({
                "Strike":       item.get("strike_price"),
                "Gamma":        co["option_greeks"].get("gamma"),
                "Call_OI":      co["market_data"].get("oi"),
                "Put_OI":       po["market_data"].get("oi"),
                "Spot":         item.get("underlying_spot_price"),
                "expiry":       item.get("expiry"),
                "PCR":          item.get("pcr"),
                "call_ltp":     co["market_data"].get("ltp"),
                "call_oi":      co["market_data"].get("oi"),
                "call_iv":      co["option_greeks"].get("iv"),
                "call_delta":   co["option_greeks"].get("delta"),
                "call_gamma":   co["option_greeks"].get("gamma"),
                "call_theta":   co["option_greeks"].get("theta"),
                "call_vega":    co["option_greeks"].get("vega"),
                "call_vanna":   co["option_greeks"].get("vanna"),
                "call_charm":   co["option_greeks"].get("charm"),
                "call_pop":     co["option_greeks"].get("pop"),
                "call_vol":     co["market_data"].get("volume"),
                "call_close":   co["market_data"].get("close"),
                "call_prev_oi": co["market_data"].get("prev_oi"),
                "call_oi_chg":  (co["market_data"].get("oi") or 0) - (co["market_data"].get("prev_oi") or 0),
                "put_ltp":      po["market_data"].get("ltp"),
                "put_oi":       po["market_data"].get("oi"),
                "put_iv":       po["option_greeks"].get("iv"),
                "put_delta":    po["option_greeks"].get("delta"),
                "put_gamma":    po["option_greeks"].get("gamma"),
                "put_theta":    po["option_greeks"].get("theta"),
                "put_vega":     po["option_greeks"].get("vega"),
                "put_vanna":    po["option_greeks"].get("vanna"),
                "put_charm":    po["option_greeks"].get("charm"),
                "put_pop":      po["option_greeks"].get("pop"),
                "put_vol":      po["market_data"].get("volume"),
                "put_close":    po["market_data"].get("close"),
                "put_prev_oi":  po["market_data"].get("prev_oi"),
                "put_oi_chg":   (po["market_data"].get("oi") or 0) - (po["market_data"].get("prev_oi") or 0),
            })

        df = pd.DataFrame(records).sort_values("Strike").reset_index(drop=True)
        return df, None

    except requests.exceptions.RequestException as exc:
        return None, f"API Error: {exc}"
    except Exception as exc:
        return None, f"Processing Error: {exc}"


# ---------------------------------------------------------------------------
# Strike filter
# ---------------------------------------------------------------------------

def filter_near_strikes(df: pd.DataFrame, radius: int = 20) -> pd.DataFrame:
    """Keep only ±radius strikes around the ATM strike."""
    ltp = df["Spot"].iloc[0]
    strikes = sorted(df["Strike"].unique())
    closest = min(strikes, key=lambda x: abs(x - ltp))
    idx = strikes.index(closest)
    low  = max(idx - radius, 0)
    high = min(idx + radius + 1, len(strikes))
    selected = strikes[low:high]
    return df[df["Strike"].isin(selected)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Market hours check
# ---------------------------------------------------------------------------

def is_market_hours(
    open_h: int = 9, open_m: int = 30,
    close_h: int = 15, close_m: int = 30,
) -> bool:
    """Returns True only Mon–Fri, 09:30–15:30 IST."""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    market_open  = now.replace(hour=open_h,  minute=open_m,  second=0, microsecond=0)
    market_close = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    return market_open <= now <= market_close


# ---------------------------------------------------------------------------
# Full collection run (called by scheduler)
# ---------------------------------------------------------------------------

def collect_all(token: str, api_url: str, indices: dict, radius: int, cutoff: int) -> list[dict]:
    """
    Fetch all indices, filter strikes, return list of snapshot dicts ready for DB insert.
    Returns: [{"index_name": ..., "expiry_date": ..., "data": [...rows...]}, ...]
    """
    results = []
    for index_name in indices:
        df, err = fetch_option_chain(index_name, token, api_url, indices, cutoff)
        if err:
            logger.warning("[COLLECT] %s failed: %s", index_name, err)
            continue

        df_filtered = filter_near_strikes(df, radius)
        expiry_date = df_filtered["expiry"].iloc[0] if "expiry" in df_filtered.columns else "unknown"

        results.append({
            "index_name":  index_name,
            "expiry_date": expiry_date,
            "data":        df_filtered.to_dict(orient="records"),
        })
        logger.info("[COLLECT] %s → %d rows (expiry %s)", index_name, len(df_filtered), expiry_date)

    return results
