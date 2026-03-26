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
