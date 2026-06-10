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
        { key: 'vwgex', label: 'Volume-Weighted', id: 'chart-vwgex' },
        { key: 'gex_decay', label: 'GEX Decay (DTE)', id: 'chart-gex-decay' },
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
      'BS Pricing': [
        { key: 'bs_pricing', label: 'Actual vs BS', id: 'chart-bs-pricing' },
      ],
      'Risk Reversal': [
        { key: 'rr_bf', label: 'RR & BF', id: 'chart-rr-bf' },
      ],
      'Expected Range': [
        { key: 'iv_cone', label: 'IV Cone', id: 'chart-iv-cone' },
        { key: 'gamma_range', label: 'Gamma-Adjusted', id: 'chart-gamma-range' },
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
        { key: 'oi_buildup', label: 'Buildup Class', id: 'chart-oi-buildup' },
      ],
      'Intraday OI Tracker': [
        { key: 'oi_tracker', label: 'Overall', id: 'chart-oi-tracker-total', mode: 'total' },
        { key: 'oi_tracker', label: 'Change', id: 'chart-oi-tracker-change', mode: 'change' },
      ],
      'Premium Flow': [
        { key: 'premium_flow', label: 'Net Direction', id: 'chart-prem-flow' },
      ],
      'OI Flow': [
        { key: 'oi_flow', label: 'OI vs Vol', id: 'chart-oi-flow' },
      ],
      'PCR Analysis': [
        { key: 'pcr_volume', label: 'Vol vs OI PCR', id: 'chart-pcr-volume' },
      ],
      'OI x Time': [
        { key: 'oi_heatmap',         label: 'Heatmap (Calls)',     id: 'chart-oi-heatmap-call',    mode: 'call' },
        { key: 'oi_heatmap',         label: 'Heatmap (Puts)',      id: 'chart-oi-heatmap-put',     mode: 'put'  },
        { key: 'oi_heatmap',         label: 'Heatmap (Net)',       id: 'chart-oi-heatmap-net',     mode: 'net'  },
        { key: 'oi_importance',      label: 'Strike Rank (Calls)', id: 'chart-oi-importance-call', mode: 'call' },
        { key: 'oi_importance',      label: 'Strike Rank (Puts)',  id: 'chart-oi-importance-put',  mode: 'put'  },
        { key: 'oi_evolution',       label: 'OI Evolution Lines',  id: 'chart-oi-evolution'               },
        { key: 'oi_lifecycle',       label: 'OI Lifecycle + PCR',  id: 'chart-oi-lifecycle'               },
        { key: 'max_pain_migration', label: 'Max Pain Migration',  id: 'chart-max-pain-migration'         },
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
      ],
      'Max Pain': [
        { key: 'max_pain', label: 'Pain & Pin Risk', id: 'chart-max-pain' },
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
        { key: 'participant', label: 'FII/DII Position', id: 'chart-participant' },
        { key: 'fii_alignment', label: 'FII × Gamma', id: 'chart-fii-alignment' },
      ],
      'Systemic Pulse': [
        { key: 'systemic_pulse', label: 'Market Pulse', id: 'chart-systemic-pulse' },
        { key: 'total_gex', label: 'Total GEX', id: 'chart-total-gex' },
        { key: 'total_dex', label: 'Total DEX', id: 'chart-total-dex' },
      ]
    },
    'Signals': {
      'Composite Score': [
        { key: 'sig_composite', label: 'Move Imminent', id: 'chart-sig-composite' },
      ],
      'Flip Proximity': [
        { key: 'sig_flip', label: 'Regime Break', id: 'chart-sig-flip' },
      ],
      'Wall Decay': [
        { key: 'sig_wall_decay', label: 'Live vs Ghost', id: 'chart-sig-wall-decay' },
      ],
      'IV Divergence': [
        { key: 'sig_iv_divergence', label: 'Smart Money Tell', id: 'chart-sig-iv-div' },
      ],
      'OI Asymmetry': [
        { key: 'sig_oi_asymmetry', label: 'Directional Trigger', id: 'chart-sig-oi-asym' },
      ],
      'Delta Acceleration': [
        { key: 'sig_delta_accel', label: 'Cascade Detector', id: 'chart-sig-delta-accel' },
      ],
    },
    'God Tier': {
      'Dealer Reflexivity': [
        { key: 'reflexivity', label: 'Hedge Curve', id: 'chart-reflexivity' },
        { key: 'hedge_flow', label: 'Hedge Simulation', id: 'chart-hedge-flow' },
      ],
      'Liquidity Profile': [
        { key: 'liquidity', label: 'Voids & Depth', id: 'chart-liquidity' },
        { key: 'spread_heatmap', label: 'Spread Conviction', id: 'chart-spread-heatmap' },
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
      ],
      'System Gamma': [
        { key: 'system_gamma', label: 'Cross-Index', id: 'chart-system-gamma' },
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
          const exposureKeys = ['gex', 'cum_gex', 'dex', 'cum_dex', 'vex', 'cum_vex', 'cex', 'cum_cex', 'vwgex'];
          const mode = chart.mode || (exposureKeys.includes(chart.key) ? st.gammaChartMode : 'net');
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
    } else if (st.selectedCategory === 'Max Pain') {
      cards = [
        { label: 'Max Pain', value: metrics.max_pain ? metrics.max_pain.toLocaleString() : 'N/A', sub: metrics.pin_label || '', classes: `flow-status ${metrics.pin_risk > 0.5 ? 'bearish' : 'bullish'}` },
        { label: 'Pin Risk', value: metrics.pin_risk ? (metrics.pin_risk * 100).toFixed(0) + '%' : 'N/A' },
        { label: 'Spot Price', value: metrics.spot.toLocaleString() },
        { label: 'Dealer Regime', value: metrics.regime, classes: `regime ${regimeClass}` },
      ];
    } else if (st.selectedCategory === 'PCR Analysis') {
      cards = [
        { label: 'PCR (Volume)', value: metrics.pcr_volume ? metrics.pcr_volume.toFixed(3) : 'N/A', sub: 'Intraday Signal', classes: `flow-status ${(metrics.pcr_volume || 0) > 1 ? 'bearish' : 'bullish'}` },
        { label: 'PCR (OI)', value: metrics.pcr_oi ? metrics.pcr_oi.toFixed(3) : 'N/A', sub: 'Accumulation Signal' },
        { label: 'Spot Price', value: metrics.spot.toLocaleString() },
        { label: 'Dealer Regime', value: metrics.regime, classes: `regime ${regimeClass}` },
      ];
    } else if (st.selectedBucket === 'Signals') {
      const flipDist = ((Math.abs(metrics.spot - metrics.flip_point) / metrics.spot) * 100).toFixed(2);
      const nearFlip = parseFloat(flipDist) < 0.3;
      if (_lastFlowSummary?.composite_score !== undefined) {
        const cs = _lastFlowSummary.composite_score;
        const urgency = _lastFlowSummary.urgency || '';
        const bias = _lastFlowSummary.bias || '';
        const urgencyClass = cs >= 60 ? 'bearish' : (cs >= 40 ? '' : 'bullish');
        const biasClass = bias === 'BULLISH' ? 'bullish' : (bias === 'BEARISH' ? 'bearish' : '');
        cards = [
          { label: 'Move Score', value: `${cs}/100`, sub: urgency, classes: `flow-status ${urgencyClass}` },
          { label: 'Direction', value: bias, sub: `${_lastFlowSummary.snapshots || 0} snapshots`, classes: `flow-status ${biasClass}` },
          { label: 'Flip Distance', value: `${flipDist}%`, sub: nearFlip ? 'DANGER ZONE' : (metrics.spot > metrics.flip_point ? 'Above Flip' : 'Below Flip'), classes: `flow-status ${nearFlip ? 'bearish' : 'bullish'}` },
          { label: 'Dealer Regime', value: metrics.regime, classes: `regime ${regimeClass}` },
        ];
      } else {
        cards = [
          { label: 'Spot Price', value: metrics.spot.toLocaleString() },
          { label: 'Flip Distance', value: `${flipDist}%`, sub: metrics.spot > metrics.flip_point ? 'Above Flip' : 'Below Flip', classes: `flow-status ${nearFlip ? 'bearish' : 'bullish'}` },
          { label: 'Flip Point', value: metrics.flip_point.toLocaleString(), sub: 'Regime Break Level' },
          { label: 'Dealer Regime', value: metrics.regime, classes: `regime ${regimeClass}` },
        ];
      }
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
        { label: 'Delta Magnet', value: metrics.apex.price.toLocaleString(undefined, { maximumFractionDigits: 0 }), sub: 'Neutral Apex Point', classes: 'flow-status' },
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

  // ── Black-Scholes math (inline, no library) ──────────────
  function _normPdf(x) { return Math.exp(-0.5 * x * x) / 2.5066282746310002; }
  function _normCdf(x) {
    if (x > 6) return 1; if (x < -6) return 0;
    const a = Math.abs(x);
    const t = 1 / (1 + 0.2316419 * a);
    const t2 = t * t, t3 = t2 * t, t4 = t3 * t, t5 = t4 * t;
    const inner = 0.319381530 * t - 0.356563782 * t2 + 1.781477937 * t3
                - 1.821255978 * t4 + 1.330274429 * t5;
    const c = 1 - _normPdf(a) * inner;
    return x >= 0 ? c : 1 - c;
  }

  function _recalcGreeks(S, strikes, callIV, putIV, callOI, putOI, lotSize, T, r) {
    const sqrtT = Math.sqrt(T);
    const n = strikes.length;
    const gex = new Array(n), dex = new Array(n);
    for (let i = 0; i < n; i++) {
      const K = strikes[i];
      const sigC = Math.max(callIV[i] / 100, 0.001);
      const d1c = (Math.log(S / K) + (r + 0.5 * sigC * sigC) * T) / (sigC * sqrtT);
      const gammaC = _normPdf(d1c) / (S * sigC * sqrtT);
      const deltaC = _normCdf(d1c);

      const sigP = Math.max(putIV[i] / 100, 0.001);
      const d1p = (Math.log(S / K) + (r + 0.5 * sigP * sigP) * T) / (sigP * sqrtT);
      const gammaP = _normPdf(d1p) / (S * sigP * sqrtT);
      const deltaP = _normCdf(d1p) - 1;

      const gexMul = lotSize * S * S * 0.01;
      gex[i] = (-gammaC * callOI[i] + gammaP * putOI[i]) * gexMul;
      const dexMul = lotSize * S;
      dex[i] = (-deltaC * callOI[i] - deltaP * putOI[i]) * dexMul;
    }
    return { gex, dex };
  }

  function _computeFlip(strikes, gex) {
    for (let i = 0; i < gex.length - 1; i++) {
      const g1 = gex[i], g2 = gex[i + 1];
      if ((g1 <= 0 && g2 >= 0) || (g1 >= 0 && g2 <= 0)) {
        if (Math.abs(g2 - g1) < 1e-9) return strikes[i];
        return strikes[i] - g1 * (strikes[i + 1] - strikes[i]) / (g2 - g1);
      }
    }
    let minIdx = 0, minVal = Math.abs(gex[0] || 0);
    for (let i = 1; i < gex.length; i++) {
      if (Math.abs(gex[i]) < minVal) { minVal = Math.abs(gex[i]); minIdx = i; }
    }
    return strikes[minIdx];
  }

  function _topNByAbs(strikes, vals, n) {
    const arr = vals.map((v, i) => ({ a: Math.abs(v), s: strikes[i] }));
    arr.sort((a, b) => b.a - a.a);
    return arr.slice(0, n).map(x => x.s);
  }

  async function _renderGexDexInteractive(index, containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = '<div class="chart-placeholder"><div class="spin"></div><span>Loading Greek Interaction…</span></div>';

    let raw;
    try {
      const json = await API.getChart(index, 'gex_dex_combined');
      raw = json.data;
    } catch (err) {
      el.innerHTML = `<div class="alert alert-error">Failed to load data: ${err.message}</div>`;
      return;
    }

    const { strikes, call_iv, put_iv, call_oi, put_oi, spot, lot_size, T, r } = raw;
    const dtick = strikes.length >= 2 ? strikes[1] - strikes[0] : 50;
    const bw = dtick * 0.8;
    const RANGE = Math.max(500, dtick * 10);
    const STEP = Math.max(25, dtick / 2);

    el.innerHTML = `
      <div style="width:100%;height:100%;display:flex;flex-direction:column;gap:8px;padding:8px 4px;">
        <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:0 8px;">
          <span style="font-size:11px;color:#94A3B8;text-transform:uppercase;letter-spacing:.06em;">Spot Shift</span>
          <input type="range" id="gi-slider-${containerId}"
            min="${-RANGE}" max="${RANGE}" step="${STEP}" value="0"
            style="flex:1;min-width:180px;accent-color:#6366f1;cursor:pointer;">
          <div style="display:flex;gap:16px;">
            <div style="text-align:center;"><div style="font-size:10px;color:#64748B;">Shifted Spot</div>
              <div id="gi-spot-${containerId}" style="font-size:14px;font-weight:700;color:#F59E0B;">${Math.round(spot).toLocaleString()}</div></div>
            <div style="text-align:center;"><div style="font-size:10px;color:#64748B;">Move</div>
              <div id="gi-move-${containerId}" style="font-size:14px;font-weight:700;color:#6366F1;">0</div></div>
            <div style="text-align:center;"><div style="font-size:10px;color:#64748B;">Net GEX</div>
              <div id="gi-gex-${containerId}" style="font-size:14px;font-weight:700;color:#6366F1;">—</div></div>
          </div>
        </div>
        <div id="gi-plot-${containerId}" style="flex:1;min-height:500px;"></div>
      </div>`;

    const plotEl   = document.getElementById(`gi-plot-${containerId}`);
    const slider   = document.getElementById(`gi-slider-${containerId}`);
    const lblSpot  = document.getElementById(`gi-spot-${containerId}`);
    const lblMove  = document.getElementById(`gi-move-${containerId}`);
    const lblGex   = document.getElementById(`gi-gex-${containerId}`);

    const C_POS  = '#6366F1', C_NEG = '#F43F5E';
    const C_ABS  = 'rgba(239,222,11,0.3)';
    const C_SPOT = '#F59E0B', C_FLIP = '#F1F5F9';
    const C_ZONE = 'rgba(245,158,11,0.12)';

    function renderPlot(deltaSpot) {
      const S = spot + deltaSpot;
      const { gex } = _recalcGreeks(S, strikes, call_iv, put_iv, call_oi, put_oi, lot_size, T, r);
      const absGex = gex.map(Math.abs);
      const flip = _computeFlip(strikes, gex);
      const zones = _topNByAbs(strikes, gex, 3);
      const netGex = gex.reduce((a, b) => a + b, 0);

      const gexPos = gex.map(v => v > 0 ? v : 0);
      const gexNeg = gex.map(v => v < 0 ? v : 0);

      const traces = [
        { name: '+Dealer GEX', x: strikes, y: gexPos, type: 'bar', width: bw,
          marker: { color: C_POS }, opacity: 0.9, yaxis: 'y' },
        { name: '-Dealer GEX', x: strikes, y: gexNeg, type: 'bar', width: bw,
          marker: { color: C_NEG }, opacity: 0.9, yaxis: 'y' },
        { name: 'Abs GEX Heat', x: strikes, y: absGex, type: 'scatter', mode: 'lines',
          fill: 'tozeroy', fillcolor: C_ABS,
          line: { color: 'rgba(168,85,247,0.4)', width: 2 }, yaxis: 'y2' },
      ];

      const shapes = [];
      const annotations = [];

      shapes.push({ type: 'line', xref: 'x', yref: 'paper',
        x0: S, x1: S, y0: 0, y1: 1,
        line: { color: C_SPOT, width: 1.5, dash: 'solid' } });
      annotations.push({ xref: 'x', yref: 'paper', x: S, y: 1.04,
        text: `SPOT: ${Math.round(S)}`, showarrow: false,
        font: { size: 10, color: C_SPOT }, xanchor: 'left',
        bgcolor: 'rgba(0,0,0,0.5)', bordercolor: 'rgba(255,255,255,0.1)' });

      shapes.push({ type: 'line', xref: 'x', yref: 'paper',
        x0: flip, x1: flip, y0: 0, y1: 1,
        line: { color: C_FLIP, width: 1.5, dash: 'dot' } });
      annotations.push({ xref: 'x', yref: 'paper', x: flip, y: 1.04,
        text: `ZERO: ${Math.round(flip)}`, showarrow: false,
        font: { size: 10, color: C_FLIP }, xanchor: 'left',
        bgcolor: 'rgba(0,0,0,0.5)', bordercolor: 'rgba(255,255,255,0.1)' });

      if (deltaSpot !== 0) {
        shapes.push({ type: 'line', xref: 'x', yref: 'paper',
          x0: spot, x1: spot, y0: 0, y1: 1,
          line: { color: 'rgba(255,255,255,0.2)', width: 1, dash: 'dot' } });
        annotations.push({ xref: 'x', yref: 'paper', x: spot, y: 0.97,
          text: `ORIG: ${Math.round(spot)}`, showarrow: false,
          font: { size: 9, color: '#64748B' }, xanchor: 'center' });
      }

      for (const zs of zones) {
        shapes.push({ type: 'rect', xref: 'x', yref: 'paper',
          x0: zs - bw / 2, x1: zs + bw / 2, y0: 0, y1: 1,
          fillcolor: C_ZONE, line: { width: 0 }, layer: 'below' });
      }

      const regime = S > flip ? 'LONG GAMMA' : 'SHORT GAMMA';
      annotations.push({ xref: 'paper', yref: 'paper', x: 0.99, y: 0.97,
        text: regime, showarrow: false, xanchor: 'right',
        font: { size: 11, color: S > flip ? C_POS : C_NEG, weight: 700 },
        bgcolor: 'rgba(0,0,0,0.5)', bordercolor: 'rgba(255,255,255,0.1)' });

      const titleText = `${index} — DEALER GAMMA EXPOSURE @ ${Math.round(S)}`;
      const layout = {
        title: { text: titleText.toUpperCase(), font: { size: 12, color: '#94A3B8', weight: 700 }, x: 0.01, y: 0.98 },
        paper_bgcolor: 'rgba(15,23,42,0)',
        plot_bgcolor: 'rgba(30,41,59,0.2)',
        font: { color: '#CBD5E1', family: "'Inter', sans-serif", size: 11 },
        legend: { bgcolor: 'rgba(0,0,0,0)', borderwidth: 0, orientation: 'h',
          yanchor: 'bottom', y: 1.02, xanchor: 'right', x: 1, font: { size: 10 } },
        margin: { l: 50, r: 50, t: 100, b: 60 },
        height: 650, autosize: true,
        barmode: 'overlay',
        xaxis: { gridcolor: 'rgba(255,255,255,0.04)', zeroline: false,
          showline: true, linecolor: 'rgba(255,255,255,0.1)',
          tickfont: { size: 10 }, tickmode: 'linear', dtick, tickangle: -45 },
        yaxis: { title: 'Dealer GEX', gridcolor: 'rgba(255,255,255,0.04)',
          zeroline: true, zerolinecolor: 'rgba(255,255,255,0.1)', tickfont: { size: 10 } },
        yaxis2: { title: 'Absolute Dealer GEX', gridcolor: 'rgba(255,255,255,0.04)',
          zeroline: false, overlaying: 'y', side: 'right', tickfont: { size: 10 } },
        shapes, annotations,
      };

      lblSpot.textContent = Math.round(S).toLocaleString();
      lblMove.textContent = (deltaSpot >= 0 ? '+' : '') + deltaSpot;
      lblMove.style.color = deltaSpot > 0 ? '#34D399' : deltaSpot < 0 ? '#F43F5E' : '#6366F1';
      lblGex.textContent = (netGex / 1e7).toFixed(1) + ' Cr';
      lblGex.style.color = netGex >= 0 ? C_POS : C_NEG;

      if (!plotEl._init) {
        Plotly.newPlot(plotEl, traces, layout, { responsive: true, displayModeBar: false });
        plotEl._init = true;
      } else {
        Plotly.react(plotEl, traces, layout);
      }
    }

    renderPlot(0);
    slider.addEventListener('input', () => renderPlot(parseInt(slider.value, 10)));
  }

  return { render };
})();
