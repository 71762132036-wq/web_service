"""
sync.py — Local app router for syncing data directly from Supabase.

The Render Cron Job writes snapshots to Supabase every 15 min.
This endpoint pulls unsynced rows, converts them to local CSVs,
then marks them as synced in Supabase.

Route: POST /api/sync
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client

import store
from core.config import (
    DATA_DIR, INDICES,
    SUPABASE_URL, SUPABASE_KEY,
)

# ---------------------------------------------------------------------------
# Sync state — persists the latest captured_at we have synced so the next
# sync only fetches rows we haven't seen yet.  Falls back to 7 days if the
# state file is missing (first run / fresh install).
# ---------------------------------------------------------------------------
_STATE_FILE = Path(DATA_DIR) / ".sync_state.json"
_FALLBACK_DAYS = 7   # how far back to look when no state exists


def _load_since() -> str:
    """Return the timestamp to start fetching from."""
    if _STATE_FILE.exists():
        try:
            state = json.loads(_STATE_FILE.read_text())
            ts = state.get("last_captured_at", "")
            if ts:
                return ts
        except Exception:
            pass
    # No state → fall back to N days ago so a fresh install catches up
    return (datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(days=_FALLBACK_DAYS)).isoformat()


def _save_since(latest_captured_at: str) -> None:
    """Persist the latest captured_at after a successful sync."""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps({"last_captured_at": latest_captured_at}))
    except Exception as exc:
        logger.warning("[SYNC] Could not save sync state: %s", exc)
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


# Done


@router.post("/sync")
def sync_from_supabase(body: SyncRequest = SyncRequest()):
    """
    Pull unsynced snapshots from Supabase and save as local CSVs.
    """
    logger.info("[SYNC] Sync started")

    # 1. Connect & query Supabase
    logger.info("[SYNC] Connecting to Supabase…")
    try:
        client = _get_supabase()
    except Exception as exc:
        logger.error("[SYNC] ✗ Connection failed: %s", exc)
        raise

    logger.info("[SYNC] Querying pending snapshots (paginated)…")
    try:
        # Use caller-supplied timestamp, or pick up from where we last left off.
        # _load_since() returns the latest captured_at from the previous sync,
        # so repeated syncs are always incremental regardless of how many days
        # have passed.  A fresh install falls back to _FALLBACK_DAYS ago.
        since_ts = body.since if body.since else _load_since()
        logger.info("[SYNC] Fetching rows with captured_at >= %s", since_ts[:19])

        PAGE_SIZE = 500
        snapshots: list = []
        offset = 0

        while True:
            page = (
                client.table("option_snapshots")
                .select("id, index_name, expiry_date, captured_at, data")
                .gte("captured_at", since_ts)
                .order("captured_at", desc=False)
                .range(offset, offset + PAGE_SIZE - 1)
                .execute()
            )
            rows = page.data or []
            snapshots.extend(rows)
            logger.info("[SYNC] Page fetched: %d row(s) (total so far: %d)", len(rows), len(snapshots))

            if len(rows) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

    except Exception as exc:
        logger.error("[SYNC] ✗ Supabase query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Supabase query failed: {exc}")

    logger.info("[SYNC] Found %d pending snapshot(s) in total", len(snapshots))

    if not snapshots:
        logger.info("[SYNC] Nothing to sync — all up to date")
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

        logger.info("[SYNC] [%d/%d] %s | captured_at=%s", i, total, index_name, captured_at)

        if not rows:
            logger.warning("[SYNC] Empty payload for %s, skipping", snap_id)
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
            # Round down to the nearest 15-minute interval
            rounded_minute = (ts_ist.minute // 15) * 15
            ts_ist = ts_ist.replace(minute=rounded_minute, second=0, microsecond=0)
            filename = ts_ist.strftime("%d_%H%M%S") + ".parquet"
        except Exception:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            rounded_minute = (now.minute // 15) * 15
            now = now.replace(minute=rounded_minute, second=0, microsecond=0)
            filename = now.strftime("%d_%H%M%S") + ".parquet"

        folder = Path(DATA_DIR) / index_name / expiry_date
        folder.mkdir(parents=True, exist_ok=True)
        filepath = folder / filename

        # Deduplicate — skip if file already exists
        if filepath.exists():
            logger.info("[SYNC] Already exists, skipping: %s", filename)
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
        logger.debug("[SYNC] Saved: %s (%d strikes)", filename, len(df))
        logger.info("[SYNC] Saved: %s", filepath)

        # Update in-memory store so dashboard reflects sync immediately
        store.set_data(index_name, df, str(filepath))

        synced_ids.append(snap_id)
        saved_count += 1

    # 3. Persist the latest captured_at so the next sync starts from here.
    if snapshots:
        latest_captured_at = max(s.get("captured_at", "") for s in snapshots)
        if latest_captured_at:
            _save_since(latest_captured_at)
            logger.info("[SYNC] Sync state saved: last_captured_at=%s", latest_captured_at[:19])

    # 5. Delete processed rows from Supabase in chunks to avoid URL length limits.
    # Supabase's .in_() becomes a query-string list; >500 IDs blows the URL limit.
    CHUNK = 400
    if synced_ids:
        logger.info("[SYNC] Deleting %d row(s) from Supabase in chunks of %d…", len(synced_ids), CHUNK)
        deleted = 0
        for i in range(0, len(synced_ids), CHUNK):
            chunk = synced_ids[i : i + CHUNK]
            try:
                client.table("option_snapshots").delete().in_("id", chunk).execute()
                deleted += len(chunk)
            except Exception as exc:
                logger.warning("[SYNC] Chunk delete failed (ids %d-%d): %s", i, i + len(chunk), exc)
        logger.info("[SYNC] Deleted %d row(s) from Supabase.", deleted)

    logger.info("[SYNC] ■ Sync complete — saved=%d, skipped=%d, total=%d", saved_count, skip_count, total)

    return {
        "synced":  saved_count,
        "skipped": skip_count,
        "total":   len(snapshots),
        "message": f"Saved {saved_count} new snapshot(s), skipped {skip_count} duplicate(s).",
    }
