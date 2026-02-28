"""
scheduler.py — APScheduler background job for the Render service.
Runs collect_all() every COLLECT_INTERVAL_MINS during NSE market hours.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import config
import collector
import db

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def _collection_job():
    """Scheduled task: collect data if in market hours."""
    if not collector.is_market_hours(
        config.MARKET_OPEN_H,  config.MARKET_OPEN_M,
        config.MARKET_CLOSE_H, config.MARKET_CLOSE_M,
    ):
        logger.info("[SCHEDULER] Outside market hours, skipping.")
        return

    logger.info("[SCHEDULER] Market hours active — starting collection cycle.")
    client = db.get_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    # Always pull the latest token from DB (updated daily via POST /set-token)
    token = db.get_token(client) or config.UPSTOX_ACCESS_TOKEN
    if not token:
        logger.error("[SCHEDULER] No access token available. Skipping.")
        return

    snapshots = collector.collect_all(
        token=token,
        api_url=config.API_URL,
        indices=config.INDICES,
        radius=config.FILTER_STRIKES_RADIUS,
        cutoff=config.CUTOFF_HOUR,
    )

    if snapshots:
        inserted = db.insert_snapshots(client, snapshots)
        logger.info("[SCHEDULER] Inserted %d snapshot(s) into Supabase.", inserted)
    else:
        logger.warning("[SCHEDULER] No data collected this cycle.")


def start():
    """Start the APScheduler background scheduler."""
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _collection_job,
        trigger=IntervalTrigger(minutes=config.COLLECT_INTERVAL_MINS),
        id="collect_option_chain",
        name="Option Chain Collector",
        replace_existing=True,
        max_instances=1,   # Never overlap runs
    )
    _scheduler.start()
    logger.info(
        "[SCHEDULER] Started. Will collect every %d min during market hours.",
        config.COLLECT_INTERVAL_MINS,
    )


def stop():
    """Shutdown the scheduler cleanly."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] Stopped.")
