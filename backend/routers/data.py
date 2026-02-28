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
    target_indices = body.indices or list(INDICES.keys())
    results = []

    for index_name in target_indices:
        if index_name not in INDICES:
            results.append({"index": index_name, "success": False, "error": "Unknown index"})
            continue

        expiry = get_next_expiry(index_name)
        df, error = fetch_option_chain_data(index_name, expiry_date=expiry)

        if error:
            results.append({"index": index_name, "success": False, "error": error})
            continue

        df_filtered = filter_near_strikes(df, FILTER_STRIKES_RADIUS)
        lot_size    = INDICES[index_name]["lot_size"]
        df_filtered = calculate_gex(df_filtered, lot_size)

        print(f"[DEBUG] fetch_data: Calling save_data with data_dir={DATA_DIR}")
        filepath = save_data(df_filtered, index_name, data_dir=DATA_DIR)

        # Auto-load into store
        store.set_data(index_name, df_filtered, filepath)

        results.append({
            "index":     index_name,
            "success":   True,
            "strikes":   len(df_filtered),
            "filepath":  filepath,
            "expiry":    expiry,
        })

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
