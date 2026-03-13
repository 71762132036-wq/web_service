/**
 * state.js — Centralized reactive application state.
 */

const State = (() => {
    let _state = {
        selectedIndex: 'Nifty',
        selectedBucket: 'Exposure',
        selectedCategory: 'Gamma',
        selectedSubChart: null, // Track sub-chart within category
        gammaChartMode: 'net', // 'net' or 'raw'
        compareMode: false,
        // instrumentType drives whether we are looking at indices or stocks
        instrumentType: 'Index',
        filterThreshold: 80,
        filterTrend: 'all',
        filterSortCol: 'Change(%)', // Default sort column
        filterSortDir: 'desc',      // Default sort direction
        // lists populated from API
        indexList: [],
        stockList: [],
        // raw metadata returned from server
        metadata: {},
        // full combined list for backward compatibility
        indices: [],
        // Store data status per instrument
        indexData: {},
    };

    const _listeners = new Set();

    function get() { return { ..._state }; }

    function set(patch) {
        _state = { ..._state, ...patch };
        _listeners.forEach(fn => fn(_state));
    }

    function getInstruments(type) {
        if (type === 'Stock') return [..._state.stockList];
        return [..._state.indexList];
    }

    function setInstrumentType(type) {
        if (type !== 'Index' && type !== 'Stock') return;
        set({ instrumentType: type });
    }

    function getInstrumentType() { return _state.instrumentType; }

    function subscribe(fn) {
        _listeners.add(fn);
        return () => _listeners.delete(fn);
    }

    function getIndex() { return _state.selectedIndex; }

    function getIndexData(index) {
        const target = index || _state.selectedIndex;
        return _state.indexData[target] || { hasData: false, loadedFile: '', expiry: '' };
    }

    function setIndexData(index, data) {
        const target = index || _state.selectedIndex;
        // Immutable update for reactivity and safety
        _state = {
            ..._state,
            indexData: {
                ..._state.indexData,
                [target]: { ..._state.indexData[target], ...data }
            }
        };
        _listeners.forEach(fn => fn(_state));
    }

    function initIndices(response) {
        // response: { indices: [...], default: ..., metadata: { name: {lot_size, expiry_type, type} } }
        const { indices, metadata } = response;
        _state.indices = indices;
        _state.metadata = metadata || {};
        _state.indexList = indices.filter(n => _state.metadata[n]?.type === 'index');
        _state.stockList = indices.filter(n => _state.metadata[n]?.type === 'stock');
        // ensure indexData exists for each instrument
        indices.forEach(index => {
            if (!_state.indexData[index]) {
                _state.indexData[index] = { hasData: false, loadedFile: '', expiry: '', selectedExpiry: '', selectedDate: '', selectedFile: '', selectedDate2: '', selectedFile2: '' };
            }
        });
        notifySubscribers();
    }

    return {
        get, set, subscribe, getIndex, getIndexData, setIndexData, initIndices,
        getInstruments, setInstrumentType, getInstrumentType
    };
})();
