import { UI } from './dom.js?v=lx20261008';
import { state } from './state.js?v=lx20261008';
import { applyServerVolume, syncLobbyMusic } from './audio.js?v=lx20261008';

export function applySessionSettings(nextSettings) {
    const previousLobbyMusic = state.sessionSettings.lobby_music;
    state.sessionSettings = Object.assign({}, state.sessionSettings, nextSettings || {});
    document.body.dataset.liveTheme = state.sessionSettings.theme_key || "aurora";
    document.body.classList.toggle("live-high-contrast", Boolean(state.sessionSettings.increase_contrast));
    if (UI.autoMode) {
        UI.autoMode.checked = Boolean(state.sessionSettings.autoplay);
    }
    if (previousLobbyMusic !== state.sessionSettings.lobby_music) {
        syncLobbyMusic();
    }
    // Server səs səviyyəsi yalnız bu cihazda şəxsi seçim yoxdursa tətbiq olunur.
    applyServerVolume(state.sessionSettings.sfx_volume);
}
