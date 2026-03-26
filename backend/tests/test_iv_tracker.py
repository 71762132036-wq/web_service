
import sys
import os
from pathlib import Path

# Add backend to sys.path
backend_path = Path(r"d:\Investments\Participant_Wise_OI\Analytical_App\gamma_stocks\GC_gamma\nifty\web_app\backend")
sys.path.append(str(backend_path))

from services.historical_service import get_intraday_iv_tracker
from services.chart_service import build_intraday_iv_chart

def test_iv_tracker():
    index = "Nifty"
    expiry = "2026-03-26"
    
    # Let's check what expiries are available
    data_dir = backend_path / "data"
    if not (data_dir / index / expiry).exists():
        print(f"Path {(data_dir / index / expiry)} does not exist.")
        # Try to find any available
        indices = [d.name for d in data_dir.iterdir() if d.is_dir() and "20" not in d.name]
        print(f"Indices: {indices}")
        if not indices: return
        idx = indices[0]
        exps = [d.name for d in (data_dir / idx).iterdir() if d.is_dir()]
        print(f"Expiries for {idx}: {exps}")
        if not exps: return
        index, expiry = idx, exps[0]

    print(f"Testing with Index: {index}, Expiry: {expiry}")
    files = list((data_dir / index / expiry).glob("*.parquet"))
    if not files:
        print("No files found.")
        return
        
    filter_day = files[0].name.split("_")[0]
    print(f"Filter day: {filter_day}")
    
    res = get_intraday_iv_tracker(index, expiry, filter_day=filter_day)
    if "error" in res:
        print(f"Error: {res['error']}")
    else:
        history = res.get('history', [])
        print(f"Success! Found {len(history)} data points.")
        if history:
            print(f"Sample data: {history[0]}")
        chart = build_intraday_iv_chart(res, index)
        print("Chart built successfully.")

if __name__ == "__main__":
    test_iv_tracker()
