// LX-FE-PLAYER (2026-09-29): bütün taymerlər bir yerdən idarə olunur — faza dəyişəndə heç biri
// «asılı» qalmır (QA: mərhələ keçidlərində köhnə interval/timeout işləməməlidir).
import { state } from './state.js?v=lx20260929';

export function clearTicker() {
    if (state.ticker) {
        window.clearInterval(state.ticker);
        state.ticker = null;
    }
}

export function startTicker(fn, intervalMs = 200) {
    clearTicker();
    state.ticker = window.setInterval(fn, intervalMs);
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
    }, Math.max(0, Number(delay) || 0));
}

export function clearAckTimer() {
    if (state.ackTimer) {
        window.clearTimeout(state.ackTimer);
        state.ackTimer = null;
    }
}

export function clearAllTimers() {
    clearTicker();
    clearPhaseTimer();
    clearAckTimer();
}
