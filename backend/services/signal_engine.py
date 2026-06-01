"""
Signal Engine — computes the 5 intraday signals that predict moves before they happen.

Signals:
  1. Flip Proximity + Velocity  (regime break detector)
  2. Wall Decay                 (live vs ghost wall health)
  3. IV-Spot Divergence          (smart money tell)
  4. OI Buildup Asymmetry        (directional trigger)
  5. Delta Acceleration          (cascade / feedback loop detector)

Composite: "Move Imminent" score (0–100) + directional bias.

All signals are computed from the intraday snapshot history (parquet files).
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

from core.config import DATA_DIR, INDICES, STOCKS
from services.upstox_service import load_data_file
from services.historical_service import _sort_parquet_files
from services.calculations import (
    calculate_flip_point,
    calculate_gex,
    calculate_delta_exposure,
    calculate_volume_weighted_gex,
    classify_oi_buildup,
    get_atm_strike,
)


def _get_intraday_files(index_name: str, expiry: str, n: int = 30) -> List[Path]:
    """Get the last N intraday snapshot files for today."""
    data_path = Path(DATA_DIR) / index_name / expiry
    if not data_path.exists():
        data_path = Path(DATA_DIR) / expiry
        if not data_path.exists():
            return []

    all_files = list(data_path.glob("*.parquet"))
    if not all_files:
        return []

    files = _sort_parquet_files(all_files, expiry)
    files = files[:n]
    files.reverse()
    return files


def _load_snapshots(files: List[Path], lot_size: int = 75) -> List[Dict[str, Any]]:
    """Load each file and extract key metrics per snapshot."""
    snapshots = []
    for f in files:
        df, error = load_data_file(str(f))
        if error or df is None or df.empty:
            continue
        try:
            spot = float(df["Spot"].iloc[0])
            df_gex = calculate_gex(df, lot_size=lot_size)
            flip = float(calculate_flip_point(df_gex))
            net_gex = float(df_gex["Total_GEX"].sum())

            df_dex = calculate_delta_exposure(df, lot_size=lot_size)
            net_delta = float(df_dex["Total_DEX"].sum())

            atm = float(get_atm_strike(df))
            atm_row = df.loc[(df["Strike"] - atm).abs().idxmin()]
            call_iv = float(atm_row.get("call_iv", 0) or 0)
            put_iv = float(atm_row.get("put_iv", 0) or 0)
            atm_iv = (call_iv + put_iv) / 2.0 if call_iv > 0 and put_iv > 0 else max(call_iv, put_iv)

            df_vw = calculate_volume_weighted_gex(df_gex, lot_size=lot_size)
            top3 = df_vw.nlargest(3, "Abs_GEX")
            wall_health = []
            for _, row in top3.iterrows():
                wall_health.append({
                    "strike": float(row["Strike"]),
                    "abs_gex": float(row["Abs_GEX"]),
                    "vwgex": float(row.get("VWGEX", 0)),
                    "vol_oi_ratio": float(row.get("vol_oi_ratio", 0)),
                })

            df_bu = classify_oi_buildup(df)
            call_buildups = df_bu["call_buildup"].value_counts().to_dict()
            put_buildups = df_bu["put_buildup"].value_counts().to_dict()

            parts = f.stem.split("_")
            time_str = parts[1] if len(parts) > 1 else "000000"
            time_label = f"{time_str[:2]}:{time_str[2:4]}"

            snapshots.append({
                "time": time_label,
                "file": f.name,
                "spot": spot,
                "flip": flip,
                "net_gex": net_gex,
                "net_delta": net_delta,
                "atm_iv": atm_iv,
                "call_iv": call_iv,
                "put_iv": put_iv,
                "wall_health": wall_health,
                "call_buildups": call_buildups,
                "put_buildups": put_buildups,
            })
        except Exception as e:
            logger.error("[SIGNAL] Skip %s: %s", f.name, e)
            continue

    return snapshots


# ---------------------------------------------------------------------------
# Signal 1: Flip Proximity + Velocity
# ---------------------------------------------------------------------------

def _signal_flip_proximity(snapshots: List[Dict]) -> Dict[str, Any]:
    if len(snapshots) < 2:
        return {"score": 0, "proximity_pct": 0, "velocity": 0, "label": "INSUFFICIENT DATA"}

    latest = snapshots[-1]
    spot, flip = latest["spot"], latest["flip"]
    proximity_pct = abs(spot - flip) / spot * 100

    distances = [abs(s["spot"] - s["flip"]) / s["spot"] * 100 for s in snapshots]
    if len(distances) >= 3:
        velocity = distances[-3] - distances[-1]
    else:
        velocity = distances[0] - distances[-1]

    score = 0
    if proximity_pct < 0.15:
        score = 30
    elif proximity_pct < 0.3:
        score = 20
    elif proximity_pct < 0.5:
        score = 10

    if velocity > 0.1:
        score = min(30, score + 10)

    if score >= 25:
        label = "REGIME BREAK IMMINENT"
    elif score >= 15:
        label = "APPROACHING FLIP"
    else:
        label = "STABLE"

    return {
        "score": score,
        "proximity_pct": round(proximity_pct, 3),
        "velocity": round(velocity, 4),
        "spot": spot,
        "flip": flip,
        "side": "ABOVE" if spot > flip else "BELOW",
        "label": label,
        "history": [{"time": s["time"], "distance_pct": round(abs(s["spot"] - s["flip"]) / s["spot"] * 100, 3)} for s in snapshots],
    }


# ---------------------------------------------------------------------------
# Signal 2: Wall Decay (Live vs Ghost)
# ---------------------------------------------------------------------------

def _signal_wall_decay(snapshots: List[Dict]) -> Dict[str, Any]:
    if len(snapshots) < 3:
        return {"score": 0, "walls": [], "label": "INSUFFICIENT DATA"}

    latest_walls = snapshots[-1]["wall_health"]
    if not latest_walls:
        return {"score": 0, "walls": [], "label": "NO WALLS"}

    wall_tracking = []
    for wall in latest_walls:
        strike = wall["strike"]
        ratios = []
        for s in snapshots:
            for w in s["wall_health"]:
                if w["strike"] == strike:
                    ratios.append(w["vol_oi_ratio"])
                    break

        if len(ratios) >= 3:
            trend = ratios[-1] - ratios[-3]
        elif len(ratios) >= 2:
            trend = ratios[-1] - ratios[0]
        else:
            trend = 0

        is_dying = trend < -0.05 and ratios[-1] < 0.3 if ratios else False

        wall_tracking.append({
            "strike": strike,
            "abs_gex": wall["abs_gex"],
            "current_vol_oi": wall["vol_oi_ratio"],
            "vol_oi_trend": round(trend, 4),
            "status": "GHOST (Dying)" if is_dying else ("LIVE (Defended)" if ratios and ratios[-1] > 0.5 else "WEAK"),
            "is_dying": is_dying,
        })

    dying_count = sum(1 for w in wall_tracking if w["is_dying"])
    score = dying_count * 10

    if dying_count >= 2:
        label = "WALLS COLLAPSING"
    elif dying_count == 1:
        label = "WALL WEAKENING"
    else:
        label = "WALLS INTACT"

    return {
        "score": min(20, score),
        "walls": wall_tracking,
        "label": label,
    }


# ---------------------------------------------------------------------------
# Signal 3: IV-Spot Divergence
# ---------------------------------------------------------------------------

def _signal_iv_divergence(snapshots: List[Dict]) -> Dict[str, Any]:
    if len(snapshots) < 5:
        return {"score": 0, "iv_roc": 0, "spot_roc": 0, "divergence": 0, "label": "INSUFFICIENT DATA"}

    recent = snapshots[-5:]
    ivs = [s["atm_iv"] for s in recent]
    spots = [s["spot"] for s in recent]

    iv_roc = (ivs[-1] - ivs[0]) / max(ivs[0], 0.01) * 100
    spot_roc = (spots[-1] - spots[0]) / spots[0] * 100

    iv_direction = 1 if iv_roc > 0.5 else (-1 if iv_roc < -0.5 else 0)
    spot_direction = 1 if spot_roc > 0.1 else (-1 if spot_roc < -0.1 else 0)

    diverging = (iv_direction != 0 and spot_direction != 0 and iv_direction != spot_direction)
    iv_leading = iv_direction != 0 and spot_direction == 0

    score = 0
    if diverging:
        score = 25
    elif iv_leading:
        score = 15

    if diverging:
        if iv_roc > 0:
            label = "IV UP + SPOT DOWN — Protection Buying (Drop Expected)"
        else:
            label = "IV DOWN + SPOT UP — Vol Selling Into Rally (Mean Reversion)"
    elif iv_leading:
        if iv_roc > 0:
            label = "IV RISING (Spot Flat) — Smart Money Hedging"
        else:
            label = "IV FALLING (Spot Flat) — Vol Compression"
    else:
        label = "NO DIVERGENCE"

    return {
        "score": score,
        "iv_roc": round(iv_roc, 3),
        "spot_roc": round(spot_roc, 3),
        "divergence": round(iv_roc - spot_roc, 3),
        "iv_direction": "UP" if iv_direction > 0 else ("DOWN" if iv_direction < 0 else "FLAT"),
        "spot_direction": "UP" if spot_direction > 0 else ("DOWN" if spot_direction < 0 else "FLAT"),
        "label": label,
        "history": [{"time": s["time"], "iv": round(s["atm_iv"], 2), "spot": s["spot"]} for s in snapshots],
    }


# ---------------------------------------------------------------------------
# Signal 4: OI Buildup Asymmetry
# ---------------------------------------------------------------------------

def _signal_oi_asymmetry(snapshots: List[Dict]) -> Dict[str, Any]:
    if not snapshots:
        return {"score": 0, "call_dominant": "", "put_dominant": "", "label": "INSUFFICIENT DATA"}

    latest = snapshots[-1]
    cb = latest["call_buildups"]
    pb = latest["put_buildups"]

    total_call = sum(cb.values()) or 1
    total_put = sum(pb.values()) or 1

    call_unwinding_pct = (cb.get("Long Unwinding", 0) + cb.get("Short Covering", 0)) / total_call * 100
    put_unwinding_pct = (pb.get("Long Unwinding", 0) + pb.get("Short Covering", 0)) / total_put * 100

    call_buildup_pct = (cb.get("Long Buildup", 0) + cb.get("Short Buildup", 0)) / total_call * 100
    put_buildup_pct = (pb.get("Long Buildup", 0) + pb.get("Short Buildup", 0)) / total_put * 100

    call_dominant = max(cb, key=cb.get) if cb else "N/A"
    put_dominant = max(pb, key=pb.get) if pb else "N/A"

    score = 0
    direction = "NEUTRAL"

    if call_unwinding_pct > 60 and put_buildup_pct > 60:
        score = 15
        direction = "BULLISH"
        label = "CALL UNWINDING + PUT BUILDUP — Rally Signal"
    elif put_unwinding_pct > 60 and call_buildup_pct > 60:
        score = 15
        direction = "BEARISH"
        label = "PUT UNWINDING + CALL BUILDUP — Drop Signal"
    elif call_unwinding_pct > 50:
        score = 8
        direction = "BULLISH"
        label = "CALLS CAPITULATING — Support Building"
    elif put_unwinding_pct > 50:
        score = 8
        direction = "BEARISH"
        label = "PUTS CAPITULATING — Resistance Building"
    else:
        label = "BALANCED — No Asymmetry"

    return {
        "score": score,
        "call_dominant": call_dominant,
        "put_dominant": put_dominant,
        "call_unwinding_pct": round(call_unwinding_pct, 1),
        "put_unwinding_pct": round(put_unwinding_pct, 1),
        "direction": direction,
        "label": label,
        "breakdown": {
            "calls": cb,
            "puts": pb,
        },
    }


# ---------------------------------------------------------------------------
# Signal 5: Delta Acceleration
# ---------------------------------------------------------------------------

def _signal_delta_acceleration(snapshots: List[Dict]) -> Dict[str, Any]:
    if len(snapshots) < 4:
        return {"score": 0, "acceleration": 0, "velocity": 0, "label": "INSUFFICIENT DATA"}

    deltas = [s["net_delta"] for s in snapshots]

    velocities = [deltas[i] - deltas[i - 1] for i in range(1, len(deltas))]
    accelerations = [velocities[i] - velocities[i - 1] for i in range(1, len(velocities))]

    current_velocity = velocities[-1] if velocities else 0
    current_acceleration = accelerations[-1] if accelerations else 0

    avg_abs_velocity = np.mean([abs(v) for v in velocities]) if velocities else 1
    normalized_accel = abs(current_acceleration) / max(avg_abs_velocity, 1)

    score = 0
    if normalized_accel > 2.0:
        score = 10
    elif normalized_accel > 1.5:
        score = 5

    if score >= 8:
        label = "FEEDBACK LOOP — Dealer Cascade Active"
    elif score >= 4:
        label = "ELEVATED ACCELERATION"
    else:
        label = "NORMAL"

    return {
        "score": score,
        "velocity": float(current_velocity),
        "acceleration": float(current_acceleration),
        "normalized_accel": round(float(normalized_accel), 3),
        "label": label,
        "history": [{"time": s["time"], "net_delta": s["net_delta"]} for s in snapshots],
    }


# ---------------------------------------------------------------------------
# Composite Score
# ---------------------------------------------------------------------------

def compute_signals(index_name: str, expiry: str) -> Dict[str, Any]:
    """Main entry point — computes all 5 signals + composite score."""
    all_instruments = {**INDICES, **STOCKS}
    cfg = all_instruments.get(index_name, {})
    lot_size = cfg.get("lot_size", 75)

    files = _get_intraday_files(index_name, expiry, n=30)
    if not files:
        return {"error": "No intraday snapshots found", "composite_score": 0}

    snapshots = _load_snapshots(files, lot_size=lot_size)
    if len(snapshots) < 2:
        return {"error": "Need at least 2 snapshots for signal analysis", "composite_score": 0}

    sig1 = _signal_flip_proximity(snapshots)
    sig2 = _signal_wall_decay(snapshots)
    sig3 = _signal_iv_divergence(snapshots)
    sig4 = _signal_oi_asymmetry(snapshots)
    sig5 = _signal_delta_acceleration(snapshots)

    composite = sig1["score"] + sig2["score"] + sig3["score"] + sig4["score"] + sig5["score"]
    composite = min(100, composite)

    direction_votes = []
    if sig1["score"] >= 15:
        direction_votes.append("ABOVE" if sig1.get("side") == "ABOVE" else "BELOW")
    if sig4["score"] >= 8:
        direction_votes.append(sig4.get("direction", "NEUTRAL"))
    if sig3["score"] >= 15:
        if "Drop" in sig3.get("label", ""):
            direction_votes.append("BEARISH")
        elif "Rally" in sig3.get("label", "") or "Mean Reversion" in sig3.get("label", ""):
            direction_votes.append("BULLISH")

    bullish = sum(1 for v in direction_votes if v in ("BULLISH", "ABOVE"))
    bearish = sum(1 for v in direction_votes if v in ("BEARISH", "BELOW"))

    if bullish > bearish:
        bias = "BULLISH"
    elif bearish > bullish:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    if composite >= 60:
        urgency = "MOVE IMMINENT"
    elif composite >= 40:
        urgency = "ELEVATED"
    elif composite >= 20:
        urgency = "WATCHLIST"
    else:
        urgency = "CALM"

    return {
        "index": index_name,
        "expiry": expiry,
        "snapshots_analyzed": len(snapshots),
        "latest_time": snapshots[-1]["time"] if snapshots else "",
        "composite_score": composite,
        "urgency": urgency,
        "directional_bias": bias,
        "signals": {
            "flip_proximity": sig1,
            "wall_decay": sig2,
            "iv_divergence": sig3,
            "oi_asymmetry": sig4,
            "delta_acceleration": sig5,
        },
    }
