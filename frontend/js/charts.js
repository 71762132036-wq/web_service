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
    function render(containerId, figure) {
        const el = document.getElementById(containerId);
        if (!el) return;

        if (typeof figure === 'string') {
            try { figure = JSON.parse(figure); } catch (e) { console.error("Parse fail", e); return; }
        }

        try {
            // Remove any legacy placeholders/spinners if they exist
            const placeholder = el.querySelector('.chart-placeholder');
            if (placeholder) placeholder.remove();

            if (figure && figure.error) {
                el.innerHTML = `<div class="chart-placeholder"><span>${figure.error}</span></div>`;
                return;
            }

            Plotly.react(el, figure.data, figure.layout, RESPONSIVE_CONFIG);
        } catch (err) {
            console.error("Plotly Error:", err, figure);
            el.innerHTML = `<div class="chart-placeholder">
        <span>Chart render error: ${err.message}</span>
      </div>`;
        }
    }

    /**
     * Show a loading state. We now use a class-based approach 
     * to avoid clearing the innerHTML and killing the Plotly instance.
     */
    function showLoading(containerId) {
        const el = document.getElementById(containerId);
        if (!el) return;

        // If the element is empty, add a placeholder
        if (!el.innerHTML || el.innerHTML.trim() === "") {
            el.innerHTML = `<div class="chart-placeholder">
                <div class="spin"></div>
                <span>Loading chart…</span>
            </div>`;
        } else {
            // If it already has a chart, we can just add a subtle 
            // loading overlay or opacity effect if desired.
            el.style.opacity = "0.6";
        }
    }

    /**
     * Generic wrapper to fetch data and render a chart.
     */
    async function _handleChartFetch(containerId, fetchPromise) {
        showLoading(containerId);
        const el = document.getElementById(containerId);
        try {
            const data = await fetchPromise();
            if (el) el.style.opacity = "1";
            render(containerId, data.figure);
            return data;
        } catch (err) {
            if (el) {
                el.style.opacity = "1";
                el.innerHTML = `<div class="chart-placeholder"><span>${err.message}</span></div>`;
            }
            return null;
        }
    }

    // ── Public API ──────────────────────────────────────────

    function fetchAndRender(index, chartType, containerId, mode = 'net') {
        return _handleChartFetch(containerId, () => API.getChart(index, chartType, mode));
    }

    function fetchAndRenderCompare(index, chartType, expiry, file1, file2, containerId) {
        return _handleChartFetch(containerId, () => API.getCompareChart(index, chartType, expiry, file1, file2));
    }

    function fetchAndRenderDirection(index, chartType, expiry, file1, file2, containerId) {
        return _handleChartFetch(containerId, () => API.getDirectionChart(index, chartType, expiry, file1, file2));
    }

    return { render, showLoading, fetchAndRender, fetchAndRenderCompare, fetchAndRenderDirection };
})();
