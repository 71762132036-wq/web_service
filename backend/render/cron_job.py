"""
cron_job.py — One-shot collection script for Render Cron Jobs.

Render runs this every 15 minutes via cron schedule.
The script checks market hours itself and exits early if outside them.
Data is saved to Supabase. No web server needed.

Run locally:  python cron_job.py
"""
import logging
import os
import sys

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("cron_job")

# ---------------------------------------------------------------------------
# Validate env vars early
# ---------------------------------------------------------------------------
SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")
ACCESS_TOKEN  = os.environ.get("UPSTOX_ACCESS_TOKEN", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("SUPABASE_URL or SUPABASE_KEY not set. Exiting.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Imports (after env check)
# ---------------------------------------------------------------------------
import config
import collector
import db


def main():
    # 1. Market hours check — exit early if outside Mon–Fri 09:30–15:30 IST
    if not collector.is_market_hours(
        config.MARKET_OPEN_H,  config.MARKET_OPEN_M,
        config.MARKET_CLOSE_H, config.MARKET_CLOSE_M,
    ):
        logger.info("Outside market hours. Nothing to collect. Exiting.")
        sys.exit(0)

    logger.info("Market hours active — starting collection.")

    # 2. Connect to Supabase
    client = db.get_client(config.SUPABASE_URL, config.SUPABASE_KEY)

    # 3. Get access token — prefer DB token (updated daily via /set-token), fallback to env
    token = db.get_token(client) or config.UPSTOX_ACCESS_TOKEN
    if not token:
        logger.error("No Upstox access token available. Set it via POST /set-token or UPSTOX_ACCESS_TOKEN env var.")
        sys.exit(1)

    # 4. Collect all indices
    snapshots = collector.collect_all(
        token=token,
        api_url=config.API_URL,
        indices=config.INDICES,
        radius=config.FILTER_STRIKES_RADIUS,
        cutoff=config.CUTOFF_HOUR,
    )

    if not snapshots:
        logger.warning("No snapshots collected (API error or empty data).")
        sys.exit(0)

    # 5. Insert into Supabase
    inserted = db.insert_snapshots(client, snapshots)
    logger.info("Done. Inserted %d snapshot(s) into Supabase.", inserted)


if __name__ == "__main__":
    main()
