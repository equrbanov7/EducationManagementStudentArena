import { UI } from './dom.js?v=lx20261019s';
import { state } from './state.js?v=lx20261019s';
import { applyServerVolume, stopAllLoops, syncLobbyMusic } from './audio.js?v=lx20261019s';
import { applyStyleToDocument, isFormal, setPresentationStyle } from './style_mode.js?v=lx20261019s';

export function applySessionSettings(nextSettings) {
    const previousLobbyMusic = state.sessionSettings.lobby_music;
    state.sessionSettings = Object.assign({}, state.sessionSettings, nextSettings || {});
    document.body.dataset.liveTheme = state.sessionSettings.theme_key || "aurora";
    document.body.classList.toggle("live-high-contrast", Boolean(state.sessionSettings.increase_contrast));
    // 2026-10-19: təqdimat üslubu (Rəsmi / Qeyri-rəsmi) — `body[data-lx-style]` + baş hərf avatarları.
    const styleChanged = setPresentationStyle(state.sessionSettings);
    applyStyleToDocument();
    if (UI.autoMode) {
        UI.autoMode.checked = Boolean(state.sessionSettings.autoplay);
    }
    if (styleChanged && isFormal()) stopAllLoops(); // rəsmi üslubda musiqi / səs effekti yoxdur
    if (styleChanged || previousLobbyMusic !== state.sessionSettings.lobby_music) {
        syncLobbyMusic();
    }
    // Server səs səviyyəsi yalnız bu cihazda şəxsi seçim yoxdursa tətbiq olunur.
    applyServerVolume(state.sessionSettings.sfx_volume);
}
