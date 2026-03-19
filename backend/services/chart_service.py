"""
Chart service — builds interactive Plotly figures from DataFrames.
Returns JSON strings that the frontend renders with Plotly.js.
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np

from services.calculations import (
    calculate_flip_point,
    calculate_quant_power,
    get_atm_strike,
    get_gamma_cage,
    get_power_zones,
)

from typing import Union, Dict, Any, List

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
# Core Exposure Engines (DRY)
# ---------------------------------------------------------------------------

def _build_exposure_chart(
    df: pd.DataFrame, 
    index_name: str, 
    mode: str, 
    total_col: str, 
    call_col: str, 
    put_col: str, 
    abs_col: str, 
    metric_label: str,
    y_title: str
) -> str:
    spot      = df["Spot"].iloc[0]
    flip      = calculate_flip_point(df)
    bw        = _bar_width(df)
    top_zones = df.nlargest(3, abs_col)

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if mode == "net":
        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df[total_col].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name=f"+Dealer {metric_label}", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=df[total_col].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name=f"-Dealer {metric_label}", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer {metric_label} Exposure"
        final_y_title = y_title
    else:
        call_vals = df[call_col].abs().tolist()
        put_vals  = (-df[put_col].abs()).tolist()
        
        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name=f"Dealer Call {metric_label} ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name=f"Dealer Put {metric_label} ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Dealer Call vs Put {metric_label}"
        final_y_title = y_title

    # Heat & Annotations
    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df[abs_col].tolist(),
        fill="tozeroy", fillcolor=C_ABS,
        line=dict(color="rgba(168,85,247,0.4)", width=2),
        name=f"Absolute Dealer {metric_label} Heat", mode="lines",
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
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title=f"Absolute Dealer {metric_label}")
    layout["yaxis"]["title"] = final_y_title
    fig.update_layout(**layout)

    return fig.to_dict()


def _build_cumulative_exposure_chart(
    df: pd.DataFrame, 
    index_name: str, 
    mode: str, 
    total_col: str, 
    call_col: str, 
    put_col: str, 
    cum_col: str,
    metric_label: str
) -> str:
    spot = df["Spot"].iloc[0]
    flip = calculate_flip_point(df)
    bw   = _bar_width(df)
    
    df_sorted = df.sort_values("Strike").copy()
    df_sorted[cum_col] = df_sorted[total_col].cumsum()
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    if mode == "net":
        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted[total_col].clip(lower=0).tolist(),
            width=bw, marker_color=C_POS, name=f"+Dealer {metric_label}", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=df_sorted[total_col].clip(upper=0).tolist(),
            width=bw, marker_color=C_NEG, name=f"-Dealer {metric_label}", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Cumulative Dealer {metric_label} Profile"
    else:
        call_vals = df_sorted[call_col].abs().tolist()
        put_vals  = (-df_sorted[put_col].abs()).tolist()

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=call_vals,
            width=bw * 0.9, marker_color=C_POS, name=f"Dealer Call {metric_label} ↑", opacity=0.9,
        ), secondary_y=False)

        fig.add_trace(go.Bar(
            x=df_sorted["Strike"].tolist(), y=put_vals,
            width=bw * 0.9, marker_color=C_NEG, name=f"Dealer Put {metric_label} ↓", opacity=0.9,
        ), secondary_y=False)
        chart_title = f"{index_name} — Raw Dealer Cum-{metric_label} View"

    fig.add_trace(go.Scatter(
        x=df_sorted["Strike"].tolist(), 
        y=df_sorted[cum_col].tolist(),
        fill="tozeroy",
        fillcolor="rgba(99, 102, 241, 0.1)",
        line=dict(color=C_POS, width=3),
        name=f"Cumulative Dealer {metric_label}",
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
    layout["yaxis"]["title"] = f"Strike-wise Dealer {metric_label}"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=True, title=f"Cumulative Dealer {metric_label}", overlaying="y", side="right")
    
    fig.update_layout(**layout)

    return fig.to_dict()



# ---------------------------------------------------------------------------
# 1 — Unified Gamma Exposure Chart
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1 — Unified Exposure Charts (Gamma, Delta, Vanna, Charm)
# ---------------------------------------------------------------------------

def build_gamma_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    return _build_exposure_chart(df, index_name, mode, "Total_GEX", "Call_GEX", "Put_GEX", "Abs_GEX", "Gamma", "Dealer GEX")

def build_delta_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    return _build_exposure_chart(df, index_name, mode, "Total_DEX", "Call_DEX", "Put_DEX", "Abs_DEX", "Delta", "Net Dealer Delta")

def build_cumulative_delta_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    return _build_cumulative_exposure_chart(df, index_name, mode, "Total_DEX", "Call_DEX", "Put_DEX", "Cum_DEX", "Delta")

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

    return fig.to_dict()


# ---------------------------------------------------------------------------
# 3 — Cumulative Gamma GEX
# ---------------------------------------------------------------------------


def build_cumulative_gamma_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    return _build_cumulative_exposure_chart(df, index_name, mode, "Total_GEX", "Call_GEX", "Put_GEX", "Cum_GEX", "Gamma")

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

    return fig.to_dict()


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
    return fig.to_dict()


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
    
    return fig.to_dict()


# ---------------------------------------------------------------------------
# 7 — Vanna Exposure
# ---------------------------------------------------------------------------


def build_vanna_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    return _build_exposure_chart(df, index_name, mode, "Total_VEX", "Call_VEX", "Put_VEX", "Abs_VEX", "Vanna", "Dealer VEX")

def build_cumulative_vanna_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    return _build_cumulative_exposure_chart(df, index_name, mode, "Total_VEX", "Call_VEX", "Put_VEX", "Cum_VEX", "Vanna")

# ---------------------------------------------------------------------------
# 8 — Charm Exposure
# ---------------------------------------------------------------------------


def build_charm_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    return _build_exposure_chart(df, index_name, mode, "Total_CEX", "Call_CEX", "Put_CEX", "Abs_CEX", "Charm", "Dealer CEX")

def build_cumulative_charm_chart(df: pd.DataFrame, index_name: str = "Index", mode: str = "net") -> str:
    return _build_cumulative_exposure_chart(df, index_name, mode, "Total_CEX", "Call_CEX", "Put_CEX", "Cum_CEX", "Charm")

def build_iv_cone_chart(df_cone: pd.DataFrame, index_name: str = "Index") -> str:
    """
    Build the IV Cone chart showing expected price ranges.
    """
    fig = go.Figure()

    # 2SD Range (Shaded)
    fig.add_trace(go.Scatter(
        x=df_cone["day"].tolist() + df_cone["day"].tolist()[::-1],
        y=df_cone["sd2_up"].tolist() + df_cone["sd2_down"].tolist()[::-1],
        fill='toself',
        fillcolor='rgba(244, 63, 94, 0.1)', # Rose tint for wider range
        line=dict(color='rgba(244, 63, 94, 0.2)', width=1),
        name="2SD Expected Range (95%)",
        hoverinfo='skip'
    ))

    # 1SD Range (Shaded)
    fig.add_trace(go.Scatter(
        x=df_cone["day"].tolist() + df_cone["day"].tolist()[::-1],
        y=df_cone["sd1_up"].tolist() + df_cone["sd1_down"].tolist()[::-1],
        fill='toself',
        fillcolor='rgba(99, 102, 241, 0.15)', # Indigo tint for core range
        line=dict(color='rgba(99, 102, 241, 0.3)', width=1),
        name="1SD Expected Range (68%)",
        hoverinfo='skip'
    ))

    # Spot Baseline
    fig.add_trace(go.Scatter(
        x=df_cone["day"].tolist(),
        y=df_cone["spot"].tolist(),
        line=dict(color=C_SPOT, width=2, dash='dash'),
        name=f"Current Spot: {df_cone['spot'].iloc[0]:.0f}"
    ))

    # Boundary Lines
    fig.add_trace(go.Scatter(
        x=df_cone["day"].tolist(), y=df_cone["sd1_up"].tolist(),
        line=dict(color=C_POS, width=1.5), name="1SD Upper", showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=df_cone["day"].tolist(), y=df_cone["sd1_down"].tolist(),
        line=dict(color=C_POS, width=1.5), name="1SD Lower", showlegend=False
    ))

    layout = _base_layout(f"{index_name} — IV Cone (Expected Price Ranges)")
    layout["xaxis"]["title"] = "Days from Today"
    layout["yaxis"]["title"] = "Dealer Net OI (Lacs)"
    fig.update_layout(**layout)

    return fig.to_dict()


# ---------------------------------------------------------------------------
# 9 — OI Analysis
# ---------------------------------------------------------------------------

def build_standard_oi_chart(df: pd.DataFrame, index_name: str = "Index") -> str:
    """
    Standard High-Fidelity OI Strike Map.
    Red: Calls, Green: Puts. Both positive upward bars.
    """
    spot = df["Spot"].iloc[0]
    atm  = get_atm_strike(df)
    
    fig = go.Figure()

    # Red for Calls (#F43F5E)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["Call_OI"].tolist(),
        marker_color="#F43F5E", name="Call OI (Resistance)", opacity=0.9,
    ))

    # Green for Puts (#10B981)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["Put_OI"].tolist(),
        marker_color="#10B981", name="Put OI (Support)", opacity=0.9,
    ))

    # Spot & ATM
    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (atm,  f"ATM: {atm:.0f}",  C_ATM,  "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    layout = _base_layout(f"{index_name} — Standard OI Strike Map")
    layout["yaxis"]["title"] = "OI Contracts"
    layout["barmode"] = "group"
    layout["bargap"] = 0.35
    layout["bargroupgap"] = 0.05
    fig.update_layout(**layout)
    return fig.to_dict()

def build_oi_flow_chart(df: pd.DataFrame, index_name: str = "Index") -> str:
    """
    OI vs Volume Strike Map.
    Red: Call OI, Rose: Call Vol.
    Green: Put OI, Emerald: Put Vol.
    """
    spot = df["Spot"].iloc[0]
    atm  = get_atm_strike(df)
    
    fig = go.Figure()

    # Call OI (Red #F43F5E)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["Call_OI"].tolist(),
        marker_color="#F43F5E", name="Call OI", opacity=0.9,
    ))

    # Call Volume (Rose #FDA4AF)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["call_vol"].tolist(),
        marker_color="#FDA4AF", name="Call Volume", opacity=0.7,
    ))

    # Put OI (Green #10B981)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["Put_OI"].tolist(),
        marker_color="#10B981", name="Put OI", opacity=0.9,
    ))

    # Put Volume (Emerald #A7F3D0)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["put_vol"].tolist(),
        marker_color="#A7F3D0", name="Put Volume", opacity=0.7,
    ))

    # Spot & ATM
    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (atm,  f"ATM: {atm:.0f}",  C_ATM,  "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    layout = _base_layout(f"{index_name} — OI Flow (OI vs Volume)")
    layout["yaxis"]["title"] = "Qty / Contracts"
    layout["barmode"] = "group"
    layout["bargap"] = 0.25
    layout["bargroupgap"] = 0.05
    fig.update_layout(**layout)
    return fig.to_dict()

def build_oi_change_chart(df: pd.DataFrame, index_name: str = "Index") -> str:
    """
    Daily OI Change Strike Map.
    Red: Call OI Change, Green: Put OI Change.
    Negative values represent positions being closed.
    """
    df = df.copy()
    
    # Fallback calculation if columns are empty or missing
    if "call_oi_chg" not in df.columns or df["call_oi_chg"].isna().all():
        if "call_oi" in df.columns and "call_prev_oi" in df.columns:
            df["call_oi_chg"] = df["call_oi"].fillna(0) - df["call_prev_oi"].fillna(0)
            
    if "put_oi_chg" not in df.columns or df["put_oi_chg"].isna().all():
        if "put_oi" in df.columns and "put_prev_oi" in df.columns:
            df["put_oi_chg"] = df["put_oi"].fillna(0) - df["put_prev_oi"].fillna(0)

    spot = df["Spot"].iloc[0]
    atm  = get_atm_strike(df)
    
    fig = go.Figure()

    # Call OI Change (Red #F43F5E)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["call_oi_chg"].tolist(),
        marker_color="#F43F5E", name="Call OI Change", opacity=0.9,
    ))

    # Put OI Change (Green #10B981)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["put_oi_chg"].tolist(),
        marker_color="#10B981", name="Put OI Change", opacity=0.9,
    ))

    # Spot & ATM
    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (atm,  f"ATM: {atm:.0f}",  C_ATM,  "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    layout = _base_layout(f"{index_name} — OI Change (Daily Shift)")
    layout["yaxis"]["title"] = "OI Change Contracts"
    layout["barmode"] = "group"
    layout["bargap"] = 0.35
    layout["bargroupgap"] = 0.05
    fig.update_layout(**layout)
    return fig.to_dict()

def build_premium_flow_chart(df: pd.DataFrame, index_name: str = "Index") -> str:
    """
    Premium Bought vs Sold (Net Flow Direction).
    Red: Call Premium Flow, Green: Put Premium Flow.
    """
    from services.calculations import calculate_premium_flow
    df = calculate_premium_flow(df)
    
    spot = df["Spot"].iloc[0]
    atm  = get_atm_strike(df)
    
    fig = go.Figure()

    # Call Premium Flow (Red #F43F5E)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["call_prem_flow"].tolist(),
        marker_color="#F43F5E", name="Call Prem Flow", opacity=0.9,
    ))

    # Put Premium Flow (Green #10B981)
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["put_prem_flow"].tolist(),
        marker_color="#10B981", name="Put Prem Flow", opacity=0.9,
    ))

    # Spot & ATM
    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (atm,  f"ATM: {atm:.0f}",  C_ATM,  "dot"),
    ]:
        fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                      annotation_text=label, annotation_font_color=color,
                      annotation_position="top left", annotation_font_size=10)

    layout = _base_layout(f"{index_name} — Premium Flow (Bought vs Sold)")
    layout["yaxis"]["title"] = "Net Premium Flow"
    layout["barmode"] = "group"
    layout["bargap"] = 0.35
    layout["bargroupgap"] = 0.05
    fig.update_layout(**layout)
    return fig.to_dict()

def build_compare_oi_change_chart(df1: pd.DataFrame, df2: pd.DataFrame, index_name: str = "Index") -> str:
    """
    Compare OI Change between two snapshots.
    Delta = df2['OI'] - df1['OI']
    """
    # Merge on Strike to ensure alignment
    merged = pd.merge(df1[['Strike', 'call_oi', 'put_oi']], 
                     df2[['Strike', 'call_oi', 'put_oi', 'Spot']], 
                     on='Strike', how='outer', suffixes=('_1', '_2')).fillna(0)
    
    merged = merged.sort_values("Strike")
    
    merged['call_oi_delta'] = merged['call_oi_2'] - merged['call_oi_1']
    merged['put_oi_delta'] = merged['put_oi_2'] - merged['put_oi_1']
    
    spot = merged["Spot"].iloc[-1] # Use latest spot
    atm  = get_atm_strike(merged)
    
    fig = go.Figure()

    # Call Delta (Red)
    fig.add_trace(go.Bar(
        x=merged["Strike"].tolist(), y=merged["call_oi_delta"].tolist(),
        marker_color="#F43F5E", name="Call OI Delta", opacity=0.9,
    ))

    # Put Delta (Green)
    fig.add_trace(go.Bar(
        x=merged["Strike"].tolist(), y=merged["put_oi_delta"].tolist(),
        marker_color="#10B981", name="Put OI Delta", opacity=0.9,
    ))

    # Spot & ATM
    for x, label, color, dash in [
        (spot, f"SPOT: {spot:.0f}", C_SPOT, "solid"),
        (atm,  f"ATM: {atm:.0f}",  C_ATM,  "dot"),
    ]:
        if x > 0:
            fig.add_vline(x=x, line_color=color, line_dash=dash, line_width=1.5,
                          annotation_text=label, annotation_font_color=color,
                          annotation_position="top left", annotation_font_size=10)

    layout = _base_layout(f"{index_name} — Comparative OI Shift")
    layout["yaxis"]["title"] = "OI Delta (Contracts)"
    layout["barmode"] = "group"
    layout["bargap"] = 0.35
    layout["bargroupgap"] = 0.05
    fig.update_layout(**layout)
    return fig.to_dict()

def build_flow_intensity_chart(flow_data: dict, index_name: str = "Index") -> str:
    """
    Visualizes flow intensity (Bought to Open, Sold to Open, etc.)
    for Calls and Puts side-by-side.
    """
    cats = ['bought_to_open', 'short_covered', 'sold_to_open', 'bought_to_close']
    labels = ['Buy Open', 'Cover Short', 'Sell Open', 'Sell Close']
    
    fig = go.Figure()
    
    # Calls
    call_vals = [flow_data['calls'].get(c, 0) for c in cats]
    fig.add_trace(go.Bar(
        name='Calls',
        x=labels,
        y=call_vals,
        marker_color="#F43F5E",
        opacity=0.85
    ))
    
    # Puts
    put_vals = [flow_data['puts'].get(c, 0) for c in cats]
    fig.add_trace(go.Bar(
        name='Puts',
        x=labels,
        y=put_vals,
        marker_color="#10B981",
        opacity=0.85
    ))
    
    layout = _base_layout(f"{index_name} — Flow Activity Intensity")
    layout["yaxis"]["title"] = "Dollar Value Flow"
    layout["barmode"] = "group"
    layout["legend"] = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    fig.update_layout(**layout)
    return fig.to_dict()

def build_strike_pressure_chart(merged_detail: list, index_name: str = "Index") -> str:
    """
    Strike-wise Net Pressure Score.
    Score = (Buy Flow - Sell Flow) / Total per strike.
    """
    df = pd.DataFrame(merged_detail)
    if df.empty: return "{}"
    
    # Calculate net pressure per strike
    # Simplified: (long_delta / total_delta) per strike
    def get_strike_pressure(g):
        buying = g[g['flow_class'].isin(['bought_to_open', 'short_covered'])]['dollar_flow'].sum()
        selling = g[g['flow_class'].isin(['sold_to_open', 'bought_to_close'])]['dollar_flow'].sum()
        total = buying + selling
        return (buying - selling) / total if total > 0 else 0

    strikes = sorted(df['strike'].unique())
    call_pressure = []
    put_pressure = []
    
    for s in strikes:
        s_df = df[df['strike'] == s]
        call_pressure.append(get_strike_pressure(s_df[s_df['option_type'] == 'call']))
        put_pressure.append(get_strike_pressure(s_df[s_df['option_type'] == 'put']))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=strikes, y=call_pressure, name="Call Pressure",
        line=dict(color="#F43F5E", width=2, shape='spline'),
        mode='lines+markers', marker=dict(size=4)
    ))
    fig.add_trace(go.Scatter(
        x=strikes, y=put_pressure, name="Put Pressure",
        line=dict(color="#10B981", width=2, shape='spline'),
        mode='lines+markers', marker=dict(size=4)
    ))
    
    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.2)")

    layout = _base_layout(f"{index_name} — Strike-wise Net Pressure")
    layout["yaxis"]["title"] = "Pressure (-1 to +1)"
    layout["yaxis"]["range"] = [-1.1, 1.1]
    layout["legend"] = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    fig.update_layout(**layout)
    return fig.to_dict()

def build_vtl_chart(vtl_data: dict, spot: float, index_name: str = "Index") -> str:
    """
    Visualizes the Volatility Trigger simulation:
    Net GEX, Net Vanna, and Combined curves.
    """
    df = pd.DataFrame(vtl_data['sim_data'])
    vtl_price = vtl_data['vtl']
    
    fig = go.Figure()
    
    # Net GEX
    fig.add_trace(go.Scatter(
        x=df['price'].tolist(), y=df['net_gex'].tolist(), name="Dealer GEX",
        line=dict(color="#6366F1", width=1.5, dash='dot'),
        mode='lines'
    ))
    
    # Net Vanna
    fig.add_trace(go.Scatter(
        x=df['price'].tolist(), y=df['net_vex'].tolist(), name="Dealer Vanna",
        line=dict(color="#F43F5E", width=1.5, dash='dot'),
        mode='lines'
    ))
    
    # Combined (The Trigger)
    fig.add_trace(go.Scatter(
        x=df['price'].tolist(), y=df['combined'].tolist(), name="Combined (Ignition)",
        line=dict(color="#F59E0B", width=3),
        mode='lines',
        fill='tozeroy', fillcolor='rgba(245, 158, 11, 0.05)'
    ))
    
    # VTL vertical line
    fig.add_vline(x=vtl_price, line_color="#F1F5F9", line_dash="dash", line_width=2,
                  annotation_text=f"VTL: {vtl_price:,.0f}", annotation_position="top left")
    
    # Current Spot line
    fig.add_vline(x=spot, line_color="#F59E0B", line_width=1,
                  annotation_text=f"SPOT: {spot:,.0f}", annotation_position="bottom right")

    layout = _base_layout(f"{index_name} — Volatility Trigger Level (VTL)")
    layout["yaxis"]["title"] = "Exposure Value"
    layout["xaxis"]["title"] = "Underlying Price"
    # Ensure X-axis covers the full simulation range even if traces are tiny
    layout["xaxis"]["range"] = [df['price'].min(), df['price'].max()]
    layout["legend"] = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    fig.update_layout(**layout)
    return fig.to_dict()

def build_migration_chart(migration_data: dict, index_name: str = "Index") -> str:
    """
    Visualizes the 'Gamma Waltz' — movement of Spot vs Flip vs QP.
    """
    if "error" in migration_data:
        return json.dumps({"error": migration_data["error"]})

    history = migration_data.get("history", [])
    if not history:
        return json.dumps({"error": "No historical snapshots found for this expiry."})

    df = pd.DataFrame(history)
    fig = go.Figure()

    # Mapping for clean display
    metrics = [
        ("spot", "Spot Price", C_SPOT, "solid", 3),
        ("flip", "Flip Point", C_FLIP, "dash", 1.5),
        ("qp",   "Quant Power", "#E879F9", "dot", 1.5),
        ("vtl",  "VTL Ignition", "#F59E0B", "dashdot", 1.5),
    ]

    for col, label, color, dash, width in metrics:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["time"].tolist(), y=df[col].tolist(),
                name=label,
                line=dict(color=color, width=width, dash=dash),
                mode='lines+markers',
                marker=dict(size=4)
            ))

    layout = _base_layout(f"{index_name} — Level Migration (The Gamma Waltz)")
    layout["yaxis"]["title"] = "Price / Strike Level"
    layout["xaxis"]["title"] = "Timestamp (Snapshots)"
    layout["hovermode"] = "x unified"
    fig.update_layout(**layout)
    
    return fig.to_dict()

def build_vol_spread_chart(vol_data: dict, index_name: str = "Index") -> str:
    """
    Comparison of Realized vs Implied Volatility.
    """
    iv = vol_data["iv"]
    rv = vol_data["rv"]
    spread = vol_data["spread"]
    
    fig = go.Figure()
    
    # Bar comparison
    fig.add_trace(go.Bar(
        x=["Implied Vol (IV)", "Realized Vol (RV)"],
        y=[iv, rv],
        marker_color=[C_POS, "#10B981"], # Indigo for IV, Green for RV
        text=[f"{iv}%", f"{rv}%"],
        textposition='outside',
        width=0.4
    ))
    
    # Indicator for spread
    fig.add_annotation(
        x=0.5, y=max(iv, rv) * 1.1,
        text=f"SPREAD: {spread:+.2f}%<br><b>{vol_data['sentiment']}</b>",
        showarrow=False,
        font=dict(size=14, color=FONT_CLR),
        bgcolor="rgba(0,0,0,0.5)",
        bordercolor=C_POS if spread > 0 else C_NEG,
        borderwidth=1
    )

    layout = _base_layout(f"{index_name} — Volatility Mispricing Spread")
    layout["yaxis"]["title"] = "Annualized Vol (%)"
    layout["showlegend"] = False
    fig.update_layout(**layout)
    
    return fig.to_dict()

def build_ignition_heatmap(grid_data: dict, index_name: str = "Index") -> str:
    """
    Visualizes the Greek Sensitivity Matrix as a Heatmap.
    """
    z = grid_data.get("z", [])
    if not z:
        return "{}"

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=grid_data["strikes"],
        y=grid_data["prices"],
        colorscale='RdBu',
        reversescale=True,
        zmid=0,
        colorbar=dict(title="GEX Mass", thickness=15),
        hovertemplate="Price: %{y}<br>Strike: %{x}<br>Mass: %{z:,.0f}<extra></extra>"
    ))

    layout = _base_layout(f"{index_name} — Ignition Heatmap (Gamma Sensitivity)")
    layout["xaxis"]["title"] = "Strikes"
    layout["yaxis"]["title"] = "Price Shift (Simulation)"
    fig.update_layout(**layout)
    
    return fig.to_dict()

def build_momentum_chart(mom_data: dict, index_name: str = "Index") -> str:
    """
    Visualizes the velocity of Greek shifts.
    """
    history = mom_data.get("momentum", [])
    if not history: return "{}"
    
    df = pd.DataFrame(history)
    fig = go.Figure()
    
    # GEX Velocity (Bar)
    fig.add_trace(go.Bar(
        x=df["time"].tolist(), y=df["gex_velocity"].tolist(),
        name="GEX Velocity",
        marker_color=df["gex_velocity"].apply(lambda v: C_POS if v > 0 else C_NEG).tolist(),
        opacity=0.6,
        yaxis="y"
    ))
    
    # GEX Total (Line)
    fig.add_trace(go.Scatter(
        x=df["time"].tolist(), y=df["gex_total"].tolist(),
        name="Net GEX",
        line=dict(color=C_POS, width=3),
        yaxis="y2"
    ))

    layout = _base_layout(f"{index_name} — Institutional Flow Momentum (GEX Flux)")
    layout["yaxis"] = dict(title="Velocity (Change)", side="left")
    layout["yaxis2"] = dict(title="Total Net GEX", side="right", overlaying="y", showgrid=False)
    layout["legend"] = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    fig.update_layout(**layout)
    
    return fig.to_dict()


def build_dealer_reflexivity_chart(reflexivity_data: Dict[str, Any], index_name: str = "Index") -> str:
    """
    Visualizes the Dealer Reflexivity Curve (Hedging Pressure vs Price Move).
    """
    profile = reflexivity_data.get("profile", [])
    if not profile: return "{}"
    
    fig = go.Figure()
    
    x_vals = [f["pct"] for f in profile]
    y_vals = [f["flow"] for f in profile]
    
    # Area Fill for impact
    fig.add_trace(go.Scatter(
        x=x_vals, y=y_vals,
        fill="tozeroy",
        fillcolor="rgba(99, 102, 241, 0.1)",
        line=dict(color=C_POS, width=3),
        mode="lines+markers",
        name="Hedging Pressure ($)",
        marker=dict(size=8, color=C_POS, symbol="diamond"),
        hovertemplate="Price Shift: %{x}%<br>Dealer Flow: %{y:,.0f} Cr<extra></extra>"
    ))
    
    # Zero Line
    fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_width=1)
    
    layout = _base_layout(f"{index_name} — Dealer Hedging Reflexivity Curve")
    layout["xaxis"]["title"] = "% Price Move from Spot"
    layout["yaxis"]["title"] = "Dealer Flow Requirement (Stabilizing < 0 > Accelerating)"
    layout["xaxis"]["tickformat"] = ".1f"
    fig.update_layout(**layout)
    
    return fig.to_dict()


def build_liquidity_depth_chart(liquidity_data: List[Dict[str, Any]], index_name: str = "Index") -> str:
    """
    Visualizes Market Depth and Spreads across strikes (Liquidity Voids).
    """
    if not liquidity_data: return "{}"
    
    df = pd.DataFrame(liquidity_data)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Depth (Bars)
    fig.add_trace(go.Bar(
        x=df["strike"].tolist(), y=df["depth"].tolist(),
        marker_color="rgba(16, 185, 129, 0.6)",
        name="Market Depth (Bid+Ask Qty)",
        opacity=0.8
    ), secondary_y=False)
    
    # Spread (Line)
    fig.add_trace(go.Scatter(
        x=df["strike"].tolist(), y=df["spread"].tolist(),
        mode="lines",
        name="Avg Bid-Ask Spread",
        line=dict(color=C_NEG, width=2),
        yaxis="y2"
    ), secondary_y=True)
    
    layout = _base_layout(f"{index_name} — Liquidity Depth & Void Profiler")
    layout["xaxis"]["title"] = "Strike"
    layout["yaxis"]["title"] = "Total Quantity (Liquidity)"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Avg Spread", side="right", overlaying="y")
    fig.update_layout(**layout)
    
    return fig.to_dict()


def build_stickiness_chart(df: pd.DataFrame, index_name: str = "Index") -> str:
    """
    Visualizes GEX Stickiness (Mass/Volume Ratio) at each strike.
    """
    if "stickiness" not in df.columns:
        return "{}"
        
    spot = df["Spot"].iloc[0]
    fig = go.Figure()
    
    # Stickiness Bars
    fig.add_trace(go.Bar(
        x=df["Strike"].tolist(), y=df["stickiness"].tolist(),
        marker_color="#FCD34D", # Gold
        name="GEX Stickiness Ratio",
        opacity=0.8,
        hovertemplate="Strike: %{x}<br>Stickiness: %{y:.2f}<extra></extra>"
    ))
    
    fig.add_vline(x=spot, line_color=C_SPOT, line_dash="dash", line_width=2)
    
    layout = _base_layout(f"{index_name} — GEX Stickiness (Dealer Conviction)")
    layout["xaxis"]["title"] = "Strike"
    layout["yaxis"]["title"] = "Stickiness Ratio (GEX / Volume)"
    fig.update_layout(**layout)
    
    return fig.to_dict()


def build_delta_apex_chart(apex_data: Dict[str, Any], index_name: str = "Index") -> str:
    """
    Visualizes the Delta Neutral Equilibrium (Apex).
    Plots Net Dealer Delta and Net Dealer GEX across a price range.
    The point where Delta = 0 is the 'Delta Magnet'.
    """
    prices = apex_data.get("prices", [])
    deltas = apex_data.get("deltas", [])
    gex = apex_data.get("gex", [])
    apex_price = apex_data.get("apex_price", 0)
    current_spot = apex_data.get("current_spot", 0)
    
    if not prices: return "{}"
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Dealer Net Delta (Line)
    fig.add_trace(go.Scatter(
        x=prices, y=deltas,
        mode="lines",
        name="Net Dealer Delta (Magnet Influence)",
        line=dict(color="#FCD34D", width=4), # Gold Line
        fill="tozeroy",
        fillcolor="rgba(252, 211, 77, 0.05)"
    ), secondary_y=False)
    
    # Net Dealer GEX (Line)
    fig.add_trace(go.Scatter(
        x=prices, y=gex,
        mode="lines",
        name="Net Dealer GEX (Stability)",
        line=dict(color=C_POS, width=2, dash='dot'),
        yaxis="y2"
    ), secondary_y=True)
    
    # Apex Vertical Line (Delta Magnet)
    fig.add_vline(x=apex_price, line_color="#E879F9", line_dash="dash", line_width=3,
                  annotation_text=f"DELTA APEX: {apex_price:.0f}", 
                  annotation_position="top left",
                  annotation_font_color="#E879F9")
    
    # Spot Vertical Line
    fig.add_vline(x=current_spot, line_color=C_SPOT, line_dash="solid", line_width=2,
                  annotation_text=f"SPOT: {current_spot:.0f}", 
                  annotation_position="bottom right",
                  annotation_font_color=C_SPOT)
    
    # Zero line for Delta
    fig.add_hline(y=0, line_color="rgba(255,255,255,0.4)", line_width=1, secondary_y=False)
    
    layout = _base_layout(f"{index_name} — Delta Neutral Equilibrium (Apex Search)")
    layout["xaxis"]["title"] = "Price Shift Simulation"
    layout["yaxis"]["title"] = "Net Dealer Delta ($ Risk)"
    layout["yaxis2"] = dict(gridcolor=GRID_CLR, zeroline=False, title="Simulated GEX Mass", side="right", overlaying="y")
    
    fig.update_layout(**layout)
    
    return fig.to_dict()


def build_gamma_profile_chart(conc_data: Dict[str, Any], index_name: str = "Index") -> str:
    """
    Visualizes the Gamma Distribution Profile (Sharpness/Concentration).
    Shows how GEX is distributed across strikes.
    """
    profile = conc_data.get("profile", [])
    if not profile: return "{}"
    
    df = pd.DataFrame(profile)
    fig = go.Figure()
    
    # Area Fill for Distribution
    fig.add_trace(go.Scatter(
        x=df["Strike"].tolist(), y=df["Abs_GEX"].tolist(),
        mode="lines",
        line=dict(color=C_POS, width=3),
        fill="tozeroy",
        fillcolor="rgba(99, 102, 241, 0.2)",
        name="Gamma Intensity Profile",
        hovertemplate="Strike: %{x}<br>Abs GEX: %{y:.2f}<extra></extra>"
    ))
    
    # Highlight the Peaks (Concentration)
    peak_strike = df.loc[df["Abs_GEX"].idxmax(), "Strike"]
    peak_val = df["Abs_GEX"].max()
    
    fig.add_trace(go.Scatter(
        x=[peak_strike], y=[peak_val],
        mode="markers",
        marker=dict(color=C_NEG, size=12, symbol="star"),
        name="Primary Gamma Peak"
    ))
    
    index_score = conc_data.get("concentration_index", 0)
    risk_label = "SHARP / EXPLOSIVE" if conc_data.get("is_sharp") else "WIDE / LINEAR"
    
    layout = _base_layout(f"{index_name} — Gamma Profile ({risk_label})")
    layout["xaxis"]["title"] = "Strike"
    layout["yaxis"]["title"] = "Gamma Exposure Intensity"
    
    # Add index annotation
    fig.add_annotation(
        text=f"Concentration Index: {index_score:.1f}<br>Top Strike: {conc_data.get('top_pct', 0):.1f}%",
        xref="paper", yref="paper",
        x=0.02, y=0.98,
        showarrow=False,
        bgcolor="rgba(0,0,0,0.5)",
        font=dict(size=14, color="#FCD34D")
    )
    
    fig.update_layout(**layout)
    
    return fig.to_dict()


def build_gamma_density_chart(density_data: Dict[str, Any], index_name: str = "Index") -> str:
    """
    Visualizes the aggregate 'Gamma Bell Curve' (Density Map).
    Plots simulated total net GEX across a price range.
    """
    prices = density_data.get("prices", [])
    total_gex = density_data.get("total_gex", [])
    current_spot = density_data.get("current_spot", 0)
    
    if not prices: return "{}"
    
    fig = go.Figure()
    
    # Gamma Density (Bell Curve)
    fig.add_trace(go.Scatter(
        x=prices, y=total_gex,
        mode="lines",
        line=dict(color=C_POS, width=4), # High visibility indigo
        fill="tozeroy",
        fillcolor="rgba(99, 102, 241, 0.15)",
        name="Net Dealer Exposure (GEX Density)",
        hovertemplate="Price: %{x:.0f}<br>Net GEX: %{y:.2f}<extra></extra>"
    ))
    
    # Fill based on regime
    # We add a horizontal line at 0 for context
    fig.add_hline(y=0, line_color="rgba(255,255,255,0.4)", line_width=1)
    
    # Spot Marker
    fig.add_vline(x=current_spot, line_color=C_SPOT, line_dash="solid", line_width=2,
                  annotation_text=f"SPOT: {current_spot:.0f}", 
                  annotation_position="bottom right")
    
    # Gamma Peak Marker
    max_idx = np.argmax(np.abs(total_gex))
    peak_price = prices[max_idx]
    peak_val = total_gex[max_idx]
    
    fig.add_trace(go.Scatter(
        x=[peak_price], y=[peak_val],
        mode="markers",
        marker=dict(color="#FCD34D", size=10, symbol="diamond"),
        name="Gamma High Tide"
    ))
    
    layout = _base_layout(f"{index_name} — Gamma Exposure Density (The Bell Curve)")
    layout["xaxis"]["title"] = "Price Shift Simulation"
    layout["yaxis"]["title"] = "Aggregate Dealer GEX ($ Exposure)"
    
    fig.update_layout(**layout)
    
    return fig.to_dict()


def build_cumulative_shield_chart(df: pd.DataFrame, shield_metrics: Dict[str, Any], index_name: str = "Index") -> str:
    """
    Visualizes the 'Gamma Shield' — highly analytical view of the cumulative GEX curve.
    Highlights Breadth, Depth, and Intensity.
    """
    if df.empty: return "{}"
    
    # Sort and calc cumulative
    df_sorted = df.copy().sort_values("Strike")
    if 'Total_GEX' not in df_sorted.columns:
        from services.calculations import calculate_gex
        df_sorted = calculate_gex(df_sorted)
        
    by_strike = df_sorted.groupby("Strike")["Total_GEX"].sum().sort_index()
    strikes = by_strike.index.values
    cum_gex = np.cumsum(by_strike.values)
    spot = df["Spot"].iloc[0]
    
    fig = go.Figure()
    
    # The Shield Curve
    fig.add_trace(go.Scatter(
        x=strikes, y=cum_gex,
        mode="lines",
        line=dict(color="#38BDF8", width=4), # Sky Blue
        fill="tozeroy",
        fillcolor="rgba(56, 189, 248, 0.1)",
        name="Cumulative Gamma Shield"
    ))
    
    # Highlight Peak (Depth)
    peak_strike = shield_metrics.get("peak_strike", 0)
    peak_val = shield_metrics.get("shield_depth", 0)
    
    fig.add_trace(go.Scatter(
        x=[peak_strike], y=[peak_val],
        mode="markers+text",
        marker=dict(color="#FCD34D", size=12, symbol="star-diamond"),
        text=[f"Peak Shield: {peak_val/1e12:.1f}T"],
        textposition="top center",
        name="Shield Apex"
    ))
    
    # Highlight Breadth Zone
    depth = shield_metrics.get("shield_depth", 0)
    threshold = abs(depth) * 0.5
    # Find zone boundaries
    in_zone = np.where(np.abs(cum_gex) >= threshold)[0]
    if len(in_zone) > 0:
        z_start, z_end = strikes[in_zone[0]], strikes[in_zone[-1]]
        fig.add_vrect(
            x0=z_start, x1=z_end,
            fillcolor="rgba(252, 211, 77, 0.05)",
            layer="below", line_width=0,
            annotation_text="SHIELD BREADTH",
            annotation_position="top left"
        )
        
    # Spot Line
    fig.add_vline(x=spot, line_color=C_SPOT, line_width=2, line_dash="solid")
    
    layout = _base_layout(f"{index_name} — Cumulative Gamma Shield Analytics")
    layout["xaxis"]["title"] = "Strike"
    layout["yaxis"]["title"] = "Cumulative Dealer Gamma ($ Exposure)"
    
    # Slope Intensity Indicator
    slope = shield_metrics.get("slope_intensity", 0)
    intensity = "High" if abs(slope) > 1e10 else "Moderate" # Empirical
    fig.add_annotation(
        text=f"Shield Depth: {peak_val/1e12:.2f}T<br>Risk Intensity: {intensity}<br>Breadth: {shield_metrics.get('breadth_pct', 0):.1f}%",
        xref="paper", yref="paper",
        x=0.02, y=0.98,
        showarrow=False,
        bgcolor="rgba(0,0,0,0.6)",
        font=dict(size=14, color="#38BDF8")
    )
    
    fig.update_layout(**layout)
    
    return fig.to_dict()


def build_cum_steepness_chart(steepness: Dict[str, Any], index_name: str = "Index") -> str:
    """
    Dual-panel chart:
    - Top: Cumulative GEX curve with tangent annotation at spot.
    - Bottom: Gradient (slope) at every strike — shows where the curve is steepest.
    """
    strikes    = steepness.get("strikes", [])
    cum_gex    = steepness.get("cum_gex", [])
    all_slopes = steepness.get("all_slopes", [])
    spot       = steepness.get("current_spot", 0)
    regime     = steepness.get("regime", "")
    slope_lbl  = steepness.get("slope_label", "")
    norm_pct   = steepness.get("norm_slope_pct", 0)
    
    if not strikes:
        return "{}"
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.4],
        subplot_titles=["Cumulative GEX", "Slope (Gradient at each Strike)"],
        vertical_spacing=0.10,
    )
    
    # ─── Panel 1: Cum GEX ─────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=strikes, y=cum_gex,
        mode="lines",
        line=dict(color="#818CF8", width=3),
        fill="tozeroy",
        fillcolor="rgba(129,140,248,0.12)",
        name="Cum GEX",
        hovertemplate="Strike: %{x}<br>Cum GEX: %{y:.2e}<extra></extra>",
    ), row=1, col=1)
    
    fig.add_vline(x=spot, line_color=C_SPOT, line_width=2,
                  annotation_text=f"SPOT: {spot:.0f}", annotation_position="top right")
    
    # ─── Panel 2: Gradient ────────────────────────────────────────────────
    slope_colors = ["#F87171" if s < 0 else "#34D399" for s in all_slopes]
    
    fig.add_trace(go.Bar(
        x=strikes, y=all_slopes,
        marker_color=slope_colors,
        name="Local Slope",
        hovertemplate="Strike: %{x}<br>Slope: %{y:.2e}<extra></extra>",
    ), row=2, col=1)
    
    fig.add_vline(x=spot, line_color=C_SPOT, line_width=2, row=2, col=1)
    
    # ─── Annotation ───────────────────────────────────────────────────────
    fig.add_annotation(
        text=f"Slope @ Spot: {slope_lbl}<br>Intensity: {norm_pct:.0f}%  |  Regime: <b>{regime}</b>",
        xref="paper", yref="paper",
        x=0.02, y=0.98,
        showarrow=False,
        bgcolor="rgba(0,0,0,0.65)",
        font=dict(size=13, color="#FCD34D"),
    )
    
    layout = _base_layout(f"{index_name} — Cumulative GEX Steepness Analysis")
    layout.update(showlegend=False)
    
    fig.update_layout(**layout)
    
    return fig.to_dict()

def build_systemic_pulse_chart(pulse_data: dict, index_name: str = "Index") -> str:
    """
    Visualizes the 'Systemic Pulse' — relationships between Price, IV, and total dealer exposure.
    Contains 4 lines: Spot, ATM IV, Net GEX, and Net DEX.
    """
    if "error" in pulse_data:
        return json.dumps({"error": pulse_data["error"]})

    history = pulse_data.get("pulse", [])
    if not history:
        return json.dumps({"error": "No pulse data found for this expiry."})

    df = pd.DataFrame(history)
    
    # We use multiple Y-axes to handle different scales:
    # Y1 (Left): Spot Price
    # Y2 (Right): Net GEX & DEX ($ Exposure)
    # Y3 (Right, offset): ATM IV (%)
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 1. Spot Price (Y1 - Left)
    fig.add_trace(go.Scatter(
        x=df["time"].tolist(), y=df["spot"].tolist(),
        name="Spot Price",
        line=dict(color=C_SPOT, width=3),
        mode='lines+markers',
        marker=dict(size=4)
    ), secondary_y=False)

    # 2. Net GEX (Y2 - Right)
    gex_cr = [v / 1e7 for v in df["cum_gamma"].tolist()]
    fig.add_trace(go.Scatter(
        x=df["time"].tolist(), y=gex_cr,
        name="Net GEX (Gamma) Cr",
        line=dict(color=C_POS, width=2, dash='solid'),
        mode='lines+markers',
        marker=dict(size=4)
    ), secondary_y=True)

    # 3. Net DEX (Y2 - Right)
    dex_cr = [v / 1e7 for v in df["cum_delta"].tolist()]
    fig.add_trace(go.Scatter(
        x=df["time"].tolist(), y=dex_cr,
        name="Net DEX (Delta) Cr",
        line=dict(color="#E879F9", width=2, dash='dot'),
        mode='lines+markers',
        marker=dict(size=4)
    ), secondary_y=True)

    # 4. ATM IV (Y2 - Right?) - For now let's put it on Right as well or a 3rd with offset
    # Given Plotly's make_subplots limitation, we'll put IV on a secondary Y as well, 
    # but maybe we need a dedicated layout change for a 3rd axis for best UX.
    # To keep it robust, let's put IV on the Left (Y1) with a large multiplier if needed, 
    # or just use secondary_y for IV and primary for Spot, and group exposures.
    
    # Let's try: 
    # Left: Spot
    # Right: IV & Exposures (They will have different scales, so let's use a 3rd axis)
    
    fig.add_trace(go.Scatter(
        x=df["time"].tolist(), y=df["iv"].tolist(),
        name="ATM IV (%)",
        line=dict(color="#FCD34D", width=2, dash='dashdot'),
        mode='lines+markers',
        marker=dict(size=4),
        yaxis="y3"
    ))

    layout = _base_layout(f"{index_name} — Systemic Market Pulse")
    layout["yaxis"] = dict(
        title="Spot Price", side="left", autorange=True, fixedrange=False
    )
    layout["yaxis2"] = dict(
        title="Dealer Net Exposure (Cr)", side="right", overlaying="y", showgrid=False, autorange=True
    )
    
    # Custom 3rd axis for IV
    layout["yaxis3"] = dict(
        title="ATM IV (%)", side="right", overlaying="y", showgrid=False, anchor="free", position=1, shift=60, autorange=True
    )
    
    layout["xaxis"]["title"] = "Timestamp"
    layout["hovermode"] = "x unified"
    
    fig.update_layout(**layout)
    
    return fig.to_dict()


def build_aggregate_exposure_chart(pulse_data: Dict[str, Any], index_name: str = "Index", chart_type: str = "GEX") -> Dict[str, Any]:
    """
    Stand-alone time-series for Total GEX or Total DEX.
    Shows the aggregate exposure of the entire portfolio over time.
    """
    if "error" in pulse_data or not pulse_data.get("pulse"):
        return {"error": pulse_data.get("error", "No data for aggregate chart")}

    df = pd.DataFrame(pulse_data["pulse"])
    # Ensure all required columns are numeric and converted to lists for Plotly JSON
    times = df["time"].tolist()
    spots = pd.to_numeric(df["spot"], errors='coerce').tolist()
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 1. Spot Price (Left Y)
    fig.add_trace(go.Scatter(
        x=times, y=spots,
        name="Spot Price",
        line=dict(color=C_SPOT, width=2, dash='dot'),
        mode='lines+markers',
        marker=dict(size=3)
    ), secondary_y=False)
    
    # 2. Exposure (Right Y)
    metrics_key = "cum_gamma" if chart_type == "GEX" else "cum_delta"
    label = "Total GEX" if chart_type == "GEX" else "Total DEX"
    color = C_POS if chart_type == "GEX" else "#E879F9"
    
    # Scale to Crores
    exposure_vals = pd.to_numeric(df[metrics_key], errors='coerce').fillna(0)
    exposure_cr = (exposure_vals / 1e7).tolist()
    
    fig.add_trace(go.Scatter(
        x=times, y=exposure_cr,
        name=f"{label} (Cr)",
        line=dict(color=color, width=4),
        fill="tozeroy",
        fillcolor=f"rgba(129, 140, 248, 0.1)" if chart_type == 'GEX' else "rgba(232, 121, 249, 0.1)",
        mode='lines'
    ), secondary_y=True)
    
    title = f"{index_name} — Historical {label} Flow"
    layout = _base_layout(title)
    
    # Fix Y-Axis Scaling: Prevent compressing Spot Price to zero
    layout["yaxis"] = dict(
        title="Spot Price",
        side="left",
        gridcolor=GRID_CLR,
        zeroline=False,
        tickfont=dict(size=10),
        autorange=True,
        fixedrange=False
    )
    
    layout["yaxis2"] = dict(
        title=f"{label} (Cr Exposure)", 
        side="right", 
        overlaying="y", 
        showgrid=False,
        tickfont=dict(size=10, color=color),
        autorange=True
    )
    
    layout["xaxis"]["title"] = "Timestamp"
    layout["hovermode"] = "x unified"
    
    fig.update_layout(**layout)
    return fig.to_dict()
