import { mountBombDrawer } from './bomb_drawer.js?v=lx20261110p';
import { bindDebugToggle, log, tr } from './utils.js?v=lx20261110p';
import { state } from './state.js?v=lx20261110p';
import { setSfxVolume, stopAllLoops } from './audio.js?v=lx20261110p';
import { hydrateIcons } from './icons.js?v=lx20261110p';
import { setSessionState } from './presentation.js?v=lx20261110p';
import { applySessionSettings } from './settings.js?v=lx20261110p';
import {
    clearPendingStateSync,
    startLobbyResync,
    startStatePolling,
    stopLobbyResync,
    stopStatePolling,
    syncState,
} from './api.js?v=lx20261110p';
import { closeHostSockets, connectHostSockets, ensureInitialStateSync } from './sockets.js?v=lx20261110p';
import { bindAudioUnlockEvents, bindHostEvents } from './events.js?v=lx20261110p';
import { installHostController } from './controller.js?v=lx20261110p';
import { mountSoundDock } from './sound_dock.js?v=lx20261110p';
import { mountTypedDrawer } from './typed_drawer.js?v=lx20261110p';
import { bindCopyGuard } from './copy_guard.js?v=lx20261110p';
import { bindTimeSettingEvents, renderTimeSettings } from './time_setting.js?v=lx20261110p';
import { bindPlayersDrawer } from './players_drawer.js?v=lx20261111f';
import { applyStyleToDocument, setPresentationStyle } from './style_mode.js?v=lx20261110p';
import { mountPowerControls } from './powerups.js?v=lx20261110p';

// 2026-10-19: təqdimat üslubu İLK render-dən əvvəl (lobbi səhnəsi baş hərflərlə çəkilsin).
setPresentationStyle(state.sessionSettings);
applyStyleToDocument();

// Tənzimləmə çekməcəsindəki səs sürüşdürücüsü (host_lobby_shell.js) bu qlobalı çağırır.
window.setSfxVolume = setSfxVolume;

hydrateIcons();
bindDebugToggle();
installHostController();
connectHostSockets();
bindHostEvents();
bindCopyGuard();
bindTimeSettingEvents();
bindPlayersDrawer();

setSessionState("lobby");
applySessionSettings(state.sessionSettings);
log(tr("hostReady", "Host ready"));

bindAudioUnlockEvents();
mountSoundDock();
mountTypedDrawer();
mountBombDrawer();
mountPowerControls();
renderTimeSettings();
ensureInitialStateSync();
startStatePolling();
startLobbyResync();

// Gizli tabdan qayıdanda vəziyyəti serverlə tutuşdur (WS qopubsa da).
document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.sessionState !== "finished") syncState();
});

window.addEventListener("beforeunload", () => {
    stopStatePolling();
    stopLobbyResync();
    clearPendingStateSync();
    closeHostSockets();
    stopAllLoops();
});
