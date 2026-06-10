"""
Historical Service — manages multi-snapshot analysis for temporal tracking.
Responsible for scanning Parquet files and aggregating level migration data.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

from core.config import DATA_DIR, INDICES, STOCKS
from services.upstox_service import load_data_file
from services.calculations import calculate_flip_point, calculate_quant_power, calculate_vtl

def _sort_parquet_files(files: List[Path], expiry_date_str: str) -> List[Path]:
    """
    Sorts files chronologically, handling month/year boundaries.
    Uses expiry_date_str (YYYY-MM-DD) as context to reconstruct full timestamps.
    """
    try:
        exp_dt = datetime.strptime(expiry_date_str, "%Y-%m-%d")
        exp_year, exp_month, exp_day = exp_dt.year, exp_dt.month, exp_dt.day
    except:
        # Fallback to simple name sort if parsing fails
        return sorted(files, key=lambda x: x.name, reverse=True)

    def get_sort_key(p: Path):
        try:
            # Format: DD_HHMMSS
            parts = p.stem.split("_")
            d_str, t_str = parts[0], parts[1]
            day = int(d_str)
            
            # Heuristic: In an expiry-specific folder, if the snapshot day 
            # is greater than the expiry day, it MUST belong to the previous month.
            year, month = exp_year, exp_month
            if day > exp_day:
                # Previous month
                month = exp_month - 1
                if month == 0:
                    month = 12
                    year -= 1
            
            # Combine into a string that sorts correctly (YYYYMMDD_HHMMSS)
            return f"{year:04d}{month:02d}{day:02d}_{t_str}"
        except:
            return p.name

    return sorted(files, key=get_sort_key, reverse=True)

def get_level_migration(index_name: str, expiry_date: str, n_files: int = 150) -> Dict[str, Any]:
    """
    Scans the last N snapshots for an index/expiry and extracts:
    - Time-series of Spot Price
    - Time-series of Flip Point
    - Time-series of Quant Power (QP)
    - Time-series of VTL
    """
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        # Fallback to legacy path
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found for this expiry."}

    # Get all parquet files, sorted by time (newest first)
    all_files = list(data_path.glob("*.parquet"))
    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files] # Take last N
    files.reverse() # Sort chronological for charting

    history = []
    
    # Cache for instrument config
    all_instruments = {**INDICES, **STOCKS}
    instr_config = all_instruments.get(index_name, {})
    lot_size = instr_config.get("lot_size", 75)

    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty:
            continue

        try:
            spot = float(df["Spot"].iloc[0])
            flip = float(calculate_flip_point(df))
            
            # Quant Power calculation
            qp_data = calculate_quant_power(df, spot, contract_size=lot_size)
            qp = qp_data["quant_power"]
            
            # VTL calculation
            vtl_data = calculate_vtl(df, spot)
            vtl = vtl_data["vtl"]

            # Filename is usually DD_HHMMSS.parquet
            # We want to extract a readable time label
            time_label = f.stem # e.g. "15_143000"
            
            history.append({
                "time": time_label,
                "spot": spot,
                "flip": flip,
                "qp": qp,
                "vtl": vtl
            })
        except Exception as e:
            logger.error("[HISTORICAL] Skip file %s due to calculation error: %s", f.name, e)
            continue

    return {
        "index": index_name,
        "expiry": expiry_date,
        "history": history
    }

def get_historical_prices(index_name: str, expiry_date: str, n_files: int = 150) -> List[float]:
    """Extracts a series of spot prices for RV calculation."""
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return []

    all_files = list(data_path.glob("*.parquet"))
    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    prices = []
    for f in files:
        df, error = load_data_file(str(f))
        if not error and df is not None and not df.empty:
            prices.append(float(df["Spot"].iloc[0]))
    
    return prices

def get_flow_momentum(index_name: str, expiry_date: str, n_files: int = 150) -> Dict[str, Any]:
    """
    Tracks the rate of change (velocity) of Net GEX and VEX.
    Helps identify if institutional hedging is accelerating.
    """
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found."}

    all_files = list(data_path.glob("*.parquet"))
    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    momentum_data = []
    prev_gex = None
    prev_vex = None

    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty: continue
        
        # Calculate totals with auto-calculate fallback
        if 'Total_GEX' not in df.columns:
            from services.calculations import calculate_gex
            df = calculate_gex(df)
        if 'Total_VEX' not in df.columns:
            from services.calculations import calculate_vanna_exposure
            df = calculate_vanna_exposure(df)

        gex_total = df['Total_GEX'].sum()
        vex_total = df['Total_VEX'].sum()
        
        # Velocity
        gex_vel = (gex_total - prev_gex) if prev_gex is not None else 0
        vex_vel = (vex_total - prev_vex) if prev_vex is not None else 0
        
        momentum_data.append({
            "time": f.stem,
            "gex_total": float(gex_total),
            "vex_total": float(vex_total),
            "gex_velocity": float(gex_vel),
            "vex_velocity": float(vex_vel)
        })
        
        prev_gex = gex_total
        prev_vex = vex_total

    return {
        "index": index_name,
        "momentum": momentum_data
    }

def get_systemic_pulse(index_name: str, expiry_date: str, n_files: int = 150, filter_day: Optional[str] = None) -> Dict[str, Any]:
    """
    Collects a 4-line time-series for systemic market regime analysis:
    - Spot Price
    - ATM IV (Volatility)
    - Net Dealer GEX (Cumulative Gamma)
    - Net Dealer DEX (Cumulative Delta)
    
    If filter_day is provided (e.g. "19"), only files from that day are included.
    """
    from services.calculations import calculate_vol_surface, calculate_gex, calculate_delta_exposure
    
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found for systemic pulse."}

    all_files = list(data_path.glob("*.parquet"))
    
    if filter_day:
        # filter_day is like "19", files are "19_103000.parquet"
        day_str = f"{filter_day}_"
        all_files = [f for f in all_files if f.name.startswith(day_str)]

    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    pulse_data = []
    all_instruments = {**INDICES, **STOCKS}
    instr_config = all_instruments.get(index_name, {})
    lot_size = instr_config.get("lot_size", 75)

    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty: continue
        
        try:
            spot = float(df["Spot"].iloc[0])
            
            # 1. Total GEX
            df_gex = calculate_gex(df, lot_size=lot_size)
            total_gex = df_gex["Total_GEX"].sum()
            
            # 2. Total DEX
            df_dex = calculate_delta_exposure(df, lot_size=lot_size)
            total_dex = df_dex["Total_DEX"].sum()
            
            # 3. ATM IV
            vs = calculate_vol_surface(df)
            iv = vs["ATM_IV"]
            
            # Filename Format: DD_HHMMSS
            parts = f.stem.split("_")
            time_str = parts[1] if len(parts) > 1 else "000000"
            time_label = f"{time_str[:2]}:{time_str[2:4]}" # HH:MM
            
            pulse_data.append({
                "time": time_label,
                "spot": spot,
                "iv": float(iv),
                "cum_gamma": float(total_gex),
                "cum_delta": float(total_dex)
            })
        except Exception as e:
            logger.error("[PULSE] Skip file %s error: %s", f.name, e)
            continue

    return {
        "index": index_name,
        "expiry": expiry_date,
        "pulse": pulse_data
    }

def get_intraday_iv_tracker(index_name: str, expiry_date: str, n_files: int = 150, filter_day: Optional[str] = None) -> Dict[str, Any]:
    """
    Tracks Call IV, Put IV, and Spot Price for the ATM strike across snapshots.
    Used for the Intraday IV Tracker chart.
    """
    from services.calculations import get_atm_strike
    
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found for IV tracker."}

    all_files = list(data_path.glob("*.parquet"))
    
    if filter_day:
        day_str = f"{filter_day}_"
        all_files = [f for f in all_files if f.name.startswith(day_str)]

    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    iv_history = []
    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty: continue
        
        try:
            spot = float(df["Spot"].iloc[0])
            atm_strike = get_atm_strike(df)
            atm_row = df[df["Strike"] == atm_strike].iloc[0]
            
            # Use call_iv and put_iv at ATM
            call_iv = float(atm_row["call_iv"])
            put_iv = float(atm_row["put_iv"])
            
            parts = f.stem.split("_")
            time_str = parts[1] if len(parts) > 1 else "000000"
            time_label = f"{time_str[:2]}:{time_str[2:4]}" # HH:MM
            
            iv_history.append({
                "time": time_label,
                "spot": spot,
                "call_iv": call_iv,
                "put_iv": put_iv
            })
        except Exception as e:
            logger.error("[IV_TRACKER] Skip file %s error: %s", f.name, e)
            continue

    return {
        "index": index_name,
        "expiry": expiry_date,
        "history": iv_history
    }

def get_vol_surface_history(index_name: str, expiry_date: str, n_files: int = 100, filter_day: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts a 3D grid of Implied Volatility across Strike and Time.
    Returns: { 'strikes': [], 'times': [], 'iv_grid': [[...], ...] }
    """
    from services.calculations import get_atm_strike
    
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found for Vol Surface."}

    all_files = list(data_path.glob("*.parquet"))
    if filter_day:
        day_str = f"{filter_day}_"
        all_files = [f for f in all_files if f.name.startswith(day_str)]

    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    if not files:
        return {"error": "No files found for selected criteria."}

    # 1. Determine common strikes from the latest file to keep the grid consistent
    latest_df, _ = load_data_file(str(files[-1]))
    if latest_df is None or latest_df.empty:
        return {"error": "Failed to load base strike data."}
    
    atm = get_atm_strike(latest_df)
    unique_strikes = sorted(latest_df["Strike"].unique().tolist())
    try:
        atm_idx = unique_strikes.index(atm)
        start_idx = max(0, atm_idx - 15)
        end_idx = min(len(unique_strikes), atm_idx + 15)
        shared_strikes = unique_strikes[start_idx:end_idx]
    except ValueError:
        shared_strikes = unique_strikes[:30]

    times = []
    iv_grid = [] # List of lists (Outer: Time, Inner: Strike)

    for f in files:
        df, _ = load_data_file(str(f))
        if df is None or df.empty: continue
        
        parts = f.stem.split("_")
        time_str = parts[1] if len(parts) > 1 else "000000"
        times.append(f"{time_str[:2]}:{time_str[2:4]}")
        
        # Build row for this timestamp
        row_ivs = []
        df_indexed = df.set_index("Strike")
        for s in shared_strikes:
            if s in df_indexed.index:
                # Average Call/Put IV
                civ = float(df_indexed.loc[s, "call_iv"])
                piv = float(df_indexed.loc[s, "put_iv"])
                avg_iv = (civ + piv) / 2.0 if civ > 0 and piv > 0 else (civ or piv)
                row_ivs.append(avg_iv)
            else:
                row_ivs.append(None)
        iv_grid.append(row_ivs)

    return {
        "index": index_name,
        "expiry": expiry_date,
        "strikes": shared_strikes,
        "times": times,
        "iv_grid": iv_grid
    }


def get_daily_study(index_name: str, expiry_date: str) -> Dict[str, Any]:
    """
    Groups all snapshots by trading day and records:
      - Morning setup: key GEX levels at market open (first snapshot of each day)
      - Intraday spot path: price at every snapshot through the day
      - Outcome: did the call wall hold? put wall? was the regime prediction accurate?

    This is the validation tool to learn whether GEX theory actually works for Nifty.
    Each day is one data point. Over months, patterns will emerge.
    """
    from services.calculations import (
        calculate_flip_point, calculate_gex, calculate_max_pain
    )

    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found."}

    all_files = list(data_path.glob("*.parquet"))
    if not all_files:
        return {"error": "No snapshots found."}

    # Group files by day (DD part of filename)
    days_dict: Dict[str, List[Path]] = {}
    for f in all_files:
        parts = f.stem.split("_")
        day = parts[0] if parts else "?"
        days_dict.setdefault(day, []).append(f)

    all_instruments = {**INDICES, **STOCKS}
    lot_size = all_instruments.get(index_name, {}).get("lot_size", 75)

    days_study = []

    for day in sorted(days_dict.keys()):
        day_files = sorted(days_dict[day], key=lambda f: f.name)
        if not day_files:
            continue

        # ── Morning setup: first snapshot of the day ─────────────────────────
        morning_df, err = load_data_file(str(day_files[0]))
        if err or morning_df is None or morning_df.empty:
            continue

        try:
            spot_open = float(morning_df["Spot"].iloc[0])
            df_gex = calculate_gex(morning_df, lot_size=lot_size)
            flip = float(calculate_flip_point(df_gex))
            regime = "LONG GAMMA" if spot_open > flip else "SHORT GAMMA"

            c_col = "Call_OI" if "Call_OI" in morning_df.columns else "call_oi"
            p_col = "Put_OI" if "Put_OI" in morning_df.columns else "put_oi"

            top_call_strike = float(morning_df.nlargest(1, c_col)["Strike"].iloc[0])
            top_put_strike  = float(morning_df.nlargest(1, p_col)["Strike"].iloc[0])

            pain     = calculate_max_pain(df_gex)
            max_pain = float(pain["max_pain_strike"])

            total_call = float(morning_df[c_col].sum())
            total_put  = float(morning_df[p_col].sum())
            pcr = round(total_put / total_call, 3) if total_call > 0 else 0.0

        except Exception as e:
            logger.error("[DAILY_STUDY] Morning setup failed day=%s: %s", day, e)
            continue

        # ── Intraday price path: all snapshots for this day ──────────────────
        intraday = []
        for f in day_files:
            df, err = load_data_file(str(f))
            if err or df is None or df.empty:
                continue
            try:
                parts_f = f.stem.split("_")
                t = parts_f[1] if len(parts_f) > 1 else "000000"
                intraday.append({
                    "time": f"{t[:2]}:{t[2:4]}",
                    "spot": float(df["Spot"].iloc[0]),
                })
            except Exception:
                continue

        if not intraday:
            continue

        # ── Outcome ──────────────────────────────────────────────────────────
        spots       = [s["spot"] for s in intraday]
        day_high    = max(spots)
        day_low     = min(spots)
        day_close   = spots[-1]
        day_range   = round(day_high - day_low, 2)

        call_wall_held   = day_high < top_call_strike
        put_wall_held    = day_low  > top_put_strike
        stayed_in_range  = call_wall_held and put_wall_held

        # Regime accuracy heuristic:
        #   Long Gamma  → expect price to stay within a tight band (low range ratio)
        #   Short Gamma → expect price to trend (large directional move)
        predicted_range = max(top_call_strike - top_put_strike, 1)
        range_ratio     = day_range / predicted_range
        price_direction = day_close - spot_open

        if regime == "LONG GAMMA":
            regime_accurate = range_ratio < 0.6          # used <60% of the predicted band
        else:
            regime_accurate = abs(price_direction) > day_range * 0.35  # clear directional bias

        days_study.append({
            "day": day,
            "morning": {
                "spot":           spot_open,
                "flip_point":     flip,
                "regime":         regime,
                "top_call_wall":  top_call_strike,
                "top_put_wall":   top_put_strike,
                "max_pain":       max_pain,
                "pcr":            pcr,
            },
            "intraday": intraday,
            "outcome": {
                "high":              round(day_high, 2),
                "low":               round(day_low, 2),
                "close":             round(day_close, 2),
                "range_pts":         day_range,
                "price_direction":   round(price_direction, 2),
                "call_wall_held":    call_wall_held,
                "put_wall_held":     put_wall_held,
                "stayed_in_range":   stayed_in_range,
                "regime_accurate":   regime_accurate,
                "range_ratio_pct":   round(range_ratio * 100, 1),
            },
        })

    if not days_study:
        return {"error": "No complete day data found."}

    n          = len(days_study)
    call_held  = sum(1 for d in days_study if d["outcome"]["call_wall_held"])
    put_held   = sum(1 for d in days_study if d["outcome"]["put_wall_held"])
    in_range   = sum(1 for d in days_study if d["outcome"]["stayed_in_range"])
    regime_ok  = sum(1 for d in days_study if d["outcome"]["regime_accurate"])

    return {
        "index":   index_name,
        "expiry":  expiry_date,
        "days":    days_study,
        "summary": {
            "total_days":          n,
            "call_wall_held_pct":  round(call_held / n * 100, 1),
            "put_wall_held_pct":   round(put_held  / n * 100, 1),
            "in_range_pct":        round(in_range  / n * 100, 1),
            "regime_accuracy_pct": round(regime_ok / n * 100, 1),
        },
    }


def get_oi_heatmap(index_name: str, expiry_date: str, n_files: int = 200) -> Dict[str, Any]:
    """
    Builds a 2D OI grid across (time x strike) for the full expiry.
    Returns call_oi_grid, put_oi_grid, net_oi_grid (outer=time, inner=strike).
    """
    from services.calculations import get_atm_strike

    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found for OI heatmap."}

    all_files = list(data_path.glob("*.parquet"))
    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    if not files:
        return {"error": "No files found."}

    # Determine shared strikes from the most recent file
    latest_df, _ = load_data_file(str(files[-1]))
    if latest_df is None or latest_df.empty:
        return {"error": "Failed to load base strike data."}

    atm = get_atm_strike(latest_df)
    unique_strikes = sorted(latest_df["Strike"].unique().tolist())
    try:
        atm_idx = unique_strikes.index(atm)
        start_idx = max(0, atm_idx - 15)
        end_idx = min(len(unique_strikes), atm_idx + 16)
        shared_strikes = unique_strikes[start_idx:end_idx]
    except ValueError:
        shared_strikes = unique_strikes[:30]

    times = []
    call_oi_grid = []
    put_oi_grid = []
    net_oi_grid = []

    for f in files:
        df, _ = load_data_file(str(f))
        if df is None or df.empty:
            continue

        parts = f.stem.split("_")
        day_str = parts[0] if len(parts) > 0 else "?"
        time_str = parts[1] if len(parts) > 1 else "000000"
        times.append(f"{day_str}T{time_str[:2]}:{time_str[2:4]}")

        df_indexed = df.set_index("Strike")
        call_row, put_row, net_row = [], [], []
        for s in shared_strikes:
            if s in df_indexed.index:
                c_oi = float(df_indexed.loc[s, "Call_OI"] if "Call_OI" in df_indexed.columns else df_indexed.loc[s, "call_oi"])
                p_oi = float(df_indexed.loc[s, "Put_OI"] if "Put_OI" in df_indexed.columns else df_indexed.loc[s, "put_oi"])
                call_row.append(c_oi)
                put_row.append(p_oi)
                net_row.append(c_oi - p_oi)
            else:
                call_row.append(None)
                put_row.append(None)
                net_row.append(None)

        call_oi_grid.append(call_row)
        put_oi_grid.append(put_row)
        net_oi_grid.append(net_row)

    return {
        "index": index_name,
        "expiry": expiry_date,
        "strikes": shared_strikes,
        "times": times,
        "call_oi_grid": call_oi_grid,
        "put_oi_grid": put_oi_grid,
        "net_oi_grid": net_oi_grid,
    }


def get_strike_importance(index_name: str, expiry_date: str, n_files: int = 200, top_n: int = 5) -> Dict[str, Any]:
    """
    Ranks strikes by how often they appeared in the top-N by OI across all snapshots.
    pct_time = appearances / total_snapshots * 100.
    """
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found."}

    all_files = list(data_path.glob("*.parquet"))
    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    call_appearances: Dict[float, int] = {}
    call_oi_sum: Dict[float, float] = {}
    call_oi_peak: Dict[float, float] = {}
    put_appearances: Dict[float, int] = {}
    put_oi_sum: Dict[float, float] = {}
    put_oi_peak: Dict[float, float] = {}
    total_snapshots = 0

    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty:
            continue
        total_snapshots += 1

        c_col = "Call_OI" if "Call_OI" in df.columns else "call_oi"
        p_col = "Put_OI" if "Put_OI" in df.columns else "put_oi"

        top_calls = df.nlargest(top_n, c_col)[["Strike", c_col]]
        for _, row in top_calls.iterrows():
            s, v = float(row["Strike"]), float(row[c_col])
            call_appearances[s] = call_appearances.get(s, 0) + 1
            call_oi_sum[s] = call_oi_sum.get(s, 0.0) + v
            call_oi_peak[s] = max(call_oi_peak.get(s, 0.0), v)

        top_puts = df.nlargest(top_n, p_col)[["Strike", p_col]]
        for _, row in top_puts.iterrows():
            s, v = float(row["Strike"]), float(row[p_col])
            put_appearances[s] = put_appearances.get(s, 0) + 1
            put_oi_sum[s] = put_oi_sum.get(s, 0.0) + v
            put_oi_peak[s] = max(put_oi_peak.get(s, 0.0), v)

    def _rank(appearances, oi_sum, oi_peak):
        records = []
        for s, count in appearances.items():
            pct = count / total_snapshots * 100 if total_snapshots > 0 else 0
            records.append({
                "strike": s,
                "appearances": count,
                "avg_oi": round(oi_sum[s] / count, 0) if count > 0 else 0,
                "peak_oi": round(oi_peak[s], 0),
                "pct_time": round(pct, 1),
            })
        return sorted(records, key=lambda x: x["pct_time"], reverse=True)[:15]

    return {
        "index": index_name,
        "expiry": expiry_date,
        "total_snapshots": total_snapshots,
        "call_ranking": _rank(call_appearances, call_oi_sum, call_oi_peak),
        "put_ranking": _rank(put_appearances, put_oi_sum, put_oi_peak),
    }


def get_oi_evolution(index_name: str, expiry_date: str, n_files: int = 200, top_n: int = 5) -> Dict[str, Any]:
    """
    Tracks OI over time for the top-N call and put strikes (by average OI across all snapshots).
    """
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found for OI evolution."}

    all_files = list(data_path.glob("*.parquet"))
    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    times: List[str] = []
    spot_series: List[float] = []
    call_oi_all: Dict[float, List[Optional[float]]] = {}
    put_oi_all: Dict[float, List[Optional[float]]] = {}
    call_oi_sums: Dict[float, float] = {}
    put_oi_sums: Dict[float, float] = {}

    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty:
            continue

        parts = f.stem.split("_")
        day_str = parts[0] if len(parts) > 0 else "?"
        time_str = parts[1] if len(parts) > 1 else "000000"
        times.append(f"{day_str}T{time_str[:2]}:{time_str[2:4]}")
        spot_series.append(float(df["Spot"].iloc[0]))

        c_col = "Call_OI" if "Call_OI" in df.columns else "call_oi"
        p_col = "Put_OI" if "Put_OI" in df.columns else "put_oi"

        snap_idx = len(times) - 1

        for _, row in df.iterrows():
            s = float(row["Strike"])
            c_v = float(row[c_col]) if not pd.isna(row[c_col]) else 0.0
            p_v = float(row[p_col]) if not pd.isna(row[p_col]) else 0.0

            if s not in call_oi_all:
                call_oi_all[s] = [None] * snap_idx
                call_oi_sums[s] = 0.0
            while len(call_oi_all[s]) < snap_idx:
                call_oi_all[s].append(None)
            call_oi_all[s].append(c_v)
            call_oi_sums[s] = call_oi_sums.get(s, 0.0) + c_v

            if s not in put_oi_all:
                put_oi_all[s] = [None] * snap_idx
                put_oi_sums[s] = 0.0
            while len(put_oi_all[s]) < snap_idx:
                put_oi_all[s].append(None)
            put_oi_all[s].append(p_v)
            put_oi_sums[s] = put_oi_sums.get(s, 0.0) + p_v

    total = len(times)

    # Pad any series shorter than total (strikes absent from some snapshots)
    for s in list(call_oi_all.keys()):
        while len(call_oi_all[s]) < total:
            call_oi_all[s].append(None)
    for s in list(put_oi_all.keys()):
        while len(put_oi_all[s]) < total:
            put_oi_all[s].append(None)

    # Pick top_n strikes by average OI
    top_call_strikes = sorted(call_oi_sums, key=lambda s: call_oi_sums[s], reverse=True)[:top_n]
    top_put_strikes = sorted(put_oi_sums, key=lambda s: put_oi_sums[s], reverse=True)[:top_n]

    return {
        "index": index_name,
        "expiry": expiry_date,
        "times": times,
        "spot_series": spot_series,
        "call_series": {str(int(s)): call_oi_all[s] for s in top_call_strikes},
        "put_series": {str(int(s)): put_oi_all[s] for s in top_put_strikes},
    }


def get_oi_lifecycle(index_name: str, expiry_date: str, n_files: int = 200) -> Dict[str, Any]:
    """
    Tracks total Call OI, Put OI, and PCR across the entire expiry (multi-day).
    Uses DDTHH:MM time labels so day boundaries are visible on the X-axis.
    """
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found for OI lifecycle."}

    all_files = list(data_path.glob("*.parquet"))
    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    history = []
    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty:
            continue
        try:
            spot = float(df["Spot"].iloc[0])
            c_col = "Call_OI" if "Call_OI" in df.columns else "call_oi"
            p_col = "Put_OI" if "Put_OI" in df.columns else "put_oi"
            total_call = float(df[c_col].sum())
            total_put = float(df[p_col].sum())
            pcr = round(total_put / total_call, 3) if total_call > 0 else 0.0

            parts = f.stem.split("_")
            day_str = parts[0] if len(parts) > 0 else "?"
            time_str = parts[1] if len(parts) > 1 else "000000"
            time_label = f"{day_str}T{time_str[:2]}:{time_str[2:4]}"

            history.append({
                "time": time_label,
                "call_oi": total_call,
                "put_oi": total_put,
                "pcr": pcr,
                "spot": spot,
            })
        except Exception as e:
            logger.error("[OI_LIFECYCLE] Skip %s: %s", f.name, e)
            continue

    return {"index": index_name, "expiry": expiry_date, "history": history}


def get_max_pain_migration(index_name: str, expiry_date: str, n_files: int = 200) -> Dict[str, Any]:
    """
    Tracks how the max pain strike moved across the full expiry vs spot price.
    Reveals whether price is converging toward or diverging from max pain.
    """
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found for max pain migration."}

    all_files = list(data_path.glob("*.parquet"))
    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    history = []
    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty:
            continue
        try:
            spot = float(df["Spot"].iloc[0])
            c_col = "Call_OI" if "Call_OI" in df.columns else "call_oi"
            p_col = "Put_OI" if "Put_OI" in df.columns else "put_oi"

            test_strikes = np.array(sorted(df["Strike"].unique()))
            strike_arr = df["Strike"].values
            call_oi_arr = df[c_col].fillna(0).values
            put_oi_arr = df[p_col].fillna(0).values

            # Vectorised max pain formula (same as calculate_max_pain in calculations.py)
            call_itm = np.maximum(test_strikes[:, None] - strike_arr[None, :], 0)
            put_itm = np.maximum(strike_arr[None, :] - test_strikes[:, None], 0)
            total_pain = (call_itm * call_oi_arr).sum(axis=1) + (put_itm * put_oi_arr).sum(axis=1)
            max_pain_strike = float(test_strikes[np.argmin(total_pain)])
            distance_pct = round((spot - max_pain_strike) / max_pain_strike * 100, 3)

            parts = f.stem.split("_")
            day_str = parts[0] if len(parts) > 0 else "?"
            time_str = parts[1] if len(parts) > 1 else "000000"
            time_label = f"{day_str}T{time_str[:2]}:{time_str[2:4]}"

            history.append({
                "time": time_label,
                "max_pain": max_pain_strike,
                "spot": spot,
                "distance_pct": distance_pct,
            })
        except Exception as e:
            logger.error("[MAX_PAIN_MIG] Skip %s: %s", f.name, e)
            continue

    return {"index": index_name, "expiry": expiry_date, "history": history}


def get_intraday_oi_tracker(index_name: str, expiry_date: str, n_files: int = 150, filter_day: Optional[str] = None) -> Dict[str, Any]:
    """
    Tracks cumulative intraday Call OI Change and Put OI Change across snapshots.
    Used for the Intraday OI Tracker chart.
    """
    data_path = Path(DATA_DIR) / index_name / expiry_date
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry_date
        if not data_path.exists():
            return {"error": "No historical data found for OI tracker."}

    all_files = list(data_path.glob("*.parquet"))
    
    if filter_day:
        day_str = f"{filter_day}_"
        all_files = [f for f in all_files if f.name.startswith(day_str)]

    files = _sort_parquet_files(all_files, expiry_date)
    files = files[:n_files]
    files.reverse()

    oi_history = []
    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty: continue
        
        try:
            spot = float(df["Spot"].iloc[0])
            
            # Fallback calculation if columns are missing
            if "call_oi_chg" not in df.columns or df["call_oi_chg"].isna().all():
                if "call_oi" in df.columns and "call_prev_oi" in df.columns:
                    df["call_oi_chg"] = df["call_oi"].fillna(0) - df["call_prev_oi"].fillna(0)
            
            if "put_oi_chg" not in df.columns or df["put_oi_chg"].isna().all():
                if "put_oi" in df.columns and "put_prev_oi" in df.columns:
                    df["put_oi_chg"] = df["put_oi"].fillna(0) - df["put_prev_oi"].fillna(0)

            total_call_oi = float(df["call_oi"].sum()) if "call_oi" in df.columns else 0.0
            total_put_oi = float(df["put_oi"].sum()) if "put_oi" in df.columns else 0.0
            total_call_chg = float(df["call_oi_chg"].sum()) if "call_oi_chg" in df.columns else 0.0
            total_put_chg = float(df["put_oi_chg"].sum()) if "put_oi_chg" in df.columns else 0.0
            
            parts = f.stem.split("_")
            time_str = parts[1] if len(parts) > 1 else "000000"
            time_label = f"{time_str[:2]}:{time_str[2:4]}" # HH:MM
            
            oi_history.append({
                "time": time_label,
                "spot": spot,
                "call_oi": total_call_oi,
                "put_oi": total_put_oi,
                "call_oi_chg": total_call_chg,
                "put_oi_chg": total_put_chg
            })
        except Exception as e:
            logger.error("[OI_TRACKER] Skip file %s error: %s", f.name, e)
            continue

    return {
        "index": index_name,
        "expiry": expiry_date,
        "history": oi_history
    }
