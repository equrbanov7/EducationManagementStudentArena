import { UI } from './dom.js';
import { state } from './state.js';
import { setSfxVolume, syncLobbyMusic } from './audio.js';

export function applySessionSettings(nextSettings) {
    const previousLobbyMusic = state.sessionSettings.lobby_music;
    state.sessionSettings = Object.assign({}, state.sessionSettings, nextSettings || {});
    document.body.dataset.liveTheme = state.sessionSettings.theme_key || "aurora";
    document.body.classList.toggle("live-high-contrast", Boolean(state.sessionSettings.increase_contrast));
    if (UI.autoMode) {
        UI.autoMode.checked = Boolean(state.sessionSettings.autoplay);
    }
    if (previousLobbyMusic !== state.sessionSettings.lobby_music) {
        syncLobbyMusic(true);
    }
    if (state.sessionSettings.sfx_volume != null) {
        setSfxVolume(state.sessionSettings.sfx_volume);
    }
}
