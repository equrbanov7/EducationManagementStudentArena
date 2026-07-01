import { UI } from './dom.js';
import { state } from './state.js';
import { finishGame, nextQuestion, post, postJson, revealQuestion, startGame } from './api.js';
import { unlockAudio } from './audio.js';
import { openPresenterWindow, tryEnterFullscreen } from './presentation.js';
import { controlsEnabled } from './utils.js';

export function bindHostEvents() {
    UI.startBtn.onclick = startGame;

    if (UI.presentBtn) {
        UI.presentBtn.onclick = () => openPresenterWindow();
    }
    UI.revealBtn.onclick = revealQuestion;
    UI.nextBtn.onclick = nextQuestion;
    UI.finishBtn.onclick = finishGame;
    UI.presentationContent?.addEventListener("click", event => {
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

    UI.questionCount?.addEventListener("keydown", event => {
        if ([8, 46, 9, 27, 13, 37, 38, 39, 40].includes(event.keyCode)) return;
        if ((event.ctrlKey || event.metaKey) && [65, 67, 86, 88].includes(event.keyCode)) return;
        if ((event.keyCode >= 48 && event.keyCode <= 57) || (event.keyCode >= 96 && event.keyCode <= 105)) return;
        event.preventDefault();
    });
}

export function bindAudioUnlockEvents() {
    document.addEventListener("pointerdown", unlockAudio, { passive: true });
    document.addEventListener("touchstart", unlockAudio, { passive: true });
    document.addEventListener("keydown", unlockAudio);

    if (CONFIG.presentationOnly) {
        setTimeout(() => {
            tryEnterFullscreen();
        }, 80);
        document.addEventListener("pointerdown", () => {
            unlockAudio();
            tryEnterFullscreen();
        }, { once: true });
        document.addEventListener("keydown", event => {
            if (event.key && event.key.toLowerCase() === "f") {
                unlockAudio();
                tryEnterFullscreen();
            }
        });
    }
}
