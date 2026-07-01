import { UI } from './dom.js';
import { STATE_POLL_INTERVAL_MS } from './constants.js';
import { state } from './state.js';
import { applySessionSettings } from './settings.js';
import { renderIdleStage } from './lobby.js';
import { applyStateSnapshot } from './snapshot.js';
import { openPresenterWindow } from './presentation.js';
import { fmt, log, notifyHostShell, tr, updateServerTimeOffset } from './utils.js';

let playWS = null;

export function setPlaySocket(socket) {
    playWS = socket;
}

export function clearPendingStateSync() {
    if (state.pendingSyncTimer) {
        window.clearTimeout(state.pendingSyncTimer);
        state.pendingSyncTimer = 0;
    }
}

export function scheduleStateSyncFallback(delayMs = 900) {
    if (state.sessionState === "finished") return;
    clearPendingStateSync();
    const mutationSnapshot = state.lastStateMutationAt;
    state.pendingSyncTimer = window.setTimeout(() => {
        state.pendingSyncTimer = 0;
        if (state.sessionState === "finished") return;
        if (state.lastStateMutationAt === mutationSnapshot) {
            syncState();
        }
    }, Math.max(150, delayMs));
}

export async function post(url, data = null) {
    try {
        const options = {
            method: "POST",
            headers: {
                "X-CSRFToken": CONFIG.csrf,
            },
        };
        if (data) options.body = data;
        const response = await fetch(url, options);
        const payload = await response.json();
        if (payload?.ok) {
            scheduleStateSyncFallback();
        }
        return payload;
    } catch (error) {
        log(fmt(tr("postError", "POST error: {message}"), { message: error.message || "" }));
        return { ok: false };
    }
}

export async function postJson(url, payload = {}) {
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": CONFIG.csrf,
            },
            body: JSON.stringify(payload || {}),
        });
        const data = await response.json();
        if (data?.ok) {
            if (data.settings) {
                applySessionSettings(data.settings);
                if (data.is_locked != null) {
                    state.isLocked = Boolean(data.is_locked);
                }
                if (state.sessionState === "lobby") {
                    renderIdleStage();
                }
                notifyHostShell();
            }
            scheduleStateSyncFallback();
        }
        return data;
    } catch (error) {
        log(fmt(tr("postError", "POST error: {message}"), { message: error.message || "" }));
        return { ok: false };
    }
}

let syncInFlight = false;
export async function syncState() {
    if (syncInFlight) return null;
    syncInFlight = true;
    try {
        const response = await fetch(CONFIG.urls.state, {
            headers: { Accept: "application/json" },
        });
        if (!response.ok) {
            log(`State sync failed: ${response.status}`);
            return null;
        }
        const receivedAtMs = Date.now();
        const snapshot = await response.json();
        updateServerTimeOffset(snapshot, receivedAtMs);
        applyStateSnapshot(snapshot);
        return snapshot;
    } catch (error) {
        log(fmt(tr("playMessageError", "Play message error: {message}"), { message: error.message || "" }));
        return null;
    } finally {
        syncInFlight = false;
    }
}

export function stopStatePolling() {
    if (state.statePollTimer) {
        window.clearInterval(state.statePollTimer);
        state.statePollTimer = 0;
    }
    clearPendingStateSync();
}

export function startStatePolling() {
    if (state.statePollTimer) return;
    state.statePollTimer = window.setInterval(() => {
        if (!document.hidden && (!playWS || playWS.readyState !== WebSocket.OPEN)) {
            syncState();
        }
    }, STATE_POLL_INTERVAL_MS);
}

export function startGame() {
    openPresenterWindow();
    const formData = new FormData();
    const count = parseInt(UI.questionCount?.value, 10) || 1;
    formData.append("question_count", count);
    return post(CONFIG.urls.start, formData);
}

export function revealQuestion() {
    return post(CONFIG.urls.reveal);
}

export function nextQuestion() {
    return post(CONFIG.urls.next);
}

export function skipQuestionIntro() {
    if (!CONFIG?.urls?.skipIntro) return Promise.resolve({ ok: false });
    return post(CONFIG.urls.skipIntro);
}

export function finishGame() {
    return post(CONFIG.urls.finish);
}
