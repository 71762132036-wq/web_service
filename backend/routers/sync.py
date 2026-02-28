"""
sync.py — Local app router for syncing data from the Render remote collector.

Route: POST /api/sync
  1. Calls GET <RENDER_URL>/data to fetch unsynced snapshots
  2. Converts each snapshot's data rows to a CSV in backend/data/
  3. Deduplicates by checking if the file already exists
  4. Calls DELETE <RENDER_URL>/data to mark rows as synced
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import store
from core.config import DATA_DIR, INDICES, RENDER_API_URL
from services.calculations import calculate_gex

router = APIRouter(prefix="/api", tags=["sync"])
logger = logging.getLogger(__name__)


class SyncRequest(BaseModel):
    since: Optional[str] = None   # ISO-8601 — only sync rows after this timestamp


@router.post("/sync")
def sync_from_render(body: SyncRequest = SyncRequest()):
    """
    Pull unsynced snapshots from the Render service and save as local CSVs.
    """
    if not RENDER_API_URL:
        raise HTTPException(
            status_code=503,
            detail="RENDER_API_URL is not configured. Set it in core/config.py or as an env var.",
        )

    # 1. Fetch unsynced data from Render
    params = {}
    if body.since:
        params["since"] = body.since

    try:
        resp = requests.get(f"{RENDER_API_URL}/data", params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Render service: {exc}")

    snapshots = payload.get("snapshots", [])
    if not snapshots:
        return {"synced": 0, "skipped": 0, "message": "No new data on Render."}

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
            skip_count += 1
            continue

        # Build target filepath — use captured_at timestamp for the filename
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
            synced_ids.append(snap_id)   # Still mark as synced so Render cleans up
            skip_count += 1
            continue

        # Convert to DataFrame and save
        df = pd.DataFrame(rows)
        if "Total_GEX" not in df.columns and index_name in INDICES:
            lot_size = INDICES[index_name]["lot_size"]
            df = calculate_gex(df, lot_size)

        df.to_csv(filepath, index=False)
        logger.info("[SYNC] Saved: %s", filepath)

        # Auto-load into store (makes dashboard update automatically)
        store.set_data(index_name, df, str(filepath))

        synced_ids.append(snap_id)
        saved_count += 1

    # 3. Mark rows as synced on Render
    if synced_ids:
        try:
            del_resp = requests.delete(
                f"{RENDER_API_URL}/data",
                json={"ids": synced_ids},
                timeout=15,
            )
            del_resp.raise_for_status()
        except Exception as exc:
            logger.warning("[SYNC] DELETE /data failed: %s", exc)
            # Don't fail the whole sync — files are already saved locally

    return {
        "synced":   saved_count,
        "skipped":  skip_count,
        "total":    len(snapshots),
        "message":  f"Saved {saved_count} new snapshot(s), skipped {skip_count} duplicate(s).",
    }
