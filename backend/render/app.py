"""
app.py — FastAPI application for the Render remote collector service.

Endpoints
---------
POST /set-token          Update the stored Upstox access token
GET  /data               Retrieve unsynced snapshots (supports ?since=<ISO timestamp>)
DELETE /data             Mark snapshots as synced after local app downloads them
GET  /health             Liveness probe for Render
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
import db
import scheduler

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("render_collector")


# ---------------------------------------------------------------------------
# Lifespan — start/stop scheduler with the app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Render collector service…")
    scheduler.start()
    yield
    scheduler.stop()
    logger.info("Render collector service stopped.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="GC Gamma — Render Collector",
    description="Remote option chain data collector + sync API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten in production if needed
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client (reused across requests)
_supabase = db.get_client(config.SUPABASE_URL, config.SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class SetTokenRequest(BaseModel):
    token: str

class DeleteDataRequest(BaseModel):
    ids: list[int]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "render-collector"}


@app.post("/set-token")
def set_token(body: SetTokenRequest):
    """Save / update the Upstox access token in Supabase."""
    ok = db.set_token(_supabase, body.token)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save token")
    logger.info("Access token updated.")
    return {"success": True, "message": "Token saved"}


@app.get("/data")
def get_data(since: Optional[str] = Query(None, description="ISO-8601 timestamp — only return rows after this")):
    """
    Return all unsynced option chain snapshots.
    Optionally filter to rows captured after `since`.
    """
    rows = db.get_unsynced(_supabase, since=since)
    return {
        "count": len(rows),
        "since": since,
        "snapshots": rows,
    }


@app.delete("/data")
def delete_data(body: DeleteDataRequest):
    """
    Mark the provided snapshot IDs as synced.
    The local app calls this after successfully saving the CSV files.
    """
    if not body.ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    ok = db.mark_synced(_supabase, body.ids)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to mark rows as synced")
    return {"success": True, "synced_count": len(body.ids)}
