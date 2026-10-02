// LX-FE-PLAYER (2026-09-29): ehtiyat sinxronizasiya.
//  * WS bağlıdırsa — hər ~3 s snapshot (əvvəlki kimi).
//  * WS açıqdırsa — «gözətçi»: gözlənilən server mesajı gecikibsə (sual bitib, reveal gəlməyib; və ya
//    növbəti sual vaxtı keçib) snapshot çəkir; gecikmə davam etdikcə interval 4 → 8 → 16 → 30 s artır
//    (host əl rejimində gözləyəndə 90 telefon serveri döyəcləməsin).
import { PHASES } from './config.js?v=lx20261002';
import { fetchState } from './api.js?v=lx20261002';
import { isSocketOpen } from './sockets.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';
import { getRevealTimings, nowMs, ts } from './utils.js?v=lx20261002';

let tickCount = 0;
let watchdogDelay = 0;
let nextWatchdogAt = 0;

function isOverdue() {
    const now = nowMs();
    const question = state.currentQuestion;
    if (
        question &&
        (state.phase === PHASES.INTRO ||
            state.phase === PHASES.QUESTION ||
            state.phase === PHASES.LOCKED ||
            state.phase === PHASES.TIMEUP)
    ) {
        const endsAt = ts(question.ends_at);
        return Boolean(endsAt && now > endsAt + 3000);
    }
    if (
        (state.phase === PHASES.RESULT || state.phase === PHASES.LEADERBOARD || state.phase === PHASES.SUSPENSE) &&
        state.revealPayload
    ) {
        return now > getRevealTimings(state.revealPayload).nextQuestionAt + 5000;
    }
    if (state.phase === PHASES.IDLE) {
        return true;
    }
    return false;
}

function watchdog() {
    if (!isOverdue()) {
        watchdogDelay = 0;
        nextWatchdogAt = 0;
        return;
    }
    if (Date.now() < nextWatchdogAt) return;
    watchdogDelay = watchdogDelay ? Math.min(30000, watchdogDelay * 2) : 4000;
    nextWatchdogAt = Date.now() + watchdogDelay;
    fetchState();
}

export function stopStatePolling() {
    if (state.pollTimer) {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
    }
}

export function startStatePolling() {
    if (state.pollTimer) return;
    state.pollTimer = window.setInterval(() => {
        tickCount += 1;
        if (document.hidden || state.removed || state.phase === PHASES.FINAL) return;
        if (!isSocketOpen()) {
            if (tickCount % 3 === 0) fetchState();
            return;
        }
        watchdog();
    }, 1000);
}

export function resetWatchdog() {
    watchdogDelay = 0;
    nextWatchdogAt = 0;
}
