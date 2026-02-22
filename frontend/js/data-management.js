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
        <div class="card-title">Fetch Live Data</div>
        <div class="alert alert-info" style="margin-bottom:16px;">
          Fetches data from Upstox API for <strong>all indices</strong> simultaneously
          and auto-loads the result.
        </div>
        <button class="btn btn-primary btn-full" id="btn-fetch-all">
          Fetch Data for All Indices
        </button>
        <div id="fetch-results" style="margin-top:14px;"></div>
      </div>`;
  }

  function buildLoadSection(index) {
    return `
      <div class="card">
        <div class="card-title">Load ${index} Data</div>
        <div id="load-form">
          <div class="loading-overlay"><div class="spinner"></div> Loading files…</div>
        </div>
      </div>`;
  }

  function buildLoadForm(filesDict, index) {
    const expiries = Object.keys(filesDict).sort().reverse();
    if (!expiries.length) return '<div class="alert alert-info">No saved data found for this index.</div>';

    const indexData = State.getIndexData(index);
    const selExpiry = indexData.selectedExpiry || expiries[0];
    const files = filesDict[selExpiry] || [];
    const selFile = indexData.selectedFile || (files.length ? files[0] : '');

    return `
      <div class="form-group">
        <label for="select-expiry">Select Expiry</label>
        <select id="select-expiry" class="styled-select">
          ${expiries.map(e => `<option value="${e}" ${e === selExpiry ? 'selected' : ''}>${e}</option>`).join('')}
        </select>
      </div>

      <div class="form-group" style="margin-top:16px;">
        <label for="select-file">Select Data Point (Timestamp)</label>
        <select id="select-file" class="styled-select">
          ${files.map(f => `<option value="${f}" ${f === selFile ? 'selected' : ''}>${f}</option>`).join('')}
        </select>
      </div>
      <button class="btn btn-primary btn-full" id="btn-load" style="margin-top:20px;">
        Load Selected File
      </button>
      <div id="load-result" style="margin-top:16px;"></div>
    `;
  }

  // ── Render ─────────────────────────────────────────────

  async function render(container) {
    const index = State.getIndex();

    container.innerHTML = `
      <div class="section-header">
        <h2>Data Management</h2><div class="section-line"></div>
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
            html += `<div class="alert alert-success"><strong>${r.index}</strong>: ${r.strikes} strikes saved — expiry ${r.expiry}</div>`;
          } else {
            html += `<div class="alert alert-error"><strong>${r.index}</strong>: ${r.error}</div>`;
          }
        });

        resultsEl.innerHTML = html;
        const anySuccess = results.some(r => r.success);

        if (anySuccess) {
          // Update state for ALL successful results in the batch
          results.forEach(r => {
            if (r.success) {
              State.setIndexData(r.index, { hasData: true, loadedFile: r.filepath, expiry: r.expiry });
            }
          });

          Toast.show('Data updated for all indices!', 'success');
          App.updateTopbar();

          // If current index was successful, we might want to refresh current view
          const curIndex = State.getIndex();
          if (results.some(r => r.index === curIndex && r.success)) {
            await _loadFilesIntoForm(curIndex);
          }
        }
      } catch (err) {
        document.getElementById('fetch-results').innerHTML = `<div class="alert alert-error">${err.message}</div>`;
        Toast.show(err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = 'Fetch Data for All Indices';
      }
    });
  }

  // ── Load files form ────────────────────────────────────

  async function _loadFilesIntoForm(index) {
    const formEl = document.getElementById('load-form');
    if (!formEl) return;

    try {
      const data = await API.getFiles(index);
      const filesDict = data.files || {};
      formEl.innerHTML = buildLoadForm(filesDict, index);
      _wireExpiry(filesDict, index);
      _wireLoadButton(index);
    } catch (err) {
      formEl.innerHTML = `<div class="alert alert-error">Error fetching files: ${err.message}</div>`;
    }
  }

  function _wireExpiry(filesDict, index) {
    const expiryEl = document.getElementById('select-expiry');
    const fileEl = document.getElementById('select-file');
    if (!expiryEl || !fileEl) return;

    expiryEl.addEventListener('change', () => {
      const expiry = expiryEl.value;
      State.setIndexData(index, { selectedExpiry: expiry }); // Persist selection

      const files = filesDict[expiry] || [];
      fileEl.innerHTML = files.map(f => `<option value="${f}">${f}</option>`).join('');

      if (files.length) {
        State.setIndexData(index, { selectedFile: fileEl.value });
      }
    });

    fileEl.addEventListener('change', () => {
      State.setIndexData(index, { selectedFile: fileEl.value });
    });
  }

  function _wireLoadButton(index) {
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
        resultEl.innerHTML = `<div class="alert alert-success">Loaded ${data.strikes} strikes successfully!</div>`;
        State.setIndexData(index, { hasData: true, loadedFile: data.filepath, expiry: data.expiry });
        Toast.show(`${index} data loaded — ${data.strikes} strikes`, 'success');
        App.updateTopbar();

        // Switch to Dashboard automatically
        App.navigate('dashboard');

      } catch (err) {
        resultEl.innerHTML = `<div class="alert alert-error">${err.message}</div>`;
        Toast.show(err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = 'Load Selected File';
      }
    });
  }

  return { render };
})();
