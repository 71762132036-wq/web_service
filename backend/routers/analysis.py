"""
Analysis router — key metrics, vol surface, and data table.
Routes:
  GET /api/metrics/{index}
  GET /api/vol-surface/{index}
  GET /api/data-table/{index}
"""

from fastapi import APIRouter, HTTPException

import store
from core.config import GAMMA_CAGE_WIDTH, INDICES
from services.calculations import (
    calculate_flip_point,
    calculate_vol_surface,
    calculate_quant_power,
    get_atm_strike,
    get_dealer_regime,
    get_gamma_cage,
    get_power_zones,
)

router = APIRouter(prefix="/api", tags=["analysis"])


def _require_data(index: str):
    if index not in INDICES:
        raise HTTPException(status_code=404, detail=f"Unknown index: {index}")
    if not store.has_data(index):
        raise HTTPException(status_code=404, detail="No data loaded for this index")
    return store.get_data(index)


# ---------------------------------------------------------------------------
# Key Metrics
# ---------------------------------------------------------------------------

@router.get("/metrics/{index}")
def get_metrics(index: str):
    """Return key metrics: spot, ATM, flip point, regime, gamma cage, power zones."""
    df = _require_data(index)

    spot        = float(df["Spot"].iloc[0])
    atm         = float(get_atm_strike(df))
    flip        = float(calculate_flip_point(df))
    regime       = get_dealer_regime(spot, flip)
    cage, vacuum = get_gamma_cage(df, atm, GAMMA_CAGE_WIDTH)
    power_zones  = [float(p) for p in get_power_zones(df, top_n=3)]
    
    try:
        qp_data = calculate_quant_power(df, spot)
        qp_strike = qp_data["quant_power"]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Quant Power error: {exc}") from exc

    return {
        "index":       index,
        "spot":        spot,
        "atm":         atm,
        "flip_point":  flip,
        "regime":      regime,
        "quant_power": qp_strike,
        "cage": {
            "low":   atm - GAMMA_CAGE_WIDTH * 50,
            "high":  atm + GAMMA_CAGE_WIDTH * 50,
            "size":  len(cage),
        },
        "vacuum_size": len(vacuum),
        "power_zones": power_zones,
        "filepath":    store.get_filepath(index),
    }


# ---------------------------------------------------------------------------
# Volatility Surface
# ---------------------------------------------------------------------------

@router.get("/vol-surface/{index}")
def get_vol_surface(index: str):
    """Return 25d RR, 10d BF, and related IV metrics."""
    df = _require_data(index)

    try:
        vs = calculate_vol_surface(df)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Vol surface error: {exc}") from exc

    return {"index": index, "vol_surface": vs}


# ---------------------------------------------------------------------------
# Data Table
# ---------------------------------------------------------------------------

DISPLAY_COLS = [
    "Strike", "Spot", "Call_OI", "Put_OI",
    "call_iv", "put_iv", "call_delta", "put_delta",
    "Total_GEX", "Abs_GEX",
]


@router.get("/data-table/{index}")
def get_data_table(index: str, limit: int = 40):
    """Return the data table rows as JSON (up to limit rows)."""
    df = _require_data(index)

    available = [c for c in DISPLAY_COLS if c in df.columns]
    subset = df[available].head(limit)

    return {
        "index":   index,
        "columns": available,
        "rows":    subset.to_dict(orient="records"),
        "total":   len(df),
    }


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

@router.get("/stats/{index}")
def get_stats(index: str):
    """Return describe() statistics for the loaded DataFrame."""
    df = _require_data(index)

    stats = df.describe().round(4).to_dict()
    return {
        "index":       index,
        "stats":       stats,
        "total_rows":  len(df),
        "expiry":      str(df["expiry"].iloc[0]) if "expiry" in df.columns else "",
        "spot":        float(df["Spot"].iloc[0]) if "Spot" in df.columns else 0,
        "columns":     list(df.columns),
    }
