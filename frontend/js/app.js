/**
 * app.js — Main application: unified router, topbar controls, and state synchronization.
 * Transitioned to a single-page macOS sleek architecture.
 */

// ── Toast utility ─────────────────────────────────────────

const Toast = (() => {
    const container = document.getElementById('toast-container');

    function show(message, type = 'info', duration = 4000) {
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

    let _isFetching = false;

    // ── Render ───────────────────────────────────────────

    function renderDashboard() {
        const content = document.getElementById('page-content');
        DashboardPage.render(content);
    }

    // ── Topbar Synchronization ───────────────────────────

    async function updateTopbar() {
        const st = State.get();
        const curData = State.getIndexData();
        const index = st.selectedIndex;

        // 1. Update status dot
        const dot = document.getElementById('fetch-status-dot');
        if (dot) {
            dot.classList.toggle('online', curData.hasData);
        }

        // 2. Update status text
        const statusChip = document.getElementById('data-status-chip');
        if (statusChip) {
            statusChip.textContent = curData.hasData ? "Connected" : "No Data";
            statusChip.style.color = curData.hasData ? "var(--accent-green)" : "var(--text-muted)";
        }

        // 3. Sync dropdowns (Expiry and File)
        await _refreshFileControls(index);
    }

    async function _refreshFileControls(index) {
        const expirySel = document.getElementById('select-expiry');
        const fileSel = document.getElementById('select-file');
        if (!expirySel || !fileSel) return;

        try {
            const data = await API.getFiles(index);
            const filesDict = data.files || {};
            const expiries = Object.keys(filesDict).sort().reverse();

            const idxData = State.getIndexData(index);
            const selExpiry = idxData.selectedExpiry || (expiries.length ? expiries[0] : '');

            // Populate Expiry
            expirySel.innerHTML = expiries.length
                ? expiries.map(e => `<option value="${e}" ${e === selExpiry ? 'selected' : ''}>${e}</option>`).join('')
                : '<option value="">No Data</option>';

            // Populate Files for selected expiry
            const files = filesDict[selExpiry] || [];
            const selFile = idxData.selectedFile || (files.length ? files[0] : '');

            fileSel.innerHTML = files.length
                ? files.map(f => `<option value="${f}" ${f === selFile ? 'selected' : ''}>${f}</option>`).join('')
                : '<option value="">—</option>';

        } catch (e) {
            console.error("Failed to refresh file controls", e);
        }
    }

    // ── Wire Controls ────────────────────────────────────

    function _wireControls() {
        const indexSel = document.getElementById('index-select');
        const expirySel = document.getElementById('select-expiry');
        const fileSel = document.getElementById('select-file');
        const fetchBtn = document.getElementById('btn-fetch-all');

        // 1. Index Change
        indexSel?.addEventListener('change', async () => {
            const newIndex = indexSel.value;
            State.set({ selectedIndex: newIndex });
            await updateTopbar();
            renderDashboard();
        });

        // 2. Expiry Change
        expirySel?.addEventListener('change', async () => {
            const expiry = expirySel.value;
            const index = State.getIndex();
            State.setIndexData(index, { selectedExpiry: expiry });

            // Re-fetch files for this expiry to update the file dropdown
            await _refreshFileControls(index);

            // Trigger load if a file is now available/selected
            const newFile = fileSel.value;
            if (newFile) _triggerLoad(index, expiry, newFile);
        });

        // 3. File Change
        fileSel?.addEventListener('change', () => {
            const file = fileSel.value;
            const expiry = expirySel.value;
            const index = State.getIndex();
            State.setIndexData(index, { selectedFile: file });
            _triggerLoad(index, expiry, file);
        });

        // 4. Fetch Button
        fetchBtn?.addEventListener('click', async () => {
            if (_isFetching) return;
            _isFetching = true;
            fetchBtn.innerHTML = '<div class="spinner"></div> Fetching…';

            try {
                const data = await API.fetchLiveData(null);
                Toast.show("Live data synchronized for all indices", "success");
                await updateTopbar();
                renderDashboard();
            } catch (e) {
                Toast.show(`Fetch failed: ${e.message}`, "error");
            } finally {
                _isFetching = false;
                fetchBtn.innerHTML = '<div class="status-dot-small" id="fetch-status-dot"></div> Fetch Live';
                // Re-sync dot state after innerHTML reset
                const curData = State.getIndexData();
                document.getElementById('fetch-status-dot')?.classList.toggle('online', curData.hasData);
            }
        });
    }

    async function _triggerLoad(index, expiry, filename) {
        if (!expiry || !filename) return;
        try {
            const data = await API.loadFile(index, expiry, filename);
            State.setIndexData(index, {
                hasData: true,
                loadedFile: data.filepath,
                expiry: data.expiry
            });
            Toast.show(`Loaded ${index} ${filename}`, "success", 2000);
            renderDashboard();
        } catch (e) {
            Toast.show(`Load failed: ${e.message}`, "error");
        }
    }

    // ── Init ──────────────────────────────────────────────

    async function init() {
        try {
            const status = await API.getStatus();
            if (status && status.status) {
                Object.entries(status.status).forEach(([idx, info]) => {
                    State.setIndexData(idx, {
                        hasData: info.hasData,
                        loadedFile: info.filepath
                    });
                });
            }
        } catch (e) { console.error("Bootstrap sync failed", e); }

        _wireControls();
        await updateTopbar();
        renderDashboard();
    }

    return { init, updateTopbar };
})();

document.addEventListener('DOMContentLoaded', () => App.init());
