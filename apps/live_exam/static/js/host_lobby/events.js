import { UI } from './dom.js?v=lx20260929';
import { state } from './state.js?v=lx20260929';
import { finishGame, nextQuestion, post, postJson, revealQuestion, startGame } from './api.js?v=lx20260929';
import { unlockAudio } from './audio.js?v=lx20260929';
import { openPresenterWindow, tryEnterFullscreen } from './presentation.js?v=lx20260929';
import { controlsEnabled, fitAll } from './utils.js?v=lx20260929';

export function bindHostEvents() {
    if (UI.startBtn) UI.startBtn.onclick = startGame;
    if (UI.presentBtn) UI.presentBtn.onclick = () => openPresenterWindow();
    if (UI.revealBtn) UI.revealBtn.onclick = revealQuestion;
    if (UI.nextBtn) UI.nextBtn.onclick = nextQuestion;
    if (UI.finishBtn) UI.finishBtn.onclick = finishGame;

    UI.presentationContent?.addEventListener("click", (event) => {
        if (event.target.closest("[data-action='open-qr']")) {
            if (typeof toggleQR === "function") toggleQR(true);
            return;
        }
        const button = event.target.closest("[data-remove-player-id]");
        if (!button || !controlsEnabled() || state.sessionState !== "lobby") return;
        button.disabled = true;
        const formData = new FormData();
        formData.append("player_id", button.dataset.removePlayerId);
        post(CONFIG.urls.removePlayer, formData).finally(() => {
            button.disabled = false;
        });
    });

    UI.autoMode?.addEventListener("change", () => {
        if (controlsEnabled() && CONFIG?.urls?.settings) {
            postJson(CONFIG.urls.settings, { autoplay: Boolean(UI.autoMode.checked) });
        }
    });

    UI.questionCount?.addEventListener("focus", function onFocus() {
        this.select();
    });
    UI.questionCount?.addEventListener("blur", function onBlur() {
        let value = parseInt(this.value, 10) || 1;
        if (value < 1) value = 1;
        if (value > CONFIG.maxQuestions) value = CONFIG.maxQuestions;
        this.value = value;
    });
    UI.questionCount?.addEventListener("keydown", (event) => {
        if (["Backspace", "Delete", "Tab", "Escape", "Enter", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
        if ((event.ctrlKey || event.metaKey) && ["a", "c", "v", "x"].includes(String(event.key).toLowerCase())) return;
        if (/^\d$/.test(event.key)) return;
        event.preventDefault();
    });

    // Pəncərə ölçüsü dəyişəndə uzun mətnləri yenidən sığdır (debounce).
    let resizeTimer = 0;
    window.addEventListener("resize", () => {
        window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(() => {
            fitAll(UI.presentationContent, "[data-fit]", { min: 18 });
            fitAll(UI.presentationContent, ".hx-tile__text", { min: 14 });
        }, 160);
    });
}

export function bindAudioUnlockEvents() {
    document.addEventListener("pointerdown", unlockAudio, { passive: true });
    document.addEventListener("touchstart", unlockAudio, { passive: true });
    document.addEventListener("keydown", unlockAudio);

    if (CONFIG.presentationOnly) {
        setTimeout(() => tryEnterFullscreen(), 80);
        document.addEventListener(
            "pointerdown",
            () => {
                unlockAudio();
                tryEnterFullscreen();
            },
            { once: true }
        );
        document.addEventListener("keydown", (event) => {
            if (event.key && event.key.toLowerCase() === "f" && !event.target.closest?.("input, textarea, [contenteditable]")) {
                unlockAudio();
                tryEnterFullscreen();
            }
        });
    }
}
