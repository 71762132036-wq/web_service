"""
Export router — download the active DataFrame as CSV.
Route: GET /api/export/{index}
"""

import io
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import store
from core.config import INDICES

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export/{index}")
def export_csv(index: str):
    """Stream the loaded DataFrame as a CSV file download."""
    if index not in INDICES:
        raise HTTPException(status_code=404, detail=f"Unknown index: {index}")
    if not store.has_data(index):
        raise HTTPException(status_code=404, detail="No data loaded for this index")

    df = store.get_data(index)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{index.lower()}_analysis_{timestamp}.csv"

    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
