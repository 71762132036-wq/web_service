"""
Charts router — returns Plotly JSON for interactive charts.
Route: GET /api/charts/{index}/{chart_type}

chart_type options:
  gex | regime | call_put | iv_smile | rr_bf
"""

from fastapi import APIRouter, HTTPException

import store
from core.config import INDICES, DATA_DIR
from services.upstox_service import load_data_file
from services.calculations import calculate_vol_surface, calculate_delta_exposure, calculate_vanna_exposure, calculate_charm_exposure, calculate_iv_cone, calculate_vtl
from services.chart_service import (
    build_dealer_regime_map,
    build_gamma_chart,
    build_delta_chart,
    build_cumulative_delta_chart,
    build_cumulative_gamma_chart,
    build_iv_smile,
    build_rr_bf,
    build_quant_power_chart,
    build_vanna_chart,
    build_cumulative_vanna_chart,
    build_charm_chart,
    build_cumulative_charm_chart,
    build_iv_cone_chart,
    build_standard_oi_chart,
    build_oi_flow_chart,
    build_oi_change_chart,
    build_premium_flow_chart,
    build_compare_oi_change_chart,
    build_flow_intensity_chart,
    build_strike_pressure_chart,
    build_vtl_chart,
)
from services.flow_service import classify_option_flow

router = APIRouter(prefix="/api", tags=["charts"])

CHART_TYPES = {"gex", "dex", "vex", "cex", "cum_gex", "cum_dex", "cum_vex", "cum_cex", "regime", "iv_smile", "iv_cone", "rr_bf", "quant_power", "oi_dist", "oi_flow", "oi_change", "premium_flow", "compare_oi_change", "flow_intensity", "strike_pressure", "vtl"}


@router.get("/charts/compare/{index}/{chart_type}")
def get_compare_chart(index: str, chart_type: str, expiry: str, file1: str, file2: str):
    """Compare two snapshots and return delta chart."""
    from pathlib import Path
    
    print(f"[COMPARE] index={index}, type={chart_type}, expiry={expiry}, f1={file1}, f2={file2}")
    
    if index not in INDICES:
        raise HTTPException(status_code=404, detail=f"Unknown index: {index}")
        
    # Build paths and verify
    data_path = Path(DATA_DIR).resolve()
    
    # Try new structure first: data/INDEX/EXPIRY/file
    path_1 = data_path / index / expiry / file1
    path_2 = data_path / index / expiry / file2
    
    # Fallback to legacy structure: data/EXPIRY/file (for Nifty)
    if not path_1.exists() and index == "Nifty":
        path_1 = data_path / expiry / file1
    if not path_2.exists() and index == "Nifty":
        path_2 = data_path / expiry / file2
    
    print(f"[COMPARE] Final Path 1: {path_1}")
    print(f"[COMPARE] Final Path 2: {path_2}")
    
    if not path_1.exists() or not path_2.exists():
        msg = f"Data files not found. Searched: {path_1} and {path_2}"
        print(f"[COMPARE] ERROR: {msg}")
        raise HTTPException(status_code=404, detail=msg)
        
    df1, err1 = load_data_file(str(path_1))
    df2, err2 = load_data_file(str(path_2))
    
    if err1 or err2:
        raise HTTPException(status_code=500, detail=f"Error loading comparison files: {err1 or err2}")
        
    try:
        if chart_type == "compare_oi_change":
            json_str = build_compare_oi_change_chart(df1, df2, index)
        else:
            raise HTTPException(status_code=400, detail="Comparison not implemented for this chart type")
            
        return {"index": index, "chart_type": chart_type, "figure": json_str}
        
    except Exception as exc:
        print(f"[COMPARE] Build error: {exc}")
        raise HTTPException(status_code=500, detail=f"Comparison error: {exc}")


@router.get("/charts/direction/{index}/{chart_type}")
def get_direction_chart(index: str, chart_type: str, expiry: str, file1: str, file2: str):
    """Directional flow analysis based on two snapshots."""
    from pathlib import Path
    
    if index not in INDICES:
        raise HTTPException(status_code=404, detail=f"Unknown index: {index}")
        
    data_path = Path(DATA_DIR).resolve()
    
    # Path resolution (same logic as compare)
    path_1 = data_path / index / expiry / file1
    path_2 = data_path / index / expiry / file2
    if not path_1.exists() and index == "Nifty": path_1 = data_path / expiry / file1
    if not path_2.exists() and index == "Nifty": path_2 = data_path / expiry / file2
    
    if not path_1.exists() or not path_2.exists():
        raise HTTPException(status_code=404, detail="Data files not found for direction analysis")
        
    df1, _ = load_data_file(str(path_1))
    df2, _ = load_data_file(str(path_2))
    
    try:
        flow_data = classify_option_flow(df2, df1, index) # df_now=df2 (later), df_prev=df1 (earlier)
        
        if chart_type == "flow_intensity":
            json_str = build_flow_intensity_chart(flow_data, index)
        elif chart_type == "strike_pressure":
            json_str = build_strike_pressure_chart(flow_data['merged'], index)
        else:
            raise HTTPException(status_code=400, detail="Unknown direction chart type")
            
        return {
            "index": index, 
            "chart_type": chart_type, 
            "figure": json_str,
            "summary": {
                "calls": {"pressure": flow_data['calls']['pressure'], "label": flow_data['calls']['label']},
                "puts": {"pressure": flow_data['puts']['pressure'], "label": flow_data['puts']['label']}
            }
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Direction analysis error: {exc}")


@router.get("/charts/{index}/{chart_type}")
def get_chart(index: str, chart_type: str, mode: str = "net"):
    """Return Plotly JSON string for the requested chart."""
    if index not in INDICES:
        raise HTTPException(status_code=404, detail=f"Unknown index: {index}")
    if chart_type not in CHART_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown chart type. Valid: {', '.join(sorted(CHART_TYPES))}",
        )
    if not store.has_data(index):
        raise HTTPException(status_code=404, detail="No data loaded for this index")

    df = store.get_data(index)

    try:
        if chart_type == "gex":
            from services.calculations import calculate_gex
            df_gex = calculate_gex(df, lot_size=INDICES[index].get("lot_size", 75))
            json_str = build_gamma_chart(df_gex, index, mode=mode)
        elif chart_type == "dex":
            df_dex   = calculate_delta_exposure(df, lot_size=INDICES[index].get("lot_size", 75))
            json_str = build_delta_chart(df_dex, index, mode=mode)
        elif chart_type == "cum_gex":
            from services.calculations import calculate_gex
            df_gex = calculate_gex(df, lot_size=INDICES[index].get("lot_size", 75))
            json_str = build_cumulative_gamma_chart(df_gex, index, mode=mode)
        elif chart_type == "cum_dex":
            df_dex   = calculate_delta_exposure(df, lot_size=INDICES[index].get("lot_size", 75))
            json_str = build_cumulative_delta_chart(df_dex, index, mode=mode)
        elif chart_type == "vex":
            df_vex   = calculate_vanna_exposure(df, lot_size=INDICES[index].get("lot_size", 75))
            json_str = build_vanna_chart(df_vex, index, mode=mode)
        elif chart_type == "cum_vex":
            df_vex   = calculate_vanna_exposure(df, lot_size=INDICES[index].get("lot_size", 75))
            json_str = build_cumulative_vanna_chart(df_vex, index, mode=mode)
        elif chart_type == "cex":
            df_cex   = calculate_charm_exposure(df, lot_size=INDICES[index].get("lot_size", 75))
            json_str = build_charm_chart(df_cex, index, mode=mode)
        elif chart_type == "cum_cex":
            df_cex   = calculate_charm_exposure(df, lot_size=INDICES[index].get("lot_size", 75))
            json_str = build_cumulative_charm_chart(df_cex, index, mode=mode)
        elif chart_type == "regime":
            json_str = build_dealer_regime_map(df, index)
        elif chart_type == "iv_smile":
            json_str = build_iv_smile(df)
        elif chart_type == "iv_cone":
            df_cone  = calculate_iv_cone(df)
            json_str = build_iv_cone_chart(df_cone, index)
        elif chart_type == "oi_dist":
            json_str = build_standard_oi_chart(df, index)
        elif chart_type == "oi_flow":
            json_str = build_oi_flow_chart(df, index)
        elif chart_type == "oi_change":
            json_str = build_oi_change_chart(df, index)
        elif chart_type == "premium_flow":
            json_str = build_premium_flow_chart(df, index)
        elif chart_type == "rr_bf":
            json_str = build_rr_bf(df, index)
        elif chart_type == "vtl":
            vtl_res  = calculate_vtl(df, df["Spot"].iloc[0])
            json_str = build_vtl_chart(vtl_res, df["Spot"].iloc[0], index)
            return {
                "index": index,
                "chart_type": chart_type,
                "figure": json_str,
                "summary": {
                    "vtl": vtl_res['vtl'],
                    "distance_pct": vtl_res['distance_pct'],
                    "direction": vtl_res['direction']
                }
            }
        elif chart_type == "quant_power":
            json_str = build_quant_power_chart(df, index)

    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Chart error: {exc}") from exc

    # Return as a plain string; the frontend will JSON.parse() it
    return {"index": index, "chart_type": chart_type, "figure": json_str}


