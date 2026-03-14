/**
 * dashboard.js — Dashboard page: metrics, hierarchical analysis (Exposure/Others), vol surface.
 */

const DashboardPage = (() => {

  const _loadedCharts = new Set();
  let _lastFlowSummary = null;

  // Track what's currently on screen to avoid unnecessary re-renders or stale data
  let _currentIndex = null;
  let _currentFile = null;
  let _currentFile2 = null;
  let _currentBucket = null;
  let _currentCategory = null;
  let _currentSubChart = null;
  let _currentMode = null; // Track mode changes
  
  let _isRendering = false; // Render lock
  let _isWired = false; 
  
  // High-level data cache to prevent global flickers
  const _metricsCache = new Map(); // index -> data
  const _volCache = new Map();     // index -> data

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
      ],
      'Vol Trigger': [
        { key: 'vtl', label: 'Volatility Trigger', id: 'chart-vtl' },
      ]
    },
    OI: {
      'OI Strike Map': [
        { key: 'oi_dist', label: 'Analysis', id: 'chart-oi-main' },
      ],
      'OI Change': [
        { key: 'oi_change', label: 'Daily Shift', id: 'chart-oi-change' },
      ],
      'Premium Flow': [
        { key: 'premium_flow', label: 'Net Direction', id: 'chart-prem-flow' },
      ],
      'OI Flow': [
        { key: 'oi_flow', label: 'OI vs Vol', id: 'chart-oi-flow' },
      ],
      'Filter': [
        { key: 'overall_filter', label: 'Overall', id: 'filter-overall' },
        { key: 'strike_filter', label: 'Strike Wise', id: 'filter-strike' }
      ]
    },
    'Others': {
      'Quant': [
        { key: 'quant_power', label: 'Quant Power', id: 'chart-quant-power' },
        { key: 'regime', label: 'Dealer Regime', id: 'chart-regime' },
      ]
    }
  };

  const COMPARE_STRUCTURE = {
    OI: {
      'Compare OI': [
        { key: 'compare_oi_change', label: 'Compare OI Change', id: 'chart-compare-oi-chg' },
      ],
    },
    'Direction': {
      'Flow Intensity': [
        { key: 'flow_intensity', label: 'Activity Map', id: 'chart-flow-intensity' },
      ],
      'Net Pressure': [
        { key: 'strike_pressure', label: 'Strike Pressure', id: 'chart-strike-pressure' },
      ]
    }
  };

  function getStructure() {
    const st = State.get();
    const structure = st.compareMode ? COMPARE_STRUCTURE : ANALYSIS_STRUCTURE;

    // Safety: if currently selected bucket is not in current structure, fallback
    if (!structure[st.selectedBucket]) {
      const fallback = Object.keys(structure)[0];
      State.set({
        selectedBucket: fallback,
        selectedCategory: Object.keys(structure[fallback])[0]
      });
    }

    return structure;
  }

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
    const structure = getStructure();
    return Object.keys(structure).map(bucket => `
      <button class="bucket-btn ${st.selectedBucket === bucket ? 'active' : ''}" 
              data-bucket="${bucket}">${bucket}</button>
    `).join('');
  }

  function buildCategoryNav() {
    const st = State.get();
    const structure = getStructure();
    const categories = structure[st.selectedBucket] || {};

    return Object.keys(categories).map(cat => `
      <button class="category-btn ${st.selectedCategory === cat ? 'active' : ''}" 
              data-category="${cat}">${cat}</button>
    `).join('');
  }

  function buildSubChartNav() {
    const st = State.get();
    const structure = getStructure();
    const charts = structure[st.selectedBucket]?.[st.selectedCategory] || [];
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
    const structure = getStructure();
    const charts = structure[st.selectedBucket]?.[st.selectedCategory] || [];

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
    const structure = getStructure();

    // Prevent concurrent renders
    if (_isRendering) return;
    _isRendering = true;

    try {
      const idxData = State.getIndexData(index);
      const filename = idxData.selectedFile;
      const filename2 = idxData.selectedFile2;

      const isContextChange = (
        _currentIndex !== index ||
        _currentFile !== filename ||
        _currentFile2 !== filename2
      );
      
      if (isContextChange) {
         FilterViews.clearContext();
      }

      const isPageChange = (
        isContextChange ||
        _currentBucket !== st.selectedBucket ||
        _currentCategory !== st.selectedCategory ||
        _currentSubChart !== st.selectedSubChart
      );
      const isModeChange = _currentMode !== st.gammaChartMode;

      // 1. Partial Update Logic — if dashboard exists, don't wipe it unless the page changed
      const existingDashboard = container.querySelector('.dashboard-wrapper');
      if (!existingDashboard) {
        container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Synchronizing ${index} Dashboard…</div>`;
      }

      // 2. Fetch critical layout data
      let metrics, volData;
      const cacheKey = `${index}|${filename}`;

      if (_metricsCache.has(cacheKey) && _volCache.has(cacheKey)) {
        metrics = _metricsCache.get(cacheKey);
        volData = _volCache.get(cacheKey);
      } else {
        [metrics, volData] = await Promise.all([
          API.getMetrics(index),
          API.getVolSurface(index),
        ]);
        _metricsCache.set(cacheKey, metrics);
        _volCache.set(cacheKey, volData);
      }

      const vs = volData?.vol_surface;
      const regimeClass = (metrics.regime || '').includes('LONG') ? 'long-gamma' : 'short-gamma';

      // 3. Structural Update
      if (!existingDashboard || isPageChange) {
        container.innerHTML = `
          <div class="dashboard-wrapper">
            <div class="analysis-nav-section">
              <div class="nav-row top-row">
                <div class="nav-group"><span class="nav-label">NAV</span><div class="bucket-selector">${buildBucketNav()}</div></div>
                <div class="nav-group context-group mode-toggle-area"></div>
              </div>
              <div class="nav-row cat-row">
                <div class="nav-group"><span class="nav-label">CAT</span><div class="category-pills"></div></div>
                <div class="nav-group context-group sub-nav-area"></div>
              </div>
            </div>
            <div class="analysis-content">
              ${buildChartPanel()}
            </div>
            <div class="metrics-section"><div class="metrics-grid"></div></div>
            <div class="surface-details-area"></div>
          </div>`;
      }

      // Always update dynamic parts
      _updateNavState(container, structure);
      _updateMetricsState(container, metrics, regimeClass);
      _updateSurfaceState(container, vs);

      // Save tracking state
      _currentIndex = index;
      _currentFile = filename;
      _currentFile2 = filename2;
      _currentBucket = st.selectedBucket;
      _currentCategory = st.selectedCategory;
      _currentSubChart = st.selectedSubChart;
      _currentMode = st.gammaChartMode;

      if (!_isWired) {
        _wireDashboard(container);
        _isWired = true;
      }

      // 4. Chart Loading Logic
      const activeCharts = structure[st.selectedBucket]?.[st.selectedCategory] || [];
      const filterKeys = ['overall_filter', 'strike_filter'];
      
      const shouldReloadChart = isPageChange || isModeChange || (filterKeys.includes(activeCharts[0]?.key));
      const chartId = st.selectedSubChart || activeCharts[0]?.id;

      if (activeCharts.length > 0 && (shouldReloadChart || !_loadedCharts.has(chartId))) {
        _loadedCharts.clear(); 
        const activeId = st.selectedSubChart || activeCharts[0].id;
        const chart = activeCharts.find(c => c.id === activeId) || activeCharts[0];

        if (st.selectedBucket === 'Direction') {
          const idxData = State.getIndexData(index);
          const { selectedFile: file1, selectedFile2: file2, selectedExpiry: expiry } = idxData;
          if (file1 && file2) {
            const res = await Charts.fetchAndRenderDirection(index, chart.key, expiry, file1, file2, chart.id);
            _lastFlowSummary = res?.summary || null;
            _renderMetricsOnly(container, metrics, regimeClass);
          } else {
            const el = document.getElementById(chart.id);
            if (el) el.innerHTML = '<div class="chart-placeholder"><span>Select two files in Compare mode</span></div>';
          }
        } 
        else if (st.compareMode) {
          const idxData = State.getIndexData(index);
          const { selectedFile: file1, selectedFile2: file2, selectedExpiry: expiry } = idxData;
          if (file1 && file2) {
            await Charts.fetchAndRenderCompare(index, chart.key, expiry, file1, file2, chart.id);
          } else {
            const el = document.getElementById(chart.id);
            if (el) el.innerHTML = '<div class="chart-placeholder"><span>Select two files to compare</span></div>';
          }
        } 
        else if (filterKeys.includes(chart.key)) {
          const filterArea = container.querySelector(`#${chart.id}`);
          if (filterArea) await FilterViews.render(filterArea);
        } 
        else {
          const exposureKeys = ['gex', 'cum_gex', 'dex', 'cum_dex', 'vex', 'cum_vex', 'cex', 'cum_cex'];
          const mode = exposureKeys.includes(chart.key) ? st.gammaChartMode : 'net';
          const res = await Charts.fetchAndRender(index, chart.key, chart.id, mode);
          _lastFlowSummary = res?.summary || null;
          _renderMetricsOnly(container, metrics, regimeClass);
        }
        _loadedCharts.add(chart.id);
      }
    } catch (err) {
      console.error("Dashboard render error:", err);
      if (err?.message?.includes('No data loaded')) {
        container.innerHTML = buildEmptyState();
      } else {
        container.innerHTML = `<div class="alert alert-error">Dashboard error: ${err?.message || 'Unknown error'}</div>`;
      }
    } finally {
      _isRendering = false;
    }
  }

  function _wireDashboard(container) {
    // Single consolidated event delegation on root container
    FilterViews.wireControls(container, render);

    container.addEventListener('click', e => {
      // 1. Navigation (Bucket, Category, Sub)
      const bucketBtn = e.target.closest('.bucket-btn');
      if (bucketBtn) {
        const bucket = bucketBtn.dataset.bucket;
        const structure = getStructure();
        const firstCat = Object.keys(structure[bucket])[0];
        const firstSub = structure[bucket][firstCat][0]?.id || null;
        State.set({ selectedBucket: bucket, selectedCategory: firstCat, selectedSubChart: firstSub });
        render(container); return;
      }
      
      const catBtn = e.target.closest('.category-btn');
      if (catBtn) {
        const cat = catBtn.dataset.category;
        const structure = getStructure();
        const firstSub = structure[State.get().selectedBucket][cat][0]?.id || null;
        State.set({ selectedCategory: cat, selectedSubChart: firstSub });
        render(container); return;
      }

      const subBtn = e.target.closest('.sub-tab-btn');
      if (subBtn) {
        State.set({ selectedSubChart: subBtn.dataset.subchart });
        render(container); return;
      }

      const modeBtn = e.target.closest('.segment-btn');
      if (modeBtn && modeBtn.closest('.mode-toggle')) {
        State.set({ gammaChartMode: modeBtn.dataset.mode });
        render(container); return;
      }
    });
  }

  function _updateNavState(container, structure) {
    const st = State.get();
    
    // 1. Bucket Nav
    const bucketArea = container.querySelector('.bucket-selector');
    if (bucketArea) bucketArea.innerHTML = buildBucketNav();
    
    // 2. Category Nav
    const catArea = container.querySelector('.category-pills');
    if (catArea) catArea.innerHTML = buildCategoryNav();
    
    // 3. Sub Nav
    const subNavArea = container.querySelector('.sub-nav-area');
    if (subNavArea) {
      const hasSub = structure[st.selectedBucket]?.[st.selectedCategory]?.length > 1;
      subNavArea.innerHTML = hasSub ? `<span class="nav-label">SUB</span>${buildSubChartNav()}` : '';
    }

    // 4. Mode Toggle (Gamma/exposure modes)
    const toggleArea = container.querySelector('.mode-toggle-area');
    if (toggleArea) {
      const hasToggle = ['Gamma', 'Delta', 'Vanna', 'Charm'].includes(st.selectedCategory);
      toggleArea.innerHTML = hasToggle ? `
        <span class="nav-label">CONTEXT</span>
        <div class="segmented-control mode-toggle">
          <button class="segment-btn ${st.gammaChartMode === 'net' ? 'active' : ''}" data-mode="net">Net Exposure</button>
          <button class="segment-btn ${st.gammaChartMode === 'raw' ? 'active' : ''}" data-mode="raw">Call vs Put</button>
        </div>
      ` : '';
    }
  }

  function _updateMetricsState(container, metrics, regimeClass) {
    const grid = container.querySelector('.metrics-grid');
    if (!grid) return;
    const st = State.get();

    if (st.selectedCategory === 'Filter') {
      const section = container.querySelector('.metrics-section');
      if (section) section.style.display = 'none';
      return;
    } else {
      const section = container.querySelector('.metrics-section');
      if (section) section.style.display = 'block';
    }

    let cards = [];

    if (_lastFlowSummary?.vtl) {
      cards = [
        { label: 'VTL Level', value: _lastFlowSummary.vtl.toLocaleString(), sub: `Price: ${_lastFlowSummary.vtl.toLocaleString()}`, classes: 'flow-status' },
        { label: 'VTL Distance', value: `${Math.abs(_lastFlowSummary.distance_pct).toFixed(2)}%`, sub: `Spot is ${_lastFlowSummary.direction} VTL`, classes: `flow-status ${_lastFlowSummary.distance_pct > 0 ? 'bullish' : 'bearish'}` },
        { label: 'Spot Price', value: metrics.spot.toLocaleString() },
        { label: 'Quant Power', value: metrics.quant_power.toLocaleString(), sub: 'Blended Zero Level' },
      ];
    } else if (st.selectedBucket === 'Direction' && _lastFlowSummary) {
      cards = [
        { label: 'Call Flow', value: _lastFlowSummary.calls.label, sub: `Pressure: ${(_lastFlowSummary.calls.pressure * 100).toFixed(1)}%`, classes: `flow-status ${_lastFlowSummary.calls.pressure > 0.2 ? 'bullish' : (_lastFlowSummary.calls.pressure < -0.2 ? 'bearish' : '')}` },
        { label: 'Put Flow', value: _lastFlowSummary.puts.label, sub: `Pressure: ${(_lastFlowSummary.puts.pressure * 100).toFixed(1)}%`, classes: `flow-status ${_lastFlowSummary.puts.pressure > 0.2 ? 'bearish' : (_lastFlowSummary.puts.pressure < -0.2 ? 'bullish' : '')}` },
        { label: 'Spot Price', value: metrics.spot.toLocaleString() },
        { label: 'Quant Power', value: metrics.quant_power.toLocaleString(), sub: 'Blended Zero Level' },
      ];
    } else {
      cards = [
        { label: 'Spot Price', value: metrics.spot.toLocaleString() },
        { label: 'Quant Power', value: metrics.quant_power.toLocaleString(), sub: 'Blended Zero Level' },
        { label: 'Flip Point', value: metrics.flip_point.toLocaleString(), sub: 'Zero Gamma Level' },
        { label: 'Dealer Regime', value: metrics.regime, classes: `regime ${regimeClass}` },
      ];
    }

    grid.innerHTML = cards.map(c => buildMetricCard(c.label, c.value, c.sub, c.classes)).join('');
  }

  function _updateSurfaceState(container, vs) {
    const area = container.querySelector('.surface-details-area');
    if (!area) return;
    const st = State.get();

    if (st.selectedBucket === 'Volatility') {
      area.innerHTML = `
        <div class="section-overlay">
          <div class="section-header"><h2>Surface Details</h2><div class="section-line"></div></div>
          <div class="card glass-card">${buildVolSurface(vs)}</div>
        </div>`;
    } else {
      area.innerHTML = '';
    }
  }

  function _renderMetricsOnly(container, metrics, regimeClass) {
    _updateMetricsState(container, metrics, regimeClass);
  }

  return { render };
})();
