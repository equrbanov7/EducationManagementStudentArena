import { UI } from './dom.js?v=lx20260929';
import { state } from './state.js?v=lx20260929';
import { renderStage } from './stage.js?v=lx20260929';
import { safeDisplay, topSignature } from './utils.js?v=lx20260929';

/* Köhnə «podium» API-si səhnəyə (stage.js) ötürülür. Sıra — serverin `top` sırası. */
export function renderPodium(top, payload = {}) {
    const rows = Array.isArray(top) ? top : [];
    state.finalSignature = topSignature(rows) || "final";
    state.finalPayload = payload;
    safeDisplay(UI.finalPodium, "block");
    safeDisplay(UI.gameArea, "none");
    renderStage(rows, {
        stats: payload?.stats || null,
        total_players: payload?.total_players ?? state.totalPlayers,
    });
}
