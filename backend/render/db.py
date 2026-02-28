"""
db.py — Supabase client wrapper for option_snapshots and tokens tables.
"""
from __future__ import annotations

import logging
from typing import Optional

from supabase import create_client, Client

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def get_client(url: str, key: str) -> Client:
    global _client
    if _client is None:
        _client = create_client(url, key)
    return _client


# ---------------------------------------------------------------------------
# Tokens table
# ---------------------------------------------------------------------------

def get_token(client: Client) -> Optional[str]:
    """Retrieve the stored Upstox access token."""
    try:
        res = client.table("tokens").select("token").eq("id", 1).execute()
        if res.data:
            return res.data[0]["token"]
    except Exception as exc:
        logger.error("get_token failed: %s", exc)
    return None


def set_token(client: Client, token: str) -> bool:
    """Upsert the Upstox access token (id=1 is the single row)."""
    try:
        client.table("tokens").upsert(
            {"id": 1, "token": token, "updated_at": "now()"}
        ).execute()
        return True
    except Exception as exc:
        logger.error("set_token failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# option_snapshots table
# ---------------------------------------------------------------------------

def insert_snapshots(client: Client, snapshots: list[dict]) -> int:
    """
    Insert a list of snapshots.
    Each snapshot: {"index_name": str, "expiry_date": str, "data": list[dict]}
    Returns number of rows inserted.
    """
    if not snapshots:
        return 0
    rows = [
        {
            "index_name":  s["index_name"],
            "expiry_date": s["expiry_date"],
            "data":        s["data"],
            "synced":      False,
        }
        for s in snapshots
    ]
    try:
        res = client.table("option_snapshots").insert(rows).execute()
        count = len(res.data) if res.data else 0
        logger.info("Inserted %d snapshot rows", count)
        return count
    except Exception as exc:
        logger.error("insert_snapshots failed: %s", exc)
        return 0


def get_unsynced(client: Client, since: Optional[str] = None) -> list[dict]:
    """
    Return all unsynced snapshots.
    Optional `since`: ISO-8601 timestamp — only return rows captured after this time.
    """
    try:
        query = (
            client.table("option_snapshots")
            .select("id, index_name, expiry_date, captured_at, data")
            .eq("synced", False)
            .order("captured_at", desc=False)
        )
        if since:
            query = query.gte("captured_at", since)
        res = query.execute()
        return res.data or []
    except Exception as exc:
        logger.error("get_unsynced failed: %s", exc)
        return []


def mark_synced(client: Client, ids: list[int]) -> bool:
    """Mark the given snapshot IDs as synced=True."""
    if not ids:
        return True
    try:
        client.table("option_snapshots").update({"synced": True}).in_("id", ids).execute()
        logger.info("Marked %d rows as synced", len(ids))
        return True
    except Exception as exc:
        logger.error("mark_synced failed: %s", exc)
        return False
