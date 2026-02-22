/**
 * data-management.js — Data Management page.
 * Fetch live data for all indices, list and load saved files.
 * Mirrors streamlit show_data_management().
 */

const DataManagementPage = (() => {

  // ── Helpers ───────────────────────────────────────────

  function buildFetchSection() {
    return `
      <div class="card">
        <div class="card-title">📥 Fetch Live Data</div>
        <div class="alert alert-info" style="margin-bottom:16px;">
          ℹ️ Fetches data from Upstox API for <strong>all indices</strong> simultaneously
          and auto-loads the result.
        </div>
        <button class="btn btn-primary btn-full" id="btn-fetch-all">
          🔄 Fetch Data for All Indices
        </button>
        <div id="fetch-results" style="margin-top:14px;"></div>
      </div>`;
  }

  function buildLoadSection(index) {
    return `
      <div class="card">
        <div class="card-title">📂 Load ${index} Data</div>
        <div id="load-form">
          <div class="loading-overlay"><div class="spinner"></div> Loading files…</div>
        </div>
      </div>`;
  }

  function buildLoadForm(filesDict) {
    const expiries = Object.keys(filesDict).sort().reverse();

    if (!expiries.length) {
      return `
        <div class="alert alert-warning">
          📭 No data files found. Fetch data first!
        </div>`;
    }

    const expiryOptions = expiries.map(e =>
      `<option value="${e}">${e}</option>`).join('');

    const firstExpiry = expiries[0];
    const fileOptions = (filesDict[firstExpiry] || []).map(f =>
      `<option value="${f}">${f}</option>`).join('');

    return `
      <div class="form-group">
        <label>Expiry Date</label>
        <select class="form-select" id="select-expiry">${expiryOptions}</select>
      </div>
      <div class="form-group">
        <label>File</label>
        <select class="form-select" id="select-file">${fileOptions}</select>
      </div>
      <button class="btn btn-primary btn-full" id="btn-load">
        📂 Load Selected File
      </button>
      <div id="load-result" style="margin-top:12px;"></div>`;
  }

  // ── Render ─────────────────────────────────────────────

  async function render(container) {
    const index = State.getIndex();

    container.innerHTML = `
      <div class="section-header">
        <h2>⚙️ Data Management</h2><div class="section-line"></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start;">
        ${buildFetchSection()}
        ${buildLoadSection(index)}
      </div>`;

    _wireFetchButton();
    await _loadFilesIntoForm(index);
  }

  // ── Fetch button ───────────────────────────────────────

  function _wireFetchButton() {
    const btn = document.getElementById('btn-fetch-all');
    if (!btn) return;

    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.innerHTML = '<div class="spinner"></div> Fetching…';
      const resultsEl = document.getElementById('fetch-results');
      resultsEl.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Contacting Upstox API…</div>';

      try {
        const data = await API.fetchLiveData(null);
        const results = data.results || [];
        let html = '';

        results.forEach(r => {
          if (r.success) {
            html += `<div class="alert alert-success">✅ <strong>${r.index}</strong>: ${r.strikes} strikes saved — expiry ${r.expiry}</div>`;
          } else {
            html += `<div class="alert alert-error">❌ <strong>${r.index}</strong>: ${r.error}</div>`;
          }
        });

        resultsEl.innerHTML = html;

        const anySuccess = results.some(r => r.success);
        if (anySuccess) {
          // Mark state as having data for current index if it was in results
          const cur = results.find(r => r.index === State.getIndex() && r.success);
          if (cur) {
            State.set({ hasData: true, loadedFile: cur.filepath, expiry: cur.expiry });
            Toast.show('Data loaded automatically!', 'success');
            App.updateTopbar();

            // Switch to Dashboard automatically
            App.navigate('dashboard');
          }
          // Refresh file list
          await _loadFilesIntoForm(State.getIndex());
        }
      } catch (err) {
        document.getElementById('fetch-results').innerHTML =
          `<div class="alert alert-error">❌ ${err.message}</div>`;
        Toast.show(err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '🔄 Fetch Data for All Indices';
      }
    });
  }

  // ── Load files form ────────────────────────────────────

  async function _loadFilesIntoForm(index) {
    const formEl = document.getElementById('load-form');
    if (!formEl) return;

    try {
      const data = await API.getFiles(index);
      formEl.innerHTML = buildLoadForm(data.files || {});
      _wireExpiry(data.files || {});
      _wireLoadButton(index, data.files || {});
    } catch (err) {
      formEl.innerHTML = `<div class="alert alert-error">❌ ${err.message}</div>`;
    }
  }

  function _wireExpiry(filesDict) {
    const expiryEl = document.getElementById('select-expiry');
    const fileEl = document.getElementById('select-file');
    if (!expiryEl || !fileEl) return;

    expiryEl.addEventListener('change', () => {
      const expiry = expiryEl.value;
      const files = filesDict[expiry] || [];
      fileEl.innerHTML = files.map(f => `<option value="${f}">${f}</option>`).join('');
    });
  }

  function _wireLoadButton(index, filesDict) {
    const btn = document.getElementById('btn-load');
    if (!btn) return;

    btn.addEventListener('click', async () => {
      const expiry = document.getElementById('select-expiry')?.value;
      const filename = document.getElementById('select-file')?.value;
      if (!expiry || !filename) return;

      btn.disabled = true;
      btn.innerHTML = '<div class="spinner"></div> Loading…';

      const resultEl = document.getElementById('load-result');
      try {
        const data = await API.loadFile(index, expiry, filename);
        resultEl.innerHTML = `<div class="alert alert-success">✅ Loaded ${data.strikes} strikes successfully!</div>`;
        State.set({ hasData: true, loadedFile: data.filepath, expiry: data.expiry });
        Toast.show(`${index} data loaded — ${data.strikes} strikes`, 'success');
        App.updateTopbar();

        // Switch to Dashboard automatically
        App.navigate('dashboard');

      } catch (err) {
        resultEl.innerHTML = `<div class="alert alert-error">❌ ${err.message}</div>`;
        Toast.show(err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '📂 Load Selected File';
      }
    });
  }

  return { render };
})();
