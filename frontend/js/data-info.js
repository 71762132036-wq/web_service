/**
 * data-info.js — Data Info page.
 * Shows stats, column info, file info, and CSV export.
 * Mirrors streamlit show_data_info().
 */

const DataInfoPage = (() => {

    function buildEmptyState() {
        return `
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <h3>No Data Loaded</h3>
        <p>Load data from the <strong>Data Management</strong> page first.</p>
      </div>`;
    }

    function buildColumnChips(columns) {
        const marketCols = ['Strike', 'Spot', 'expiry', 'PCR', 'call_ltp', 'put_ltp'];
        const greekCols = ['call_delta', 'call_gamma', 'call_theta', 'call_vega',
            'put_delta', 'put_gamma', 'put_theta', 'put_vega'];
        const oiCols = ['Call_OI', 'Put_OI', 'call_iv', 'put_iv'];
        const gexCols = ['Call_GEX', 'Put_GEX', 'Total_GEX', 'Abs_GEX'];

        function section(title, list) {
            const filtered = list.filter(c => columns.includes(c));
            if (!filtered.length) return '';
            return `
        <div>
          <div class="card-title" style="margin-bottom:10px;">${title}</div>
          <div class="columns-grid">
            ${filtered.map(c => `<div class="col-chip"><div class="dot"></div>${c}</div>`).join('')}
          </div>
        </div>`;
        }

        return `
      <div style="display:flex;flex-direction:column;gap:16px;">
        ${section('📊 Market Data', marketCols)}
        ${section('🔣 Greeks', greekCols)}
        ${section('📈 Open Interest & IV', oiCols)}
        ${section('⚡ GEX Columns', gexCols)}
      </div>`;
    }

    function buildStatsTable(statsData) {
        if (!statsData || !Object.keys(statsData).length) return '';
        const metrics = Object.keys(statsData);
        const statKeys = Object.keys(statsData[metrics[0]] || {});

        const headers = ['', ...statKeys].map(k => `<th>${k}</th>`).join('');
        const rows = metrics.map(metric => {
            const cells = statKeys.map(k => {
                const val = statsData[metric][k];
                return `<td>${val == null ? '—' : Number(val).toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>`;
            }).join('');
            return `<tr><td>${metric}</td>${cells}</tr>`;
        }).join('');

        return `
      <div class="table-wrapper" style="max-height:320px;">
        <table class="stats-table">
          <thead><tr>${headers}</tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
    }

    // ── Render ─────────────────────────────────────────────

    async function render(container) {
        const index = State.getIndex();

        if (!State.get().hasData) {
            container.innerHTML = buildEmptyState();
            return;
        }

        container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Loading data info…</div>`;

        try {
            const stats = await API.getStats(index);

            container.innerHTML = `
        <!-- Summary Metrics -->
        <div class="section-header">
          <h2>📋 Data Overview</h2><div class="section-line"></div>
        </div>
        <div class="metrics-grid">
          <div class="metric-card">
            <div class="metric-label">Total Strikes</div>
            <div class="metric-value">${stats.total_rows}</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Expiry Date</div>
            <div class="metric-value" style="font-size:16px;">${stats.expiry || '—'}</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Spot Price</div>
            <div class="metric-value">${stats.spot ? stats.spot.toLocaleString() : '—'}</div>
          </div>
          <div class="metric-card">
            <div class="metric-label">Total Columns</div>
            <div class="metric-value">${(stats.columns || []).length}</div>
          </div>
        </div>

        <!-- Column Info -->
        <div class="section-header">
          <h2>📊 Available Columns</h2><div class="section-line"></div>
        </div>
        <div class="card" style="margin-bottom:22px;">
          ${buildColumnChips(stats.columns || [])}
        </div>

        <!-- Statistics -->
        <div class="section-header">
          <h2>📈 Statistics</h2><div class="section-line"></div>
        </div>
        <div class="card" style="margin-bottom:22px;">
          ${buildStatsTable(stats.stats)}
        </div>

        <!-- File Info & Export -->
        <div class="section-header">
          <h2>💾 File & Export</h2><div class="section-line"></div>
        </div>
        <div class="card">
          <div class="alert alert-info" style="margin-bottom:16px;">
            📂 Current file: <code style="font-size:11px;color:#a5b4fc;">${State.get().loadedFile || 'N/A'}</code>
          </div>
          <button class="btn btn-primary" id="btn-export">
            ⬇️ Download CSV
          </button>
        </div>
      `;

            _wireExportButton(index);

        } catch (err) {
            container.innerHTML = `<div class="alert alert-error">❌ ${err.message}</div>`;
        }
    }

    function _wireExportButton(index) {
        const btn = document.getElementById('btn-export');
        if (!btn) return;
        btn.addEventListener('click', () => {
            API.exportCSV(index);
            Toast.show('CSV download started!', 'success');
        });
    }

    return { render };
})();
