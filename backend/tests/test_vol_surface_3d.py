
import sys
import os
from pathlib import Path

# Add backend to sys.path
backend_path = Path(r"d:\Investments\Participant_Wise_OI\Analytical_App\gamma_stocks\GC_gamma\nifty\web_app\backend")
sys.path.append(str(backend_path))

from services.historical_service import get_vol_surface_history
from services.chart_service import build_vol_surface_3d_chart

def test_vol_surface_3d():
    index = "Nifty"
    expiry = "2026-03-26"
    
    data_dir = backend_path / "data"
    if not (data_dir / index / expiry).exists():
        print(f"Path {(data_dir / index / expiry)} does not exist. Finding alternatives...")
        indices = [d.name for d in data_dir.iterdir() if d.is_dir() and "20" not in d.name]
        if not indices: return
        index = indices[0]
        exps = [d.name for d in (data_dir / index).iterdir() if d.is_dir()]
        if not exps: return
        expiry = exps[0]

    print(f"Testing Vol Surface with Index: {index}, Expiry: {expiry}")
    files = list((data_dir / index / expiry).glob("*.parquet"))
    if not files:
        print("No files found.")
        return
        
    filter_day = files[0].name.split("_")[0]
    print(f"Filter day: {filter_day}")
    
    res = get_vol_surface_history(index, expiry, filter_day=filter_day)
    if "error" in res:
        print(f"Error: {res['error']}")
    else:
        strikes = res.get('strikes', [])
        times = res.get('times', [])
        iv_grid = res.get('iv_grid', [])
        print(f"Success! Grid size: {len(times)} times x {len(strikes)} strikes.")
        if iv_grid and iv_grid[0]:
            print(f"Sample IV point: {iv_grid[0][0]}")
        
        chart = build_vol_surface_3d_chart(res, index)
        print("3D Chart built successfully.")
        # print(chart.get("data")[0].get("type"))

if __name__ == "__main__":
    test_vol_surface_3d()
