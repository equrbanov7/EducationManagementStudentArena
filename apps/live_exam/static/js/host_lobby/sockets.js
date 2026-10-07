import { UI } from './dom.js?v=lx20261008';
import { state } from './state.js?v=lx20261008';
import { applySessionSettings } from './settings.js?v=lx20261008';
import { renderLobbyPlayers } from './lobby.js?v=lx20261008';
import { applyQuestionState, updateAnsweredCounter, updateReceivedCounter } from './question.js?v=lx20261008';
import { applyRevealState } from './reveal.js?v=lx20261008';
import { renderPodium } from './podium.js?v=lx20261008';
import { clearAutoTimers, clearPhaseLoop, setSessionState } from './presentation.js?v=lx20261008';
import { clearPendingStateSync, setPlaySocket, stopStatePolling, syncState } from './api.js?v=lx20261008';
import {
    esc,
    fmt,
    log,
    markStateMutation,
    rememberTimelinePayload,
    shouldApplyTimelinePayload,
    toMs,
    tr,
    updateServerTimeOffset,
    wsUrl,
} from './utils.js?v=lx20261008';

/* WS: lobbi + oyun kanalları. Bağlantı qopanda eksponensial gözləmə ilə yenidən
 * qoşulur (1 → 2 → 4 … ≤ 15 s + titrəmə); açılanda HTTP snapshot ilə vəziyyət
 * serverlə sinxronlaşır (UI həmişə server vəziyyətinə yaxınsayır). */

function spawnReaction(eventData) {
    if (!UI.reactionOverlay) return;
    const meta = (window.LiveAvatarCatalog || {}).reactions?.[eventData?.reaction_key] || {};
    if (UI.reactionOverlay.childElementCount > 24) return; // çox reaksiya — DOM-u şişirtmə
    const burst = document.createElement("div");
    burst.className = "host-reaction-burst";
    burst.innerHTML = `
        <span class="host-reaction-burst__emoji">${esc(meta.emoji || eventData?.emoji || "✨")}</span>
        <span class="host-reaction-burst__name">${esc(eventData?.player?.nickname || "")}</span>
    `;
    burst.style.left = `${16 + Math.random() * 68}%`;
    burst.style.setProperty("--reaction-drift", `${-26 + Math.random() * 52}px`);
    UI.reactionOverlay.appendChild(burst);
    setTimeout(() => burst.remove(), 2300);
}

const sockets = { lobby: null, play: null, retries: { lobby: 0, play: 0 }, timers: { lobby: 0, play: 0 }, closing: false };
let initialStateSynced = false;

export async function ensureInitialStateSync() {
    if (initialStateSynced) return null;
    initialStateSynced = true;
    return syncState();
}

function scheduleReconnect(kind, open) {
    if (sockets.closing) return;
    window.clearTimeout(sockets.timers[kind]);
    const attempt = Math.min(sockets.retries[kind], 4);
    const delay = Math.min(15000, 1000 * 2 ** attempt) + Math.random() * 400;
    sockets.retries[kind] += 1;
    sockets.timers[kind] = window.setTimeout(open, delay);
}

function onLobbyMessage(event) {
    try {
        const message = JSON.parse(event.data);
        const data = message.data || message;
        updateServerTimeOffset(data);
        if (data.type === "lobby_state") {
            // Sıradan çıxmış (daha köhnə) siyahı yeni sayı əzməsin (sahib 2026-09-30: «say azalır»).
            const builtAt = toMs(data.server_time);
            if (builtAt && state.lobbyStateAt && builtAt < state.lobbyStateAt) return;
            if (builtAt) state.lobbyStateAt = builtAt;
            markStateMutation();
            if (data.settings) applySessionSettings(data.settings);
            if (data.is_locked != null) state.isLocked = Boolean(data.is_locked);
            renderLobbyPlayers(data.players || [], data.count);
            return;
        }
        if (data.type === "reaction_event") spawnReaction(data);
    } catch (error) {
        log(fmt(tr("lobbyMessageError", "Lobby message error: {message}"), { message: error.message || "" }));
    }
}

function onPlayMessage(event) {
    try {
        const message = JSON.parse(event.data);
        const data = message.data || message;
        updateServerTimeOffset(data);

        if (data.type === "question_published") {
            if (!shouldApplyTimelinePayload(data)) return;
            rememberTimelinePayload(data);
            markStateMutation();
            const sameQuestion = state.currentQuestion && Number(state.currentQuestion.id) === Number(data.question?.id);
            // 2026-10-08 (L3): server bu suala cavab verməli oyunçu sayını göndərir (gec qoşulanlar növbəti sualdan).
            const total = data.total_players != null ? Number(data.total_players) : state.totalPlayers;
            applyQuestionState(data.question, sameQuestion ? state.answeredCount : 0, total);
            return;
        }
        if (data.type === "answer_progress") {
            if (state.currentQuestion && Number(data.question_id || 0) !== Number(state.currentQuestion.id || 0)) return;
            markStateMutation();
            state.answeredCount = Number(data.answered_count || 0);
            state.totalPlayers = Number(data.total_players || state.totalPlayers || 0);
            updateAnsweredCounter();
            return;
        }
        if (data.type === "delivery_progress") {
            // LXNET: sualı telefonuna alan oyunçu sayı (yalnız artır; köhnə sual üçün olanlar atılır).
            if (!state.currentQuestion || Number(data.question_id || 0) !== Number(state.currentQuestion.id || 0)) return;
            state.receivedQuestionId = Number(data.question_id);
            state.receivedCount = Math.max(Number(state.receivedCount || 0), Number(data.received_count || 0));
            updateReceivedCounter();
            return;
        }
        if (data.type === "reveal") {
            if (!shouldApplyTimelinePayload(data)) return;
            rememberTimelinePayload(data);
            markStateMutation();
            applyRevealState(data, state.currentQuestion);
            return;
        }
        if (data.type === "session_settings") {
            if (data.settings) applySessionSettings(data.settings);
            if (data.is_locked != null) state.isLocked = Boolean(data.is_locked);
            return;
        }
        if (data.type === "finished") {
            if (!shouldApplyTimelinePayload(data)) return;
            rememberTimelinePayload(data);
            markStateMutation();
            clearPhaseLoop();
            clearAutoTimers();
            stopStatePolling();
            clearPendingStateSync();
            setSessionState("finished");
            renderPodium(data.top || [], data);
        }
    } catch (error) {
        log(fmt(tr("playMessageError", "Play message error: {message}"), { message: error.message || "" }));
    }
}

function openLobby() {
    const ws = new WebSocket(wsUrl(`/ws/live/${CONFIG.pin}/lobby/`));
    sockets.lobby = ws;
    ws.onopen = () => {
        const reconnect = sockets.retries.lobby > 0;
        sockets.retries.lobby = 0;
        log(tr("wsLobbyOpen", "Lobby WS open"));
        // Qopma zamanı buraxılmış qoşulmalar: siyahını serverdən tutuşdur (sahib 2026-09-30).
        if (reconnect && state.sessionState === "lobby") syncState();
    };
    ws.onclose = () => {
        log(tr("wsLobbyClosed", "Lobby WS closed"));
        if (sockets.lobby === ws && state.sessionState !== "finished") scheduleReconnect("lobby", openLobby);
    };
    ws.onmessage = onLobbyMessage;
}

function openPlay() {
    const ws = new WebSocket(wsUrl(`/ws/live/${CONFIG.pin}/play/`));
    sockets.play = ws;
    setPlaySocket(ws);
    ws.onopen = async () => {
        const reconnect = sockets.retries.play > 0;
        sockets.retries.play = 0;
        log(tr("wsPlayOpen", "Play WS open"));
        if (reconnect) await syncState();
        else await ensureInitialStateSync();
    };
    ws.onclose = () => {
        log(tr("wsPlayClosed", "Play WS closed"));
        if (sockets.play === ws && state.sessionState !== "finished") scheduleReconnect("play", openPlay);
    };
    ws.onmessage = onPlayMessage;
}

export function connectHostSockets() {
    sockets.closing = false;
    openLobby();
    openPlay();
    return { lobbyWS: sockets.lobby, playWS: sockets.play };
}

export function closeHostSockets() {
    sockets.closing = true;
    window.clearTimeout(sockets.timers.lobby);
    window.clearTimeout(sockets.timers.play);
    [sockets.lobby, sockets.play].forEach((ws) => {
        if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
    });
}
