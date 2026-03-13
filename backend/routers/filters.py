from fastapi import APIRouter, HTTPException
from typing import Optional
import store
from core.config import STOCKS
import pandas as pd

router = APIRouter(prefix="/api/filters", tags=["filters"])

def _get_nearest_df(name: str, target_filename: str, context_expiry: Optional[str] = None):
    """
    Find the nearest historical data for a stock within a 5-minute (300s) tolerance.
    Searches across all expiry folders because stock expiries often differ from indices.
    """
    from core.config import DATA_DIR
    from services.upstox_service import load_data_file, get_available_files
    from pathlib import Path
    from datetime import datetime
    
    # 1. Parse target time (Format: DD_HHMMSS)
    try:
        target_dt = datetime.strptime(target_filename.replace(".csv", ""), "%d_%H%M%S")
    except Exception:
        return None

    best_df = None
    min_diff = 300  # 5-minute tolerance (300 seconds)
    
    files_dict = get_available_files(name)
    
    # Prioritize the provided context_expiry (usually index expiry)
    sorted_expiries = sorted(files_dict.keys(), key=lambda x: x != context_expiry)
    
    for exp_name in sorted_expiries:
        for fname in files_dict[exp_name]:
            try:
                # Parse file time
                file_dt = datetime.strptime(fname.replace(".csv", ""), "%d_%H%M%S")
                diff = abs((target_dt - file_dt).total_seconds())
                
                if diff < min_diff:
                    min_diff = diff
                    filepath = Path(DATA_DIR) / name / exp_name / fname
                    best_df, _ = load_data_file(str(filepath))
                    
                    if diff == 0:  # Perfect match
                        print(f"[DEBUG-FILTER] EXACT MATCH for {name}: {fname}")
                        return best_df
            except Exception:
                continue
    if best_df is not None:
        print(f"[DEBUG-FILTER] FUZZY MATCH for {name}: {target_filename} -> closest is {min_diff:.1f}s away")
    else:
        print(f"[DEBUG-FILTER] NO DATA found for {name} within {target_filename} range")
        
    return best_df


@router.get("/overall")
def get_overall_filter(
    threshold: float = 80.0, 
    trend: str = "all",
    expiry: Optional[str] = None,
    filename: Optional[str] = None,
    apply_filter: bool = True
):
    """
    Returns a list of stocks where cumulative sum of OI change
    is more than threshold% of cumulative sum of OI strike map.
    """
    results = []
    
    for name in STOCKS:
        df = None
        
        # 1. Try Temporal Sync (Exact or Fuzzy)
        if filename:
            df = _get_nearest_df(name, filename, context_expiry=expiry)
            
        # 2. Fallback to Memory
        if df is None:
            df = store.get_data(name)

        if df is None or df.empty:
            continue
            
        try:
            gross_chg = (df['call_oi_chg'].abs().sum() + df['put_oi_chg'].abs().sum())
            net_chg = (df['call_oi_chg'].sum() + df['put_oi_chg'].sum())
            total_oi = (df['Call_OI'].sum() + df['Put_OI'].sum())
            
            if total_oi > 0:
                percentage = (gross_chg / total_oi) * 100
                
                # Check threshold ONLY if apply_filter is True
                if apply_filter and percentage <= threshold:
                    continue

                if trend == "positive" and net_chg <= 0:
                    continue
                if trend == "negative" and net_chg >= 0:
                    continue
                    
                call_oi = df['Call_OI'].sum()
                put_oi = df['Put_OI'].sum()
                
                call_oi_chg = df['call_oi_chg'].sum()
                put_oi_chg = df['put_oi_chg'].sum()
                
                # Calculate percentages relative to their own strike map totals
                call_chg_pct = (call_oi_chg / call_oi * 100) if call_oi > 0 else 0
                put_chg_pct = (put_oi_chg / put_oi * 100) if put_oi > 0 else 0
                
                results.append({
                    "Stock": name,
                    "Change(%)": round(percentage, 2),
                    "Call_OI_Chg_Pct": round(float(call_chg_pct), 2),
                    "Put_OI_Chg_Pct": round(float(put_chg_pct), 2),
                    "Net_Chg": float(net_chg)
                })
        except Exception:
            continue
            
    results.sort(key=lambda x: x["Change(%)"], reverse=True)
    return {"results": results}
