/**
 * state.js — Centralized reactive application state.
 */

const State = (() => {
    let _state = {
        selectedIndex: 'Nifty',
        indices: ['Nifty', 'BankNifty', 'Sensex'],
        // Store data status per index: { indexName: { hasData, loadedFile, expiry, selectedExpiry, selectedFile } }
        indexData: {
            'Nifty': { hasData: false, loadedFile: '', expiry: '', selectedExpiry: '', selectedFile: '' },
            'BankNifty': { hasData: false, loadedFile: '', expiry: '', selectedExpiry: '', selectedFile: '' },
            'Sensex': { hasData: false, loadedFile: '', expiry: '', selectedExpiry: '', selectedFile: '' },
        }
    };

    const _listeners = new Set();

    function get() { return { ..._state }; }

    function set(patch) {
        _state = { ..._state, ...patch };
        _listeners.forEach(fn => fn(_state));
    }

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

    return { get, set, subscribe, getIndex, getIndexData, setIndexData };
})();
