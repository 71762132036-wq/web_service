"""
Chart service — builds interactive Plotly figures from DataFrames.
Returns JSON strings that the frontend renders with Plotly.js.
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

from services.calculations import (
    calculate_flip_point,
    calculate_quant_power,
    get_atm_strike,
    get_gamma_cage,
    get_power_zones,
)

# ---------------------------------------------------------------------------
# Colour palette (dark theme)
# ---------------------------------------------------------------------------
C_POS    = "#00C8FF"   # positive gamma (cyan)
C_NEG    = "#FF4B4B"   # negative gamma (red)
C_ABS    = "rgba(147, 51, 234, 0.30)"   # absolute gamma fill
C_SPOT   = "#FF9900"   # spot price line
C_ATM    = "#9CA3AF"   # ATM line
C_FLIP   = "#F9FAFB"   # flip point line
C_CAGE   = "rgba(59, 130, 246, 0.08)"   # gamma cage fill
C_ZONE   = "rgba(250, 204, 21, 0.15)"   # power zone highlight
PAPER_BG = "#0F172A"
PLOT_BG  = "#1E293B"
FONT_CLR = "#E2E8F0"
GRID_CLR = "rgba(255,255,255,0.06)"


def _base_layout(title: str) -> dict:
    return dict(
        title=dict(text=title, font=dict(size=14, color=FONT_CLR), x=0.01),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_CLR, family="Inter, sans-serif"),
        legend=dict(
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
        ),
        margin=dict(l=60, r=60, t=65, b=50),
        xaxis=dict(gridcolor=GRID_CLR, zeroline=False),
        yaxis=dict(gridcolor=GRID_CLR, zeroline=False),
        height=500,
        autosize=True
    )


def _bar_width(df: pd.DataFrame) -> float:
    strikes = sorted(df["Strike"].unique())
    if len(strikes) < 2:
        return 50.0
    return (strikes[1] - strikes[0]) * 0.8


# ---------------------------------------------------------------------------
# 1 — GEX Chart
# ---------------------------------------------------------------------------

def build_gex_chart(df: pd.DataFrame, index_name: str = "Index") -> str:
    spot       = df["Spot"].iloc[0]
    flip       = calculate_flip_point(df)
    bw         = _bar_width(df)
    top_zones  = df.nlargest(3, "Abs_GEX")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # +Gamma bars
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["Total_GEX"].clip(lower=0).tolist(),
        width=bw, marker_color=C_POS, name="+Gamma", opacity=0.9,
    ), secondary_y=False)

    # -Gamma bars
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["Total_GEX"].clip(upper=0).tolist(),
        width=bw, marker_color=C_NEG, name="-Gamma", opacity=0.9,
    ), secondary_y=False)

    # ABS Gamma area
    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["Abs_GEX"].tolist(),
        fill="tozeroy", fillcolor=C_ABS,
        line=dict(color="rgba(147,51,234,0.6)", width=1.5),
        name="ABS GEX", mode="lines",
    ), secondary_y=True)

    # Spot & flip lines
    for x, label, color, dash in [
        (spot, f"Spot: {spot:.0f}", C_SPOT, "dash"),
        (flip, f"Flip: {flip:.0f}", C_FLIP, "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=2,
                      annotation_text=label, annotation_font_color=color)

    # Power zone highlights
    for _, row in top_zones.iterrows():
        fig.add_vrect(
            x0=row["Strike"] - bw / 2, x1=row["Strike"] + bw / 2,
            fillcolor=C_ZONE, layer="below", line_width=0,
        )

    layout = _base_layout(f"{index_name} — Gamma Exposure (GEX) Chart")
    layout["barmode"] = "overlay"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Absolute Gamma")
    layout["yaxis"]["title"] = "Net Gamma Exposure"
    fig.update_layout(**layout)

    return fig.to_json()


# ---------------------------------------------------------------------------
# 2 — Dealer Regime Map
# ---------------------------------------------------------------------------

def build_dealer_regime_map(df: pd.DataFrame, index_name: str = "Index") -> str:
    spot        = df["Spot"].iloc[0]
    atm         = get_atm_strike(df)
    flip        = calculate_flip_point(df)
    bw          = _bar_width(df)
    cage_width  = 4
    _, _        = get_gamma_cage(df, atm, cage_width)
    power_nodes = get_power_zones(df, top_n=3)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["Total_GEX"].clip(lower=0).tolist(),
        width=bw, marker_color=C_POS, name="+Gamma (Stability)", opacity=0.9,
    ), secondary_y=False)

    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["Total_GEX"].clip(upper=0).tolist(),
        width=bw, marker_color=C_NEG, name="-Gamma (Fuel)", opacity=0.9,
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["Abs_GEX"].tolist(),
        fill="tozeroy", fillcolor=C_ABS,
        line=dict(color="rgba(147,51,234,0.6)", width=1.5),
        name="Absolute Gamma Heat", mode="lines",
    ), secondary_y=True)

    for x, label, color, dash in [
        (spot, f"Spot: {spot:.0f}", C_SPOT, "dash"),
        (atm,  f"ATM: {atm:.0f}",  C_ATM,  "dot"),
        (flip, f"Flip: {flip:.0f}", C_FLIP, "dashdot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=2,
                      annotation_text=label, annotation_font_color=color)

    # Gamma cage band
    fig.add_vrect(
        x0=atm - cage_width * 50, x1=atm + cage_width * 50,
        fillcolor=C_CAGE, layer="below", line_width=0,
        annotation_text="Gamma Cage", annotation_position="top left",
        annotation_font_color="#93C5FD",
    )

    # Power zones
    for node in power_nodes:
        fig.add_vrect(x0=node - bw/2, x1=node + bw/2,
                      fillcolor=C_ZONE, layer="below", line_width=0)

    layout = _base_layout(f"{index_name} — Dealer Regime Map")
    layout["barmode"] = "overlay"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Absolute Gamma")
    layout["yaxis"]["title"] = "Net Gamma Exposure"
    fig.update_layout(**layout)

    return fig.to_json()


# ---------------------------------------------------------------------------
# 3 — Call / Put GEX
# ---------------------------------------------------------------------------

def build_call_put_gex(df: pd.DataFrame, index_name: str = "Index") -> str:
    spot = df["Spot"].iloc[0]
    atm  = get_atm_strike(df)
    flip = calculate_flip_point(df)
    bw   = _bar_width(df) * 0.875

    call_plot = df["Call_GEX"].abs().tolist()
    put_plot  = (-df["Put_GEX"].abs()).tolist()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=call_plot,
        width=bw, marker_color=C_POS, name="Call GEX ↑", opacity=0.9,
    ), secondary_y=False)

    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=put_plot,
        width=bw, marker_color=C_NEG, name="Put GEX ↓", opacity=0.9,
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["Abs_GEX"].tolist(),
        fill="tozeroy", fillcolor=C_ABS,
        line=dict(color="rgba(147,51,234,0.6)", width=1.5),
        name="ABS Gamma Heat", mode="lines",
    ), secondary_y=True)

    for x, label, color, dash in [
        (spot, f"Spot: {spot:.0f}", C_SPOT, "dash"),
        (atm,  f"ATM: {atm:.0f}",  C_ATM,  "dot"),
        (flip, f"Flip: {flip:.0f}", C_FLIP, "dashdot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=2,
                      annotation_text=label, annotation_font_color=color)

    for _, r in df.nlargest(3, "Abs_GEX").iterrows():
        fig.add_vrect(x0=r["Strike"] - bw/2, x1=r["Strike"] + bw/2,
                      fillcolor=C_ZONE, layer="below", line_width=0)

    layout = _base_layout(f"{index_name} — Call Above / Put Below")
    layout["barmode"] = "overlay"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Absolute Gamma")
    layout["yaxis"]["title"] = "Gamma Exposure"
    fig.update_layout(**layout)

    return fig.to_json()


# ---------------------------------------------------------------------------
# 4 — IV Smile
# ---------------------------------------------------------------------------

def build_iv_smile(df: pd.DataFrame) -> str:
    spot = df["Spot"].iloc[0]
    atm  = get_atm_strike(df)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["call_iv"].tolist(),
        mode="lines+markers", name="Call IV",
        line=dict(color="#3B82F6", width=2),
        marker=dict(size=5),
    ))

    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["put_iv"].tolist(),
        mode="lines+markers", name="Put IV",
        line=dict(color=C_NEG, width=2),
        marker=dict(size=5),
    ))

    fig.add_vline(x=spot, line_color=C_SPOT, line_dash="dash", line_width=2,
                  annotation_text=f"Spot: {spot:.0f}", annotation_font_color=C_SPOT)
    fig.add_vline(x=atm, line_color=C_ATM, line_dash="dot", line_width=2,
                  annotation_text=f"ATM: {atm:.0f}", annotation_font_color=C_ATM)

    layout = _base_layout("IV Smile / Skew — Call vs Put Implied Volatility")
    layout["yaxis"]["title"] = "Implied Volatility (%)"
    layout["xaxis"]["title"] = "Strike Price"
    fig.update_layout(**layout)

    return fig.to_json()


# ---------------------------------------------------------------------------
# 5 — Risk Reversal & Butterfly
# ---------------------------------------------------------------------------

def build_rr_bf(vol_surface: dict) -> str:
    rr25 = vol_surface["RR25"]
    bf10 = vol_surface["BF10"]

    colors = [C_POS if rr25 > 0 else C_NEG, "#8B5CF6"]

    fig = go.Figure(go.Bar(
        x=["25d Risk Reversal (RR25)", "10d Butterfly (BF10)"],
        y=[rr25, bf10],
        marker_color=colors,
        text=[f"{rr25:.3f}%", f"{bf10:.3f}%"],
        textposition="outside",
        textfont=dict(color=FONT_CLR, size=13),
    ))

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_width=1)

    layout = _base_layout("25d Risk Reversal & 10d Butterfly")
    layout["yaxis"]["title"] = "Vol %"
    layout["showlegend"] = False
    fig.update_layout(**layout)

    return fig.to_json()


# ---------------------------------------------------------------------------
# 6 — Quant Power Profile
# ---------------------------------------------------------------------------

def build_quant_power_chart(df: pd.DataFrame, index_name: str = "Index") -> str:
    spot = df["Spot"].iloc[0]
    qp_data = calculate_quant_power(df, spot)
    
    strikes = qp_data["strikes"]
    blended = qp_data["blended"]
    cum_delta = qp_data["cum_delta"]
    
    qp_strike = qp_data["quant_power"]
    pz_upper = qp_data["power_zone_upper"]
    pz_lower = qp_data["power_zone_lower"]
    
    bw = _bar_width(df)
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Blended GEX/Vanna Mass (Bars)
    # We color positive mass cyan and negative mass red, 
    # but the formula treats positive as calls and negative as puts.
    # We will color purely by the sign of the blended value.
    colors = [C_POS if val >= 0 else C_NEG for val in blended]
    
    fig.add_trace(go.Bar(
        x=strikes, y=blended,
        width=bw, marker_color=colors, name="Blended GEX+Vex Mass", opacity=0.8,
    ), secondary_y=False)
    
    # Cumulative Dealer Delta (Line)
    fig.add_trace(go.Scatter(
        x=strikes, y=cum_delta,
        mode="lines", name="Cumulative Dealer Delta",
        line=dict(color="#FCD34D", width=3),
    ), secondary_y=True)
    
    # Key Levels
    fig.add_vline(x=spot, line_color=C_SPOT, line_dash="dash", line_width=2,
                  annotation_text=f"Spot: {spot:.0f}", annotation_font_color=C_SPOT)
                  
    fig.add_vline(x=qp_strike, line_color="#E879F9", line_dash="dot", line_width=2,
                  annotation_text=f"Quant Power: {qp_strike:.0f}", annotation_font_color="#E879F9")
                  
    # Power Zone band
    fig.add_vrect(
        x0=pz_lower, x1=pz_upper,
        fillcolor="rgba(232, 121, 249, 0.1)", layer="below", line_width=1,
        line_color="rgba(232, 121, 249, 0.5)", line_dash="dash",
        annotation_text="Power Zone (1σ)", annotation_position="top left",
        annotation_font_color="#E879F9",
    )
    
    layout = _base_layout(f"{index_name} — Quant Power Profile (GEX + Vanna)")
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=True, zerolinecolor="rgba(255,255,255,0.2)", title="Cumulative Dealer Delta")
    layout["yaxis"]["title"] = "Blended GEX+Vex Exposure"
    fig.update_layout(**layout)
    
    return fig.to_json()
