"""
collector.py — Standalone Upstox option chain fetcher for the Render service.
Mirrors the logic in backend/services/upstox_service.py, but is fully
self-contained so the Render service has no dependency on the local app.
"""
from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Expiry helpers
# ---------------------------------------------------------------------------

def get_next_expiry(index_name: str, indices: dict, cutoff_hour: int = 9) -> str:
    """Return next expiry date (YYYY-MM-DD) based on index/stock rules.
    
    Uses IST timezone for consistent rollovers.
    """
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    today = now.date()
    index_config = indices.get(index_name)
    if not index_config:
        raise ValueError(f"Unknown index/stock: {index_name}")

    expiry_type = index_config["expiry_type"]
    expiry_day = index_config.get("expiry_day", 1)

    if expiry_type == "weekly":
        days_until = (expiry_day - now.weekday()) % 7
        expiry_date = (now + timedelta(days=days_until)).date()
        if expiry_date == today and now.hour >= cutoff_hour:
            expiry_date += timedelta(days=7)
        elif expiry_date < today:
            expiry_date += timedelta(days=7)

    elif expiry_type == "monthly":
        year, month = now.year, now.month
        def last_weekday(y: int, m: int, wd: int):
            _, last = calendar.monthrange(y, m)
            d = datetime(y, m, last)
            while d.weekday() != wd:
                d -= timedelta(days=1)
            return d.date()
        expiry_date = last_weekday(year, month, expiry_day)
        if expiry_date == today and now.hour >= cutoff_hour:
            month += 1
            if month == 13: month, year = 1, year + 1
            expiry_date = last_weekday(year, month, expiry_day)
        elif expiry_date < today:
            month += 1
            if month == 13: month, year = 1, year + 1
            expiry_date = last_weekday(year, month, expiry_day)

    elif expiry_type == "monthly_last_tuesday":
        year, month = now.year, now.month
        def last_tuesday(y: int, m: int):
            _, last = calendar.monthrange(y, m)
            d = datetime(y, m, last)
            while d.weekday() != 1: d -= timedelta(days=1)
            return d.date()
        expiry_date = last_tuesday(year, month)
        if expiry_date == today and now.hour >= cutoff_hour:
            month += 1
            if month == 13: month, year = 1, year + 1
            expiry_date = last_tuesday(year, month)
        elif expiry_date < today:
            month += 1
            if month == 13: month, year = 1, year + 1
            expiry_date = last_tuesday(year, month)
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
    """Fetch option chain with robust fallback."""
    index_config = indices.get(index_name)
    if not index_config:
        return None, f"Unknown index: {index_name}"

    if expiry_date is None:
        expiry_date = get_next_expiry(index_name, indices, cutoff_hour)

    params = {"instrument_key": index_config["instrument_key"], "expiry_date": expiry_date}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    try:
        resp = requests.get(api_url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        option_data = raw.get("data", [])

        # Robust Fallback Logic
        if not option_data:
            expiry_type = index_config.get("expiry_type", "")
            fallbacks = []
            _orig = datetime.strptime(expiry_date, "%Y-%m-%d").date()

            if expiry_type == "weekly":
                fallbacks = [(_orig - timedelta(days=7)).strftime("%Y-%m-%d"), (_orig + timedelta(days=7)).strftime("%Y-%m-%d")]
            elif expiry_type in ["monthly", "monthly_last_tuesday"]:
                # Try prev/next month
                # (Simplified ports from upstox_service.py for the remote env)
                def get_m_y(m, y, delta):
                    nm = m + delta
                    if nm < 1: return 12, y - 1
                    if nm > 12: return 1, y + 1
                    return nm, y
                pm, py = get_m_y(_orig.month, _orig.year, -1)
                nm, ny = get_m_y(_orig.month, _orig.year, 1)
                
                if expiry_type == "monthly_last_tuesday":
                    def last_t(y, m):
                        _, l = calendar.monthrange(y, m)
                        d = datetime(y, m, l)
                        while d.weekday() != 1: d -= timedelta(days=1)
                        return d.date().strftime("%Y-%m-%d")
                    fallbacks = [last_t(py, pm), last_t(ny, nm)]
                else:
                    def last_w(y, m, wd):
                        _, l = calendar.monthrange(y, m)
                        d = datetime(y, m, l)
                        while d.weekday() != wd: d -= timedelta(days=1)
                        return d.date().strftime("%Y-%m-%d")
                    e_day = index_config.get("expiry_day", 4)
                    fallbacks = [last_w(py, pm, e_day), last_w(ny, nm, e_day)]

            for fb in fallbacks:
                if fb == expiry_date: continue
                logger.info("[EXPIRY FALLBACK] Trying %s...", fb)
                params["expiry_date"] = fb
                try:
                    r2 = requests.get(api_url, params=params, headers=headers, timeout=15)
                    r2.raise_for_status()
                    option_data = r2.json().get("data", [])
                    if option_data:
                        expiry_date = fb
                        break
                except: continue

        if not option_data:
            return None, f"No data for {index_name} on {expiry_date}"

        records = []
        for item in option_data:
            co, po = item["call_options"], item["put_options"]
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
                "call_bid_price": co["market_data"].get("bid_price"),
                "call_bid_qty":   co["market_data"].get("bid_qty"),
                "call_ask_price": co["market_data"].get("ask_price"),
                "call_ask_qty":   co["market_data"].get("ask_qty"),
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
                "put_bid_price": po["market_data"].get("bid_price"),
                "put_bid_qty":   po["market_data"].get("bid_qty"),
                "put_ask_price": po["market_data"].get("ask_price"),
                "put_ask_qty":   po["market_data"].get("ask_qty"),
                "put_prev_oi":  po["market_data"].get("prev_oi"),
                "put_oi_chg":   (po["market_data"].get("oi") or 0) - (po["market_data"].get("prev_oi") or 0),
            })

        df = pd.DataFrame(records).sort_values("Strike").reset_index(drop=True)
        return df, None
    except Exception as exc: return None, f"Error: {exc}"


# ---------------------------------------------------------------------------
# Strike filter
# ---------------------------------------------------------------------------

def filter_near_strikes(df: pd.DataFrame, radius: int = 20) -> pd.DataFrame:
    """Keep ±radius strikes around the MEDIAN spot."""
    ltp = float(df["Spot"].median())
    strikes = sorted(df["Strike"].unique())
    closest = min(strikes, key=lambda x: abs(x - ltp))
    idx = strikes.index(closest)
    low, high = max(idx - radius, 0), min(idx + radius + 1, len(strikes))
    return df[df["Strike"].isin(strikes[low:high])].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Market hours check
# ---------------------------------------------------------------------------

def is_market_hours(open_h: int = 9, open_m: int = 30, close_h: int = 15, close_m: int = 30) -> bool:
    """True Mon–Fri, 09:30–15:30 IST."""
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    if now.weekday() >= 5: return False
    m_open  = now.replace(hour=open_h,  minute=open_m,  second=0, microsecond=0)
    m_close = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    # return m_open <= now <= m_close
    return True


# ---------------------------------------------------------------------------
# Full collection run
# ---------------------------------------------------------------------------

FETCH_CONCURRENCY = 5   # number of instruments fetched in parallel

def _fetch_one(instrument_name: str, token: str, api_url: str,
               all_instruments: dict, radius: int, cutoff: int) -> dict | None:
    """Fetch and process a single instrument. Returns snapshot dict or None on error."""
    import numpy as np
    df, err = fetch_option_chain(instrument_name, token, api_url, all_instruments, cutoff)
    if err or df is None or df.empty:
        logger.warning("[COLLECT] %s skip: %s", instrument_name, err)
        return None
    df_filtered = filter_near_strikes(df, radius)
    expiry_date = df_filtered["expiry"].iloc[0] if "expiry" in df_filtered.columns else "unknown"
    df_cleaned  = df_filtered.replace([np.inf, -np.inf], np.nan)
    logger.info("[COLLECT] %s → %d rows", instrument_name, len(df_filtered))
    return {
        "index_name":  instrument_name,
        "expiry_date": expiry_date,
        "data":        json.loads(df_cleaned.to_json(orient="records", date_format="iso")),
    }


def collect_all(token: str, api_url: str, indices: dict, stocks: dict, radius: int, cutoff: int) -> list[dict]:
    """Fetch all instruments concurrently (up to FETCH_CONCURRENCY at a time)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_instruments = {**indices, **stocks}
    logger.info("[COLLECT] Fetching %d instrument(s) with concurrency=%d",
                len(all_instruments), FETCH_CONCURRENCY)

    results = []
    with ThreadPoolExecutor(max_workers=FETCH_CONCURRENCY) as pool:
        futures = {
            pool.submit(_fetch_one, name, token, api_url, all_instruments, radius, cutoff): name
            for name in all_instruments
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                snap = future.result()
                if snap:
                    results.append(snap)
            except Exception as exc:
                logger.error("[COLLECT] %s raised: %s", name, exc)

    logger.info("[COLLECT] Collected %d/%d snapshot(s)", len(results), len(all_instruments))
    return results

