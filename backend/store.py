"""
In-memory data store — holds the active DataFrame per index.
Acts as a lightweight session replacement for Streamlit's session_state.
"""

from __future__ import annotations
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
