import { UI } from './dom.js?v=lx20261008';
import { LOBBY_RESYNC_INTERVAL_MS, STATE_POLL_INTERVAL_MS } from './constants.js?v=lx20261008';
import { state } from './state.js?v=lx20261008';
import { applySessionSettings } from './settings.js?v=lx20261008';
import { rebuildLobbyCloud, renderIdleStage } from './lobby.js?v=lx20261008';
import { applyStateSnapshot } from './snapshot.js?v=lx20261008';
import { openPresenterWindow } from './presentation.js?v=lx20261008';
import { fmt, log, notifyHostShell, tr, updateServerTimeOffset } from './utils.js?v=lx20261008';

let playWS = null;
// Eyni URL-ə eyni anda ikinci POST göndərilmir (sürətli təkrar kliklər → 409 yox).
const inflight = new Map();

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
        if (state.lastStateMutationAt === mutationSnapshot) syncState();
    }, Math.max(150, delayMs));
}

async function readJson(response) {
    try {
        return await response.json();
    } catch (error) {
        return { ok: false, status: response.status };
    }
}

export function post(url, data = null) {
    if (!data && inflight.has(url)) return inflight.get(url);
    const request = (async () => {
        try {
            const options = { method: "POST", headers: { "X-CSRFToken": CONFIG.csrf } };
            if (data) options.body = data;
            const response = await fetch(url, options);
            const payload = await readJson(response);
            if (payload?.ok) scheduleStateSyncFallback();
            else if (response.status === 409) scheduleStateSyncFallback(150); // vəziyyət artıq dəyişib — serverlə tutuşdur
            return payload;
        } catch (error) {
            log(fmt(tr("postError", "POST error: {message}"), { message: error.message || "" }));
            return { ok: false };
        } finally {
            if (!data) inflight.delete(url);
        }
    })();
    if (!data) inflight.set(url, request);
    return request;
}

export async function postJson(url, payload = {}) {
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": CONFIG.csrf },
            body: JSON.stringify(payload || {}),
        });
        const data = await readJson(response);
        if (data?.ok) {
            if (data.settings) {
                applySessionSettings(data.settings);
                if (data.is_locked != null) state.isLocked = Boolean(data.is_locked);
                if (state.sessionState === "lobby") renderIdleStage();
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
let syncPromise = null;
export function syncState() {
    if (syncInFlight) return Promise.resolve(null);
    syncInFlight = true;
    syncPromise = fetchAndApplyState();
    return syncPromise;
}

async function fetchAndApplyState() {
    try {
        const response = await fetch(CONFIG.urls.state, { headers: { Accept: "application/json" } });
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
        syncPromise = null;
    }
}

/**
 * Sahib 2026-09-30: aparıcının «Yenilə» düyməsi — HƏQİQİ vəziyyəti (oyunçu siyahısı + say,
 * sual/cavab sayğacı) serverdən yenidən çəkir və səhifəni yeniləmədən yerində çəkir.
 * Yolda olan sinxron varsa, onun bitməsini gözləyib TƏZƏ sorğu göndərir.
 */
export async function refreshHostState() {
    const buttons = () => document.querySelectorAll("[data-action='refresh-state']");
    buttons().forEach((button) => {
        button.disabled = true;
        button.classList.remove("is-done");
        button.classList.add("is-busy");
        button.setAttribute("aria-busy", "true");
    });
    let snapshot = null;
    try {
        if (syncPromise) await syncPromise;
        snapshot = await syncState();
        if (snapshot && snapshot.state === "lobby") rebuildLobbyCloud();
    } finally {
        buttons().forEach((button) => {
            button.disabled = false;
            button.classList.remove("is-busy");
            button.removeAttribute("aria-busy");
            if (snapshot) {
                button.classList.add("is-done");
                window.setTimeout(() => button.classList.remove("is-done"), 1400);
            }
        });
    }
    log(snapshot ? "State refreshed" : "State refresh failed");
    return snapshot;
}

/** Lobbi açıq olduqca yüngül avtomatik sinxron (host başına ~15 s-də bir sorğu; oyunçularda YOX). */
export function startLobbyResync() {
    if (state.lobbyResyncTimer) return;
    state.lobbyResyncTimer = window.setInterval(() => {
        if (document.hidden || state.sessionState !== "lobby") return;
        syncState();
    }, LOBBY_RESYNC_INTERVAL_MS);
}

export function stopLobbyResync() {
    if (state.lobbyResyncTimer) {
        window.clearInterval(state.lobbyResyncTimer);
        state.lobbyResyncTimer = 0;
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
        if (!document.hidden && (!playWS || playWS.readyState !== WebSocket.OPEN)) syncState();
    }, STATE_POLL_INTERVAL_MS);
}

export function startGame() {
    openPresenterWindow();
    const formData = new FormData();
    const count = parseInt(UI.questionCount?.value, 10) || 1;
    formData.append("question_count", count);
    const key = CONFIG.urls.start;
    if (inflight.has(key)) return inflight.get(key);
    const request = post(CONFIG.urls.start, formData).finally(() => inflight.delete(key));
    inflight.set(key, request);
    return request;
}

export const revealQuestion = () => post(CONFIG.urls.reveal);
export const nextQuestion = () => post(CONFIG.urls.next);
export const finishGame = () => post(CONFIG.urls.finish);

export function skipQuestionIntro() {
    if (!CONFIG?.urls?.skipIntro) return Promise.resolve({ ok: false });
    return post(CONFIG.urls.skipIntro);
}
