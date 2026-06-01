"""
Participant service — loads FII/DII/Client/Pro positioning data
from the external Cumulative_Participant_Wise_OI_Data.csv and
correlates it with gamma levels.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

PARTICIPANT_CSV = Path("D:/Investments/Participant_Wise_OI/OI_Data/Cumulative_Participant_Wise_OI_Data.csv")


def load_participant_data() -> Optional[pd.DataFrame]:
    """Load and parse the participant-wise OI CSV."""
    if not PARTICIPANT_CSV.exists():
        logger.warning("[PARTICIPANT] CSV not found at %s", PARTICIPANT_CSV)
        return None
    try:
        df = pd.read_csv(PARTICIPANT_CSV)
        df["Date"] = pd.to_datetime(df["Date"], format="%d-%m-%Y", dayfirst=True)
        df = df.sort_values("Date").reset_index(drop=True)
        return df
    except Exception as exc:
        logger.error("[PARTICIPANT] Failed to load CSV: %s", exc)
        return None


def get_participant_summary(last_n_days: int = 10) -> Dict[str, Any]:
    """
    Returns recent participant positioning summary:
    - FII net futures (long - short) and change
    - FII net options (call long - put long, call short - put short)
    - Client and Pro equivalents
    - Nifty close and change for correlation
    """
    df = load_participant_data()
    if df is None or df.empty:
        return {"error": "Participant data not available"}

    recent = df.tail(last_n_days).copy()

    def _net_futures(row, prefix):
        return row.get(f"{prefix}_Total_FutureIndex_Long", 0) - row.get(f"{prefix}_Total_FutureIndex_Short", 0)

    def _net_options_call(row, prefix):
        return row.get(f"{prefix}_Total_OptionIndexCall_Long", 0) - row.get(f"{prefix}_Total_OptionIndexCall_Short", 0)

    def _net_options_put(row, prefix):
        return row.get(f"{prefix}_Total_OptionIndexPut_Long", 0) - row.get(f"{prefix}_Total_OptionIndexPut_Short", 0)

    history = []
    for _, row in recent.iterrows():
        entry = {
            "date": row["Date"].strftime("%Y-%m-%d"),
            "nifty_close": float(row.get("Nifty Close", 0) or 0),
            "nifty_change": float(row.get("Nifty_Change", 0) or 0),
        }
        for prefix in ["FII", "Client", "Pro"]:
            entry[f"{prefix.lower()}_net_futures"] = float(_net_futures(row, prefix))
            entry[f"{prefix.lower()}_fut_chg"] = float(
                row.get(f"{prefix}_Change_FutureIndex_Long", 0) or 0
            ) - float(row.get(f"{prefix}_Change_FutureIndex_Short", 0) or 0)
            entry[f"{prefix.lower()}_net_call"] = float(_net_options_call(row, prefix))
            entry[f"{prefix.lower()}_net_put"] = float(_net_options_put(row, prefix))
        history.append(entry)

    latest = history[-1] if history else {}
    fii_bias = "BULLISH" if latest.get("fii_net_futures", 0) > 0 else "BEARISH"
    fii_option_bias = "BULLISH" if latest.get("fii_net_call", 0) > latest.get("fii_net_put", 0) else "BEARISH"

    return {
        "history": history,
        "latest": latest,
        "fii_futures_bias": fii_bias,
        "fii_options_bias": fii_option_bias,
        "data_points": len(history),
    }


def get_fii_gamma_correlation(gamma_regime: int, flip_point: float, spot: float) -> Dict[str, Any]:
    """
    Correlates FII positioning direction with gamma tilt.
    gamma_regime: +1 (positive gamma / above flip) or -1 (negative gamma / below flip)
    Returns alignment score and trade setup interpretation.
    """
    summary = get_participant_summary(last_n_days=5)
    if "error" in summary:
        return summary

    latest = summary.get("latest", {})
    fii_net_fut = latest.get("fii_net_futures", 0)
    fii_fut_chg = latest.get("fii_fut_chg", 0)

    fii_direction = 1 if fii_net_fut > 0 else -1
    fii_momentum = 1 if fii_fut_chg > 0 else -1

    alignment = fii_direction * gamma_regime
    momentum_alignment = fii_momentum * gamma_regime

    if alignment > 0 and momentum_alignment > 0:
        setup = "STRONG ALIGNMENT — FII and Gamma agree, high conviction setup"
        score = 1.0
    elif alignment > 0:
        setup = "PARTIAL ALIGNMENT — FII position agrees but momentum diverging"
        score = 0.5
    elif momentum_alignment > 0:
        setup = "MOMENTUM CONVERGENCE — FII building towards gamma direction"
        score = 0.3
    else:
        setup = "DIVERGENCE — FII vs Gamma disagree, mean-reversion likely"
        score = -0.5

    return {
        "fii_net_futures": float(fii_net_fut),
        "fii_futures_change": float(fii_fut_chg),
        "fii_direction": "Long" if fii_direction > 0 else "Short",
        "gamma_regime": "Positive" if gamma_regime > 0 else "Negative",
        "alignment_score": score,
        "setup": setup,
        "spot": float(spot),
        "flip_point": float(flip_point),
    }
