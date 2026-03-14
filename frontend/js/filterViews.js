/**
 * filterViews.js — Dedicated module for rendering the "Overall" and "Strike Wise"
 * OI filtering views. Extracted from dashboard.js for better maintainability.
 */

const FilterViews = (() => {

    let _lastFilterData = null;
    let _lastStrikeFilterData = null;
    let _lastFilterContext = null;
    let _lastStrikeFilterContext = null;
    let _expandedStocks = new Set();

    /**
     * Re-wires event listeners specifically for the filter tables.
     * Delegate to the main container.
     */
    function wireControls(container, renderCallback) {
        container.addEventListener('click', e => {
            // 1. Table Sorting
            const sortHeader = e.target.closest('.sortable-header');
            if (sortHeader) {
                const col = sortHeader.dataset.col;
                const currentSort = State.get().filterSortCol;
                const currentDir = State.get().filterSortDir;
                const newDir = (col === currentSort && currentDir === 'desc') ? 'asc' : 'desc';
                State.set({ filterSortCol: col, filterSortDir: newDir });
                renderCallback(container);
                return;
            }

            // 2. Stock Expansion (Strike Filter)
            const expandBtn = e.target.closest('.expand-stock-btn');
            if (expandBtn) {
                const stock = expandBtn.dataset.stock;
                if (_expandedStocks.has(stock)) _expandedStocks.delete(stock);
                else _expandedStocks.add(stock);
                renderCallback(container);
                return;
            }

            // 3. Sentiment Toggle (Strike Filter)
            const segmentBtn = e.target.closest('.segment-btn');
            if (segmentBtn) {
                const sentiment = segmentBtn.dataset.sentiment;
                if (sentiment) {
                    State.set({ strikeFilterSentiment: sentiment });
                    renderCallback(container);
                    return;
                }
            }
        });
    }

    /**
     * Clears cached data context when necessary (e.g. index/file changes)
     */
    function clearContext() {
        _lastFilterData = null;
        _lastStrikeFilterData = null;
        _lastFilterContext = null;
        _lastStrikeFilterContext = null;
        _expandedStocks.clear();
    }

    async function render(container) {
        const st = State.get();
        const activeSub = st.selectedSubChart || 'filter-overall';

        if (activeSub === 'filter-strike') {
            await _renderStrikeFilter(container, st);
        } else {
            await _renderOverallFilter(container, st);
        }
    }

    // ── Internal Render Methods ──────────────────────────────────────────────

    async function _renderStrikeFilter(container, st) {
        try {
            const idxData = State.getIndexData(st.selectedIndex);
            const { selectedExpiry: expiry, selectedFile: filename } = idxData;
            const contextKey = `${st.selectedIndex}|${expiry}|${filename}`;

            let data;
            if (_lastStrikeFilterData && _lastStrikeFilterContext === contextKey) {
                data = _lastStrikeFilterData;
            } else {
                container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Scanning market strikes…</div>`;
                data = await API.getStrikeFilter(10, expiry, filename);
                _lastStrikeFilterData = data;
                _lastStrikeFilterContext = contextKey;
                _expandedStocks.clear();
            }

            const results = data.results || [];

            // Toggles
            const currentSentiment = State.get().strikeFilterSentiment || 'all';
            const togglesHtml = `
            <div class="quick-filters">
                <div class="segmented-control">
                <button class="segment-btn ${currentSentiment === 'all' ? 'active' : ''}" data-sentiment="all">All Trends</button>
                <button class="segment-btn ${currentSentiment === 'Writing' ? 'active' : ''}" data-sentiment="Writing">Writing Only</button>
                <button class="segment-btn ${currentSentiment === 'Unwinding' ? 'active' : ''}" data-sentiment="Unwinding">Unwinding</button>
                </div>
            </div>
            `;

            // Filter Logic
            let filteredResults = results;
            if (currentSentiment !== 'all') {
                filteredResults = results.filter(r => r.Sentiment === currentSentiment);
            }

            // Group by Stock
            const groups = {};
            filteredResults.forEach(r => {
                if (!groups[r.Stock]) groups[r.Stock] = [];
                groups[r.Stock].push(r);
            });

            const groupedStocks = Object.keys(groups).map(name => {
                const stockStrikes = groups[name];
                const top = stockStrikes[0];
                return { name, top, count: stockStrikes.length, all: stockStrikes };
            });

            // Sorting
            const sortCol = st.filterSortCol || 'Influence';
            const sortDir = st.filterSortDir || 'desc';

            groupedStocks.sort((a, b) => {
                let valA = a.top[sortCol] || a[sortCol];
                let valB = b.top[sortCol] || b[sortCol];
                if (sortCol === 'Stock' || sortCol === 'name') {
                    valA = a.name; valB = b.name;
                    return sortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
                }
                return sortDir === 'asc' ? valA - valB : valB - valA;
            });

            const getSortIcon = (col) => {
                if (st.filterSortCol !== col) return '<span class="sort-icon-neutral">↕</span>';
                return st.filterSortDir === 'desc' ? '<span class="sort-icon-active">▼</span>' : '<span class="sort-icon-active">▲</span>';
            };

            container.innerHTML = `
            ${togglesHtml}
            <div class="filter-table-wrapper" style="margin-top: 20px;">
                ${groupedStocks.length > 0 ? `
                    <table class="simple-table grouped-table">
                        <thead>
                            <tr>
                                <th class="sortable-header" data-col="Stock">Stock ${getSortIcon('Stock')}</th>
                                <th style="text-align: right;">Cherry Picked Strike</th>
                                <th class="sortable-header" data-col="Influence" style="text-align: right;">Strike Influence ${getSortIcon('Influence')}</th>
                                <th class="sortable-header" data-col="OI_Chg_Pct" style="text-align: right;">OI Chg (%) ${getSortIcon('OI_Chg_Pct')}</th>
                                <th>Signal Setup</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${groupedStocks.map(stock => {
                                const r = stock.top;
                                const isExpanded = _expandedStocks.has(stock.name);
                                
                                // Setup Logic
                                let setupName = '';
                                let setupClass = '';
                                if (r.Sentiment === 'Writing') {
                                    setupName = r.Type === 'Put' ? 'BULLISH WRITING' : 'BEARISH WRITING';
                                    setupClass = r.Type === 'Put' ? 'setup-bullish' : 'setup-bearish';
                                } else {
                                    setupName = r.Type === 'Call' ? 'BULLISH UNWIND' : 'BEARISH UNWIND';
                                    setupClass = r.Type === 'Call' ? 'setup-bull-unwind' : 'setup-bear-unwind';
                                }

                                const chgClass = r.OI_Chg_Raw > 0 ? 'text-accent-green' : 'text-accent-red';

                                let rows = `
                                <tr class="stock-group-header">
                                    <td class="stock-name">
                                        <button class="expand-stock-btn" data-stock="${stock.name}">${isExpanded ? '▼' : '▶'}</button>
                                        ${stock.name} 
                                        <span class="badge">${stock.count}</span>
                                    </td>
                                    <td style="text-align: right; font-weight: 700; color: var(--text-primary);">
                                        <span style="opacity: 0.5; font-size: 10px; margin-right: 4px;">${r.Type.toUpperCase()}</span>
                                        ${r.Strike.toLocaleString()}
                                    </td>
                                    <td style="text-align: right;">
                                        <div class="influence-container">
                                        <span class="influence-val">${r.Influence}%</span>
                                        <div class="influence-bar-bg"><div class="influence-bar-fill" style="width: ${r.Influence}%"></div></div>
                                        </div>
                                    </td>
                                    <td style="text-align: right; font-weight: 800; font-size: 15px;">${r.OI_Chg_Pct}%</td>
                                    <td><span class="setup-signal-badge ${setupClass}">${setupName}</span></td>
                                </tr>
                                `;

                                if (isExpanded) {
                                stock.all.slice(1).forEach(sub => {
                                    let subSetup = '';
                                    let subClass = '';
                                    if (sub.Sentiment === 'Writing') {
                                        subSetup = sub.Type === 'Put' ? 'Bull Writing' : 'Bear Writing';
                                        subClass = sub.Type === 'Put' ? 'text-accent-green' : 'text-accent-red';
                                    } else {
                                        subSetup = sub.Type === 'Call' ? 'Bull Unwind' : 'Bear Unwind';
                                        subClass = sub.Type === 'Call' ? 'text-accent-cyan' : 'text-accent-amber';
                                    }
                                    const schgClass = sub.OI_Chg_Raw > 0 ? 'text-accent-green' : 'text-accent-red';
                                    rows += `
                                        <tr class="sub-strike-row">
                                            <td class="indent-cell"></td>
                                            <td style="text-align: right; opacity: 0.8;">
                                                <span style="opacity: 0.5; font-size: 9px; margin-right: 4px;">${sub.Type.toUpperCase()}</span>
                                                ${sub.Strike.toLocaleString()}
                                            </td>
                                            <td style="text-align: right; opacity: 0.6; font-size: 11px;">Inf: ${sub.Influence}%</td>
                                            <td style="text-align: right; opacity: 0.8;">${sub.OI_Chg_Pct}%</td>
                                            <td class="${subClass}" style="font-size: 11px; font-weight: 600; opacity: 0.8;">${subSetup}</td>
                                        </tr>
                                    `;
                                });
                                }
                                return rows;
                            }).join('')}
                        </tbody>
                    </table>
                ` : `
                    <div class="empty-results">
                        <div class="empty-icon" style="font-size: 24px; margin-bottom: 12px; opacity: 0.5;">🔍</div>
                        <p>No trade setups found with current filter.</p>
                    </div>
                `}
            </div>`;
        } catch (err) {
            container.innerHTML = `<div class="alert alert-error">Strike Filter error: ${err.message}</div>`;
        }
    }

    async function _renderOverallFilter(container, st) {
        try {
            // Temporal sync: get expiry and filename from current dashboard selection
            const idxData = State.getIndexData(st.selectedIndex);
            const { selectedExpiry: expiry, selectedFile: filename } = idxData;
            const contextKey = `${st.selectedIndex}|${expiry}|${filename}`;

            let results;
            if (_lastFilterData && _lastFilterContext === contextKey) {
                results = [..._lastFilterData];
            } else {
                container.innerHTML = `<div class="loading-overlay"><div class="spinner"></div> Loading analysis…</div>`;
                const data = await API.getOverallFilter(0, 'all', expiry, filename, false);
                _lastFilterData = data.results || [];
                _lastFilterContext = contextKey;
                results = [..._lastFilterData];
            }

            const sortCol = st.filterSortCol || 'Influence'; // Changed default sort column
            const sortDir = st.filterSortDir || 'desc';

            results.sort((a, b) => {
                let valA = a[sortCol];
                let valB = b[sortCol];
                if (sortCol === 'Stock') return sortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
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
                            <p>No stocks currently meet the filtering criteria.</p>
                        </div>
                    `}
                </div>`;
        } catch (err) {
            container.innerHTML = `<div class="alert alert-error">Filter error: ${err.message}</div>`;
        }
    }

    return { render, wireControls, clearContext };
})();
