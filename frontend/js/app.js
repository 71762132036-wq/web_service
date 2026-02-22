/**
 * app.js — Main application: router, index selector, topbar updates, toasts.
 * Initializes the app and wires all navigation.
 */

// ── Toast utility ─────────────────────────────────────────

const Toast = (() => {
    const container = document.getElementById('toast-container');

    function show(message, type = 'info', duration = 4000) {
        const icons = { info: '', success: '', error: '', warning: '' };
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span>${message}</span>`;
        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('removing');
            toast.addEventListener('animationend', () => toast.remove());
        }, duration);
    }

    return { show };
})();


// ── Main App ──────────────────────────────────────────────

const App = (() => {

    const PAGES = {
        'dashboard': DashboardPage,
        'data-management': DataManagementPage,
    };

    let _currentPage = 'dashboard';

    // ── Navigate ─────────────────────────────────────────

    function navigate(page) {
        if (!PAGES[page]) return;
        _currentPage = page;

        // Update nav items
        document.querySelectorAll('.nav-item').forEach(el => {
            el.classList.toggle('active', el.dataset.page === page);
        });

        // Update topbar title
        const titles = {
            'dashboard': `${State.getIndex()} — Gamma Exposure Analysis`,
            'data-management': 'Data Management',
        };
        document.getElementById('topbar-title').textContent = titles[page] || '';

        // Render page
        const content = document.getElementById('page-content');
        PAGES[page].render(content);
    }

    // ── Topbar ────────────────────────────────────────────

    function updateTopbar() {
        const st = State.get();
        const curData = State.getIndexData();

        const statusChip = document.getElementById('data-status-chip');
        const expiryChip = document.getElementById('expiry-chip');

        if (statusChip) {
            statusChip.textContent = curData.hasData
                ? `${st.selectedIndex} loaded`
                : 'No data loaded';
        }
        if (expiryChip) {
            expiryChip.textContent = curData.expiry ? `Expiry: ${curData.expiry}` : 'No Expiry';
        }

        // Also update the topbar title for dashboard
        if (_currentPage === 'dashboard') {
            const el = document.getElementById('topbar-title');
            if (el) el.textContent = `${st.selectedIndex} — Gamma Exposure Analysis`;
        }
    }

    // ── Index selector ────────────────────────────────────

    function _wireIndexSelector() {
        const sel = document.getElementById('index-select');
        if (!sel) return;

        sel.addEventListener('change', () => {
            const newIndex = sel.value;
            if (newIndex === State.getIndex()) return;

            State.set({ selectedIndex: newIndex });

            updateTopbar();
            navigate(_currentPage); // Re-render current page for new index
            Toast.show(`Switched to ${newIndex}`, 'info', 2500);
        });
    }

    // ── Sidebar nav ───────────────────────────────────────

    function _wireNavItems() {
        document.querySelectorAll('.nav-item[data-page]').forEach(item => {
            item.addEventListener('click', () => navigate(item.dataset.page));
        });
    }

    // ── Init ──────────────────────────────────────────────

    async function init() {
        // Check API health
        try {
            await API.health();
            document.getElementById('sidebar-status').textContent = 'API Connected';
        } catch (_) {
            document.getElementById('sidebar-status').textContent = 'API Offline';
            Toast.show('Cannot reach backend. Is the server running?', 'error', 8000);
        }

        _wireIndexSelector();
        _wireNavItems();

        // Sync initial state from backend
        try {
            const data = await API.getStatus();
            if (data && data.status) {
                Object.entries(data.status).forEach(([idx, info]) => {
                    State.setIndexData(idx, {
                        hasData: info.hasData,
                        loadedFile: info.filepath
                    });
                });
            }
        } catch (e) { console.error("Initial sync failed", e); }

        navigate('dashboard');
        updateTopbar();
    }

    return { init, navigate, updateTopbar };
})();


// ── Bootstrap ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => App.init());
