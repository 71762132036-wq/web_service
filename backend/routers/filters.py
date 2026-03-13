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


@router.get("/strike")
def get_strike_filter(
    threshold: float = 10.0,
    expiry: Optional[str] = None,
    filename: Optional[str] = None
):
    """
    Returns individual strikes across all stocks where |OI Change| / |OI Strike Map| > threshold%.
    Scans ALL available strikes for maximum visibility.
    """
    strike_results = []
    
    for name in STOCKS:
        df = None
        if filename:
            df = _get_nearest_df(name, filename, context_expiry=expiry)
        if df is None:
            df = store.get_data(name)

        if df is None or df.empty:
            continue

        try:
            # Vectorized calculation for efficiency
            # We want to identify specific strikes where change is dominant
            
            # Calculate total absolute change for the entire stock at this timestamp
            total_abs_chg = (df['call_oi_chg'].abs() + df['put_oi_chg'].abs()).sum()
            if total_abs_chg == 0:
                continue

            # 1. Prepare Call data
            calls = df[df['Call_OI'] > 0].copy()
            if not calls.empty:
                calls['chg_pct'] = (calls['call_oi_chg'].abs() / calls['Call_OI']) * 100
                hot_calls = calls[calls['chg_pct'] > threshold]
                for _, row in hot_calls.iterrows():
                    strike_results.append({
                        "Stock": name,
                        "Strike": float(row['Strike']),
                        "Type": "Call",
                        "OI_Chg_Pct": round(float(row['chg_pct']), 2),
                        "OI_Chg_Raw": int(row['call_oi_chg']),
                        "Total_OI": int(row['Call_OI']),
                        "Influence": round((abs(float(row['call_oi_chg'])) / total_abs_chg) * 100, 1),
                        "Sentiment": "Writing" if row['call_oi_chg'] > 0 else "Unwinding"
                    })

            # 2. Prepare Put data
            puts = df[df['Put_OI'] > 0].copy()
            if not puts.empty:
                puts['chg_pct'] = (puts['put_oi_chg'].abs() / puts['Put_OI']) * 100
                hot_puts = puts[puts['chg_pct'] > threshold]
                for _, row in hot_puts.iterrows():
                    strike_results.append({
                        "Stock": name,
                        "Strike": float(row['Strike']),
                        "Type": "Put",
                        "OI_Chg_Pct": round(float(row['chg_pct']), 2),
                        "OI_Chg_Raw": int(row['put_oi_chg']),
                        "Total_OI": int(row['Put_OI']),
                        "Influence": round((abs(float(row['put_oi_chg'])) / total_abs_chg) * 100, 1),
                        "Sentiment": "Writing" if row['put_oi_chg'] > 0 else "Unwinding"
                    })

        except Exception as e:
            print(f"[ERROR-STRIKE-FILTER] Error processing {name}: {e}")
            continue

    # Calculate Summary Stats
    summary = {
        "total_hot_strikes": len(strike_results),
        "writing_bias": 0.0,
        "top_writer": None,
        "top_unwinder": None,
    }

    if strike_results:
        # 1. Writing Bias (What % of hot strikes are writing?)
        writing_count = sum(1 for x in strike_results if x["Sentiment"] == "Writing")
        summary["writing_bias"] = round((writing_count / len(strike_results)) * 100, 1)

        # 2. Top Writer (Highest % Chg Writing)
        writers = [x for x in strike_results if x["Sentiment"] == "Writing"]
        if writers:
            summary["top_writer"] = max(writers, key=lambda x: x["OI_Chg_Pct"])

        # 3. Top Unwinder (Highest % Chg Unwinding - based on absolute change)
        unwinders = [x for x in strike_results if x["Sentiment"] == "Unwinding"]
        if unwinders:
            summary["top_unwinder"] = max(unwinders, key=lambda x: x["OI_Chg_Pct"])

    # Sort by最高的 percentage change
    strike_results.sort(key=lambda x: x["OI_Chg_Pct"], reverse=True)
    return {
        "summary": summary,
        "results": strike_results
    }
