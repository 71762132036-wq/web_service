/**
 * state.js — Centralized reactive application state.
 * Mirrors what Streamlit's session_state did for the POC.
 */

const State = (() => {
    let _state = {
        selectedIndex: 'Nifty',
        hasData: false,   // whether data is loaded for the current index
        loadedFile: '',
        expiry: '',
        indices: ['Nifty', 'BankNifty', 'Sensex'],
    };

    const _listeners = new Set();

    function get() { return { ..._state }; }

    function set(patch) {
        _state = { ..._state, ...patch };
        _listeners.forEach(fn => fn(_state));
    }

    function subscribe(fn) {
        _listeners.add(fn);
        return () => _listeners.delete(fn);  // returns unsubscribe
    }

    function getIndex() { return _state.selectedIndex; }

    return { get, set, subscribe, getIndex };
})();
