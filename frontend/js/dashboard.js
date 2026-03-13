/**
 * dashboard.js — Dashboard page: metrics, hierarchical analysis (Exposure/Others), vol surface.
 */

const DashboardPage = (() => {

  const _loadedCharts = new Set();
  let _lastFlowSummary = null;
  let _lastFilterData = null;
  let _lastFilterContext = null;
  
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

    // 1. Partial Update Logic — if dashboard exists, don't wipe it
    const existingDashboard = container.querySelector('.dashboard-wrapper');
    if (!existingDashboard) {
      container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Synchronizing ${index} Dashboard…</div>`;
    }

    try {
      // 2. Multi-level caching for Metrics & Vol
      let metrics, volData;
      
      if (_metricsCache.has(index) && _volCache.has(index)) {
        metrics = _metricsCache.get(index);
        volData = _volCache.get(index);
      } else {
        [metrics, volData] = await Promise.all([
          API.getMetrics(index),
          API.getVolSurface(index),
        ]);
        _metricsCache.set(index, metrics);
        _volCache.set(index, volData);
      }

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

            <div class="nav-row cat-row">
              <div class="nav-group">
                <span class="nav-label">CAT</span>
                <div class="category-pills">${buildCategoryNav()}</div>
              </div>

              ${structure[st.selectedBucket]?.[st.selectedCategory]?.length > 1 ? `
                <div class="nav-group context-group">
                  <span class="nav-label">SUB</span>
                  ${buildSubChartNav()}
                </div>
              ` : ''}
            </div>

            ${st.selectedCategory === 'Filter' ? `
              <!-- Filter Controls Removed (Sorting implemented via Headers) -->
            ` : ''}
          </div>

          <!-- Main Analysis Canvas -->
          <div class="analysis-content">
            ${buildChartPanel()}
          </div>

          <!-- Secondary Metrics Row -->
          ${!['Filter'].includes(st.selectedCategory) ? `
          <div class="metrics-section">
            <div class="metrics-grid">
              ${_lastFlowSummary?.vtl ? `
                ${buildMetricCard('VTL Level', _lastFlowSummary.vtl.toLocaleString(), `Price: ${_lastFlowSummary.vtl.toLocaleString()}`, 'flow-status')}
                ${buildMetricCard('VTL Distance', `${Math.abs(_lastFlowSummary.distance_pct).toFixed(2)}%`, `Spot is ${_lastFlowSummary.direction} VTL`, `flow-status ${_lastFlowSummary.distance_pct > 0 ? 'bullish' : 'bearish'}`)}
                ${buildMetricCard('Spot Price', metrics.spot.toLocaleString())}
                ${buildMetricCard('Quant Power', metrics.quant_power.toLocaleString(), 'Blended Zero Level')}
              ` : (st.selectedBucket === 'Direction' && _lastFlowSummary ? `
                ${buildMetricCard('Call Flow', _lastFlowSummary.calls.label, `Pressure: ${(_lastFlowSummary.calls.pressure * 100).toFixed(1)}%`, `flow-status ${_lastFlowSummary.calls.pressure > 0.2 ? 'bullish' : (_lastFlowSummary.calls.pressure < -0.2 ? 'bearish' : '')}`)}
                ${buildMetricCard('Put Flow', _lastFlowSummary.puts.label, `Pressure: ${(_lastFlowSummary.puts.pressure * 100).toFixed(1)}%`, `flow-status ${_lastFlowSummary.puts.pressure > 0.2 ? 'bearish' : (_lastFlowSummary.puts.pressure < -0.2 ? 'bullish' : '')}`)}
                ${buildMetricCard('Spot Price', metrics.spot.toLocaleString())}
                ${buildMetricCard('Quant Power', metrics.quant_power.toLocaleString(), 'Blended Zero Level')}
              ` : `
                ${buildMetricCard('Spot Price', metrics.spot.toLocaleString())}
                ${buildMetricCard('Quant Power', metrics.quant_power.toLocaleString(), 'Blended Zero Level')}
                ${buildMetricCard('Flip Point', metrics.flip_point.toLocaleString(), 'Zero Gamma Level')}
                ${buildMetricCard('Dealer Regime', metrics.regime, '', `regime ${regimeClass}`)}
              `)}
            </div>
          </div>
          ` : ''}

          <!-- Contextual Surface Details -->
          ${st.selectedBucket === 'Volatility' ? `
            <div class="section-overlay">
              <div class="section-header"><h2>Surface Details</h2><div class="section-line"></div></div>
              <div class="card glass-card">${buildVolSurface(vs)}</div>
            </div>
          ` : ''}

        </div>`;

      _wireAnalysisNav(container);

      _loadedCharts.clear();

      // 1. Chart Loading Logic
      const activeCharts = structure[st.selectedBucket]?.[st.selectedCategory] || [];
      const filterKeys = ['overall_filter', 'strike_filter'];

      if (activeCharts.length > 0) {
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
            Charts.fetchAndRenderCompare(index, chart.key, expiry, file1, file2, chart.id);
          } else {
            const el = document.getElementById(chart.id);
            if (el) el.innerHTML = '<div class="chart-placeholder"><span>Select two files to compare</span></div>';
          }
        } 
        else if (filterKeys.includes(chart.key)) {
          // Render filter table into the standard chart container
          const filterArea = container.querySelector(`#${chart.id}`);
          if (filterArea) renderFilterPage(filterArea);
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
      
      _wireAnalysisNav(container);
      _wireAnalysisContent(container);

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
        const structure = getStructure();
        const firstCat = Object.keys(structure[bucket])[0];
        const firstSub = structure[bucket][firstCat][0]?.id || null;
        State.set({ selectedBucket: bucket, selectedCategory: firstCat, selectedSubChart: firstSub });
        render(container);
        return;
      }

      // 2. Category clicks
      const catBtn = e.target.closest('.category-btn');
      if (catBtn) {
        const cat = catBtn.dataset.category;
        const structure = getStructure();
        const firstSub = structure[State.get().selectedBucket][cat][0]?.id || null;
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
      if (modeBtn && modeBtn.closest('.mode-toggle')) {
        State.set({ gammaChartMode: modeBtn.dataset.mode });
        render(container);
        return;
      }

      // 5. ... removed trend and threshold ...
    });
  }

  function _wireAnalysisContent(container) {
    const contentSection = container.querySelector('.analysis-content');
    if (!contentSection) return;

    contentSection.addEventListener('click', e => {
      const sortHeader = e.target.closest('.sortable-header');
      if (sortHeader) {
        const col = sortHeader.dataset.col;
        const currentSort = State.get().filterSortCol;
        const currentDir = State.get().filterSortDir;
        
        const newDir = (col === currentSort && currentDir === 'desc') ? 'asc' : 'desc';
        State.set({ filterSortCol: col, filterSortDir: newDir });
        render(container);
      }
    });
  }

  function _renderMetricsOnly(container, metrics, regimeClass) {
    const grid = container.querySelector('.metrics-grid');
    if (!grid) return;
    const st = State.get();
    grid.innerHTML = `
      ${_lastFlowSummary?.vtl ? `
        ${buildMetricCard('VTL Level', _lastFlowSummary.vtl.toLocaleString(), `Price: ${_lastFlowSummary.vtl.toLocaleString()}`, 'flow-status')}
        ${buildMetricCard('VTL Distance', `${Math.abs(_lastFlowSummary.distance_pct).toFixed(2)}%`, `Spot is ${_lastFlowSummary.direction} VTL`, `flow-status ${_lastFlowSummary.distance_pct > 0 ? 'bullish' : 'bearish'}`)}
        ${buildMetricCard('Spot Price', metrics.spot.toLocaleString())}
        ${buildMetricCard('Quant Power', metrics.quant_power.toLocaleString(), 'Blended Zero Level')}
      ` : (st.selectedBucket === 'Direction' && _lastFlowSummary ? `
        ${buildMetricCard('Call Flow', _lastFlowSummary.calls.label, `Pressure: ${(_lastFlowSummary.calls.pressure * 100).toFixed(1)}%`, `flow-status ${_lastFlowSummary.calls.pressure > 0.2 ? 'bullish' : (_lastFlowSummary.calls.pressure < -0.2 ? 'bearish' : '')}`)}
        ${buildMetricCard('Put Flow', _lastFlowSummary.puts.label, `Pressure: ${(_lastFlowSummary.puts.pressure * 100).toFixed(1)}%`, `flow-status ${_lastFlowSummary.puts.pressure > 0.2 ? 'bearish' : (_lastFlowSummary.puts.pressure < -0.2 ? 'bullish' : '')}`)}
        ${buildMetricCard('Spot Price', metrics.spot.toLocaleString())}
        ${buildMetricCard('Quant Power', metrics.quant_power.toLocaleString(), 'Blended Zero Level')}
      ` : `
        ${buildMetricCard('Spot Price', metrics.spot.toLocaleString())}
        ${buildMetricCard('Quant Power', metrics.quant_power.toLocaleString(), 'Blended Zero Level')}
        ${buildMetricCard('Flip Point', metrics.flip_point.toLocaleString(), 'Zero Gamma Level')}
        ${buildMetricCard('Dealer Regime', metrics.regime, '', `regime ${regimeClass}`)}
      `)}
    `;
  }

  async function renderFilterPage(container) {
    const st = State.get();
    const activeSub = st.selectedSubChart || 'filter-overall';

    if (activeSub === 'filter-strike') {
      container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🛠️</div>
                    <h3>Strike Wise Filter</h3>
                    <p>This feature is currently under development. Stay tuned!</p>
                </div>`;
      return;
    }

    try {
      // Temporal sync: get expiry and filename from current dashboard selection
      const idxData = State.getIndexData(st.selectedIndex);
      const { selectedExpiry: expiry, selectedFile: filename } = idxData;
      const contextKey = `${st.selectedIndex}|${expiry}|${filename}`;

      let results;
      if (_lastFilterData && _lastFilterContext === contextKey) {
        results = [..._lastFilterData];
      } else {
        // Only show internal loading if we don't have cached data
        container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Loading analysis…</div>`;
        const data = await API.getOverallFilter(0, 'all', expiry, filename, false);
        _lastFilterData = data.results || [];
        _lastFilterContext = contextKey;
        results = [..._lastFilterData];
      }

      // Client-Side Sorting
      const sortCol = st.filterSortCol || 'Change(%)';
      const sortDir = st.filterSortDir || 'desc';

      results.sort((a, b) => {
        let valA = a[sortCol];
        let valB = b[sortCol];
        
        // Handle string comparison for names
        if (sortCol === 'Stock') {
          return sortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        
        // Handle numeric comparison
        return sortDir === 'asc' ? valA - valB : valB - valA;
      });

      const getSortIcon = (col) => {
        if (st.filterSortCol !== col) return '<span class="sort-icon-neutral">↕</span>';
        return st.filterSortDir === 'desc' ? '<span class="sort-icon-active">▼</span>' : '<span class="sort-icon-active">▲</span>';
      };

      container.innerHTML = `
                <div class="filter-table-wrapper" style="margin-top: 0;">
                    ${results.length > 0 ? `
                        <table class="simple-table">
                            <thead>
                                <tr>
                                    <th class="sortable-header" data-col="Stock">Stock Name ${getSortIcon('Stock')}</th>
                                    <th class="sortable-header" data-col="Change(%)" style="text-align: right;">Gross Chg (%) ${getSortIcon('Change(%)')}</th>
                                    <th class="sortable-header" data-col="Call_OI_Chg_Pct" style="text-align: right;">Call Chg (%) ${getSortIcon('Call_OI_Chg_Pct')}</th>
                                    <th class="sortable-header" data-col="Put_OI_Chg_Pct" style="text-align: right;">Put Chg (%) ${getSortIcon('Put_OI_Chg_Pct')}</th>
                                    <th class="sortable-header" data-col="Net_Chg" style="text-align: right;">Net Chg ${getSortIcon('Net_Chg')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${results.map(r => {
                                    const netClass = r.Net_Chg > 0 ? 'text-accent-green' : (r.Net_Chg < 0 ? 'text-accent-red' : '');
                                    const callClass = r.Call_OI_Chg_Pct > 0 ? 'text-accent-green' : (r.Call_OI_Chg_Pct < 0 ? 'text-accent-red' : '');
                                    const putClass = r.Put_OI_Chg_Pct > 0 ? 'text-accent-green' : (r.Put_OI_Chg_Pct < 0 ? 'text-accent-red' : '');
                                    
                                    return `
                                    <tr>
                                        <td class="stock-name">${r.Stock}</td>
                                        <td class="stock-change" style="text-align: right;">${r["Change(%)"]}%</td>
                                        <td style="text-align: right; font-weight: 600;" class="${callClass}">${r.Call_OI_Chg_Pct}%</td>
                                        <td style="text-align: right; font-weight: 600;" class="${putClass}">${r.Put_OI_Chg_Pct}%</td>
                                        <td style="text-align: right; font-weight: 700;" class="${netClass}">${r.Net_Chg.toLocaleString()}</td>
                                    </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    ` : `
                        <div class="empty-results">
                            <div class="empty-icon" style="font-size: 24px; margin-bottom: 12px; opacity: 0.5;">🔍</div>
                            <p>No stocks currently meet the filtering criteria (>${threshold}% Gross OI Change).</p>
                        </div>
                    `}
                </div>`;
    } catch (err) {
      container.innerHTML = `<div class="alert alert-error">Filter error: ${err.message}</div>`;
    }
  }

  return { render };
})();
