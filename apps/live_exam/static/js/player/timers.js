import { state } from './state.js';

export function clearTicker() {
    if (state.ticker) {
        window.clearInterval(state.ticker);
        state.ticker = null;
    }
}

export function clearPhaseTimer() {
    if (state.phaseTimer) {
        window.clearTimeout(state.phaseTimer);
        state.phaseTimer = null;
    }
}

export function queuePhaseTransition(callback, delay) {
    clearPhaseTimer();
    state.phaseTimer = window.setTimeout(() => {
        state.phaseTimer = null;
        callback();
    }, Math.max(0, delay));
}
