/**
 * api.js — Typed fetch wrappers for all backend endpoints.
 * All functions return parsed JSON or throw an Error with a message.
 */

const BASE = 'http://localhost:8000';

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// ── Indices ──────────────────────────────────────────────
const API = {

  /** GET /api/health */
  health: () => apiFetch('/api/health'),

  /** GET /api/indices */
  getIndices: () => apiFetch('/api/indices'),

  /** GET /api/next-expiry/{index} */
  getNextExpiry: (index) => apiFetch(`/api/next-expiry/${index}`),

  // ── Data Management ─────────────────────────────────────

  /** GET /api/files/{index} → { files: { [expiry]: [filename, ...] } } */
  getFiles: (index) => apiFetch(`/api/files/${index}`),

  /** POST /api/fetch → fetch live data for one or all indices */
  fetchLiveData: (indices = null) =>
    apiFetch('/api/fetch', {
      method: 'POST',
      body: JSON.stringify({ indices }),
    }),

  /** POST /api/load → load a saved file into the store */
  loadFile: (index, expiry, filename) =>
    apiFetch('/api/load', {
      method: 'POST',
      body: JSON.stringify({ index, expiry, filename }),
    }),

  // ── Analysis ────────────────────────────────────────────

  /** GET /api/metrics/{index} */
  getMetrics: (index) => apiFetch(`/api/metrics/${index}`),

  /** GET /api/vol-surface/{index} */
  getVolSurface: (index) => apiFetch(`/api/vol-surface/${index}`),

  /** GET /api/data-table/{index}?limit=N */
  getDataTable: (index, limit = 40) =>
    apiFetch(`/api/data-table/${index}?limit=${limit}`),

  /** GET /api/stats/{index} */
  getStats: (index) => apiFetch(`/api/stats/${index}`),

  // ── Charts ──────────────────────────────────────────────

  /** GET /api/charts/{index}/{chart_type} → { figure: "plotly-json-string" } */
  getChart: (index, chartType) =>
    apiFetch(`/api/charts/${index}/${chartType}`),

  // ── Export ──────────────────────────────────────────────

  /** GET /api/export/{index} — triggers browser download */
  exportCSV: (index) => {
    const a = document.createElement('a');
    a.href = `${BASE}/api/export/${index}`;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
  },
};
