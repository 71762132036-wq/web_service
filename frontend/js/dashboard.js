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
      'Greek Interaction': [
        { key: 'gex_dex_combined', label: 'Gamma × Delta', id: 'chart-gex-dex' },
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
      ],
      'Intraday IV': [
        { key: 'iv_tracker', label: 'IV Tracker', id: 'chart-iv-tracker' },
      ],
      '3D Surface': [
        { key: 'vol_surface_3d', label: '3D Vol Surface', id: 'chart-vol-surface-3d' },
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
    },
    'Advanced': {
      'Migration Pulse': [
        { key: 'migration', label: 'Gamma Waltz', id: 'chart-migration' },
      ],
      'Vol Mispricing': [
        { key: 'vol_spread', label: 'IV vs RV', id: 'chart-vol-spread' },
      ],
      'Ignition Zone': [
        { key: 'ignition', label: 'Sensitivity Heatmap', id: 'chart-ignition' },
      ],
      'Institutional Flow': [
        { key: 'momentum', label: 'Flow Momentum', id: 'chart-momentum' },
      ],
      'Systemic Pulse': [
        { key: 'systemic_pulse', label: 'Market Pulse', id: 'chart-systemic-pulse' },
        { key: 'total_gex', label: 'Total GEX', id: 'chart-total-gex' },
        { key: 'total_dex', label: 'Total DEX', id: 'chart-total-dex' },
      ]
    },
    'God Tier': {
      'Dealer Reflexivity': [
        { key: 'reflexivity', label: 'Hedge Curve', id: 'chart-reflexivity' },
      ],
      'Liquidity Profile': [
        { key: 'liquidity', label: 'Voids & Depth', id: 'chart-liquidity' },
      ],
      'Stickiness': [
        { key: 'stickiness', label: 'Level Heat', id: 'chart-stickiness' },
      ],
      'Delta Magnet': [
        { key: 'apex', label: 'Neutral Apex', id: 'chart-apex' },
      ],
      'Gamma Sharpness': [
        { key: 'gamma_profile', label: 'Gamma Profile', id: 'chart-gamma_profile' },
      ],
      'Curve Steepness': [
        { key: 'cum_steepness', label: 'GEX Slope', id: 'chart-cum_steepness' },
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
      _updateMetricsState(container, metrics, regimeClass, vs);
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
            _renderMetricsOnly(container, metrics, regimeClass, vs);
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
          if (chart.key === 'gex_dex_combined') {
            await _renderGexDexInteractive(index, chart.id);
          } else {
            const res = await Charts.fetchAndRender(index, chart.key, chart.id, mode);
            _lastFlowSummary = res?.summary || null;
          }
          _renderMetricsOnly(container, metrics, regimeClass, vs);
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

  function _updateMetricsState(container, metrics, regimeClass, vs) {
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
    } else if (st.selectedCategory === 'Migration Pulse') {
      cards = [
        { label: 'Spot Price', value: metrics.spot.toLocaleString() },
        { label: 'Flip Point', value: metrics.flip_point.toLocaleString(), sub: 'Gamma Neutral Level' },
        { label: 'Quant Power', value: metrics.quant_power.toLocaleString(), sub: 'Blended Zero Level' },
        { label: 'Level Bias', value: metrics.spot > metrics.flip_point ? 'BULLISH' : 'BEARISH', classes: `regime ${metrics.spot > metrics.flip_point ? 'long-gamma' : 'short-gamma'}` },
      ];
    } else if (st.selectedCategory === 'Systemic Pulse') {
       cards = [
        { label: 'Spot Price', value: metrics.spot.toLocaleString() },
        { label: 'ATM IV (%)', value: `${vs?.ATM_IV ? vs.ATM_IV.toFixed(2) : 'N/A'}%`, sub: 'Implied Volatility' },
        { label: 'Net Gamma', value: Math.round(metrics.cum_gex / 1e7).toLocaleString() + ' Cr', sub: 'Portfolio GEX (1% Move)', classes: `flow-status ${metrics.cum_gex > 0 ? 'bullish' : 'bearish'}` },
        { label: 'Net Delta', value: Math.round(metrics.cum_dex / 1e7).toLocaleString() + ' Cr', sub: 'Portfolio Delta (Notional)', classes: `flow-status ${metrics.cum_dex > 0 ? 'bullish' : 'bearish'}` },
      ];
    } else {
      cards = [
        { label: 'Spot Price', value: metrics.spot.toLocaleString() },
        { label: 'Quant Power', value: metrics.quant_power.toLocaleString(), sub: 'Blended Zero Level' },
        { label: 'Flip Point', value: metrics.flip_point.toLocaleString(), sub: 'Zero Gamma Level' },
        { label: 'Dealer Regime', value: metrics.regime, classes: `regime ${regimeClass}` },
      ];
    }

    // EXTRA: If God Tier is selected, we want to add specific Apex info
    if (st.selectedBucket === 'God Tier' && metrics.apex) {
      cards = [
        { label: 'Delta Magnet', value: metrics.apex.price.toLocaleString(undefined, {maximumFractionDigits:0}), sub: 'Neutral Apex Point', classes: 'flow-status' },
        { label: 'Apex Distance', value: `${metrics.apex.distance_pct.toFixed(2)}%`, sub: metrics.apex.distance_pct > 0 ? 'Spot < Apex' : 'Spot > Apex', classes: `flow-status ${Math.abs(metrics.apex.distance_pct) < 1 ? 'bullish' : 'bearish'}` },
        { label: 'Spot Price', value: metrics.spot.toLocaleString() },
        { label: 'Quant Power', value: metrics.quant_power.toLocaleString(), sub: 'Blended Zero Level' },
      ];

      if (metrics.concentration) {
        cards.push({ 
          label: 'Gamma Sharpness', 
          value: metrics.concentration.index.toFixed(1), 
          sub: metrics.concentration.is_sharp ? 'SHARP / EXPLOSIVE' : 'WIDE / LINEAR',
          classes: `flow-status ${metrics.concentration.is_sharp ? 'bearish' : 'bullish'}`
        });
      }

      if (metrics.steepness) {
        const s = metrics.steepness;
        cards.push({ 
          label: 'Curve Steepness', 
          value: s.slope_label, 
          sub: s.regime,
          classes: `flow-status ${s.regime === 'High Sensitivity' ? 'bearish' : (s.regime === 'Stable Grip' ? 'bullish' : 'neutral')}`
        });
      }
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

  function _renderMetricsOnly(container, metrics, regimeClass, vs) {
    _updateMetricsState(container, metrics, regimeClass, vs);
  }

  async function _renderGexDexInteractive(index, containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div class="chart-placeholder"><div class="spin"></div><span>Loading Greek Interaction…</span></div>';

    let rawData;
    try {
      const res = await fetch(`/api/charts/${index}/gex_dex_combined`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      rawData = json.data;
    } catch (err) {
      el.innerHTML = `<div class="alert alert-error">Failed to load data: ${err.message}</div>`;
      return;
    }

    const { strikes, gex, dex, dex_abs, spot } = rawData;
    const RANGE = 350;
    const STEP = 25;

    // Build wrapper with slider on top
    el.innerHTML = `
      <div class="gex-dex-wrapper" style="width:100%;height:100%;display:flex;flex-direction:column;gap:10px;padding:8px 4px;">
        <div class="gex-dex-controls" style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:0 8px;">
          <span style="font-size:11px;color:#94A3B8;text-transform:uppercase;letter-spacing:.06em;">Spot Shift</span>
          <input type="range" id="spot-slider-${containerId}"
            min="${-RANGE}" max="${RANGE}" step="${STEP}" value="0"
            style="flex:1;min-width:180px;accent-color:#6366f1;cursor:pointer;">
          <div style="display:flex;gap:18px;">
            <div style="text-align:center;">
              <div style="font-size:10px;color:#64748B;">Shifted Spot</div>
              <div id="slider-spot-label-${containerId}" style="font-size:14px;font-weight:700;color:#E2E8F0;">${Math.round(spot).toLocaleString()}</div>
            </div>
            <div style="text-align:center;">
              <div style="font-size:10px;color:#64748B;">Δ Spot</div>
              <div id="slider-delta-label-${containerId}" style="font-size:14px;font-weight:700;color:#6366F1;">0</div>
            </div>
            <div style="text-align:center;">
              <div style="font-size:10px;color:#64748B;">Net Abs Δ</div>
              <div id="slider-netdex-label-${containerId}" style="font-size:14px;font-weight:700;color:#34D399;">—</div>
            </div>
          </div>
        </div>
        <div id="gex-dex-plotly-${containerId}" style="flex:1;min-height:400px;"></div>
      </div>`;

    const plotEl = document.getElementById(`gex-dex-plotly-${containerId}`);
    const slider = document.getElementById(`spot-slider-${containerId}`);
    const spotLabel = document.getElementById(`slider-spot-label-${containerId}`);
    const deltaLabel = document.getElementById(`slider-delta-label-${containerId}`);
    const netDexLabel = document.getElementById(`slider-netdex-label-${containerId}`);

    // colour arrays  
    const POS = 'rgba(52,211,153,0.82)';
    const NEG = 'rgba(239,68,68,0.82)';
    const GEX_CLR = 'rgba(99,102,241,0.5)';
    const GEX_POS = 'rgba(99,102,241,0.75)';
    const GEX_NEG = 'rgba(232,121,249,0.75)';

    function computeShiftedDex(deltaSpot) {
      // When spot moves ΔS, each option's delta changes by gamma × ΔS
      // GEX is already in ₹ terms (gamma × lots × lot_size × spot²/100), but the
      // ratio gex/spot gives delta sensitivity per ₹. Use gex/spot as the shift rate.
      return dex.map((d, i) => d + (gex[i] / (spot || 1)) * deltaSpot);
    }

    function renderPlot(deltaSpot) {
      const shiftedDex = computeShiftedDex(deltaSpot);
      const shiftedAbsDex = shiftedDex.map(Math.abs);
      const netAbsDex = shiftedAbsDex.reduce((a, b) => a + b, 0);

      const dexColors = shiftedDex.map(v => v >= 0 ? POS : NEG);
      const gexColors = gex.map(v => v >= 0 ? GEX_POS : GEX_NEG);

      const traces = [
        {
          name: 'Abs Delta (Shifted)',
          x: strikes,
          y: shiftedAbsDex,
          type: 'bar',
          marker: { color: dexColors, opacity: 0.88 },
          yaxis: 'y',
          hovertemplate: '<b>Strike %{x}</b><br>|ΔEX|: %{y:.2f}<extra></extra>'
        },
        {
          name: 'Gamma Exposure',
          x: strikes,
          y: gex,
          type: 'bar',
          marker: { color: gexColors, opacity: 0.65 },
          yaxis: 'y2',
          hovertemplate: '<b>Strike %{x}</b><br>GEX: %{y:.2f}<extra></extra>'
        },
      ];

      const shiftedSpot = spot + deltaSpot;
      const layout = {
        paper_bgcolor: 'rgba(15,23,42,0)',
        plot_bgcolor: 'rgba(30,41,59,0.15)',
        font: { color: '#CBD5E1', family: "'Inter', sans-serif", size: 11 },
        margin: { l: 55, r: 55, t: 32, b: 50 },
        barmode: 'overlay',
        legend: { bgcolor: 'rgba(0,0,0,0)', borderwidth: 0, orientation: 'h', y: 1.08, xanchor: 'right', x: 1, font: { size: 10 } },
        xaxis: {
          title: 'Strike Price',
          gridcolor: 'rgba(255,255,255,0.04)',
          zeroline: false,
          tickfont: { size: 10 },
        },
        yaxis: {
          title: '|Abs Delta Exposure|',
          gridcolor: 'rgba(255,255,255,0.04)',
          zeroline: true,
          zerolinecolor: 'rgba(255,255,255,0.15)',
          tickfont: { size: 10 },
        },
        yaxis2: {
          title: 'Gamma Exposure (GEX)',
          overlaying: 'y',
          side: 'right',
          gridcolor: 'rgba(255,255,255,0)',
          zeroline: false,
          tickfont: { size: 10, color: '#818CF8' },
          titlefont: { color: '#818CF8' },
        },
        shapes: [
          // Current spot line
          {
            type: 'line', xref: 'x', yref: 'paper',
            x0: spot, x1: spot, y0: 0, y1: 1,
            line: { color: 'rgba(255,255,255,0.25)', width: 1.5, dash: 'dot' }
          },
          // Shifted spot line
          ...(deltaSpot !== 0 ? [{
            type: 'line', xref: 'x', yref: 'paper',
            x0: shiftedSpot, x1: shiftedSpot, y0: 0, y1: 1,
            line: { color: '#6366F1', width: 2, dash: 'solid' }
          }] : [])
        ],
        annotations: [
          { xref: 'x', yref: 'paper', x: spot, y: 1.02, text: `Spot ${Math.round(spot).toLocaleString()}`, showarrow: false, font: { size: 10, color: '#94A3B8' }, xanchor: 'center' },
          ...(deltaSpot !== 0 ? [{ xref: 'x', yref: 'paper', x: shiftedSpot, y: 1.02, text: `→ ${Math.round(shiftedSpot).toLocaleString()}`, showarrow: false, font: { size: 10, color: '#818CF8' }, xanchor: 'center' }] : [])
        ]
      };

      // Update summary labels
      spotLabel.textContent = Math.round(shiftedSpot).toLocaleString();
      deltaLabel.textContent = (deltaSpot >= 0 ? '+' : '') + deltaSpot;
      deltaLabel.style.color = deltaSpot > 0 ? '#34D399' : deltaSpot < 0 ? '#F87171' : '#6366F1';
      netDexLabel.textContent = (netAbsDex / 1e7).toFixed(1) + ' Cr';

      if (!plotEl._gexDexInit) {
        Plotly.newPlot(plotEl, traces, layout, { responsive: true, displayModeBar: false });
        plotEl._gexDexInit = true;
      } else {
        Plotly.react(plotEl, traces, layout);
      }
    }

    // Initial render at delta=0
    renderPlot(0);

    // Wire slider
    slider.addEventListener('input', () => {
      const dS = parseInt(slider.value, 10);
      renderPlot(dS);
    });
  }

  return { render };
})();
