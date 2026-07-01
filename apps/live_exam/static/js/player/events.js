import { submitAnswer } from './answer.js';
import { UI } from './dom.js';
import { unlockAudio } from './audio.js';
import { closePlayerSocket } from './sockets.js';
import { stopStatePolling } from './polling.js';
import { clearPhaseTimer, clearTicker } from './timers.js';
import { state } from './state.js';

export function bindPlayerEvents() {
    UI.submitBtn.addEventListener("click", () => {
        if (state.phase === "question") {
            submitAnswer();
        }
    });

    ["pointerdown", "touchstart", "keydown"].forEach((eventName) => {
        document.addEventListener(eventName, unlockAudio, { passive: true });
    });

    window.addEventListener("beforeunload", () => {
        stopStatePolling();
        clearTicker();
        clearPhaseTimer();
        closePlayerSocket();
    });
}
