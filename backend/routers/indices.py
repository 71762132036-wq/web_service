"""GET /api/indices — list available indices and their metadata."""

from fastapi import APIRouter

from core.config import DEFAULT_INDEX, INDICES

router = APIRouter(prefix="/api", tags=["indices"])


@router.get("/indices")
def list_indices():
    """Return all configured indices with metadata."""
    return {
        "indices": list(INDICES.keys()),
        "default": DEFAULT_INDEX,
        "metadata": {
            name: {
                "lot_size":    cfg["lot_size"],
                "expiry_type": cfg["expiry_type"],
            }
            for name, cfg in INDICES.items()
        },
    }

@router.get("/indices/status")
def indices_status():
    """Return the current load status and metadata for all indices."""
    import store
    return {
        "status": {
            name: {
                "hasData": store.has_data(name),
                "filepath": store.get_filepath(name),
            }
            for name in INDICES
        }
    }
