"""
sync.py — Local app router for syncing data directly from Supabase.

The Render Cron Job writes snapshots to Supabase every 15 min.
This endpoint pulls unsynced rows, converts them to local CSVs,
then marks them as synced in Supabase.

Route: POST /api/sync
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client

import store
from core.config import (
    DATA_DIR, INDICES,
    SUPABASE_URL, SUPABASE_KEY,
)
from services.calculations import calculate_gex

router = APIRouter(prefix="/api", tags=["sync"])
logger = logging.getLogger(__name__)


# Lazy Supabase client (only created when /api/sync is called)
_supabase = None

def _get_supabase():
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise HTTPException(
                status_code=503,
                detail="SUPABASE_URL / SUPABASE_KEY not configured in backend/core/config.py",
            )
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase


class SyncRequest(BaseModel):
    since: Optional[str] = None   # ISO-8601: only sync rows after this timestamp


@router.post("/sync")
def sync_from_supabase(body: SyncRequest = SyncRequest()):
    """
    Pull unsynced snapshots from Supabase and save as local CSVs.
    """
    client = _get_supabase()

    # 1. Fetch unsynced rows
    try:
        query = (
            client.table("option_snapshots")
            .select("id, index_name, expiry_date, captured_at, data")
            .eq("synced", False)
            .order("captured_at", desc=False)
        )
        if body.since:
            query = query.gte("captured_at", body.since)
        result = query.execute()
        snapshots = result.data or []
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Supabase query failed: {exc}")

    if not snapshots:
        return {"synced": 0, "skipped": 0, "message": "No new data in Supabase."}

    # 2. Save each snapshot to disk
    synced_ids  = []
    saved_count = 0
    skip_count  = 0

    for snap in snapshots:
        snap_id     = snap["id"]
        index_name  = snap["index_name"]
        expiry_date = snap["expiry_date"]
        rows        = snap["data"]
        captured_at = snap.get("captured_at", "")

        if not rows:
            synced_ids.append(snap_id)
            skip_count += 1
            continue

        # Build filename from captured_at timestamp
        try:
            ts = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            filename = ts.strftime("%d_%H%M%S") + ".csv"
        except Exception:
            filename = datetime.now().strftime("%d_%H%M%S") + ".csv"

        folder = Path(DATA_DIR) / index_name / expiry_date
        folder.mkdir(parents=True, exist_ok=True)
        filepath = folder / filename

        # Deduplicate — skip if file already exists
        if filepath.exists():
            logger.info("[SYNC] Skip (exists): %s", filepath)
            synced_ids.append(snap_id)
            skip_count += 1
            continue

        # Convert to DataFrame, add GEX if missing
        df = pd.DataFrame(rows)
        if "Total_GEX" not in df.columns and index_name in INDICES:
            df = calculate_gex(df, INDICES[index_name]["lot_size"])

        df.to_csv(filepath, index=False)
        logger.info("[SYNC] Saved: %s", filepath)

        # Update in-memory store so dashboard reflects sync immediately
        store.set_data(index_name, df, str(filepath))

        synced_ids.append(snap_id)
        saved_count += 1

    # 3. Mark all processed rows as synced in Supabase
    if synced_ids:
        try:
            client.table("option_snapshots").update({"synced": True}).in_("id", synced_ids).execute()
            logger.info("[SYNC] Marked %d row(s) as synced.", len(synced_ids))
        except Exception as exc:
            logger.warning("[SYNC] Failed to mark rows as synced: %s", exc)

    return {
        "synced":  saved_count,
        "skipped": skip_count,
        "total":   len(snapshots),
        "message": f"Saved {saved_count} new snapshot(s), skipped {skip_count} duplicate(s).",
    }
