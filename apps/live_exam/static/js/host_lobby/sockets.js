import { UI } from './dom.js';
import { state } from './state.js';
import { applySessionSettings } from './settings.js';
import { renderIdleStage, renderLobbyPlayers, updateAnsweredCounter } from './lobby.js';
import { applyQuestionState } from './question.js';
import { applyRevealState } from './reveal.js';
import { renderPodium } from './podium.js';
import { clearAutoTimers, clearPhaseLoop, setSessionState } from './presentation.js';
import { clearPendingStateSync, setPlaySocket, stopStatePolling, syncState } from './api.js';
import {
    controlsEnabled,
    esc,
    fmt,
    log,
    markStateMutation,
    rememberTimelinePayload,
    shouldApplyTimelinePayload,
    tr,
    updateServerTimeOffset,
    wsUrl,
} from './utils.js';

function spawnReaction(eventData) {
    if (!UI.reactionOverlay) return;
    const meta = (window.LiveAvatarCatalog || {}).reactions?.[eventData?.reaction_key] || {};
    const burst = document.createElement("div");
    burst.className = "host-reaction-burst";
    burst.innerHTML = `
        <span class="host-reaction-burst__emoji">${meta.emoji || eventData?.emoji || "✨"}</span>
        <span class="host-reaction-burst__name">${esc(eventData?.player?.nickname || "")}</span>
    `;
    burst.style.left = `${16 + Math.random() * 68}%`;
    burst.style.setProperty("--reaction-drift", `${-26 + Math.random() * 52}px`);
    UI.reactionOverlay.appendChild(burst);
    setTimeout(() => burst.remove(), 2300);
}


let lobbyWS = null;
let playWS = null;
let initialStateSynced = false;

export async function ensureInitialStateSync() {
    if (initialStateSynced) {
        return null;
    }
    initialStateSynced = true;
    return syncState();
}

export function connectHostSockets() {
    lobbyWS = new WebSocket(wsUrl(`/ws/live/${CONFIG.pin}/lobby/`));
    lobbyWS.onopen = () => log(tr("wsLobbyOpen", "Lobby WS open"));
    lobbyWS.onclose = () => log(tr("wsLobbyClosed", "Lobby WS closed"));
    lobbyWS.onmessage = event => {
        try {
            const message = JSON.parse(event.data);
            const data = message.data || message;
            updateServerTimeOffset(data);

            if (data.type === "lobby_state") {
                markStateMutation();
                if (data.settings) {
                    applySessionSettings(data.settings);
                }
                if (data.is_locked != null) {
                    state.isLocked = Boolean(data.is_locked);
                }
                renderLobbyPlayers(data.players || [], data.count);

                if (state.sessionState === "lobby") {
                    renderIdleStage();
                }
                return;
            }

            if (data.type === "reaction_event") {
                spawnReaction(data);
            }
        } catch (error) {
            log(fmt(tr("lobbyMessageError", "Lobby message error: {message}"), { message: error.message || "" }));
        }
    };

    playWS = new WebSocket(wsUrl(`/ws/live/${CONFIG.pin}/play/`));
    setPlaySocket(playWS);
    playWS.onopen = async () => {
        log(tr("wsPlayOpen", "Play WS open"));
        await ensureInitialStateSync();
    };
    playWS.onclose = () => log(tr("wsPlayClosed", "Play WS closed"));
    playWS.onmessage = event => {
        try {
            const message = JSON.parse(event.data);
            const data = message.data || message;
            updateServerTimeOffset(data);

            if (data.type === "question_published") {
                if (!shouldApplyTimelinePayload(data)) {
                    return;
                }
                rememberTimelinePayload(data);
                markStateMutation();
                state.answeredCount = 0;
                applyQuestionState(data.question, 0, state.totalPlayers);
                return;
            }

            if (data.type === "answer_progress") {
                if (state.currentQuestion && Number(data.question_id || 0) !== Number(state.currentQuestion.id || 0)) {
                    return;
                }
                markStateMutation();
                state.answeredCount = Number(data.answered_count || 0);
                state.totalPlayers = Number(data.total_players || state.totalPlayers || 0);
                updateAnsweredCounter();

                if (
                    controlsEnabled()
                    && state.answeredCount >= state.totalPlayers
                    && state.totalPlayers > 0
                    && state.sessionState === "question"
                ) {
                    log(tr("allAnsweredAutoReveal", "All answered, auto reveal!"));
                    clearTimeout(state.autoRevealTimeout);
                    setTimeout(() => {
                        if (state.sessionState === "question") {
                            UI.revealBtn.click();
                        }
                    }, 400);
                }
                return;
            }

            if (data.type === "reveal") {
                if (!shouldApplyTimelinePayload(data)) {
                    return;
                }
                rememberTimelinePayload(data);
                markStateMutation();
                applyRevealState(data, state.currentQuestion);
                return;
            }

            if (data.type === "finished") {
                if (!shouldApplyTimelinePayload(data)) return;
                rememberTimelinePayload(data);
                if (state.sessionState === "finished") return;
                markStateMutation();
                clearPhaseLoop();
                clearAutoTimers();
                stopStatePolling();
                clearPendingStateSync();
                setSessionState("finished");
                renderPodium(data.top || []);
                return;
            }
        } catch (error) {
            log(fmt(tr("playMessageError", "Play message error: {message}"), { message: error.message || "" }));
        }
    };

    return { lobbyWS, playWS };
}

export function closeHostSockets() {
    if (lobbyWS && lobbyWS.readyState <= WebSocket.OPEN) {
        lobbyWS.close();
    }
    if (playWS && playWS.readyState <= WebSocket.OPEN) {
        playWS.close();
    }
}
