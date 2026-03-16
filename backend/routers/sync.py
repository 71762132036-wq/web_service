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

# ---------------------------------------------------------------------------
# Column order helpers
#
# We record the "canonical" column ordering used by the live-fetcher so that
# snapshots pulled from the database are written with the same header.  The
# Supabase JSON API tends to reorder object keys (often alphabetically) which
# caused files saved by /api/sync to have columns shuffled, leading to
# misleading comparisons and mismatched data when loading multiple sources.
#
_canonical_cols: list[str] | None = None

def _get_canonical_cols() -> list[str]:
    """Return a list of columns in the order produced by fetch_option_chain_data.
    Cached after the first call; if the API fails we fall back to an empty list.
    """
    global _canonical_cols
    if _canonical_cols is None:
        try:
            from services.upstox_service import fetch_option_chain_data
            df, err = fetch_option_chain_data("Nifty")
            if df is not None:
                _canonical_cols = df.columns.tolist()
            else:
                _canonical_cols = []
        except Exception:
            _canonical_cols = []
    return _canonical_cols


def _reorder_df(df: pd.DataFrame) -> pd.DataFrame:
    """Reorder columns to match canonical order, preserving any extras at end."""
    cols = _get_canonical_cols()
    if not cols:
        return df
    ordered = [c for c in cols if c in df.columns]
    ordered += [c for c in df.columns if c not in ordered]
    return df[ordered]

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


def _plog(msg: str) -> None:
    """Print a timestamped progress line to the terminal (visible in uvicorn output)."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%H:%M:%S")
    # print(f"[SYNC {now}] {msg}", flush=True)


@router.post("/sync")
def sync_from_supabase(body: SyncRequest = SyncRequest()):
    """
    Pull unsynced snapshots from Supabase and save as local CSVs.
    """
    _plog("▶ Sync started")

    # 1. Connect & query Supabase
    _plog("Connecting to Supabase…")
    try:
        client = _get_supabase()
    except Exception as exc:
        _plog(f"✗ Connection failed: {exc}")
        raise

    _plog("Querying pending snapshots (paginated)…")
    try:
        from zoneinfo import ZoneInfo
        today_str = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")

        PAGE_SIZE = 500          # well below Supabase's 1000-row cap
        snapshots: list = []
        offset = 0

        while True:
            base_query = (
                client.table("option_snapshots")
                .select("id, index_name, expiry_date, captured_at, data")
                .gte("expiry_date", today_str)
                .order("captured_at", desc=False)
            )
            if body.since:
                base_query = base_query.gte("captured_at", body.since)

            page = base_query.range(offset, offset + PAGE_SIZE - 1).execute()
            rows = page.data or []
            snapshots.extend(rows)
            _plog(f"  Page fetched: {len(rows)} row(s)  (total so far: {len(snapshots)})")

            if len(rows) < PAGE_SIZE:
                break   # last page — no more rows
            offset += PAGE_SIZE

    except Exception as exc:
        _plog(f"✗ Supabase query failed: {exc}")
        raise HTTPException(status_code=502, detail=f"Supabase query failed: {exc}")

    _plog(f"Found {len(snapshots)} pending snapshot(s) in total")

    if not snapshots:
        _plog("Nothing to sync — all up to date")
        return {"synced": 0, "skipped": 0, "message": "No new data in Supabase."}

    # 2. Save each snapshot to disk
    synced_ids  = []
    saved_count = 0
    skip_count  = 0
    total       = len(snapshots)

    for i, snap in enumerate(snapshots, start=1):
        snap_id     = snap["id"]
        index_name  = snap["index_name"]
        expiry_date = snap["expiry_date"]
        rows        = snap["data"]
        captured_at = snap.get("captured_at", "")

        _plog(f"[{i}/{total}] {index_name} | captured_at={captured_at}")

        if not rows:
            _plog(f"  → Empty payload, skipping")
            synced_ids.append(snap_id)
            skip_count += 1
            continue

        # Build filename from captured_at.
        # Supabase REST API always returns timestamptz as UTC regardless of the
        # timezone-aware value inserted — so we must always convert to IST here.
        try:
            from datetime import timezone as _tz
            from zoneinfo import ZoneInfo as _ZI
            ts = datetime.fromisoformat(captured_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_tz.utc)   # treat naive as UTC
            ts_ist = ts.astimezone(_ZI("Asia/Kolkata"))
            filename = ts_ist.strftime("%d_%H%M%S") + ".parquet"
        except Exception:
            from zoneinfo import ZoneInfo
            filename = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d_%H%M%S") + ".parquet"

        folder = Path(DATA_DIR) / index_name / expiry_date
        folder.mkdir(parents=True, exist_ok=True)
        filepath = folder / filename

        # Deduplicate — skip if file already exists
        if filepath.exists():
            _plog(f"  → Already exists, skipping: {filename}")
            logger.info("[SYNC] Skip (exists): %s", filepath)
            synced_ids.append(snap_id)
            skip_count += 1
            continue

        # Convert to DataFrame and force canonical column order before saving
        df = pd.DataFrame(rows)
        df = _reorder_df(df)
        if "Total_GEX" not in df.columns and index_name in INDICES:
            df = calculate_gex(df, INDICES[index_name]["lot_size"])
            df = _reorder_df(df)

        df.to_parquet(filepath, engine="pyarrow", index=False)
        _plog(f"  → Saved: {filename}  ({len(df)} strikes)")
        logger.info("[SYNC] Saved: %s", filepath)

        # Update in-memory store so dashboard reflects sync immediately
        store.set_data(index_name, df, str(filepath))

        synced_ids.append(snap_id)
        saved_count += 1

    # 3. Delete all processed rows from Supabase to keep the table lean
    if synced_ids:
        _plog(f"Deleting {len(synced_ids)} row(s) from Supabase…")
        try:
            client.table("option_snapshots").delete().in_("id", synced_ids).execute()
            _plog(f"✓ Deleted {len(synced_ids)} row(s)")
            logger.info("[SYNC] Deleted %d row(s) from Supabase.", len(synced_ids))
        except Exception as exc:
            _plog(f"⚠ Failed to delete rows: {exc}")
            logger.warning("[SYNC] Failed to delete rows: %s", exc)

    _plog(f"■ Sync complete — saved={saved_count}, skipped={skip_count}, total={total}")

    return {
        "synced":  saved_count,
        "skipped": skip_count,
        "total":   len(snapshots),
        "message": f"Saved {saved_count} new snapshot(s), skipped {skip_count} duplicate(s).",
    }
