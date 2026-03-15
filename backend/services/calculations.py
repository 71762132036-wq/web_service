"""
Calculation service — GEX metrics, flip point, gamma cage, vol surface.
Ported from streamlit_app/modules/calculations.py
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
from typing import List, Dict, Any, Optional


# ---------------------------------------------------------------------------
# GEX
# ---------------------------------------------------------------------------

def calculate_gex(df: pd.DataFrame, lot_size: int = 75) -> pd.DataFrame:
    """
    Standard GEX calculation ($ per 1% move).
    Multiplier = lot_size * spot^2 * 0.01
    """
    df = df.copy()
    spot = df["Spot"].iloc[0] if "Spot" in df.columns else 1.0
    multiplier = lot_size * (spot ** 2) * 0.01
    
    df["Call_GEX"] = -df["call_gamma"] * df["Call_OI"] * multiplier
    df["Put_GEX"] = df["put_gamma"] * df["Put_OI"] * multiplier
    df["Total_GEX"] = df["Call_GEX"] + df["Put_GEX"]
    df["Abs_GEX"] = df["Total_GEX"].abs()
    return df


def calculate_vanna_exposure(df: pd.DataFrame, lot_size: int = 75) -> pd.DataFrame:
    """
    Dealer Vanna Exposure (VEX) calculation using vectorized operations.
    VEX = - (Vanna * OI * lot_size * spot * 0.01)
    """
    df = df.copy()
    spot = df["Spot"].iloc[0] if "Spot" in df.columns else 1.0
    r = 0.05
    today = pd.Timestamp("today").normalize()

    # Vectorized Time to Expiry (T)
    T_days = (pd.to_datetime(df["expiry"], format="%Y-%m-%d") - today).dt.days
    T = np.maximum(T_days / 365.0, 1.0 / 365.0)

    K = df["Strike"]

    # --- Call Vanna ---
    sigma_call = df["call_iv"] / 100.0
    valid_c = (sigma_call > 0) & ~sigma_call.isna()
    d1_c = np.zeros(len(df))
    d2_c = np.zeros(len(df))
    vanna_c = np.zeros(len(df))
    
    d1_c[valid_c] = (np.log(spot / K[valid_c]) + (r + 0.5 * sigma_call[valid_c]**2) * T[valid_c]) / (sigma_call[valid_c] * np.sqrt(T[valid_c]))
    d2_c[valid_c] = d1_c[valid_c] - sigma_call[valid_c] * np.sqrt(T[valid_c])
    vanna_c[valid_c] = -norm.pdf(d1_c[valid_c]) * d2_c[valid_c] / sigma_call[valid_c]
    df["call_vanna"] = vanna_c

    # --- Put Vanna ---
    sigma_put = df["put_iv"] / 100.0
    valid_p = (sigma_put > 0) & ~sigma_put.isna()
    d1_p = np.zeros(len(df))
    d2_p = np.zeros(len(df))
    vanna_p = np.zeros(len(df))
    
    d1_p[valid_p] = (np.log(spot / K[valid_p]) + (r + 0.5 * sigma_put[valid_p]**2) * T[valid_p]) / (sigma_put[valid_p] * np.sqrt(T[valid_p]))
    d2_p[valid_p] = d1_p[valid_p] - sigma_put[valid_p] * np.sqrt(T[valid_p])
    vanna_p[valid_p] = -norm.pdf(d1_p[valid_p]) * d2_p[valid_p] / sigma_put[valid_p]
    df["put_vanna"] = vanna_p

    multiplier = lot_size * spot * 0.01
    
    df["Call_VEX"] = -df["call_vanna"] * df["Call_OI"] * multiplier
    df["Put_VEX"]  = -df["put_vanna"] * df["Put_OI"] * multiplier
    
    df["Total_VEX"] = df["Call_VEX"] + df["Put_VEX"]
    df["Abs_VEX"]   = df["Total_VEX"].abs()
    return df


def calculate_charm_exposure(df: pd.DataFrame, lot_size: int = 75) -> pd.DataFrame:
    """
    Dealer Charm Exposure (CEX) calculation using vectorized operations.
    Dealer_CEX = - (Charm * OI * lot_size * spot * sign)
    """
    import numpy as np
    from scipy.stats import norm

    df = df.copy()
    spot = df["Spot"].iloc[0] if "Spot" in df.columns else 1.0
    r = 0.05
    today = pd.Timestamp("today").normalize()

    # Vectorized Time to Expiry (T)
    T_days = (pd.to_datetime(df["expiry"], format="%Y-%m-%d") - today).dt.days
    T = np.maximum(T_days / 365.0, 1.0 / 365.0)

    K = df["Strike"]

    # --- Call Charm ---
    sigma_call = df["call_iv"] / 100.0
    valid_c = (sigma_call > 0) & ~sigma_call.isna()
    d1_c = np.zeros(len(df))
    d2_c = np.zeros(len(df))
    charm_c = np.zeros(len(df))
    
    d1_c[valid_c] = (np.log(spot / K[valid_c]) + (r + 0.5 * sigma_call[valid_c]**2) * T[valid_c]) / (sigma_call[valid_c] * np.sqrt(T[valid_c]))
    d2_c[valid_c] = d1_c[valid_c] - sigma_call[valid_c] * np.sqrt(T[valid_c])
    charm_c[valid_c] = -norm.pdf(d1_c[valid_c]) * ((r / (sigma_call[valid_c] * np.sqrt(T[valid_c]))) - (d2_c[valid_c] / (2.0 * T[valid_c])))
    df["call_charm"] = charm_c

    # --- Put Charm ---
    sigma_put = df["put_iv"] / 100.0
    valid_p = (sigma_put > 0) & ~sigma_put.isna()
    d1_p = np.zeros(len(df))
    d2_p = np.zeros(len(df))
    charm_p = np.zeros(len(df))
    
    d1_p[valid_p] = (np.log(spot / K[valid_p]) + (r + 0.5 * sigma_put[valid_p]**2) * T[valid_p]) / (sigma_put[valid_p] * np.sqrt(T[valid_p]))
    d2_p[valid_p] = d1_p[valid_p] - sigma_put[valid_p] * np.sqrt(T[valid_p])
    charm_p[valid_p] = -norm.pdf(d1_p[valid_p]) * ((r / (sigma_put[valid_p] * np.sqrt(T[valid_p]))) - (d2_p[valid_p] / (2.0 * T[valid_p])))
    df["put_charm"] = charm_p

    multiplier = lot_size * spot
    
    df["Call_CEX"] = -(df["call_charm"] * df["Call_OI"] * multiplier * 1.0)
    df["Put_CEX"]  = -(df["put_charm"] * df["Put_OI"] * multiplier * -1.0)
    
    df["Total_CEX"] = df["Call_CEX"] + df["Put_CEX"]
    df["Abs_CEX"]   = df["Total_CEX"].abs()
    return df


def calculate_delta_exposure(df: pd.DataFrame, lot_size: int = 75) -> pd.DataFrame:
    """
    Standard Delta Exposure calculation.
    DEX = delta * OI * lot_size * spot
    """
    df = df.copy()
    spot = df["Spot"].iloc[0] if "Spot" in df.columns else 1.0
    multiplier = lot_size * spot
    
    df["Call_DEX"] = -df["call_delta"] * df["Call_OI"] * multiplier
    df["Put_DEX"] = -df["put_delta"] * df["Put_OI"] * multiplier
    df["Total_DEX"] = df["Call_DEX"] + df["Put_DEX"]
    df["Abs_DEX"] = df["Total_DEX"].abs()
    return df


# ---------------------------------------------------------------------------
# Key level helpers
# ---------------------------------------------------------------------------

def calculate_flip_point(df: pd.DataFrame) -> float:
    """
    Find the strike price where Total GEX crosses zero (Zero Gamma / Flip Point).
    Standard: Call GEX is Negative, Put GEX is Positive.
    Uses linear interpolation for sub-strike precision.
    """
    df = df.copy()
    if "Total_GEX" not in df.columns:
        df = calculate_gex(df)
        
    # Group by Strike and Sort
    by_strike = df.groupby("Strike")["Total_GEX"].sum().sort_index()
    strikes = by_strike.index.values
    gex_vals = by_strike.values
    
    # 1. Look for sign change (crossing zero)
    # We find where sign flips from negative (Calls dominate) to positive (Puts dominate)
    # or vice versa.
    for i in range(len(gex_vals) - 1):
        g1, g2 = gex_vals[i], gex_vals[i+1]
        s1, s2 = strikes[i], strikes[i+1]
        
        # Check for zero crossing
        if (g1 <= 0 and g2 >= 0) or (g1 >= 0 and g2 <= 0):
            if abs(g2 - g1) < 1e-9: return float(s1)
            # Linear interpolation: find s where g = 0
            # formula: s = s1 + (0 - g1) * (s2 - s1) / (g2 - g1)
            flip_p = s1 - g1 * (s2 - s1) / (g2 - g1)
            return float(flip_p)
            
    # 2. Fallback: If no crossing found, return the strike closest to zero
    return float(by_strike.abs().idxmin())


def get_atm_strike(df: pd.DataFrame) -> float:
    """Return the strike closest to the spot price."""
    spot = df["Spot"].iloc[0]
    return df.iloc[(df["Strike"] - spot).abs().argsort().iloc[:1]]["Strike"].values[0]


def get_dealer_regime(spot_price: float, flip_point: float) -> str:
    """Return a human-readable dealer regime label."""
    if spot_price > flip_point:
        return "LONG GAMMA → MEAN REVERSION"
    return "SHORT GAMMA → TREND/MOMENTUM"


def get_gamma_cage(
    df: pd.DataFrame, atm_strike: float, cage_width: int = 4
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split data into gamma cage (stability zone) and vacuum (expansion zone)."""
    lo = atm_strike - cage_width * 50
    hi = atm_strike + cage_width * 50
    cage = df[(df["Strike"] >= lo) & (df["Strike"] <= hi)]
    vacuum = df[(df["Strike"] < lo) | (df["Strike"] > hi)]
    return cage, vacuum


def get_power_zones(df: pd.DataFrame, top_n: int = 3) -> list[float]:
    """Return the top_n strikes by absolute GEX."""
    return df.nlargest(top_n, "Abs_GEX")["Strike"].tolist()


# ---------------------------------------------------------------------------
# Volatility surface
# ---------------------------------------------------------------------------

def calculate_vol_surface(df: pd.DataFrame) -> dict:
    """
    Compute 25d Risk Reversal, 10d Butterfly, and related IV metrics.

    Returns a dict with RR25, BF10, sentiments, and strike details.
    """
    atm_row   = df.iloc[(df["call_delta"] - 0.50).abs().argsort().iloc[0]]
    call_25d  = df.iloc[(df["call_delta"] - 0.25).abs().argsort().iloc[0]]
    put_25d   = df.iloc[(df["put_delta"]  + 0.25).abs().argsort().iloc[0]]
    call_10d  = df.iloc[(df["call_delta"] - 0.10).abs().argsort().iloc[0]]
    put_10d   = df.iloc[(df["put_delta"]  + 0.10).abs().argsort().iloc[0]]

    ATM_IV    = atm_row["call_iv"]
    IV_call25 = call_25d["call_iv"]
    IV_put25  = put_25d["put_iv"]
    IV_call10 = call_10d["call_iv"]
    IV_put10  = put_10d["put_iv"]

    RR25 = IV_call25 - IV_put25
    BF10 = 0.5 * (IV_call10 + IV_put10) - ATM_IV

    rr_sentiment = "Bullish 🔼" if RR25 > 0 else ("Bearish 🔽" if RR25 < 0 else "Neutral ⚪")
    bf_sentiment = (
        "Tails Expensive 📈" if BF10 > 0
        else ("Flat/Control 📉" if BF10 < 0 else "Neutral ⚪")
    )

    return {
        "ATM_IV":        ATM_IV,
        "RR25":          RR25,
        "BF10":          BF10,
        "ATM_Strike":    float(atm_row["Strike"]),
        "Call25_Strike": float(call_25d["Strike"]),
        "Put25_Strike":  float(put_25d["Strike"]),
        "Call10_Strike": float(call_10d["Strike"]),
        "Put10_Strike":  float(put_10d["Strike"]),
        "IV_call25":     IV_call25,
        "IV_put25":      IV_put25,
        "IV_call10":     IV_call10,
        "IV_put10":      IV_put10,
        "RR_Sentiment":  rr_sentiment,
        "BF_Sentiment":  bf_sentiment,
    }


def calculate_iv_cone(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate 1SD and 2SD price paths based on ATM IV.
    move = spot * iv * sqrt(days/252)
    """
    import numpy as np
    
    spot = df["Spot"].iloc[0] if "Spot" in df.columns else 1.0
    
    # Get ATM IV (using mean of call/put IV for stability)
    atm_row = df.iloc[(df["Strike"] - spot).abs().argsort().iloc[0]]
    iv = (atm_row["call_iv"] + atm_row["put_iv"]) / 2.0 / 100.0
    
    # Horizon: days to nearest expiry (max 30 days for better visualization)
    today = pd.Timestamp("today").normalize()
    expiry = pd.to_datetime(df["expiry"].iloc[0])
    days_to_expiry = (expiry - today).days
    
    # Ensure at least 5 days for a nice cone shape, max 30
    horizon = max(min(days_to_expiry, 30), 5)
    
    days_range = np.arange(0, horizon + 1)
    
    # Formula: move = spot * iv * sqrt(days/252)
    moves_1sd = spot * iv * np.sqrt(days_range / 252.0)
    
    data = {
        "day": days_range,
        "spot": [spot] * len(days_range),
        "sd1_up": spot + moves_1sd,
        "sd1_down": spot - moves_1sd,
        "sd2_up": spot + 2 * moves_1sd,
        "sd2_down": spot - 2 * moves_1sd
    }
    
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Quant Power (Blended Vanna & GEX)
# ---------------------------------------------------------------------------

def calculate_quant_power(
    df: pd.DataFrame, spot: float, r: float = 0.05, 
    vanna_weight: float = 0.3, contract_size: int = 75
) -> dict:
    """
    Returns: quant_power_strike, power_zone_upper, power_zone_lower
    """
    from scipy.stats import norm
    import numpy as np

    calc_df = df.copy()

    # Expand the standard df to look like a chain (Call side and Put side)
    # The original Streamlit app data is one row per strike with call/put columns.
    # To match the intended formula structure which acts on an 'option_type' row,
    # we unpivot the dataframe momentarily.

    calls = pd.DataFrame({
        "strike": calc_df["Strike"],
        "expiry_days": (pd.to_datetime(calc_df["expiry"], format="%Y-%m-%d") - pd.Timestamp("today").normalize()).dt.days.clip(lower=1),
        "option_type": "call",
        "open_interest": calc_df["Call_OI"],
        "iv": calc_df["call_iv"] / 100.0,  # Ensure IV is a decimal
        "gamma": calc_df["call_gamma"],
        "delta": calc_df["call_delta"]
    })

    puts = pd.DataFrame({
        "strike": calc_df["Strike"],
        "expiry_days": (pd.to_datetime(calc_df["expiry"], format="%Y-%m-%d") - pd.Timestamp("today").normalize()).dt.days.clip(lower=1),
        "option_type": "put",
        "open_interest": calc_df["Put_OI"],
        "iv": calc_df["put_iv"] / 100.0,
        "gamma": calc_df["put_gamma"],
        "delta": calc_df["put_delta"]
    })

    chain_df = pd.concat([calls, puts], ignore_index=True)

    # Vectorized BS Greeks
    T = np.maximum(chain_df['expiry_days'].values / 365.0, 1.0 / 365.0)
    K = chain_df['strike'].values
    sigma = chain_df['iv'].values
    opt_type = chain_df['option_type'].str.lower().values

    valid = (sigma > 0) & ~np.isnan(sigma)
    
    d1 = np.zeros(len(chain_df))
    d2 = np.zeros(len(chain_df))
    pdf_d1 = np.zeros(len(chain_df))
    
    d1[valid] = (np.log(spot / K[valid]) + (r + 0.5 * sigma[valid]**2) * T[valid]) / (sigma[valid] * np.sqrt(T[valid]))
    d2[valid] = d1[valid] - sigma[valid] * np.sqrt(T[valid])
    pdf_d1[valid] = norm.pdf(d1[valid])
    
    calc_gamma = np.zeros(len(chain_df))
    calc_vanna = np.zeros(len(chain_df))
    calc_delta = np.zeros(len(chain_df))
    
    calc_gamma[valid] = pdf_d1[valid] / (spot * sigma[valid] * np.sqrt(T[valid]))
    calc_vanna[valid] = -pdf_d1[valid] * d2[valid] / sigma[valid]
    
    # Delta logic: norm.cdf(d1) for calls, norm.cdf(d1) - 1 for puts
    cdf_d1 = np.zeros(len(chain_df))
    cdf_d1[valid] = norm.cdf(d1[valid])
    calc_delta[valid] = np.where(opt_type[valid] == 'call', cdf_d1[valid], cdf_d1[valid] - 1)

    # We always override Vanna
    chain_df['vanna'] = calc_vanna
    
    # Set Gamma/Delta fallbacks if column is missing/zero/NaN
    if "gamma" not in chain_df.columns or (chain_df["gamma"] == 0).all():
        chain_df['gamma'] = calc_gamma
    else:
        chain_df['gamma'] = chain_df['gamma'].fillna(pd.Series(calc_gamma))

    if "delta" not in chain_df.columns or (chain_df["delta"] == 0).all():
        chain_df['delta'] = calc_delta
    else:
        chain_df['delta'] = chain_df['delta'].fillna(pd.Series(calc_delta))

    # Add missing/null protection for greek columns used below
    chain_df = chain_df.fillna(0)

    # ── Sign: calls +ve, puts -ve ─────────────────────────────────────
    sign = np.where(chain_df['option_type'].str.lower() == 'call', 1, -1)

    # ── Dealer delta contribution per contract ────────────────────────
    # Dealers are SHORT options → opposite sign to buyer's delta
    chain_df['dealer_delta'] = -chain_df['delta'] * chain_df['open_interest'] * contract_size

    # ── Dealer exposure = weighted combo of Dealer GEX + Dealer Vanna exposure ─────
    # Standard GEX/VEX are from buyer perspective (Call +, Put -)
    # Dealer perspective = flip signs
    gex = -(chain_df['gamma'] * chain_df['open_interest'] * contract_size * spot**2 * 0.01 * sign)
    vex = -(chain_df['vanna'] * chain_df['open_interest'] * contract_size * spot    * 0.01 * sign)
    chain_df['blended'] = (1 - vanna_weight) * gex + vanna_weight * vex

    # ── Aggregate by strike ───────────────────────────────────────────
    by_strike = chain_df.groupby('strike').agg(
        net_dealer_delta=('dealer_delta', 'sum'),
        blended=('blended', 'sum')
    ).sort_index()

    strikes   = by_strike.index.values
    cum_delta = np.cumsum(by_strike['net_dealer_delta'].values)

    # ── Quant Power = strike where cumulative dealer delta crosses 0 ──
    sign_changes = np.where(np.diff(np.sign(cum_delta)))[0]
    if len(sign_changes) > 0:
        i = sign_changes[0]
        s0, s1, d0, d1 = strikes[i], strikes[i+1], cum_delta[i], cum_delta[i+1]
        
        # Protect against divide-by-zero
        if d1 == d0:
            quant_power = s0
        else:
            qp_price = s0 + (s1 - s0) * (-d0) / (d1 - d0)
            quant_power = strikes[np.argmin(np.abs(strikes - qp_price))]
    else:
        quant_power = strikes[np.argmin(np.abs(cum_delta))]

    # ── Power Zone = ±1 std dev of blended GEX mass distribution ─────
    w = np.abs(by_strike['blended'].values)
    gex_mean = np.average(strikes, weights=w) if w.sum() > 0 else spot
    gex_std  = np.sqrt(np.average((strikes - gex_mean)**2, weights=w)) if w.sum() > 0 else spot*0.01

    power_zone_upper = strikes[np.argmin(np.abs(strikes - (gex_mean + gex_std)))]
    power_zone_lower = strikes[np.argmin(np.abs(strikes - (gex_mean - gex_std)))]

    # Also return the raw blended bar data for charting
    return {
        'quant_power'       : float(quant_power),
        'power_zone_upper'  : float(power_zone_upper),
        'power_zone_lower'  : float(power_zone_lower),
        'strikes'           : strikes.tolist(),
        'blended'           : by_strike['blended'].values.tolist(),
        'cum_delta'         : cum_delta.tolist()
    }

def calculate_premium_flow(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bought vs Sold (Net Flow Direction).
    Logic:
    If IV > ATM_IV → Buyer initiated (Paying up)
    If IV < ATM_IV → Seller initiated (Hitting bid)
    """
    df = df.copy()
    spot = df["Spot"].iloc[0]
    atm_row = df.iloc[(df["Strike"] - spot).abs().argsort().iloc[0]]
    atm_iv = (atm_row["call_iv"] + atm_row["put_iv"]) / 2.0
    
    # Calculate net premium flow per strike
    df["call_prem_flow"] = df.apply(
        lambda r: r["call_ltp"] * (1 if r["call_iv"] > atm_iv else -1) if not pd.isna(r["call_iv"]) else 0,
        axis=1
    )
    df["put_prem_flow"] = df.apply(
        lambda r: r["put_ltp"] * (1 if r["put_iv"] > atm_iv else -1) if not pd.isna(r["put_iv"]) else 0,
        axis=1
    )
    
    return df

def calculate_vtl(df: pd.DataFrame, spot: float, r: float = 0.05) -> dict:
    """
    Vectorized Volatility Ignition point (VTL) calculation.
    Finds the price where GEX + Vanna flips.
    """
    # 1. Normalize data
    df = df.dropna(subset=['call_iv', 'put_iv', 'Call_OI', 'Put_OI']).copy()
    today = pd.Timestamp("today").normalize()
    
    strikes = df['Strike'].values
    T = np.maximum((pd.to_datetime(df['expiry']) - today).dt.days.values, 1.0) / 365.0
    
    iv_c = df['call_iv'].values / 100.0
    iv_p = df['put_iv'].values / 100.0
    oi_c = df['Call_OI'].values
    oi_p = df['Put_OI'].values
    
    # Prices to test (+/- 5%)
    test_prices = np.linspace(spot * 0.95, spot * 1.05, 50)
    
    # We use broadcasting to calculate greeks for all test prices at once
    # S shape: (50, 1), K/T/IV shape: (1, N_strikes)
    S = test_prices.reshape(-1, 1)
    K = strikes.reshape(1, -1)
    T_mat = np.maximum(T.reshape(1, -1), 1e-5) # Protect against 0 time
    IV_c_mat = np.maximum(iv_c.reshape(1, -1), 0.001) # Protect against 0 IV
    IV_p_mat = np.maximum(iv_p.reshape(1, -1), 0.001)
    
    # --- Call Greeks ---
    sqrtT = np.sqrt(T_mat)
    d1_c = (np.log(S/K) + (r + 0.5*IV_c_mat**2)*T_mat) / (IV_c_mat*sqrtT)
    d2_c = d1_c - IV_c_mat*sqrtT
    pdf_d1_c = norm.pdf(d1_c)
    
    gamma_c = pdf_d1_c / (S * IV_c_mat * sqrtT)
    vanna_c = -pdf_d1_c * d2_c / IV_c_mat
    
    # --- Put Greeks ---
    d1_p = (np.log(S/K) + (r + 0.5*IV_p_mat**2)*T_mat) / (IV_p_mat*sqrtT)
    d2_p = d1_p - IV_p_mat*sqrtT
    pdf_d1_p = norm.pdf(d1_p)
    
    gamma_p = pdf_d1_p / (S * IV_p_mat * sqrtT)
    vanna_p = -pdf_d1_p * d2_p / IV_p_mat
    
    # Exposures
    # Sign: Call +1, Put -1
    # total_gex = sum(gamma * oi * S^2 * sign)
    # total_vex = sum(vanna * oi * S * sign)
    
    # Standardize Signs: Call=-1, Put=+1
    gex_c = (gamma_c * oi_c.reshape(1, -1) * S**2 * -1).sum(axis=1) # (50,)
    gex_p = (gamma_p * oi_p.reshape(1, -1) * S**2).sum(axis=1)
    
    vex_c = (vanna_c * oi_c.reshape(1, -1) * S * -1).sum(axis=1)
    vex_p = (vanna_p * oi_p.reshape(1, -1) * S).sum(axis=1)
    
    net_gex = gex_c + gex_p
    net_vex = vex_c + vex_p
    combined = net_gex + net_vex
    
    results = []
    for i in range(len(test_prices)):
        results.append({
            'price': float(test_prices[i]),
            'net_gex': float(net_gex[i]),
            'net_vex': float(net_vex[i]),
            'combined': float(combined[i])
        })
    
    results_df = pd.DataFrame(results)
    sign_change = np.where(np.diff(np.sign(results_df['combined'])))[0]
    
    if len(sign_change) > 0:
        idx = sign_change[0]
        r0, r1 = results_df.iloc[idx], results_df.iloc[idx+1]
        vtl = r0['price'] + (r1['price'] - r0['price']) * (-r0['combined'] / (r1['combined'] - r0['combined']))
    else:
        vtl = float(results_df.loc[results_df['combined'].abs().idxmin(), 'price'])
    
    return {
        'vtl': round(float(vtl), 2),
        'distance_pct': round(float((spot - vtl) / spot * 100), 3),
        'direction': 'above' if spot > vtl else 'below',
        'sim_data': results
    }

def calculate_realized_vol(prices: List[float], annualize_factor: float = 252 * 50) -> float:
    """
    Computes annualized realized volatility from a series of spot prices.
    Assumes snapshots are distinct price points.
    """
    if len(prices) < 2:
        return 0.0
    
    # Calculate log returns
    log_returns = np.diff(np.log(np.array(prices) + 1e-6))
    if len(log_returns) == 0:
        return 0.0
        
    rv = np.std(log_returns) * np.sqrt(annualize_factor)
    if np.isnan(rv):
        return 0.0
    return float(rv * 100) # Percentage

def calculate_greek_sensitivity_grid(df: pd.DataFrame, spot: float, range_pct: float = 0.05, steps: int = 21) -> Dict[str, Any]:
    """
    Generates a matrix of GEX mass across Price vs Strikes.
    This helps identify 'Ignition Zones' where price movement triggers 
    maximum hedging delta.
    """
    # 1. Price simulation range
    price_range = np.linspace(spot * (1 - range_pct), spot * (1 + range_pct), steps)
    
    # 2. Filter for strikes near spot for cleaner grid
    strike_df = df[(df['Strike'] > spot * 0.9) & (df['Strike'] < spot * 1.1)].copy()
    strikes = strike_df['Strike'].values
    
    lot_size = df['lot_size'].iloc[0] if 'lot_size' in df.columns else 75
    
    # 3. Build Heatmap Z-matrix
    # Dimensions: [Price Step] x [Strike]
    z_gex = []
    
    # Pre-calculate common parts for speed
    T_val = np.maximum(df['T'].iloc[0] if 'T' in df.columns else 0.01, 1e-5)
    r = 0.05
    sqrtT = np.sqrt(T_val)
    
    # Clip IVs to avoid div-by-zero
    c_iv = np.maximum(strike_df['call_iv'].values / 100.0, 0.001)
    p_iv = np.maximum(strike_df['put_iv'].values / 100.0, 0.001)
    
    for s_test in price_range:
        # Re-calc Gamma at s_test for each strike
        # Call GEX
        d1_c = (np.log(s_test / strikes) + (r + 0.5 * c_iv**2) * T_val) / (c_iv * sqrtT)
        gamma_c = norm.pdf(d1_c) / (s_test * c_iv * sqrtT)
        gex_c = (strike_df['call_oi'].values * lot_size * 0.1 * s_test * 0.01 * gamma_c)
        
        # Put GEX
        d1_p = (np.log(s_test / strikes) + (r + 0.5 * p_iv**2) * T_val) / (p_iv * sqrtT)
        gamma_p = norm.pdf(d1_p) / (s_test * p_iv * sqrtT)
        gex_p = -(strike_df['put_oi'].values * lot_size * 0.1 * s_test * 0.01 * gamma_p)
        
        z_gex.append((gex_c + gex_p).tolist())

    return {
        "prices": price_range.tolist(),
        "strikes": strikes.tolist(),
        "z": z_gex # Z[price_idx][strike_idx]
    }
