/**
 * app.js — Main application: router, index selector, topbar updates, toasts.
 * Initializes the app and wires all navigation.
 */

// ── Toast utility ─────────────────────────────────────────

const Toast = (() => {
    const container = document.getElementById('toast-container');

    function show(message, type = 'info', duration = 4000) {
        const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span>${icons[type] || '💬'}</span><span>${message}</span>`;
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
            'dashboard': `📊 ${State.getIndex()} — Gamma Exposure Analysis`,
            'data-management': '⚙️ Data Management',
        };
        document.getElementById('topbar-title').textContent = titles[page] || '';

        // Render page
        const content = document.getElementById('page-content');
        PAGES[page].render(content);
    }

    // ── Topbar ────────────────────────────────────────────

    function updateTopbar() {
        const st = State.get();

        const statusChip = document.getElementById('data-status-chip');
        const expiryChip = document.getElementById('expiry-chip');

        if (statusChip) {
            statusChip.textContent = st.hasData
                ? `✅ ${st.selectedIndex} loaded`
                : '⚡ No data loaded';
        }
        if (expiryChip) {
            expiryChip.textContent = st.expiry ? `📅 ${st.expiry}` : '📅 —';
        }

        // Also update the topbar title for dashboard
        if (_currentPage === 'dashboard') {
            const el = document.getElementById('topbar-title');
            if (el) el.textContent = `📊 ${st.selectedIndex} — Gamma Exposure Analysis`;
        }
    }

    // ── Index selector ────────────────────────────────────

    function _wireIndexSelector() {
        const sel = document.getElementById('index-select');
        if (!sel) return;

        sel.addEventListener('change', () => {
            const newIndex = sel.value;
            if (newIndex === State.getIndex()) return;

            // Clear data state when switching index
            State.set({
                selectedIndex: newIndex,
                hasData: false,
                loadedFile: '',
                expiry: '',
            });

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

        // Load initial index state
        navigate('dashboard');
        updateTopbar();
    }

    return { init, navigate, updateTopbar };
})();


// ── Bootstrap ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => App.init());
