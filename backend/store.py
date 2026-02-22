"""
In-memory data store — holds the active DataFrame per index.
Acts as a lightweight session replacement for Streamlit's session_state.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import pandas as pd

# { index_name: {"df": DataFrame, "filepath": str} }
_store: dict = {}


def set_data(index_name: str, df: pd.DataFrame, filepath: str = "") -> None:
    _store[index_name] = {"df": df, "filepath": filepath}


def get_data(index_name: str) -> Optional[pd.DataFrame]:
    entry = _store.get(index_name)
    return entry["df"] if entry else None


def get_filepath(index_name: str) -> str:
    entry = _store.get(index_name)
    return entry["filepath"] if entry else ""


def clear_data(index_name: str) -> None:
    _store.pop(index_name, None)


def has_data(index_name: str) -> bool:
    return index_name in _store and _store[index_name]["df"] is not None

def initialize_from_disk() -> None:
    """Bootstrap the store by loading the latest file for each index from disk."""
    from core.config import INDICES
    from services.upstox_service import get_available_files, load_data_file
    from services.calculations import calculate_gex
    
    # Base data directory (sibling of web_app)
    DATA_DIR = str(Path(__file__).parent.parent.parent / "streamlit_app" / "data")
    
    print("[BOOTSTRAP] Initializing store from disk...")
    
    for index_name in INDICES:
        try:
            files_dict = get_available_files(index_name, data_dir=DATA_DIR)
            if not files_dict:
                continue
                
            # Get latest expiry and latest file
            latest_expiry = sorted(files_dict.keys(), reverse=True)[0]
            latest_file = files_dict[latest_expiry][0]
            
            filepath = Path(DATA_DIR) / index_name / latest_expiry / latest_file
            if not filepath.exists():
                filepath = Path(DATA_DIR) / latest_expiry / latest_file # fallback
                
            if filepath.exists():
                df, error = load_data_file(str(filepath))
                if not error:
                    # Ensure GEX is calculated for legacy files
                    if "Total_GEX" not in df.columns:
                        lot_size = INDICES[index_name]["lot_size"]
                        df = calculate_gex(df, lot_size)
                        
                    set_data(index_name, df, str(filepath))
                    print(f"[BOOTSTRAP] Successfully auto-loaded {index_name} from {filepath.name}")
        except Exception as e:
            print(f"[BOOTSTRAP] Error auto-loading {index_name}: {e}")
