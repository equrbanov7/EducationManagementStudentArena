import { UI } from './dom.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';
import { stopAllLoops, stopDanceBeat, stopLobbyMusic, syncLobbyMusic } from './audio.js?v=lx20261002';
import { stopStatePolling } from './api.js?v=lx20261002';
import { renderIdleStage, resetLobbyStage } from './lobby.js?v=lx20261002';
import { teardownStage } from './stage.js?v=lx20261002';
import { cancelWipe } from './transitions.js?v=lx20261002';
import { fmt, log, markStateMutation, notifyHostShell, safeDisplay, tr } from './utils.js?v=lx20261002';

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
    clearTimeout(state.allAnsweredTimeout);
    state.autoRevealTimeout = 0;
    state.autoNextTimeout = 0;
    state.allAnsweredTimeout = 0;
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
    if (value === "question") return tr("stateQuestion", "Sual");
    if (value === "reveal") return tr("stateReveal", "Cavab");
    if (value === "finished") return tr("stateFinished", "Bitdi");
    return tr("stateLobby", "Lobbi");
}

/** Kadr dövrəsində (RAF) markup qurmadan ƏVVƏL yoxlamaq üçün — eyni faza/imza artıq ekrandadır? */
export const isCurrentPhase = (phase, signature) => state.phase === phase && state.phaseSignature === signature;

/**
 * Fazanın məzmununu yalnız imza dəyişəndə yeniləyir (idempotent render):
 * eyni vəziyyətin təkrar gəlməsi animasiyanı / səsi təkrarlamır.
 * `afterMount(root)` — DOM daxil ediləndən sonra (şrift sığdırma və s.).
 */
export function setPresentationMarkup(phase, signature, markup, afterMount) {
    if (!UI.presentationStage || !UI.presentationContent) return false;
    if (UI.presentationStage.dataset.phase !== phase) UI.presentationStage.dataset.phase = phase;
    if (isCurrentPhase(phase, signature)) return false;
    state.phase = phase;
    state.phaseSignature = signature;
    UI.presentationContent.innerHTML = markup;
    if (typeof afterMount === "function") {
        try {
            afterMount(UI.presentationContent);
        } catch (error) {
            log(`afterMount: ${error.message || error}`);
        }
    }
    markStateMutation();
    notifyHostShell();
    return true;
}

export function setSessionState(nextState) {
    if (nextState === "finished" && state.sessionState === "finished") {
        return;
    }
    const previous = state.sessionState;
    state.sessionState = nextState;
    document.body.dataset.sessionState = nextState;
    if (nextState !== "finished") {
        state.finalSignature = "";
        if (previous === "finished") teardownStage();
    }
    if (UI.gameState) UI.gameState.textContent = stateLabel(nextState);

    if (UI.startBtn) UI.startBtn.disabled = nextState !== "lobby";
    if (UI.revealBtn) UI.revealBtn.disabled = nextState !== "question";
    if (UI.nextBtn) UI.nextBtn.disabled = nextState !== "reveal";
    if (UI.finishBtn) UI.finishBtn.disabled = nextState === "finished";

    const isLobby = nextState === "lobby";
    const isPlay = nextState === "question" || nextState === "reveal";
    const isFinished = nextState === "finished";

    safeDisplay(UI.playersSection, "none");
    safeDisplay(UI.gameArea, (isLobby || isPlay) && !isFinished ? "block" : "none");
    safeDisplay(UI.finalPodium, isFinished ? "block" : "none");
    safeDisplay(UI.progressBox, !CONFIG.presentationOnly && nextState === "question" ? "flex" : "none");

    if (previous !== nextState) {
        if (previous === "lobby") {
            stopLobbyMusic();
            resetLobbyStage();
        }
        if (previous === "finished") stopDanceBeat();
        if (isFinished) stopAllLoops();
    }

    if (isFinished) {
        clearPhaseLoop();
        clearAutoTimers();
        cancelWipe();
        stopStatePolling();
        if (UI.presentationContent) UI.presentationContent.innerHTML = "";
        if (UI.presentationStage) UI.presentationStage.dataset.phase = "finished";
        state.phase = "finished";
        state.phaseSignature = "";
    }

    if (isLobby) {
        clearPhaseLoop();
        clearAutoTimers();
        renderIdleStage();
    }

    syncLobbyMusic();
    if (previous !== nextState) {
        log(fmt(tr("stateLog", "State: {state}"), { state: stateLabel(nextState) }));
    }
    notifyHostShell();
}
