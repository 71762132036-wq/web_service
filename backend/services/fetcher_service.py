"""
Fetcher service — manages background periodic data retrieval.
"""

import asyncio
import socket
import logging
from datetime import datetime

from core.config import AUTO_FETCH, FETCH_INTERVAL_MINS, INDICES, DATA_DIR, FILTER_STRIKES_RADIUS
from services.upstox_service import fetch_option_chain_data, save_data, filter_near_strikes

import os
from pathlib import Path

# Setup simple logging to both console and file
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "fetcher.log"

logger = logging.getLogger("fetcher")
logger.setLevel(logging.INFO)

# Avoid adding multiple handlers if the module is reloaded
if not logger.handlers:
    # Console Handler
    c_handler = logging.StreamHandler()
    c_format  = logging.Formatter('%(asctime)s - FETCH - %(levelname)s - %(message)s')
    c_handler.setFormatter(c_format)
    logger.addHandler(c_handler)

    # File Handler
    f_handler = logging.FileHandler(LOG_FILE)
    f_format  = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    f_handler.setFormatter(f_format)
    logger.addHandler(f_handler)

# Ensure it doesn't propagate to root to avoid double logging if uvicorn is active
logger.propagate = False

def is_internet_available(host="api.upstox.com", port=443, timeout=5):
    """
    Check if internet is available by attempting to connect to the API host.
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False

async def run_auto_fetcher():
    """
    Background loop that fetches live data every N minutes.
    """
    if not AUTO_FETCH:
        logger.info("Auto-fetch is disabled in config.")
        return

    logger.info(f"Starting auto-fetcher. Interval: {FETCH_INTERVAL_MINS} minutes.")
    
    # Wait a bit on startup to let the server initialize
    await asyncio.sleep(5)

    while True:
        try:
            # 1. Calculate time until next aligned slot
            now_ts = datetime.now().timestamp()
            interval_sec = FETCH_INTERVAL_MINS * 60
            sleep_sec = interval_sec - (now_ts % interval_sec)
            
            # Avoid sleeping less than 1 second to prevent tight loops if tiny diff
            if sleep_sec < 1:
                sleep_sec = interval_sec

            logger.info(f"Next auto-fetch in {int(sleep_sec/60)}m {int(sleep_sec%60)}s (aligned to {FETCH_INTERVAL_MINS}m clock).")
            await asyncio.sleep(sleep_sec)

            now = datetime.now()
            logger.info(f"Auto-fetch cycle triggered at {now.strftime('%Y-%m-%d %H:%M:%S')}")

            if not is_internet_available():
                logger.warning("Connection to api.upstox.com failed. Skipping this fetch cycle.")
            else:
                for index_name in INDICES.keys():
                    logger.info(f"Auto-fetching data for {index_name}...")
                    
                    df, err = fetch_option_chain_data(index_name)
                    if err:
                        logger.error(f"Failed to fetch {index_name}: {err}")
                        continue
                    
                    if df is not None and not df.empty:
                        # APPLY FILTERING HERE
                        df_filtered = filter_near_strikes(df, FILTER_STRIKES_RADIUS)
                        
                        path = save_data(df_filtered, index_name, data_dir=DATA_DIR)
                        logger.info(f"Successfully saved {index_name} data (filtered ±{FILTER_STRIKES_RADIUS}) to {path}")
                        
                        # Auto-load into store so dashboard metrics/charts update automatically
                        import store
                        from services.calculations import calculate_gex
                        
                        lot_size = INDICES[index_name]["lot_size"]
                        df_with_gex = calculate_gex(df_filtered, lot_size)
                        store.set_data(index_name, df_with_gex, path)
                        logger.info(f"Updated in-memory store for {index_name}")
                    else:
                        logger.warning(f"No data received for {index_name}")

            logger.info(f"Fetch cycle complete. Waiting for next aligned slot.")

        except Exception as e:
            logger.exception(f"Unexpected error in auto-fetcher loop: {e}")
            # Protect against tight loop in case of continuous error
            await asyncio.sleep(60)
