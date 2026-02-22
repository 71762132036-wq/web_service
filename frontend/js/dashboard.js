/**
 * dashboard.js — Dashboard page: metrics, hierarchical analysis (Exposure/Others), vol surface.
 */

const DashboardPage = (() => {

  const _loadedCharts = new Set();

  const ANALYSIS_STRUCTURE = {
    'Exposure': {
      'Gamma': [
        { key: 'gex', label: 'Gamma Exposure', id: 'chart-gex' },
      ],
      'Delta': [], // Future
      'Vanna': [], // Future
    },
    'Others': {
      'Volatility': [
        { key: 'iv_smile', label: 'IV Smile', id: 'chart-iv-smile' },
        { key: 'rr_bf', label: 'RR & BF', id: 'chart-rr-bf' },
      ],
      'Quant': [
        { key: 'quant_power', label: 'Quant Power', id: 'chart-quant-power' },
        { key: 'regime', label: 'Dealer Regime', id: 'chart-regime' },
      ]
    }
  };

  // ── Templates ─────────────────────────────────────────

  function buildEmptyState() {
    return `
      <div class="empty-state">
        <div class="empty-icon">...</div>
        <h3>No Data Loaded</h3>
        <p>Use the <strong>Fetch Live</strong> button or select a file in the top bar to load data.</p>
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

  function buildBucketNav() {
    const st = State.get();
    return Object.keys(ANALYSIS_STRUCTURE).map(bucket => `
      <button class="bucket-btn ${st.selectedBucket === bucket ? 'active' : ''}" 
              data-bucket="${bucket}">${bucket}</button>
    `).join('');
  }

  function buildCategoryNav() {
    const st = State.get();
    const categories = ANALYSIS_STRUCTURE[st.selectedBucket] || {};

    return Object.keys(categories).map(cat => `
      <button class="category-btn ${st.selectedCategory === cat ? 'active' : ''}" 
              data-category="${cat}">${cat}</button>
    `).join('');
  }

  function buildChartTabs() {
    const st = State.get();
    const charts = ANALYSIS_STRUCTURE[st.selectedBucket]?.[st.selectedCategory] || [];

    if (charts.length === 0) {
      return '<div class="alert alert-info" style="margin-top:20px;">This section is coming soon.</div>';
    }

    const headers = charts.map((c, i) => `
      <button class="tab-btn ${i === 0 ? 'active' : ''}" data-tab="${c.id}">${c.label}</button>
    `).join('');

    const panels = charts.map((c, i) => `
      <div class="tab-panel ${i === 0 ? 'active' : ''}" id="panel-${c.id}">
        <div class="chart-container" id="${c.id}">
          <div class="chart-placeholder"><div class="spin"></div><span>Loading…</span></div>
        </div>
      </div>
    `).join('');

    return `
      <div class="tabs" id="chart-tabs">
        <div class="tab-header">${headers}</div>
        ${panels}
      </div>
    `;
  }

  function buildVolSurface(vs) {
    if (!vs) return '<div class="alert alert-warning">Vol surface not available</div>';
    return `
      <div class="vol-grid">
        <div class="vol-card">
          <div class="vol-card-title">25-Delta Risk Reversal (RR25)</div>
          <div class="vol-value">${vs.RR25.toFixed(3)}%</div>
          <div class="vol-sentiment">${vs.RR_Sentiment}</div>
        </div>
        <div class="vol-card">
          <div class="vol-card-title">10-Delta Butterfly (BF10)</div>
          <div class="vol-value">${vs.BF10.toFixed(3)}%</div>
          <div class="vol-sentiment">${vs.BF_Sentiment}</div>
        </div>
      </div>`;
  }


  // ── Render ─────────────────────────────────────────────

  async function render(container) {
    const st = State.get();
    const index = st.selectedIndex;

    // Loading overlay
    container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Synchronizing ${index} Dashboard…</div>`;

    try {
      const [metrics, volData] = await Promise.all([
        API.getMetrics(index),
        API.getVolSurface(index),
      ]);

      const vs = volData?.vol_surface;
      const regimeClass = metrics.regime?.includes('LONG') ? 'long-gamma' : 'short-gamma';

      container.innerHTML = `
        <div class="dashboard-wrapper">
          
          <!-- Unified Analysis Header (Nav + Mode) -->
          <div class="analysis-nav-section">
            <div class="analysis-nav-container">
              <div class="bucket-selector">${buildBucketNav()}</div>
              <div class="category-pills">${buildCategoryNav()}</div>
            </div>
            ${st.selectedCategory === 'Gamma' ? `
              <div class="gamma-mode-selector">
                <span class="selector-label">View Mode</span>
                <div class="segmented-control mode-toggle">
                  <button class="segment-btn ${st.gammaChartMode === 'net' ? 'active' : ''}" data-mode="net">Net Exposure</button>
                  <button class="segment-btn ${st.gammaChartMode === 'raw' ? 'active' : ''}" data-mode="raw">Call vs Put</button>
                </div>
              </div>
            ` : ''}
          </div>

          <!-- Main Analysis Canvas -->
          <div class="analysis-content">
            ${buildChartTabs()}
          </div>

          <!-- Secondary Metrics Row -->
          <div class="metrics-section">
            <div class="metrics-grid">
              ${buildMetricCard('Spot Price', metrics.spot.toLocaleString())}
              ${buildMetricCard('Quant Power', metrics.quant_power.toLocaleString(), 'Blended Zero Level')}
              ${buildMetricCard('Flip Point', metrics.flip_point.toLocaleString(), 'Zero Gamma Level')}
              ${buildMetricCard('Dealer Regime', metrics.regime, '', `regime ${regimeClass}`)}
            </div>
          </div>

          <!-- Contextual Surface Details -->
          ${st.selectedCategory === 'Volatility' ? `
            <div class="section-overlay">
              <div class="section-header"><h2>Surface Details</h2><div class="section-line"></div></div>
              <div class="card glass-card">${buildVolSurface(vs)}</div>
            </div>
          ` : ''}

        </div>
      `;

      _wireAnalysisNav(container);
      _wireTabNav(index);

      // Load initial chart of the category
      const activeCharts = ANALYSIS_STRUCTURE[st.selectedBucket]?.[st.selectedCategory] || [];
      if (activeCharts.length > 0) {
        const first = activeCharts[0];
        const mode = (first.key === 'gex') ? st.gammaChartMode : 'net';
        Charts.fetchAndRender(index, first.key, first.id, mode);
        _loadedCharts.clear();
        _loadedCharts.add(first.id);
      }

    } catch (err) {
      if (err.message.includes('No data loaded')) {
        container.innerHTML = buildEmptyState();
      } else {
        container.innerHTML = `<div class="alert alert-error">Dashboard error: ${err.message}</div>`;
      }
    }
  }

  function _wireAnalysisNav(container) {
    const navSection = container.querySelector('.analysis-nav-section');

    navSection.addEventListener('click', e => {
      // Bucket clicks
      const bucketBtn = e.target.closest('.bucket-btn');
      if (bucketBtn) {
        const bucket = bucketBtn.dataset.bucket;
        const firstCat = Object.keys(ANALYSIS_STRUCTURE[bucket])[0];
        State.set({ selectedBucket: bucket, selectedCategory: firstCat });
        render(container);
        return;
      }

      // Category clicks
      const catBtn = e.target.closest('.category-btn');
      if (catBtn) {
        State.set({ selectedCategory: catBtn.dataset.category });
        render(container);
        return;
      }

      // Mode switch clicks
      const modeBtn = e.target.closest('.segment-btn');
      if (modeBtn) {
        State.set({ gammaChartMode: modeBtn.dataset.mode });
        render(container);
      }
    });
  }

  function _wireTabNav(index) {
    const tabsEl = document.getElementById('chart-tabs');
    if (!tabsEl) return;

    tabsEl.addEventListener('click', e => {
      const btn = e.target.closest('.tab-btn');
      if (!btn) return;
      const targetId = btn.dataset.tab;

      tabsEl.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      tabsEl.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      document.getElementById(`panel-${targetId}`).classList.add('active');

      if (!_loadedCharts.has(targetId)) {
        // Find chart key across active bucket/category
        const st = State.get();
        const charts = ANALYSIS_STRUCTURE[st.selectedBucket][st.selectedCategory];
        const chart = charts.find(c => c.id === targetId);
        if (chart) {
          const mode = (chart.key === 'gex') ? State.get().gammaChartMode : 'net';
          Charts.fetchAndRender(index, chart.key, targetId, mode);
          _loadedCharts.add(targetId);
        }
      }
    });
  }

  return { render };
})();
