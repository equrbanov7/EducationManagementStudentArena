import { finishGame, nextQuestion, post, postJson, revealQuestion, skipQuestionIntro, startGame, syncState } from './api.js';
import { hostShellSubscribers, publicHostState } from './utils.js';

export function installHostController() {
    window.LiveHostLobbyController = {
        subscribe(listener) {
            if (typeof listener !== "function") return () => {};
            hostShellSubscribers.add(listener);
            listener(publicHostState());
            return () => hostShellSubscribers.delete(listener);
        },
        getState: publicHostState,
        syncState,
        updateSettings(updates) {
            if (!CONFIG?.urls?.settings) return Promise.resolve({ ok: false });
            return postJson(CONFIG.urls.settings, updates);
        },
        startGame,
        skipQuestionIntro,
        revealQuestion,
        nextQuestion,
        finishGame,
        toggleLock(locked) {
            if (!CONFIG?.urls?.lock) return Promise.resolve({ ok: false });
            const formData = new FormData();
            formData.append("locked", locked ? "1" : "0");
            return post(CONFIG.urls.lock, formData);
        },
        removePlayer(playerId) {
            if (!CONFIG?.urls?.removePlayer) return Promise.resolve({ ok: false });
            const formData = new FormData();
            formData.append("player_id", playerId);
            return post(CONFIG.urls.removePlayer, formData);
        },
    };
}
