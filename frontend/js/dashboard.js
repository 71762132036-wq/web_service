/**
 * dashboard.js — Dashboard page: metrics, gamma cage, chart tabs, vol surface, data table.
 * Mirrors the streamlit show_dashboard() function.
 */

const DashboardPage = (() => {

  // Track which chart tabs have been loaded already (lazy load)
  const _loadedCharts = new Set();

  const CHART_TABS = [
    { key: 'gex', label: '📊 GEX Chart', id: 'chart-gex' },
    { key: 'regime', label: '🗺️ Dealer Regime', id: 'chart-regime' },
    { key: 'call_put', label: '📉 Call / Put GEX', id: 'chart-call-put' },
    { key: 'iv_smile', label: '📈 IV Smile', id: 'chart-iv-smile' },
    { key: 'rr_bf', label: '🔬 RR & BF', id: 'chart-rr-bf' },
    { key: 'quant_power', label: '⚡ Quant Power', id: 'chart-quant-power' },
  ];

  // ── Templates ─────────────────────────────────────────

  function buildEmptyState() {
    return `
      <div class="empty-state">
        <div class="empty-icon">📭</div>
        <h3>No Data Loaded</h3>
        <p>Go to <strong>Data Management</strong> to fetch live data or load a saved file.</p>
      </div>`;
  }

  function buildMetricCard(label, value, sub = '', extraClass = '') {
    return `
      <div class="metric-card ${extraClass}">
        <div class="metric-label">${label}</div>
        <div class="metric-value">${value}</div>
        ${sub ? `<div class="metric-sub">${sub}</div>` : ''}
      </div>`;
  }

  function buildTabHeaders() {
    return CHART_TABS.map((t, i) =>
      `<button class="tab-btn ${i === 0 ? 'active' : ''}"
               data-tab="${t.id}">${t.label}</button>`
    ).join('');
  }

  function buildTabPanels() {
    return CHART_TABS.map((t, i) => `
      <div class="tab-panel ${i === 0 ? 'active' : ''}" id="panel-${t.id}">
        <div class="chart-container" id="${t.id}">
          <div class="chart-placeholder"><div class="spin"></div><span>Loading…</span></div>
        </div>
      </div>`
    ).join('');
  }

  function buildPowerZones(zones) {
    if (!zones || !zones.length) return '<span class="text-muted">—</span>';
    return zones.map(z => `<span class="zone-badge">⚡ ${z.toLocaleString()}</span>`).join('');
  }

  function buildVolSurface(vs) {
    if (!vs) return '<div class="alert alert-warning">⚠️ Vol surface not available</div>';

    const rr25Class = vs.RR25 >= 0 ? '' : 'negative';
    const bf10Class = vs.BF10 >= 0 ? '' : 'negative';

    return `
      <div class="vol-grid">
        <div class="vol-card">
          <div class="vol-card-title">25-Delta Risk Reversal (RR25)</div>
          <div class="vol-value ${rr25Class}">${vs.RR25.toFixed(3)}%</div>
          <div class="vol-sentiment">${vs.RR_Sentiment}</div>
          <div class="vol-detail">
            <span>25Δ Call IV: <b>${vs.IV_call25.toFixed(2)}%</b> @ ${vs.Call25_Strike.toLocaleString()}</span>
            <span>25Δ Put IV:  <b>${vs.IV_put25.toFixed(2)}%</b>  @ ${vs.Put25_Strike.toLocaleString()}</span>
          </div>
        </div>
        <div class="vol-card">
          <div class="vol-card-title">10-Delta Butterfly (BF10)</div>
          <div class="vol-value ${bf10Class}">${vs.BF10.toFixed(3)}%</div>
          <div class="vol-sentiment">${vs.BF_Sentiment}</div>
          <div class="vol-detail">
            <span>ATM IV (50Δ): <b>${vs.ATM_IV.toFixed(2)}%</b>  @ ${vs.ATM_Strike.toLocaleString()}</span>
            <span>10Δ Call IV:  <b>${vs.IV_call10.toFixed(2)}%</b> @ ${vs.Call10_Strike.toLocaleString()}</span>
            <span>10Δ Put IV:   <b>${vs.IV_put10.toFixed(2)}%</b>  @ ${vs.Put10_Strike.toLocaleString()}</span>
          </div>
        </div>
      </div>`;
  }

  function buildDataTable(tableData) {
    if (!tableData || !tableData.rows || !tableData.rows.length) {
      return '<div class="alert alert-info">ℹ️ No data available</div>';
    }

    const headers = tableData.columns.map(c =>
      `<th>${c}</th>`).join('');

    const rows = tableData.rows.map(row => {
      const cells = tableData.columns.map(col => {
        const val = row[col];
        let display = val == null ? '—' : (typeof val === 'number' ? val.toLocaleString(undefined, { maximumFractionDigits: 4 }) : val);
        let cls = '';
        if (col === 'Total_GEX') {
          cls = val > 0 ? 'positive' : 'negative';
        }
        return `<td class="${cls}">${display}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');

    return `
      <div class="flex-between mb-16">
        <span class="text-muted text-sm">Showing top rows of ${tableData.total} total strikes</span>
      </div>
      <div class="table-wrapper">
        <table class="data-table">
          <thead><tr>${headers}</tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // ── Render ─────────────────────────────────────────────

  async function render(container) {
    const index = State.getIndex();

    // Check if data is loaded
    if (!State.get().hasData) {
      container.innerHTML = buildEmptyState();
      return;
    }

    // Show skeleton
    container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Loading dashboard…</div>`;

    try {
      const [metrics, volData, tableData] = await Promise.all([
        API.getMetrics(index),
        API.getVolSurface(index),
        API.getDataTable(index, 40),
      ]);

      const vs = volData?.vol_surface;
      const regime = metrics.regime || '';
      const regimeClass = regime.includes('LONG') ? 'long-gamma' : 'short-gamma';

      container.innerHTML = `

        <!-- Key Metrics -->
        <div class="section-header">
          <h2>📌 Key Metrics</h2><div class="section-line"></div>
        </div>
        <div class="metrics-grid">
          ${buildMetricCard('Spot Price', metrics.spot.toLocaleString())}
          ${buildMetricCard('ATM Strike', metrics.atm.toLocaleString())}
          ${buildMetricCard('Quant Power', metrics.quant_power.toLocaleString(), 'Blended Zero Level')}
          ${buildMetricCard('Flip Point', metrics.flip_point.toLocaleString(), 'Zero Gamma Level')}
          ${buildMetricCard('Dealer Regime', regime, '', `regime ${regimeClass}`)}
        </div>

        <!-- Gamma Cage -->
        <div class="section-header">
          <h2>🔒 Gamma Cage Analysis</h2><div class="section-line"></div>
        </div>
        <div class="card" style="margin-bottom:22px;">
          <div class="cage-grid">
            <div class="cage-stat">
              <div class="cage-stat-label">Cage Range</div>
              <div class="cage-stat-value range">${metrics.cage.low.toLocaleString()} – ${metrics.cage.high.toLocaleString()}</div>
            </div>
            <div class="cage-stat">
              <div class="cage-stat-label">Cage Strikes</div>
              <div class="cage-stat-value">${metrics.cage.size}</div>
            </div>
            <div class="cage-stat">
              <div class="cage-stat-label">Vacuum Strikes</div>
              <div class="cage-stat-value text-warn">${metrics.vacuum_size}</div>
            </div>
          </div>
          <div style="margin-top:16px;">
            <div class="cage-stat-label" style="margin-bottom:8px;">💥 Power Zones (High Control)</div>
            <div class="power-zones">${buildPowerZones(metrics.power_zones)}</div>
          </div>
        </div>

        <!-- Chart Tabs -->
        <div class="section-header">
          <h2>📊 Visualizations</h2><div class="section-line"></div>
        </div>
        <div class="tabs" id="chart-tabs">
          <div class="tab-header">${buildTabHeaders()}</div>
          ${buildTabPanels()}
        </div>

        <!-- Vol Surface -->
        <div class="section-header" style="margin-top:28px;">
          <h2>📈 Volatility Surface Details</h2><div class="section-line"></div>
        </div>
        <div class="card" style="margin-bottom:22px;">
          <div id="vol-surface-content">${buildVolSurface(vs)}</div>
        </div>

        <!-- Data Table -->
        <div class="section-header">
          <h2>📋 Data Table</h2><div class="section-line"></div>
        </div>
        <div class="card">
          <div id="data-table-content">${buildDataTable(tableData)}</div>
        </div>
      `;

      _wireTabNav(index);
      // Load first chart immediately
      Charts.fetchAndRender(index, 'gex', 'chart-gex');
      _loadedCharts.clear();
      _loadedCharts.add('chart-gex');

    } catch (err) {
      container.innerHTML = `<div class="alert alert-error">❌ Error loading dashboard: ${err.message}</div>`;
    }
  }

  // ── Tab navigation + lazy chart loading ───────────────

  function _wireTabNav(index) {
    const tabsEl = document.getElementById('chart-tabs');
    if (!tabsEl) return;

    tabsEl.addEventListener('click', e => {
      const btn = e.target.closest('.tab-btn');
      if (!btn) return;

      const targetId = btn.dataset.tab;

      // Toggle active on buttons
      tabsEl.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      // Toggle active on panels
      tabsEl.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      const panel = document.getElementById(`panel-${targetId}`);
      if (panel) panel.classList.add('active');

      // Lazy-load chart if not already loaded
      if (!_loadedCharts.has(targetId)) {
        const chartType = CHART_TABS.find(t => t.id === targetId)?.key;
        if (chartType) {
          Charts.fetchAndRender(index, chartType, targetId);
          _loadedCharts.add(targetId);
        }
      }
    });
  }

  return { render };
})();
