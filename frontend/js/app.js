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

        // 4. Handle Compare button visibility for second file
        const fileSel2 = document.getElementById('select-file-2');
        if (fileSel2) {
            fileSel2.style.display = st.compareMode ? 'block' : 'none';
        }
    }

    async function _refreshFileControls(index) {
        const expirySel = document.getElementById('select-expiry');
        const dateSel = document.getElementById('select-date');
        const fileSel = document.getElementById('select-file');
        const dateSel2 = document.getElementById('select-date-2');
        const fileSel2 = document.getElementById('select-file-2');

        if (!expirySel || !dateSel || !fileSel) return;

        try {
            const data = await API.getFiles(index);
            const filesDict = data.files || {};
            const expiries = Object.keys(filesDict).sort().reverse();

            const idxData = State.getIndexData(index);
            const selExpiry = idxData.selectedExpiry || (expiries.length ? expiries[0] : '');

            // 1. Populate Expiry
            expirySel.innerHTML = expiries.length
                ? expiries.map(e => `<option value="${e}" ${e === selExpiry ? 'selected' : ''}>${e}</option>`).join('')
                : '<option value="">No Data</option>';

            // Helper to process files for an expiry
            const processFiles = (expiry) => {
                const files = filesDict[expiry] || [];
                const dateMap = {}; // { date: [files] }
                files.forEach(f => {
                    let datePart;
                    if (f.length >= 10 && f.includes('-')) {
                        // New format: YYYY-MM-DD_HHMMSS.csv
                        datePart = f.substring(0, 10);
                    } else {
                        // Legacy format: DD_HHMMSS.csv or similar
                        datePart = f.substring(0, 2);
                    }
                    if (!dateMap[datePart]) dateMap[datePart] = [];
                    dateMap[datePart].push(f);
                });
                return dateMap;
            };

            const dateMap = processFiles(selExpiry);
            const dates = Object.keys(dateMap).sort().reverse();
            const selDate = idxData.selectedDate || (dates.length ? dates[0] : '');

            // 2. Populate Date
            dateSel.innerHTML = dates.length
                ? dates.map(d => `<option value="${d}" ${d === selDate ? 'selected' : ''}>${d}</option>`).join('')
                : '<option value="">—</option>';

            // 3. Populate Files for selected date
            const files = dateMap[selDate] || [];
            const selFile = idxData.selectedFile || (files.length ? files[0] : '');

            fileSel.innerHTML = files.length
                ? files.map(f => `<option value="${f}" ${f === selFile ? 'selected' : ''}>${f}</option>`).join('')
                : '<option value="">—</option>';

            // 4. Handle Compare Mode (Repeat for File 2)
            let selDate2 = idxData.selectedDate2;
            let selFile2 = idxData.selectedFile2;

            if (State.get().compareMode) {
                dateSel2.style.display = 'block';
                fileSel2.style.display = 'block';

                if (!selDate2) selDate2 = dates.length > 0 ? dates[0] : '';
                dateSel2.innerHTML = dates.map(d => `<option value="${d}" ${d === selDate2 ? 'selected' : ''}>${d}</option>`).join('');

                const files2 = dateMap[selDate2] || [];
                if (!selFile2) selFile2 = files2.length > 1 ? files2[1] : (files2.length ? files2[0] : '');
                fileSel2.innerHTML = '<option value="">Compare With...</option>' +
                    files2.map(f => `<option value="${f}" ${f === selFile2 ? 'selected' : ''}>${f}</option>`).join('');
            } else {
                dateSel2.style.display = 'none';
                fileSel2.style.display = 'none';
            }

            // Important: update state so renderDashboard has the correct values
            State.setIndexData(index, {
                selectedExpiry: selExpiry,
                selectedDate: selDate,
                selectedFile: selFile,
                selectedDate2: selDate2,
                selectedFile2: selFile2
            });

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
            State.setIndexData(index, {
                selectedExpiry: expiry,
                selectedDate: '', // Reset down the chain
                selectedFile: ''
            });

            await _refreshFileControls(index);
            const st = State.getIndexData(index);
            if (st.selectedFile) _triggerLoad(index, expiry, st.selectedFile);
        });

        // 2.1 Date Change
        const dateSel = document.getElementById('select-date');
        dateSel?.addEventListener('change', async () => {
            const date = dateSel.value;
            const index = State.getIndex();
            const expiry = expirySel.value;
            State.setIndexData(index, {
                selectedDate: date,
                selectedFile: ''
            });

            await _refreshFileControls(index);
            const st = State.getIndexData(index);
            if (st.selectedFile) _triggerLoad(index, expiry, st.selectedFile);
        });

        // 3. File Change
        fileSel?.addEventListener('change', () => {
            const file = fileSel.value;
            const expiry = expirySel.value;
            const index = State.getIndex();
            State.setIndexData(index, { selectedFile: file });
            _triggerLoad(index, expiry, file);
        });

        // 6. Date 2 Change
        const dateSel2 = document.getElementById('select-date-2');
        dateSel2?.addEventListener('change', async () => {
            const date = dateSel2.value;
            const index = State.getIndex();
            State.setIndexData(index, {
                selectedDate2: date,
                selectedFile2: ''
            });
            await _refreshFileControls(index);
            renderDashboard();
        });

        // 6.1 File 2 Change
        const fileSel2 = document.getElementById('select-file-2');
        fileSel2?.addEventListener('change', () => {
            const file = fileSel2.value;
            const index = State.getIndex();
            State.setIndexData(index, { selectedFile2: file });
            renderDashboard();
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

        // 5. Compare Button
        const compareBtn = document.getElementById('btn-toggle-compare');
        compareBtn?.addEventListener('click', async () => {
            const st = State.get();
            const nextMode = !st.compareMode;
            State.set({ compareMode: nextMode });

            // Visual state update
            compareBtn.classList.toggle('active', nextMode);

            // Sync topbar (shows/hides file2)
            await updateTopbar();

            // Re-render dashboard
            renderDashboard();
        });

        // 6. Sync DB Button
        const syncBtn = document.getElementById('btn-sync-db');
        let _isSyncing = false;
        syncBtn?.addEventListener('click', async () => {
            if (_isSyncing) return;
            _isSyncing = true;
            syncBtn.innerHTML = '<div class="spinner"></div> Syncing…';

            try {
                const response = await API.syncSupabaseData();
                const syncedCount = response?.synced_count || 0;
                if (syncedCount > 0) {
                    Toast.show(`Successfully synced ${syncedCount} snapshots from DB`, "success");
                    await updateTopbar();
                    renderDashboard();
                } else {
                    Toast.show("DB is already fully synced", "info");
                }
            } catch (e) {
                Toast.show(`Sync failed: ${e.message}`, "error");
            } finally {
                _isSyncing = false;
                syncBtn.innerHTML = '<div class="status-dot-small online" id="sync-status-dot"></div> Sync DB';
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
