"""
Data router — handles listing files, fetching live data, and loading saved files.
Routes:
  GET  /api/files/{index}
  GET  /api/next-expiry/{index}
  POST /api/fetch
  POST /api/load
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import store
from core.config import FILTER_STRIKES_RADIUS, INDICES, DATA_DIR
from services.calculations import calculate_gex
from services.upstox_service import (
    fetch_option_chain_data,
    filter_near_strikes,
    get_available_files,
    get_next_expiry,
    load_data_file,
    save_data,
)

router = APIRouter(prefix="/api", tags=["data"])


# ---------------------------------------------------------------------------
# List available files
# ---------------------------------------------------------------------------

@router.get("/files/{index}")
def list_files(index: str):
    """Return all saved data files for the given index, grouped by expiry."""
    if index not in INDICES:
        raise HTTPException(status_code=404, detail=f"Unknown index: {index}")
    files = get_available_files(index, data_dir=DATA_DIR)
    return {"index": index, "files": files}


# ---------------------------------------------------------------------------
# Next expiry helper
# ---------------------------------------------------------------------------

@router.get("/next-expiry/{index}")
def next_expiry(index: str):
    """Return the next expiry date for the given index."""
    if index not in INDICES:
        raise HTTPException(status_code=404, detail=f"Unknown index: {index}")
    return {"index": index, "expiry": get_next_expiry(index)}


# ---------------------------------------------------------------------------
# Fetch live data
# ---------------------------------------------------------------------------

class FetchRequest(BaseModel):
    indices: Optional[List[str]] = None  # None = all indices


@router.post("/fetch")
def fetch_data(body: FetchRequest):
    """Fetch live option chain data from Upstox API for one or all indices."""
    print(f"\n[DEBUG-FETCH] /fetch endpoint called with indices={body.indices}")
    target_indices = body.indices or list(INDICES.keys())
    print(f"[DEBUG-FETCH] Target indices: {target_indices}")
    results = []

    for index_name in target_indices:
        try:
            print(f"\n[DEBUG-FETCH] Processing {index_name}...")
            
            if index_name not in INDICES:
                error_msg = f"Unknown index: {index_name}"
                print(f"[DEBUG-FETCH] ✗ {index_name}: {error_msg}")
                results.append({"index": index_name, "success": False, "error": error_msg})
                continue

            print(f"[DEBUG-FETCH] Getting next expiry for {index_name}")
            expiry = get_next_expiry(index_name)
            print(f"[DEBUG-FETCH] Next expiry: {expiry}")
            
            print(f"[DEBUG-FETCH] Fetching option chain data...")
            df, error = fetch_option_chain_data(index_name, expiry_date=expiry)

            if error:
                error_msg = f"Failed to fetch data: {error}"
                print(f"[DEBUG-FETCH] ✗ {index_name}: {error_msg}")
                results.append({"index": index_name, "success": False, "error": error_msg})
                continue

            print(f"[DEBUG-FETCH] Fetched {len(df)} rows, filtering strikes...")
            df_filtered = filter_near_strikes(df, FILTER_STRIKES_RADIUS)
            print(f"[DEBUG-FETCH] After filter: {len(df_filtered)} strikes")
            
            lot_size    = INDICES[index_name]["lot_size"]
            df_filtered = calculate_gex(df_filtered, lot_size)
            print(f"[DEBUG-FETCH] Calculated GEX for {len(df_filtered)} strikes")

            print(f"[DEBUG-FETCH] Calling save_data with data_dir={DATA_DIR}")
            filepath = save_data(df_filtered, index_name, data_dir=DATA_DIR)
            print(f"[DEBUG-FETCH] save_data returned: {filepath}")

            print(f"[DEBUG-FETCH] Setting data in store...")
            # Auto-load into store
            store.set_data(index_name, df_filtered, filepath)
            print(f"[DEBUG-FETCH] ✓ Store updated for {index_name}")

            results.append({
                "index":     index_name,
                "success":   True,
                "strikes":   len(df_filtered),
                "filepath":  filepath,
                "expiry":    expiry,
            })
            print(f"[DEBUG-FETCH] ✓ {index_name} completed successfully")
        
        except Exception as e:
            error_msg = f"Exception during fetch for {index_name}: {type(e).__name__}: {e}"
            print(f"[ERROR-FETCH] {error_msg}")
            results.append({
                "index": index_name,
                "success": False,
                "error": str(e)
            })

    print(f"[DEBUG-FETCH] /fetch endpoint returning results\n")
    return {"results": results}


# ---------------------------------------------------------------------------
# Load a saved file
# ---------------------------------------------------------------------------

class LoadRequest(BaseModel):
    index:    str
    expiry:   str
    filename: str


@router.post("/load")
def load_data(body: LoadRequest):
    """Load a previously saved CSV file into the in-memory store."""
    if body.index not in INDICES:
        raise HTTPException(status_code=404, detail=f"Unknown index: {body.index}")

    # Try new structure first, then legacy
    filepath = Path(DATA_DIR) / body.index / body.expiry / body.filename
    if not filepath.exists():
        filepath = Path(DATA_DIR) / body.expiry / body.filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    df, error = load_data_file(str(filepath))
    if error:
        raise HTTPException(status_code=500, detail=error)

    # Recalculate GEX if missing (backward compat)
    if "Total_GEX" not in df.columns:
        lot_size = INDICES[body.index]["lot_size"]
        df = calculate_gex(df, lot_size)

    store.set_data(body.index, df, str(filepath))
    print(f"[DEBUG] Load successful for {body.index}. Updated store: {list(store._store.keys())}")

    return {
        "success":  True,
        "index":    body.index,
        "filepath": str(filepath),
        "strikes":  len(df),
        "expiry":   df["expiry"].iloc[0] if "expiry" in df.columns else body.expiry,
    }
