"""
Historical Service — manages multi-snapshot analysis for temporal tracking.
Responsible for scanning Parquet files and aggregating level migration data.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

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
            print(f"[HISTORICAL] Skip file {f.name} due to calculation error: {e}")
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
            
            pulse_data.append({
                "time": f.stem,
                "spot": spot,
                "iv": float(iv),
                "cum_gamma": float(total_gex),
                "cum_delta": float(total_dex)
            })
        except Exception as e:
            print(f"[PULSE] Skip file {f.name} error: {e}")
            continue

    return {
        "index": index_name,
        "expiry": expiry_date,
        "pulse": pulse_data
    }
