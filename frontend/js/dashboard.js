/**
 * dashboard.js — Dashboard page: metrics, hierarchical analysis (Exposure/Others), vol surface.
 */

const DashboardPage = (() => {

  const _loadedCharts = new Set();

  const ANALYSIS_STRUCTURE = {
    'Exposure': {
      'Gamma': [
        { key: 'gex', label: 'Gamma Exposure', id: 'chart-gex' },
        { key: 'cum_gex', label: 'Cumulative GEX', id: 'chart-cum-gex' },
      ],
      'Delta': [
        { key: 'dex', label: 'Delta Exposure', id: 'chart-dex' },
        { key: 'cum_dex', label: 'Cumulative Delta', id: 'chart-cum-dex' },
      ],
      'Vanna': [
        { key: 'vex', label: 'Vanna Exposure', id: 'chart-vex' },
        { key: 'cum_vex', label: 'Cumulative Vanna', id: 'chart-cum-vex' },
      ],
      'Charm': [
        { key: 'cex', label: 'Charm Exposure', id: 'chart-cex' },
        { key: 'cum_cex', label: 'Cumulative Charm', id: 'chart-cum-cex' },
      ],
    },
    'Volatility': {
      'IV Smile/Skew': [
        { key: 'iv_smile', label: 'IV Smile', id: 'chart-iv-smile' },
      ],
      'Risk Reversal': [
        { key: 'rr_bf', label: 'RR & BF', id: 'chart-rr-bf' },
      ],
      'Expected Range': [
        { key: 'iv_cone', label: 'IV Cone', id: 'chart-iv-cone' },
      ]
    },
    'Others': {
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

  function buildSubChartNav() {
    const st = State.get();
    const charts = ANALYSIS_STRUCTURE[st.selectedBucket]?.[st.selectedCategory] || [];
    if (charts.length <= 1) return '';

    const activeId = st.selectedSubChart || charts[0].id;

    return `
      <div class="sub-chart-nav">
        ${charts.map(c => `
          <button class="sub-tab-btn ${c.id === activeId ? 'active' : ''}" 
                  data-subchart="${c.id}">
            ${c.label}
          </button>
        `).join('')}
      </div>
    `;
  }

  function buildChartPanel() {
    const st = State.get();
    const charts = ANALYSIS_STRUCTURE[st.selectedBucket]?.[st.selectedCategory] || [];

    if (charts.length === 0) {
      return '<div class="alert alert-info" style="margin-top:20px;">This section is coming soon.</div>';
    }

    const activeId = st.selectedSubChart || charts[0].id;
    const activeChart = charts.find(c => c.id === activeId) || charts[0];

    return `
      <div class="active-chart-panel">
        <div class="card chart-card">
          <div id="${activeChart.id}" class="chart-container">
            <div class="chart-placeholder"><div class="spin"></div><span>Loading ${activeChart.label}…</span></div>
          </div>
        </div>
      </div>`;
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
          
          <!-- Consolidated Analysis Header -->
          <div class="analysis-nav-section">
            <div class="nav-row top-row">
              <div class="nav-group">
                <span class="nav-label">NAV</span>
                <div class="bucket-selector">${buildBucketNav()}</div>
              </div>
              
              ${['Gamma', 'Delta', 'Vanna', 'Charm'].includes(st.selectedCategory) ? `
                <div class="nav-group context-group">
                  <span class="nav-label">CONTEXT</span>
                  <div class="segmented-control mode-toggle">
                    <button class="segment-btn ${st.gammaChartMode === 'net' ? 'active' : ''}" data-mode="net">Net Exposure</button>
                    <button class="segment-btn ${st.gammaChartMode === 'raw' ? 'active' : ''}" data-mode="raw">Call vs Put</button>
                  </div>
                </div>
              ` : ''}
            </div>

            <div class="nav-row bottom-row">
              <div class="nav-group">
                <span class="nav-label">CAT</span>
                <div class="category-pills">${buildCategoryNav()}</div>
              </div>
              <div class="nav-group">
                <span class="nav-label">SUB</span>
                <div class="sub-nav-container">${buildSubChartNav()}</div>
              </div>
            </div>
          </div>

          <!-- Main Analysis Canvas -->
          <div class="analysis-content">
            ${buildChartPanel()}
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
          ${st.selectedBucket === 'Volatility' ? `
            <div class="section-overlay">
              <div class="section-header"><h2>Surface Details</h2><div class="section-line"></div></div>
              <div class="card glass-card">${buildVolSurface(vs)}</div>
            </div>
          ` : ''}

        </div>`;

      _wireAnalysisNav(container);

      // Load ONLY the active sub-chart
      const activeCharts = ANALYSIS_STRUCTURE[st.selectedBucket]?.[st.selectedCategory] || [];
      if (activeCharts.length > 0) {
        const activeId = st.selectedSubChart || activeCharts[0].id;
        const chart = activeCharts.find(c => c.id === activeId) || activeCharts[0];

        _loadedCharts.clear();
        const exposureKeys = ['gex', 'cum_gex', 'dex', 'cum_dex', 'vex', 'cum_vex', 'cex', 'cum_cex'];
        const mode = exposureKeys.includes(chart.key) ? st.gammaChartMode : 'net';
        Charts.fetchAndRender(index, chart.key, chart.id, mode);
        _loadedCharts.add(chart.id);
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
      // 1. Bucket clicks
      const bucketBtn = e.target.closest('.bucket-btn');
      if (bucketBtn) {
        const bucket = bucketBtn.dataset.bucket;
        const firstCat = Object.keys(ANALYSIS_STRUCTURE[bucket])[0];
        const firstSub = ANALYSIS_STRUCTURE[bucket][firstCat][0]?.id || null;
        State.set({ selectedBucket: bucket, selectedCategory: firstCat, selectedSubChart: firstSub });
        render(container);
        return;
      }

      // 2. Category clicks
      const catBtn = e.target.closest('.category-btn');
      if (catBtn) {
        const cat = catBtn.dataset.category;
        const firstSub = ANALYSIS_STRUCTURE[State.get().selectedBucket][cat][0]?.id || null;
        State.set({ selectedCategory: cat, selectedSubChart: firstSub });
        render(container);
        return;
      }

      // 3. Sub-chart clicks
      const subBtn = e.target.closest('.sub-tab-btn');
      if (subBtn) {
        State.set({ selectedSubChart: subBtn.dataset.subchart });
        render(container);
        return;
      }

      // 4. View mode clicks
      const modeBtn = e.target.closest('.segment-btn');
      if (modeBtn) {
        State.set({ gammaChartMode: modeBtn.dataset.mode });
        render(container);
      }
    });
  }

  return { render };
})();
