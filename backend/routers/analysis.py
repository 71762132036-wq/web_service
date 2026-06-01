"""
Analysis router — key metrics, vol surface, and data table.
Routes:
  GET /api/metrics/{index}
  GET /api/vol-surface/{index}
  GET /api/data-table/{index}
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException

import store
from core.config import GAMMA_CAGE_WIDTH, INDICES, STOCKS
from services.calculations import (
    calculate_flip_point,
    calculate_vol_surface,
    calculate_quant_power,
    calculate_gex,
    calculate_delta_exposure,
    get_atm_strike,
    get_dealer_regime,
    get_gamma_cage,
    get_power_zones,
    calculate_realized_vol,
    calculate_dealer_reflexivity,
    calculate_liquidity_profile,
    calculate_gex_stickiness,
    calculate_delta_neutral_apex,
    calculate_gamma_concentration,
    calculate_gamma_density_profile,
    calculate_cum_gex_steepness,
    calculate_max_pain,
    calculate_gamma_adjusted_range,
    calculate_pcr_volume,
    calculate_system_gamma_score,
)
from services.historical_service import get_level_migration, get_historical_prices
from services.signal_engine import compute_signals

router = APIRouter(prefix="/api", tags=["analysis"])


def _require_data(index: str):
    # accept both indices and stocks
    if index not in {**INDICES, **STOCKS}:
        raise HTTPException(status_code=404, detail=f"Unknown index: {index}")
    
    import store
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

    try:
        pain = calculate_max_pain(df)
        max_pain_strike = pain["max_pain_strike"]
        pin_risk = pain["pin_risk_score"]
        pin_label = pain["pin_label"]
    except Exception:
        max_pain_strike = 0
        pin_risk = 0
        pin_label = ""

    try:
        pcr = calculate_pcr_volume(df)
    except Exception:
        pcr = {"pcr_volume": 0, "pcr_oi": 0}

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
        "cum_gex":     float(df["Total_GEX"].sum()) if "Total_GEX" in df.columns else 0.0,
        "cum_dex":     float(calculate_delta_exposure(df).Total_DEX.sum()) if "Spot" in df.columns else 0.0,
        "max_pain":    max_pain_strike,
        "pin_risk":    pin_risk,
        "pin_label":   pin_label,
        "pcr_volume":  pcr.get("pcr_volume", 0),
        "pcr_oi":      pcr.get("pcr_oi", 0),
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

# ---------------------------------------------------------------------------
# Advanced Analytics Suite
# ---------------------------------------------------------------------------

@router.get("/migration/{index}")
def get_migration(index: str, expiry: Optional[str] = None):
    """Return historical trajectory of key levels."""
    # If no expiry provided, use the one from the active store
    df = _require_data(index)
    if not expiry and "expiry" in df.columns:
        expiry = str(df["expiry"].iloc[0])
    
    if not expiry:
        raise HTTPException(status_code=400, detail="Expiry date required for migration analysis")

    data = get_level_migration(index, expiry)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    
    return data

@router.get("/vol-spread/{index}")
def get_vol_spread(index: str):
    """Return Realized vs Implied Volatility spread."""
    df = _require_data(index)
    spot = df["Spot"].iloc[0]
    expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
    
    # 1. Get Implied Vol (ATM)
    vs = calculate_vol_surface(df)
    iv = vs["ATM_IV"]
    
    # 2. Get Realized Vol (Historical Series)
    prices = get_historical_prices(index, expiry) if expiry else []
    rv = calculate_realized_vol(prices)
    
    return {
        "index": index,
        "iv": round(iv, 2),
        "rv": round(rv, 2),
        "spread": round(iv - rv, 2),
        "sentiment": "Oversold Vol" if iv < rv else "Overpriced Vol (Premium Harvesting)"
    }

@router.get("/god-tier-metrics/{index}")
def get_god_tier_metrics(index: str):
    """Return Dealer Reflexivity, Liquidity Profile, and GEX Stickiness."""
    df = _require_data(index)
    spot = float(df["Spot"].iloc[0])
    
    # 1. Dealer Reflexivity
    # Check lot size
    lot_size = 75
    if index in INDICES:
        lot_size = INDICES[index]["lot_size"]
    elif index in STOCKS:
        lot_size = STOCKS[index].get("lot_size", 1)
        
    reflexivity = calculate_dealer_reflexivity(df, spot, lot_size=lot_size)
    
    # 2. Liquidity Profile
    liquidity = calculate_liquidity_profile(df)
    
    # 3. GEX Stickiness (Top 10 levels)
    sticky_df = calculate_gex_stickiness(df)
    top_sticky = sticky_df.sort_values("stickiness", ascending=False).head(10)[["Strike", "stickiness", "total_vol"]].to_dict(orient="records")
    
    # 4. Delta Apex (Equilibrium)
    apex = calculate_delta_neutral_apex(df, spot, lot_size=lot_size)
    
    # 5. Gamma Concentration (Sharpness)
    conc = calculate_gamma_concentration(df)
    
    return {
        "index": index,
        "reflexivity": reflexivity,
        "liquidity": liquidity,
        "stickiness": top_sticky,
        "apex": {
            "price": apex["apex_price"],
            "distance_pct": apex["distance_to_apex_pct"]
        },
        "concentration": {
            "index": conc.get("concentration_index", 0),
            "top_pct": conc.get("top_strike_pct", 0),
            "is_sharp": conc.get("is_sharp", False)
        },
        "density": calculate_gamma_density_profile(df, spot, lot_size=lot_size),
        "steepness": calculate_cum_gex_steepness(df, spot),
    }


# ---------------------------------------------------------------------------
# Max Pain & Pin Risk
# ---------------------------------------------------------------------------

@router.get("/max-pain/{index}")
def get_max_pain(index: str):
    """Return max pain strike, pin risk score, and pain profile."""
    df = _require_data(index)
    return calculate_max_pain(df)


# ---------------------------------------------------------------------------
# Gamma-Adjusted Expected Range
# ---------------------------------------------------------------------------

@router.get("/gamma-range/{index}")
def get_gamma_range(index: str):
    """Return gamma-adjusted expected move vs straddle-implied move."""
    df = _require_data(index)
    lot_size = 75
    if index in INDICES:
        lot_size = INDICES[index]["lot_size"]
    elif index in STOCKS:
        lot_size = STOCKS[index].get("lot_size", 1)
    return calculate_gamma_adjusted_range(df, lot_size=lot_size)


# ---------------------------------------------------------------------------
# PCR Volume vs OI
# ---------------------------------------------------------------------------

@router.get("/pcr/{index}")
def get_pcr(index: str):
    """Return put-call ratio by volume and OI with divergence."""
    df = _require_data(index)
    return calculate_pcr_volume(df)


# ---------------------------------------------------------------------------
# System Gamma Score (Cross-Index)
# ---------------------------------------------------------------------------

@router.get("/system-gamma")
def get_system_gamma():
    """Return cross-index gamma regime correlation."""
    import store
    data_map = {}
    for idx_name in ["Nifty", "BankNifty", "Sensex"]:
        if store.has_data(idx_name):
            data_map[idx_name] = store.get_data(idx_name)
    if not data_map:
        return {"system_score": 0, "label": "No Data", "indices": {}}
    return calculate_system_gamma_score(data_map)


# ---------------------------------------------------------------------------
# FII / Participant Data
# ---------------------------------------------------------------------------

@router.get("/participants")
def get_participants():
    """Return FII/Client/Pro positioning summary."""
    from services.participant_service import get_participant_summary
    return get_participant_summary(last_n_days=20)


@router.get("/fii-alignment/{index}")
def get_fii_alignment(index: str):
    """Return FII positioning vs gamma regime alignment."""
    df = _require_data(index)
    from services.participant_service import get_fii_gamma_correlation
    spot = float(df["Spot"].iloc[0])
    flip = float(calculate_flip_point(df))
    gamma_regime = 1 if spot > flip else -1
    return get_fii_gamma_correlation(gamma_regime, flip, spot)


# ---------------------------------------------------------------------------
# Signal Engine — Move Imminent Detection
# ---------------------------------------------------------------------------

@router.get("/signals/{index}")
def get_signals(index: str):
    """Return composite signal score and all 5 sub-signals."""
    df = _require_data(index)
    expiry = str(df["expiry"].iloc[0]) if "expiry" in df.columns else None
    if not expiry:
        raise HTTPException(status_code=400, detail="Expiry required for signal analysis")
    return compute_signals(index, expiry)
