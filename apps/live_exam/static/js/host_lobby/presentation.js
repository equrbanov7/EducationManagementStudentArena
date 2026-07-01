import { UI } from './dom.js';
import { PHASES } from './constants.js';
import { state } from './state.js';
import { syncLobbyMusic } from './audio.js';
import { stopStatePolling } from './api.js';
import { renderIdleStage } from './lobby.js';
import { destroyRevealChart } from './reveal.js';
import { fmt, log, markStateMutation, notifyHostShell, safeDisplay, tr } from './utils.js';

let presenterWindowRef = null;

export function clearPhaseLoop() {
    if (state.frameId) {
        cancelAnimationFrame(state.frameId);
        state.frameId = 0;
    }
}

export function clearAutoTimers() {
    clearTimeout(state.autoRevealTimeout);
    clearTimeout(state.autoNextTimeout);
    state.autoRevealTimeout = 0;
    state.autoNextTimeout = 0;
}

function presenterUrl() {
    if (!CONFIG?.urls?.present) return "";
    return `${CONFIG.urls.present}${CONFIG.urls.present.includes("?") ? "&" : "?"}autofs=1&controls=0`;
}

export function openPresenterWindow() {
    if (CONFIG.presentationOnly || !CONFIG?.urls?.present) return null;
    try {
        presenterWindowRef = window.open(presenterUrl(), `liveExamPresentation_${CONFIG.pin}`);
        if (presenterWindowRef) {
            presenterWindowRef.focus();
            window.setTimeout(() => {
                try {
                    const root = presenterWindowRef?.document?.documentElement;
                    if (root && presenterWindowRef.document.visibilityState === "visible" && root.requestFullscreen) {
                        root.requestFullscreen({ navigationUI: "hide" }).catch(() => {});
                    }
                } catch (error) {
                    log(`Presenter fullscreen skipped: ${error.message || error}`);
                }
            }, 120);
        }
        return presenterWindowRef;
    } catch (error) {
        log(`Presenter window error: ${error.message || error}`);
        return null;
    }
}

export async function tryEnterFullscreen() {
    if (!CONFIG.presentationOnly || !CONFIG.autoFullscreen) return;
    const root = document.documentElement;
    if (!root || document.fullscreenElement || !root.requestFullscreen) return;
    try {
        await root.requestFullscreen({ navigationUI: "hide" });
    } catch (error) {
        log(`Fullscreen request skipped: ${error.message || error}`);
    }
}

export function schedulePhaseLoop(fn) {
    clearPhaseLoop();
    const tick = () => {
        fn();
        if (state.frameId) {
            state.frameId = requestAnimationFrame(tick);
        }
    };
    state.frameId = requestAnimationFrame(tick);
}

function stateLabel(value) {
    if (value === "question") return tr("stateQuestion", "Question");
    if (value === "reveal") return tr("stateReveal", "Reveal");
    if (value === "finished") return tr("stateFinished", "Finished");
    return tr("stateLobby", "Lobby");
}

export function setPresentationMarkup(phase, signature, markup) {
    if (!UI.presentationStage || !UI.presentationContent) return;
    UI.presentationStage.dataset.phase = phase;
    if (state.phaseSignature === signature && state.phase === phase) {
        return;
    }
    // Destroy Chart.js instance when leaving the reveal phase
    destroyRevealChart();
    state.phase = phase;
    state.phaseSignature = signature;
    UI.presentationContent.innerHTML = markup;
    markStateMutation();
    notifyHostShell();
}

export function setSessionState(nextState) {
    if (nextState === "finished" && state.sessionState === "finished") {
        return;
    }
    state.sessionState = nextState;
    if (nextState !== "finished") {
        state.finalSignature = "";
    }
    UI.gameState.textContent = stateLabel(nextState);

    UI.startBtn.disabled = nextState !== "lobby";
    UI.revealBtn.disabled = nextState !== "question";
    UI.nextBtn.disabled = nextState !== "reveal";

    const isLobby = nextState === "lobby";
    const isPlay = nextState === "question" || nextState === "reveal";
    const isFinished = nextState === "finished";

    safeDisplay(UI.playersSection, CONFIG.presentationOnly ? "none" : (isLobby ? "block" : "none"));
    safeDisplay(UI.gameArea, (isLobby || isPlay) && !isFinished ? "block" : "none");
    safeDisplay(UI.finalPodium, isFinished ? "grid" : "none");
    safeDisplay(UI.progressBox, !CONFIG.presentationOnly && nextState === "question" ? "flex" : "none");

    if (isFinished) {
        clearPhaseLoop();
        clearAutoTimers();
        stopStatePolling();
        if (UI.presentationContent) {
            UI.presentationContent.innerHTML = "";
        }
        if (UI.presentationStage) {
            UI.presentationStage.dataset.phase = "finished";
        }
    }

    if (isLobby) {
        clearPhaseLoop();
        clearAutoTimers();
        renderIdleStage();
    }

    syncLobbyMusic(true);
    log(fmt(tr("stateLog", "State: {state}"), { state: stateLabel(nextState) }));
    notifyHostShell();
}
