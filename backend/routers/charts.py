"""
Charts router — returns Plotly JSON for interactive charts.
Route: GET /api/charts/{index}/{chart_type}

chart_type options:
  gex | regime | call_put | iv_smile | rr_bf
"""

from fastapi import APIRouter, HTTPException
import numpy as np
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

import json
import store
from core.config import INDICES, STOCKS, DATA_DIR
from services.upstox_service import load_data_file
from services.calculations import (
    calculate_vol_surface,
    calculate_delta_exposure,
    calculate_vanna_exposure,
    calculate_charm_exposure,
    calculate_iv_cone,
    calculate_vtl,
    calculate_cum_gex_steepness,
    calculate_gex,
    calculate_dealer_reflexivity,
    calculate_liquidity_profile,
    calculate_gex_stickiness,
    calculate_delta_neutral_apex,
    calculate_gamma_concentration,
    calculate_gamma_density_profile,
    calculate_bs_pricing,
    calculate_volume_weighted_gex,
    calculate_spread_heatmap,
    classify_oi_buildup,
    calculate_gex_decay,
    calculate_hedge_flow_simulation,
    calculate_max_pain,
    calculate_gamma_adjusted_range,
    calculate_pcr_volume,
    calculate_system_gamma_score,
    calculate_flip_point,
)
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
    build_migration_chart,
    build_ignition_heatmap,
    build_momentum_chart,
    build_vol_spread_chart,
    build_dealer_reflexivity_chart,
    build_liquidity_depth_chart,
    build_delta_apex_chart,
    build_gamma_profile_chart,
    build_gamma_density_chart,
    build_cum_steepness_chart,
    build_systemic_pulse_chart,
    build_aggregate_exposure_chart,
    build_stickiness_chart,
    build_intraday_iv_chart,
    build_vol_surface_3d_chart,
    build_bs_pricing_chart,
    build_intraday_oi_chart,
    build_vwgex_chart,
    build_spread_heatmap_chart,
    build_oi_buildup_chart,
    build_gex_decay_chart,
    build_hedge_flow_chart,
    build_max_pain_chart,
    build_gamma_adjusted_range_chart,
    build_participant_chart,
    build_fii_gamma_alignment_chart,
    build_pcr_comparison_chart,
    build_system_gamma_chart,
    build_flip_proximity_chart,
    build_wall_decay_chart,
    build_iv_divergence_chart,
    build_oi_asymmetry_chart,
    build_delta_acceleration_chart,
    build_composite_signal_chart,
    build_oi_heatmap_chart,
    build_strike_importance_chart,
    build_oi_evolution_chart,
    build_oi_lifecycle_chart,
    build_max_pain_migration_chart,
)
from services.signal_engine import compute_signals
from services.historical_service import (
    get_level_migration,
    get_historical_prices,
    get_flow_momentum,
    get_systemic_pulse,
    get_intraday_iv_tracker,
    get_vol_surface_history,
    get_intraday_oi_tracker,
    get_oi_heatmap,
    get_strike_importance,
    get_oi_evolution,
    get_oi_lifecycle,
    get_max_pain_migration,
)
from services.calculations import calculate_realized_vol, calculate_greek_sensitivity_grid
from services.flow_service import classify_option_flow

router = APIRouter(prefix="/api", tags=["charts"])

CHART_TYPES = {"gex", "dex", "vex", "cex", "cum_gex", "cum_dex", "cum_vex", "cum_cex", "regime", "iv_smile", "iv_cone", "rr_bf", "quant_power", "oi_dist", "oi_flow", "oi_change", "premium_flow", "compare_oi_change", "flow_intensity", "strike_pressure", "vtl", "migration", "vol_spread", "ignition", "momentum", "reflexivity", "liquidity", "stickiness", "apex", "gamma_profile", "gamma_density", "cum_steepness", "systemic_pulse", "total_gex", "total_dex", "iv_tracker", "vol_surface_3d", "gex_dex_combined", "bs_pricing", "oi_tracker", "vwgex", "spread_heatmap", "oi_buildup", "gex_decay", "hedge_flow", "max_pain", "gamma_range", "participant", "fii_alignment", "pcr_volume", "system_gamma", "sig_composite", "sig_flip", "sig_wall_decay", "sig_iv_divergence", "sig_oi_asymmetry", "sig_delta_accel", "oi_heatmap", "oi_importance", "oi_evolution", "oi_lifecycle", "max_pain_migration"}


@router.get("/charts/compare/{index}/{chart_type}")
def get_compare_chart(index: str, chart_type: str, expiry: str, file1: str, file2: str):
    """Compare two snapshots and return delta chart."""
    logger.info("[COMPARE] index=%s, type=%s, expiry=%s, f1=%s, f2=%s", index, chart_type, expiry, file1, file2)
    
    if index not in {**INDICES, **STOCKS}:
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
    
    logger.debug("[COMPARE] Final Path 1: %s", path_1)
    logger.debug("[COMPARE] Final Path 2: %s", path_2)
    
    if not path_1.exists() or not path_2.exists():
        msg = f"Data files not found. Searched: {path_1} and {path_2}"
        logger.error("[COMPARE] ERROR: %s", msg)
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
        logger.error("[COMPARE] Build error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Comparison error: {exc}")


@router.get("/charts/direction/{index}/{chart_type}")
def get_direction_chart(index: str, chart_type: str, expiry: str, file1: str, file2: str):
    """Directional flow analysis based on two snapshots."""
    from pathlib import Path
    
    if index not in {**INDICES, **STOCKS}:
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
    if index not in {**INDICES, **STOCKS}:
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
            cfg = {**INDICES, **STOCKS}.get(index, {})
            df_gex = calculate_gex(df, lot_size=cfg.get("lot_size", 75))
            json_str = build_gamma_chart(df_gex, index, mode=mode)
        elif chart_type == "dex":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            df_dex   = calculate_delta_exposure(df, lot_size=cfg.get("lot_size", 75))
            json_str = build_delta_chart(df_dex, index, mode=mode)
        elif chart_type == "cum_gex":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            df_gex = calculate_gex(df, lot_size=cfg.get("lot_size", 75))
            json_str = build_cumulative_gamma_chart(df_gex, index, mode=mode)
        elif chart_type == "cum_dex":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            df_dex   = calculate_delta_exposure(df, lot_size=cfg.get("lot_size", 75))
            json_str = build_cumulative_delta_chart(df_dex, index, mode=mode)
        elif chart_type == "vex":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            df_vex   = calculate_vanna_exposure(df, lot_size=cfg.get("lot_size", 75))
            json_str = build_vanna_chart(df_vex, index, mode=mode)
        elif chart_type == "cum_vex":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            df_vex   = calculate_vanna_exposure(df, lot_size=cfg.get("lot_size", 75))
            json_str = build_cumulative_vanna_chart(df_vex, index, mode=mode)
        elif chart_type == "cex":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            df_cex   = calculate_charm_exposure(df, lot_size=cfg.get("lot_size", 75))
            json_str = build_charm_chart(df_cex, index, mode=mode)
        elif chart_type == "cum_cex":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            df_cex   = calculate_charm_exposure(df, lot_size=cfg.get("lot_size", 75))
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
        elif chart_type == "migration":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            mig_data = get_level_migration(index, expiry)
            json_str = build_migration_chart(mig_data, index)
        elif chart_type == "vol_spread":
            spot = df["Spot"].iloc[0]
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            vs = calculate_vol_surface(df)
            prices = get_historical_prices(index, expiry) if expiry else []
            rv = calculate_realized_vol(prices)
            vol_data = {
                "iv": round(vs["ATM_IV"], 2),
                "rv": round(rv, 2),
                "spread": round(vs["ATM_IV"] - rv, 2),
                "sentiment": "Oversold Vol" if vs["ATM_IV"] < rv else "Overpriced Vol (Premium Harvesting)"
            }
            json_str = build_vol_spread_chart(vol_data, index)
        elif chart_type == "ignition":
            spot = df["Spot"].iloc[0]
            grid_data = calculate_greek_sensitivity_grid(df, spot)
            json_str = build_ignition_heatmap(grid_data, index)
        elif chart_type == "momentum":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            mom_data = get_flow_momentum(index, expiry)
            json_str = build_momentum_chart(mom_data, index)
        elif chart_type == "reflexivity":
            spot = df["Spot"].iloc[0]
            cfg = {**INDICES, **STOCKS}.get(index, {})
            lot_size = cfg.get("lot_size", 75)
            reflex_data = calculate_dealer_reflexivity(df, spot, lot_size=lot_size)
            json_str = build_dealer_reflexivity_chart(reflex_data, index)
        elif chart_type == "liquidity":
            liq_data = calculate_liquidity_profile(df)
            json_str = build_liquidity_depth_chart(liq_data, index)
        elif chart_type == "stickiness":
            sticky_df = calculate_gex_stickiness(df)
            json_str = build_stickiness_chart(sticky_df, index)
        elif chart_type == "apex":
            spot = df["Spot"].iloc[0]
            cfg = {**INDICES, **STOCKS}.get(index, {})
            lot_size = cfg.get("lot_size", 75)
            apex_data = calculate_delta_neutral_apex(df, spot, lot_size=lot_size)
            json_str = build_delta_apex_chart(apex_data, index)
        elif chart_type == "gamma_profile":
            conc_data = calculate_gamma_concentration(df)
            json_str = build_gamma_profile_chart(conc_data, index)
        elif chart_type == "gamma_density":
            spot = df["Spot"].iloc[0]
            cfg = {**INDICES, **STOCKS}.get(index, {})
            lot_size = cfg.get("lot_size", 75)
            density_data = calculate_gamma_density_profile(df, spot, lot_size=lot_size)
            json_str = build_gamma_density_chart(density_data, index)
        elif chart_type == "cum_steepness":
            spot = df["Spot"].iloc[0]
            steepness = calculate_cum_gex_steepness(df, spot)
            json_str = build_cum_steepness_chart(steepness, index)
        elif chart_type == "iv_tracker":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            
            filepath = store.get_filepath(index)
            filter_day = None
            if filepath:
                filename = Path(filepath).name
                if "_" in filename:
                    filter_day = filename.split("_")[0]
            
            iv_data = get_intraday_iv_tracker(index, expiry, filter_day=filter_day)
            json_str = build_intraday_iv_chart(iv_data, index)
        elif chart_type == "vol_surface_3d":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            filepath = store.get_filepath(index)
            filter_day = filename.split("_")[0] if filepath and "_" in (filename := Path(filepath).name) else None
            iv_data = get_vol_surface_history(index, expiry, filter_day=filter_day)
            json_str = build_vol_surface_3d_chart(iv_data, index)
        elif chart_type == "systemic_pulse":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            
            # Extract day from current file path if possible
            filepath = store.get_filepath(index)
            filter_day = None
            if filepath:
                filename = Path(filepath).name
                if "_" in filename:
                    filter_day = filename.split("_")[0] # e.g. "19"
                    
            pulse_data = get_systemic_pulse(index, expiry, filter_day=filter_day)
            json_str = build_systemic_pulse_chart(pulse_data, index)
        elif chart_type in ["total_gex", "total_dex"]:
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            filepath = store.get_filepath(index)
            filter_day = filename.split("_")[0] if filepath and "_" in (filename := Path(filepath).name) else None
            pulse_data = get_systemic_pulse(index, expiry, filter_day=filter_day)
            exposure_type = "GEX" if chart_type == "total_gex" else "DEX"
            json_str = build_aggregate_exposure_chart(pulse_data, index, chart_type=exposure_type)
        elif chart_type == "oi_tracker":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            
            filepath = store.get_filepath(index)
            filter_day = None
            if filepath:
                filename = Path(filepath).name
                if "_" in filename:
                    filter_day = filename.split("_")[0]
            
            oi_data = get_intraday_oi_tracker(index, expiry, filter_day=filter_day)
            json_str = build_intraday_oi_chart(oi_data, index, mode=mode)
        elif chart_type == "bs_pricing":
            df_bs = calculate_bs_pricing(df)
            json_str = build_bs_pricing_chart(df_bs, index)
        elif chart_type == "vwgex":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            lot_size = cfg.get("lot_size", 75)
            df_vw = calculate_volume_weighted_gex(df, lot_size=lot_size)
            json_str = build_vwgex_chart(df_vw, index, mode=mode)
        elif chart_type == "spread_heatmap":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            lot_size = cfg.get("lot_size", 75)
            df_gex = calculate_gex(df, lot_size=lot_size)
            spread_data = calculate_spread_heatmap(df_gex)
            json_str = build_spread_heatmap_chart(spread_data, index)
        elif chart_type == "oi_buildup":
            df_bu = classify_oi_buildup(df)
            json_str = build_oi_buildup_chart(df_bu, index)
        elif chart_type == "gex_decay":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            lot_size = cfg.get("lot_size", 75)
            df_decay = calculate_gex_decay(df, lot_size=lot_size)
            json_str = build_gex_decay_chart(df_decay, index)
        elif chart_type == "hedge_flow":
            spot = df["Spot"].iloc[0]
            cfg = {**INDICES, **STOCKS}.get(index, {})
            lot_size = cfg.get("lot_size", 75)
            sim_data = calculate_hedge_flow_simulation(df, spot, lot_size=lot_size)
            json_str = build_hedge_flow_chart(sim_data, index)
        elif chart_type == "max_pain":
            pain_data = calculate_max_pain(df)
            json_str = build_max_pain_chart(pain_data, index)
            return {
                "index": index,
                "chart_type": chart_type,
                "figure": json_str if not isinstance(json_str, dict) else json.dumps(json_str, default=lambda o: float(o) if isinstance(o, (np.integer, np.floating)) else o),
                "summary": {
                    "max_pain": pain_data["max_pain_strike"],
                    "pin_risk": pain_data["pin_risk_score"],
                    "pin_label": pain_data["pin_label"],
                    "distance_pct": pain_data["distance_pct"],
                }
            }
        elif chart_type == "gamma_range":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            lot_size = cfg.get("lot_size", 75)
            range_data = calculate_gamma_adjusted_range(df, lot_size=lot_size)
            json_str = build_gamma_adjusted_range_chart(range_data, index)
            return {
                "index": index,
                "chart_type": chart_type,
                "figure": json_str if not isinstance(json_str, dict) else json.dumps(json_str, default=lambda o: float(o) if isinstance(o, (np.integer, np.floating)) else o),
                "summary": {
                    "implied_move": range_data["implied_move_pct"],
                    "adjusted_move": range_data["adjusted_move_pct"],
                    "gamma_multiplier": range_data["gamma_multiplier"],
                    "regime": range_data["regime"],
                }
            }
        elif chart_type == "participant":
            from services.participant_service import get_participant_summary
            participant_data = get_participant_summary(last_n_days=20)
            json_str = build_participant_chart(participant_data, index)
        elif chart_type == "fii_alignment":
            from services.participant_service import get_fii_gamma_correlation
            spot = df["Spot"].iloc[0]
            flip = calculate_flip_point(df)
            gamma_regime = 1 if spot > flip else -1
            alignment = get_fii_gamma_correlation(gamma_regime, flip, spot)
            json_str = build_fii_gamma_alignment_chart(alignment, index)
        elif chart_type == "pcr_volume":
            pcr_data = calculate_pcr_volume(df)
            json_str = build_pcr_comparison_chart(pcr_data, index)
        elif chart_type == "system_gamma":
            data_map = {}
            for idx_name in ["Nifty", "BankNifty", "Sensex"]:
                if store.has_data(idx_name):
                    data_map[idx_name] = store.get_data(idx_name)
            system_data = calculate_system_gamma_score(data_map)
            json_str = build_system_gamma_chart(system_data)
        elif chart_type.startswith("sig_"):
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry:
                raise HTTPException(status_code=400, detail="Expiry required for signals")
            sig_data = compute_signals(index, str(expiry))
            if "error" in sig_data:
                raise HTTPException(status_code=404, detail=sig_data["error"])
            chart_builders = {
                "sig_composite": build_composite_signal_chart,
                "sig_flip": build_flip_proximity_chart,
                "sig_wall_decay": build_wall_decay_chart,
                "sig_iv_divergence": build_iv_divergence_chart,
                "sig_oi_asymmetry": build_oi_asymmetry_chart,
                "sig_delta_accel": build_delta_acceleration_chart,
            }
            builder = chart_builders[chart_type]
            json_str = builder(sig_data, index)
            if chart_type == "sig_composite":
                return {
                    "index": index,
                    "chart_type": chart_type,
                    "figure": json_str if not isinstance(json_str, dict) else json.dumps(json_str, default=lambda o: float(o) if isinstance(o, (np.integer, np.floating)) else o),
                    "summary": {
                        "composite_score": sig_data.get("composite_score", 0),
                        "urgency": sig_data.get("urgency", ""),
                        "bias": sig_data.get("directional_bias", ""),
                        "snapshots": sig_data.get("snapshots_analyzed", 0),
                    }
                }
        elif chart_type == "oi_heatmap":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            heatmap_data = get_oi_heatmap(index, expiry)
            json_str = build_oi_heatmap_chart(heatmap_data, index, mode=mode)
        elif chart_type == "oi_importance":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            importance_data = get_strike_importance(index, expiry)
            json_str = build_strike_importance_chart(importance_data, index, mode=mode)
            return {
                "index": index, "chart_type": chart_type,
                "figure": json.dumps(json_str, default=lambda o: float(o) if isinstance(o, (np.integer, np.floating)) else o) if isinstance(json_str, dict) else json_str,
                "summary": {
                    "top_call_strike": importance_data["call_ranking"][0]["strike"] if importance_data.get("call_ranking") else None,
                    "top_put_strike": importance_data["put_ranking"][0]["strike"] if importance_data.get("put_ranking") else None,
                    "snapshots": importance_data.get("total_snapshots", 0),
                }
            }
        elif chart_type == "oi_evolution":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            evo_data = get_oi_evolution(index, expiry)
            json_str = build_oi_evolution_chart(evo_data, index)
        elif chart_type == "oi_lifecycle":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            lifecycle_data = get_oi_lifecycle(index, expiry)
            json_str = build_oi_lifecycle_chart(lifecycle_data, index)
        elif chart_type == "max_pain_migration":
            expiry = df["expiry"].iloc[0] if "expiry" in df.columns else None
            if not expiry: raise HTTPException(status_code=400, detail="Expiry not found")
            migration_data = get_max_pain_migration(index, expiry)
            json_str = build_max_pain_migration_chart(migration_data, index)
            latest = migration_data.get("history", [{}])[-1]
            return {
                "index": index, "chart_type": chart_type,
                "figure": json.dumps(json_str, default=lambda o: float(o) if isinstance(o, (np.integer, np.floating)) else o) if isinstance(json_str, dict) else json_str,
                "summary": {
                    "current_max_pain": latest.get("max_pain"),
                    "distance_pct": latest.get("distance_pct"),
                }
            }
        elif chart_type == "gex_dex_combined":
            cfg = {**INDICES, **STOCKS}.get(index, {})
            lot_size = cfg.get("lot_size", 75)
            spot = float(df["Spot"].iloc[0])

            today = pd.Timestamp("today").normalize()
            expiry_date = pd.to_datetime(df["expiry"].iloc[0], format="%Y-%m-%d")
            T_days = (expiry_date - today).days
            T = max(T_days / 365.0, 1.0 / 365.0)

            chain = df.groupby("Strike").agg({
                "call_iv": "first",
                "put_iv": "first",
                "Call_OI": "sum",
                "Put_OI": "sum",
            }).sort_index().reset_index()

            return {
                "index": index,
                "chart_type": chart_type,
                "figure": None,
                "data": {
                    "strikes": chain["Strike"].tolist(),
                    "call_iv": chain["call_iv"].fillna(0).tolist(),
                    "put_iv": chain["put_iv"].fillna(0).tolist(),
                    "call_oi": chain["Call_OI"].fillna(0).astype(int).tolist(),
                    "put_oi": chain["Put_OI"].fillna(0).astype(int).tolist(),
                    "spot": spot,
                    "lot_size": lot_size,
                    "T": T,
                    "r": 0.05,
                }
            }

    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Chart error: {exc}") from exc
    # Explicitly serialize the figure to JSON on the backend to avoid 
    # FastAPI's encoder potentially failing on complex Plotly dicts.
    if isinstance(json_str, dict):
        # We can use Plotly's JSON encoder if it was a Figure, 
        # but here we already have a dict or string.
        # But wait, json_str might have been from fig.to_dict().
        # Let's just use standard json.dumps for the dict form.
        def npy_encoder(obj):
            if isinstance(obj, (np.integer, np.floating)): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            return obj
        json_str = json.dumps(json_str, default=npy_encoder)

    return {"index": index, "chart_type": chart_type, "figure": json_str}


