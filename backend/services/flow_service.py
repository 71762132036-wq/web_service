import numpy as np
import pandas as pd
from typing import Dict, Any

def classify_option_flow(df_now: pd.DataFrame, df_prev: pd.DataFrame, index_name: str = "Index") -> Dict[str, Any]:
    """
    Approximates whether calls/puts are being bought or sold
    using IV change + OI change + volume as proxy signals.
    """
    import numpy as np
    import pandas as pd
    
    # ── Normalize Data Structure ──────────────────────────────────────
    def to_long(df: pd.DataFrame) -> pd.DataFrame:
        cols = {
            'strike': 'Strike',
            'expiry': 'expiry',
            'iv': 'call_iv',
            'open_interest': 'call_oi',
            'volume': 'call_vol',
            'last_price': 'call_ltp',
            'spot': 'Spot'
        }
        
        def extract_side(prefix):
            df_cols_lower = {c.lower(): c for c in df.columns}
            out = pd.DataFrame(index=df.index)
            
            for target, source_base in cols.items():
                source = source_base
                if source_base.startswith('call_') and prefix == 'put':
                    source = f"put_{source_base[5:]}"
                if source_base in ['Strike', 'Spot', 'expiry']:
                    source = source_base

                s_lower = source.lower()
                if s_lower in df_cols_lower:
                    out[target] = df[df_cols_lower[s_lower]]
                else:
                    out[target] = 0
            
            out['option_type'] = prefix
            return out

        return pd.concat([extract_side('call'), extract_side('put')], ignore_index=True)

    long_now = to_long(df_now)
    long_prev = to_long(df_prev)

    # User's Merge Logic
    merged = long_now.merge(
        long_prev[['strike', 'expiry', 'option_type', 'iv', 'open_interest', 'last_price', 'volume']],
        on=['strike', 'expiry', 'option_type'],
        suffixes=('_now', '_prev')
    ).fillna(0)

    # ── Calculate Incremental Volume ─────────────────────────────────
    # Since snapshots have cumulative volume, we must get the delta
    merged['incremental_volume'] = (merged['volume_now'] - merged['volume_prev']).clip(lower=0)

    # ── User's Signals ───────────────────────────────────────────────
    merged['iv_change'] = merged['iv_now'] - merged['iv_prev']
    merged['oi_change'] = merged['open_interest_now'] - merged['open_interest_prev']
    merged['vol_intensity'] = merged['incremental_volume'] / merged['open_interest_prev'].replace(0, np.nan)

    # ── User's Classification Logic ──────────────────────────────────
    def classify(row):
        if row['incremental_volume'] <= 0:
            return 'neutral'
            
        iv_up = row['iv_change'] >  0.002
        iv_dn = row['iv_change'] < -0.002
        oi_up = row['oi_change'] >  0
        oi_dn = row['oi_change'] <= 0

        if iv_up and oi_up:
            return 'bought_to_open'
        elif iv_up and oi_dn:
            return 'short_covered'
        elif iv_dn and oi_up:
            return 'sold_to_open'
        elif iv_dn and oi_dn:
            return 'bought_to_close'
        else:
            return 'neutral'

    merged['flow_class'] = merged.apply(classify, axis=1)

    # ── Dollar Value ──────────────────────────────────────────────────
    from core.config import INDICES
    lot_size = INDICES.get(index_name, {}).get('lot_size', 1)
    
    # We use incremental volume for flow value
    merged['dollar_flow'] = merged['incremental_volume'] * merged['last_price_now'] * lot_size

    # ── Aggregate ─────────────────────────────────────────────────────
    def summarize(df_side):
        g = df_side.groupby('flow_class')['dollar_flow'].sum()
        sum_dict = {
            'bought_to_open'  : float(g.get('bought_to_open',   0)),
            'sold_to_open'    : float(g.get('sold_to_open',     0)),
            'bought_to_close' : float(g.get('bought_to_close',  0)),
            'short_covered'   : float(g.get('short_covered',    0)),
        }
        
        buying  = sum_dict['bought_to_open'] + sum_dict['short_covered']
        selling = sum_dict['sold_to_open']   + sum_dict['bought_to_close']
        total   = buying + selling
        pressure = (buying - selling) / total if total > 0 else 0
        
        return {
            **sum_dict,
            'pressure': pressure,
            'label': get_flow_label(pressure)
        }

    calls = merged[merged['option_type'] == 'call']
    puts  = merged[merged['option_type'] == 'put']

    return {
        'calls': summarize(calls),
        'puts': summarize(puts),
        'merged': merged.to_dict(orient='records')
    }

def get_flow_label(pressure: float) -> str:
    if pressure > 0.6: return 'aggressively bought'
    elif pressure > 0.2: return 'lightly bought'
    elif pressure > -0.2: return 'neutral / mixed'
    elif pressure > -0.6: return 'lightly sold'
    else: return 'aggressively sold'
