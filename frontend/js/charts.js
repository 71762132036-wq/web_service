/**
 * charts.js — Plotly chart rendering helpers.
 * Each chart receives a container element ID and Plotly JSON string.
 */

const Charts = (() => {

    const RESPONSIVE_CONFIG = {
        responsive: true,
        displayModeBar: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
        toImageButtonOptions: { format: 'png', scale: 2 },
    };

    /**
     * Render a Plotly chart from JSON string into a container element.
     * @param {string} containerId  - DOM element id
     * @param {string} figureJson   - Plotly JSON string (from backend)
     */
    function render(containerId, figureJson) {
        const el = document.getElementById(containerId);
        if (!el) return;

        // Force clear any CSS spinners or placeholder HTML
        // before asking Plotly to take over the container.
        el.innerHTML = "";

        try {
            const figure = JSON.parse(figureJson);
            Plotly.react(el, figure.data, figure.layout, RESPONSIVE_CONFIG);
        } catch (err) {
            el.innerHTML = `<div class="chart-placeholder">
        <span>Chart render error: ${err.message}</span>
      </div>`;
        }
    }

    /**
     * Show a loading spinner inside a chart container.
     */
    function showLoading(containerId) {
        const el = document.getElementById(containerId);
        if (!el) return;

        // CRITICAL FIX: If the element was already a Plotly chart, we must purge it
        // before overwriting its innerHTML with our loading spinner. 
        // Otherwise, Plotly.react will get confused and fail to clear our spinner.
        try { Plotly.purge(el); } catch (e) { }

        el.innerHTML = `<div class="chart-placeholder">
      <div class="spin"></div>
      <span>Loading chart…</span>
    </div>`;
    }

    /**
     * Fetch a chart from the API and render it.
     * @param {string} index
     * @param {string} chartType  - gex | regime | call_put | iv_smile | rr_bf
     * @param {string} containerId
     */
    async function fetchAndRender(index, chartType, containerId, mode = 'net') {
        showLoading(containerId);
        try {
            const data = await API.getChart(index, chartType, mode);
            render(containerId, data.figure);
            return data;
        } catch (err) {
            const el = document.getElementById(containerId);
            if (el) el.innerHTML = `<div class="chart-placeholder">
        <span>${err.message}</span>
      </div>`;
        }
    }

    async function fetchAndRenderCompare(index, chartType, expiry, file1, file2, containerId) {
        showLoading(containerId);
        try {
            const data = await API.getCompareChart(index, chartType, expiry, file1, file2);
            render(containerId, data.figure);
        } catch (err) {
            const el = document.getElementById(containerId);
            if (el) el.innerHTML = `<div class="chart-placeholder">
        <span>${err.message}</span>
      </div>`;
        }
    }

    async function fetchAndRenderDirection(index, chartType, expiry, file1, file2, containerId) {
        showLoading(containerId);
        try {
            const data = await API.getDirectionChart(index, chartType, expiry, file1, file2);
            render(containerId, data.figure);
            return data; // Return full data for summary info (pressure labels)
        } catch (err) {
            const el = document.getElementById(containerId);
            if (el) el.innerHTML = `<div class="chart-placeholder">
        <span>${err.message}</span>
      </div>`;
            return null;
        }
    }

    return { render, showLoading, fetchAndRender, fetchAndRenderCompare, fetchAndRenderDirection };
})();
