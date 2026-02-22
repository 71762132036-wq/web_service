"""
FastAPI entry point — mounts all routers, CORS, and serves the frontend.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import analysis, charts, data, export, indices

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Index Gamma Exposure API",
    description="REST API for option chain gamma exposure analysis (Nifty, BankNifty, Sensex)",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS — allow browser requests from any origin (dev convenience)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(indices.router)
app.include_router(data.router)
app.include_router(analysis.router)
app.include_router(charts.router)
app.include_router(export.router)

# ---------------------------------------------------------------------------
# Health check  (must be BEFORE the static file mount)
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Gamma Exposure API"}


# ---------------------------------------------------------------------------
# Serve frontend static files (catch-all — must be LAST)
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
