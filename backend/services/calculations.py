"""
Calculation service — GEX metrics, flip point, gamma cage, vol surface.
Ported from streamlit_app/modules/calculations.py
"""

import itertools

import pandas as pd


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
    
    df["Call_GEX"] = df["call_gamma"] * df["Call_OI"] * multiplier
    df["Put_GEX"] = -df["put_gamma"] * df["Put_OI"] * multiplier
    df["Total_GEX"] = df["Call_GEX"] + df["Put_GEX"]
    df["Abs_GEX"] = df["Total_GEX"].abs()
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
    Find the strike price where cumulative GEX crosses zero (flip point).
    Matches Step 2 & 3: Group by strike -> Cumsum -> Find Zero Crossing.
    """
    # Group by Strike (sums Call/Put GEX) and Sort
    by_strike = df.groupby("Strike")["Total_GEX"].sum().sort_index()
    
    # Cumulative sum
    cum_gex = by_strike.cumsum()
    
    # The flip point is the strike where cumulative GEX is closest to 0
    flip_strike = cum_gex.abs().idxmin()
    return float(flip_strike)


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

    def bs_greeks(S, K, T, r, sigma, option_type):
        if T <= 0 or sigma <= 0 or pd.isna(sigma):
            return 0.0, 0.0, 0.0
        d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
        d2 = d1 - sigma*np.sqrt(T)
        pdf_d1 = norm.pdf(d1)
        gamma  = pdf_d1 / (S * sigma * np.sqrt(T))
        vanna  = -pdf_d1 * d2 / sigma
        delta  = norm.cdf(d1) if option_type == 'call' else norm.cdf(d1) - 1
        return delta, gamma, vanna

    # Fill Vanna using BS
    greeks = chain_df.apply(lambda r: bs_greeks(
        spot, r['strike'], r['expiry_days']/365.0,
        0.05, r['iv'], r['option_type']
    ), axis=1)
    
    # We always override Vanna. 
    # If delta/gamma from exchange are NaN, we'll override those too.
    _, _, vanna = zip(*greeks)
    chain_df['vanna'] = vanna
    
    for i, col in [(0, 'delta'), (1, 'gamma')]:
        calc_arr = [g[i] for g in greeks]
        chain_df[col] = chain_df[col].fillna(pd.Series(calc_arr))

    # Add missing/null protection for greek columns used below
    chain_df = chain_df.fillna(0)

    # ── Sign: calls +ve, puts -ve ─────────────────────────────────────
    sign = np.where(chain_df['option_type'].str.lower() == 'call', 1, -1)

    # ── Dealer delta contribution per contract ────────────────────────
    # Dealers are SHORT options → opposite sign to buyer's delta
    chain_df['dealer_delta'] = -chain_df['delta'] * chain_df['open_interest'] * contract_size

    # ── Blended exposure = weighted combo of GEX + Vanna exposure ─────
    gex   = chain_df['gamma'] * chain_df['open_interest'] * contract_size * spot**2 * 0.01 * sign
    vex   = chain_df['vanna'] * chain_df['open_interest'] * contract_size * spot    * 0.01 * sign
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
