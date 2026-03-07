"""GET /api/indices — list available indices and their metadata."""

from fastapi import APIRouter

from core.config import DEFAULT_INDEX, INDICES, STOCKS

router = APIRouter(prefix="/api", tags=["indices"])


@router.get("/indices")
def list_indices():
    """Return all configured indices and stocks with metadata."""
    all_instruments = {**INDICES, **STOCKS}
    return {
        "indices": list(all_instruments.keys()),
        "default": DEFAULT_INDEX,
        "metadata": {
            name: {
                "lot_size":    cfg["lot_size"],
                "expiry_type": cfg["expiry_type"],
                "type":        "stock" if name in STOCKS else "index",
            }
            for name, cfg in all_instruments.items()
        },
    }

@router.get("/indices/status")
def indices_status():
    """Return the current load status and metadata for all indices and stocks."""
    import store
    all_instruments = {**INDICES, **STOCKS}
    return {
        "status": {
            name: {
                "hasData": store.has_data(name),
                "filepath": store.get_filepath(name),
            }
            for name in all_instruments
        }
    }
