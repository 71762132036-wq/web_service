"""
Charts router — returns Plotly JSON for interactive charts.
Route: GET /api/charts/{index}/{chart_type}

chart_type options:
  gex | regime | call_put | iv_smile | rr_bf
"""

from fastapi import APIRouter, HTTPException

import store
from core.config import INDICES
from services.calculations import calculate_vol_surface, calculate_delta_exposure
from services.chart_service import (
    build_dealer_regime_map,
    build_gamma_chart,
    build_delta_chart,
    build_cumulative_delta_chart,
    build_cumulative_gamma_chart,
    build_iv_smile,
    build_rr_bf,
    build_quant_power_chart,
)

router = APIRouter(prefix="/api", tags=["charts"])

CHART_TYPES = {"gex", "dex", "cum_gex", "cum_dex", "regime", "iv_smile", "rr_bf", "quant_power"}


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
            json_str = build_gamma_chart(df, index, mode=mode)
        elif chart_type == "dex":
            df_dex   = calculate_delta_exposure(df)
            json_str = build_delta_chart(df_dex, index, mode=mode)
        elif chart_type == "cum_gex":
            json_str = build_cumulative_gamma_chart(df, index, mode=mode)
        elif chart_type == "cum_dex":
            df_dex   = calculate_delta_exposure(df)
            json_str = build_cumulative_delta_chart(df_dex, index, mode=mode)
        elif chart_type == "regime":
            json_str = build_dealer_regime_map(df, index)
        elif chart_type == "iv_smile":
            json_str = build_iv_smile(df)
        elif chart_type == "rr_bf":
            vs       = calculate_vol_surface(df)
            json_str = build_rr_bf(vs)
        elif chart_type == "quant_power":
            json_str = build_quant_power_chart(df, index)

    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Chart error: {exc}") from exc

    # Return as a plain string; the frontend will JSON.parse() it
    return {"index": index, "chart_type": chart_type, "figure": json_str}
