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
# Colour palette (Premium Terminal Theme)
# ---------------------------------------------------------------------------
C_POS    = "#6366F1"   # Indigo (Stabilizing / Call)
C_NEG    = "#F43F5E"   # Rose (Fuel / Put)
C_ABS    = "rgba(239, 222, 11, 0.3)"   # Absolute Gamma Fill (Pale Yellow)
C_SPOT   = "#F59E0B"   # Spot (Amber)
C_ATM    = "#94A3B8"   # ATM (Slate)
C_FLIP   = "#F1F5F9"   # Flip (Cloud)
C_CAGE   = "rgba(99, 102, 241, 0.05)"
C_ZONE   = "rgba(245, 158, 11, 0.12)"
PAPER_BG = "rgba(15, 23, 42, 0)"  # Fully transparent back, handle in CSS
PLOT_BG  = "rgba(30, 41, 59, 0.2)"
FONT_CLR = "#CBD5E1"
GRID_CLR = "rgba(255,255,255,0.04)"


def _base_layout(title: str) -> dict:
    return dict(
        title=dict(
            text=title.upper(), 
            font=dict(size=12, color="#94A3B8", weight=700), 
            x=0.01,
            y=0.98
        ),
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=PLOT_BG,
        font=dict(color=FONT_CLR, family="'Inter', sans-serif", size=11),
        legend=dict(
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(size=10)
        ),
        margin=dict(l=50, r=50, t=100, b=60), # More air around title
        xaxis=dict(
            gridcolor=GRID_CLR, 
            zeroline=False, 
            showline=True, 
            linecolor="rgba(255,255,255,0.1)",
            tickfont=dict(size=10)
        ),
        yaxis=dict(
            gridcolor=GRID_CLR, 
            zeroline=True, 
            zerolinecolor="rgba(255,255,255,0.1)",
            tickfont=dict(size=10)
        ),
        height=650, # Taller charts per user request
        autosize=True
    )


def _bar_width(df: pd.DataFrame) -> float:
    strikes = sorted(df["Strike"].unique())
    if len(strikes) < 2:
        return 50.0
    return (strikes[1] - strikes[0]) * 0.8


# ---------------------------------------------------------------------------
# 1 — Unified Gamma Exposure Chart
# ---------------------------------------------------------------------------

def build_gamma_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    """
    Unifies Net GEX and Call/Put GEX into one powerful engine.
    mode='net':  Shows Net Bar (Call - Put)
    mode='raw':  Shows Call (Up) and Put (Down) separately
    """
    spot      = df["Spot"].iloc[0]
    flip      = calculate_flip_point(df)
    bw        = _bar_width(df)
    top_zones = df.nlargest(3, "Abs_GEX")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if mode == "net":
        # +Gamma bars
        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df["Total_GEX"].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name="+Gamma", opacity=0.9,
        ), secondary_y=False)

        # -Dealer Gamma bars
        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df["Total_GEX"].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name="-Dealer Gamma", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer Gamma Exposure"
        y_title = "Dealer GEX"
    else:
        # Raw Mode: Dealer Call Up / Dealer Put Down
        call_vals = df["Call_GEX"].abs().tolist()
        put_vals  = (-df["Put_GEX"].abs()).tolist()

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name="Dealer Call GEX ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name="Dealer Put GEX ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer Call vs Put Gamma"
        y_title = "Dealer GEX"

    # Common Overlays (ABS Heat, Spot, Flip, Zones)
    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["Abs_GEX"].tolist(),
        fill="tozeroy", fillcolor=C_ABS,
        line=dict(color="rgba(168,85,247,0.4)", width=2),
        name="Absolute Dealer Gamma Heat", mode="lines",
    ), secondary_y=True)

    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (flip, f"ZERO: {flip:.0f}", C_FLIP, "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    for _, row in top_zones.iterrows():
        fig.add_vrect(
            x0=row["Strike"] - bw / 2, x1=row["Strike"] + bw / 2,
            fillcolor=C_ZONE, layer="below", line_width=0,
        )

    layout = _base_layout(chart_title)
    # Granular Strike X-Axis
    strikes = sorted(df["Strike"].unique())
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["barmode"] = "overlay"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Absolute Dealer Gamma")
    layout["yaxis"]["title"] = y_title
    fig.update_layout(**layout)

    return fig.to_json()


def build_delta_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    """
    Carbon copy of Gamma Exposure chart, but for Delta.
    """
    spot      = df["Spot"].iloc[0]
    flip      = calculate_flip_point(df)
    bw        = _bar_width(df)
    top_zones = df.nlargest(3, "Abs_DEX")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if mode == "net":
        # Dealer Delta bars
        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df["Total_DEX"].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name="+Dealer Delta", opacity=0.9,
        ), secondary_y=False)

        # -Dealer Delta bars
        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df["Total_DEX"].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name="-Dealer Delta", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer Delta Exposure"
        y_title = "Dealer DEX"
    else:
        # Raw Mode: Dealer Call Up / Dealer Put Down
        call_vals = df["Call_DEX"].abs().tolist()
        put_vals  = (-df["Put_DEX"].abs()).tolist()

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name="Dealer Call Delta ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name="Dealer Put Delta ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer Call vs Put Delta"
        y_title = "Dealer DEX"

    # Heat & Annotations
    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["Abs_DEX"].tolist(),
        fill="tozeroy", fillcolor=C_ABS,
        line=dict(color="rgba(168,85,247,0.4)", width=2),
        name="Absolute Dealer Delta Heat", mode="lines",
    ), secondary_y=True)

    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (flip, f"ZERO: {flip:.0f}", C_FLIP, "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    for _, row in top_zones.iterrows():
        fig.add_vrect(
            x0=row["Strike"] - bw / 2, x1=row["Strike"] + bw / 2,
            fillcolor=C_ZONE, layer="below", line_width=0,
        )

    layout = _base_layout(chart_title)
    strikes = sorted(df["Strike"].unique())
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["barmode"] = "overlay"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Absolute Dealer Delta")
    layout["yaxis"]["title"] = "Net Dealer Delta"
    fig.update_layout(**layout)

    return fig.to_json()


def build_cumulative_delta_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    """
    A 'carbon copy' of the Delta Exposure chart, but replaces the 
    Absolute Heat overlay with a Cumulative DEX line.
    """
    spot = df["Spot"].iloc[0]
    flip = calculate_flip_point(df)
    bw   = _bar_width(df)
    
    # Pre-sort for cumulative calc
    df_sorted = df.sort_values("Strike").copy()
    df_sorted["Cum_DEX"] = df_sorted["Total_DEX"].cumsum()
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    if mode == "net":
        # Dealer Delta Bars
        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted["Total_DEX"].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name="+Dealer Delta", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted["Total_DEX"].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name="-Dealer Delta", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Cumulative Dealer Delta Profile"
    else:
        # Dealer Delta Bars (Raw)
        call_vals = df_sorted["Call_DEX"].abs().tolist()
        put_vals  = (-df_sorted["Put_DEX"].abs()).tolist()

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name="Dealer Call Delta ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name="Dealer Put Delta ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Raw Dealer Cum-Delta View"

    # Cumulative Delta Line
    fig.add_trace(go.Scatter(
        x=df_sorted["Strike"].tolist(), 
        y=df_sorted["Cum_DEX"].tolist(),
        fill="tozeroy",
        fillcolor="rgba(99, 102, 241, 0.1)",
        line=dict(color=C_POS, width=3),
        name="Cumulative Dealer Delta",
        mode="lines",
    ), secondary_y=True)
    
    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (flip, f"ZERO: {flip:.0f}", C_FLIP, "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    layout = _base_layout(chart_title)
    
    strikes = df_sorted["Strike"].unique().tolist()
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["barmode"] = "overlay"
    layout["yaxis"]["title"] = "Strike-wise Dealer Delta"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=True, title="Cumulative Dealer Delta", overlaying="y", side="right")
    
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
        name="Absolute Dealer Gamma Heat", mode="lines",
    ), secondary_y=True)

    for x, label, color, dash in [
        (spot, f"Spot: {spot:.0f}", C_SPOT, "dash"),
        (atm,  f"ATM: {atm:.0f}",  C_ATM,  "dot"),
        (flip, f"Flip: {flip:.0f}", C_FLIP, "dashdot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=2,
                      annotation_text=label, annotation_font_color=color)

    # Dealer Gamma cage band
    fig.add_vrect(
        x0=atm - cage_width * 50, x1=atm + cage_width * 50,
        fillcolor=C_CAGE, layer="below", line_width=0,
        annotation_text="Dealer Gamma Cage", annotation_position="top left",
        annotation_font_color="#93C5FD",
    )

    # Power zones
    for node in power_nodes:
        fig.add_vrect(x0=node - bw/2, x1=node + bw/2,
                      fillcolor=C_ZONE, layer="below", line_width=0)

    layout = _base_layout(f"{index_name} — Dealer Gamma Regime Map")
    # Granular Strike X-Axis
    strikes = sorted(df["Strike"].unique())
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["barmode"] = "overlay"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Absolute Dealer Gamma")
    layout["yaxis"]["title"] = "Dealer GEX"
    fig.update_layout(**layout)

    return fig.to_json()


# ---------------------------------------------------------------------------
# 3 — Cumulative Gamma GEX
# ---------------------------------------------------------------------------

def build_cumulative_gamma_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    """
    A 'carbon copy' of the Gamma Exposure chart, but replaces the 
    Absolute Heat overlay with a Cumulative GEX line.
    """
    spot = df["Spot"].iloc[0]
    flip = calculate_flip_point(df)
    bw   = _bar_width(df)
    
    # Pre-sort for cumulative calc
    df_sorted = df.sort_values("Strike").copy()
    df_sorted["Cum_GEX"] = df_sorted["Total_GEX"].cumsum()
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    if mode == "net":
        # Dealer Gamma Bars
        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted["Total_GEX"].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name="+Dealer Gamma", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted["Total_GEX"].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name="-Dealer Gamma", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Cumulative Dealer Gamma Profile"
    else:
        # Dealer Gamma Bars (Raw)
        call_vals = df_sorted["Call_GEX"].abs().tolist()
        put_vals  = (-df_sorted["Put_GEX"].abs()).tolist()

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name="Dealer Call GEX ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name="Dealer Put GEX ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Raw Dealer Cum-Gamma View"

    # REPLACE Absolute Heat with Cumulative Dealer Gamma Line
    fig.add_trace(go.Scatter(
        x=df_sorted["Strike"].tolist(), 
        y=df_sorted["Cum_GEX"].tolist(),
        fill="tozeroy",
        fillcolor="rgba(99, 102, 241, 0.1)",
        line=dict(color=C_POS, width=3),
        name="Cumulative Dealer Gamma",
        mode="lines",
    ), secondary_y=True)
    
    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (flip, f"ZERO: {flip:.0f}", C_FLIP, "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    layout = _base_layout(chart_title)
    
    # Granular Strike X-Axis
    strikes = df_sorted["Strike"].unique().tolist()
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["barmode"] = "overlay"
    layout["yaxis"]["title"] = "Strike-wise Dealer Gamma"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=True, title="Cumulative Dealer Gamma", overlaying="y", side="right")
    
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
    # Granular Strike X-Axis
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=True, zerolinecolor="rgba(255,255,255,0.2)", title="Cumulative Dealer Delta")
    layout["yaxis"]["title"] = "Blended GEX+Vex Exposure"
    fig.update_layout(**layout)
    
    return fig.to_json()


# ---------------------------------------------------------------------------
# 7 — Vanna Exposure
# ---------------------------------------------------------------------------

def build_vanna_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    """
    Build the Dealer Vanna Exposure chart.
    """
    spot = df["Spot"].iloc[0]
    flip = calculate_flip_point(df)
    bw   = _bar_width(df)
    top_zones = df.nlargest(3, "Abs_VEX")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if mode == "net":
        # Dealer Vanna bars
        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df["Total_VEX"].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name="+Dealer Vanna", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df["Total_VEX"].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name="-Dealer Vanna", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer Vanna Exposure"
        y_title = "Dealer VEX"
    else:
        # Raw Mode: Dealer Call Up / Dealer Put Down
        call_vals = df["Call_VEX"].abs().tolist()
        put_vals  = (-df["Put_VEX"].abs()).tolist()

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name="Dealer Call VEX ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name="Dealer Put VEX ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer Call vs Put Vanna"
        y_title = "Dealer VEX"

    # Heat & Annotations
    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["Abs_VEX"].tolist(),
        fill="tozeroy", fillcolor=C_ABS,
        line=dict(color="rgba(168,85,247,0.4)", width=2),
        name="Absolute Dealer Vanna Heat", mode="lines",
    ), secondary_y=True)

    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (flip, f"ZERO: {flip:.0f}", C_FLIP, "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    for _, row in top_zones.iterrows():
        fig.add_vrect(
            x0=row["Strike"] - bw / 2, x1=row["Strike"] + bw / 2,
            fillcolor=C_ZONE, layer="below", line_width=0,
        )

    layout = _base_layout(chart_title)
    strikes = sorted(df["Strike"].unique())
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["barmode"] = "overlay"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Absolute Dealer Vanna")
    layout["yaxis"]["title"] = y_title
    fig.update_layout(**layout)

    return fig.to_json()


def build_cumulative_vanna_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    """
    Cumulative Vanna Profile (Dealer Perspective).
    """
    spot = df["Spot"].iloc[0]
    flip = calculate_flip_point(df)
    bw   = _bar_width(df)
    
    # Pre-sort for cumulative calc
    df_sorted = df.sort_values("Strike").copy()
    df_sorted["Cum_VEX"] = df_sorted["Total_VEX"].cumsum()
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    if mode == "net":
        # Dealer Vanna Bars
        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted["Total_VEX"].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name="+Dealer Vanna", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted["Total_VEX"].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name="-Dealer Vanna", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Cumulative Dealer Vanna Profile"
    else:
        # Dealer Vanna Bars (Raw)
        call_vals = df_sorted["Call_VEX"].abs().tolist()
        put_vals  = (-df_sorted["Put_VEX"].abs()).tolist()

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name="Dealer Call VEX ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name="Dealer Put VEX ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Raw Dealer Cum-Vanna View"

    # Cumulative Vanna Line
    fig.add_trace(go.Scatter(
        x=df_sorted["Strike"].tolist(), 
        y=df_sorted["Cum_VEX"].tolist(),
        fill="tozeroy",
        fillcolor="rgba(99, 102, 241, 0.1)",
        line=dict(color=C_POS, width=3),
        name="Cumulative Dealer Vanna",
        mode="lines",
    ), secondary_y=True)
    
    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (flip, f"ZERO: {flip:.0f}", C_FLIP, "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    layout = _base_layout(chart_title)
    strikes = df_sorted["Strike"].unique().tolist()
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["barmode"] = "overlay"
    layout["yaxis"]["title"] = "Strike-wise Dealer Vanna"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=True, title="Cumulative Dealer Vanna", overlaying="y", side="right")
    
    fig.update_layout(**layout)

    return fig.to_json()


# ---------------------------------------------------------------------------
# 8 — Charm Exposure
# ---------------------------------------------------------------------------

def build_charm_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    """
    Build the Dealer Charm Exposure chart.
    """
    spot = df["Spot"].iloc[0]
    flip = calculate_flip_point(df)
    bw   = _bar_width(df)
    top_zones = df.nlargest(3, "Abs_CEX")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if mode == "net":
        # Dealer Charm bars
        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df["Total_CEX"].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name="+Dealer Charm", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df["Total_CEX"].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name="-Dealer Charm", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer Charm Exposure"
        y_title = "Dealer CEX"
    else:
        # Raw Mode: Dealer Call Up / Dealer Put Down
        call_vals = df["Call_CEX"].abs().tolist()
        put_vals  = (-df["Put_CEX"].abs()).tolist()

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name="Dealer Call CEX ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name="Dealer Put CEX ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer Call vs Put Charm"
        y_title = "Dealer CEX"

    # Heat & Annotations
    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["Abs_CEX"].tolist(),
        fill="tozeroy", fillcolor=C_ABS,
        line=dict(color="rgba(168,85,247,0.4)", width=2),
        name="Absolute Dealer Charm Heat", mode="lines",
    ), secondary_y=True)

    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (flip, f"ZERO: {flip:.0f}", C_FLIP, "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    for _, row in top_zones.iterrows():
        fig.add_vrect(
            x0=row["Strike"] - bw / 2, x1=row["Strike"] + bw / 2,
            fillcolor=C_ZONE, layer="below", line_width=0,
        )

    layout = _base_layout(chart_title)
    strikes = sorted(df["Strike"].unique())
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["barmode"] = "overlay"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Absolute Dealer Charm")
    layout["yaxis"]["title"] = y_title
    fig.update_layout(**layout)

    return fig.to_json()


def build_cumulative_charm_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    """
    Cumulative Charm Profile (Dealer Perspective).
    """
    spot = df["Spot"].iloc[0]
    flip = calculate_flip_point(df)
    bw   = _bar_width(df)
    
    # Pre-sort for cumulative calc
    df_sorted = df.sort_values("Strike").copy()
    df_sorted["Cum_CEX"] = df_sorted["Total_CEX"].cumsum()
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    if mode == "net":
        # Dealer Charm Bars
        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted["Total_CEX"].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name="+Dealer Charm", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted["Total_CEX"].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name="-Dealer Charm", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Cumulative Dealer Charm Profile"
    else:
        # Dealer Charm Bars (Raw)
        call_vals = df_sorted["Call_CEX"].abs().tolist()
        put_vals  = (-df_sorted["Put_CEX"].abs()).tolist()

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name="Dealer Call CEX ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name="Dealer Put CEX ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Raw Dealer Cum-Charm View"

    # Cumulative Charm Line
    fig.add_trace(go.Scatter(
        x=df_sorted["Strike"].tolist(), 
        y=df_sorted["Cum_CEX"].tolist(),
        fill="tozeroy",
        fillcolor="rgba(99, 102, 241, 0.1)",
        line=dict(color=C_POS, width=3),
        name="Cumulative Dealer Charm",
        mode="lines",
    ), secondary_y=True)
    
    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (flip, f"ZERO: {flip:.0f}", C_FLIP, "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    layout = _base_layout(chart_title)
    strikes = df_sorted["Strike"].unique().tolist()
    if len(strikes) > 1:
        layout["xaxis"]["tickmode"] = "linear"
        layout["xaxis"]["dtick"]    = strikes[1] - strikes[0]
        layout["xaxis"]["tickangle"] = -45

    layout["barmode"] = "overlay"
    layout["yaxis"]["title"] = "Strike-wise Dealer Charm"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=True, title="Cumulative Dealer Charm", overlaying="y", side="right")
    
    fig.update_layout(**layout)

    return fig.to_json()
