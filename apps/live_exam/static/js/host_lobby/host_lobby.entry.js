import { mountBombDrawer } from './bomb_drawer.js?v=lx20261111f';
import { bindDebugToggle, log, tr } from './utils.js?v=lx20261111f';
import { state } from './state.js?v=lx20261111f';
import { setSfxVolume, stopAllLoops } from './audio.js?v=lx20261111f';
import { hydrateIcons } from './icons.js?v=lx20261111f';
import { setSessionState } from './presentation.js?v=lx20261111f';
import { applySessionSettings } from './settings.js?v=lx20261111f';
import {
    clearPendingStateSync,
    startLobbyResync,
    startStatePolling,
    stopLobbyResync,
    stopStatePolling,
    syncState,
} from './api.js?v=lx20261111f';
import { closeHostSockets, connectHostSockets, ensureInitialStateSync } from './sockets.js?v=lx20261111f';
import { bindAudioUnlockEvents, bindHostEvents } from './events.js?v=lx20261111f';
import { installHostController } from './controller.js?v=lx20261111f';
import { mountSoundDock } from './sound_dock.js?v=lx20261111f';
import { mountTypedDrawer } from './typed_drawer.js?v=lx20261111f';
import { bindCopyGuard } from './copy_guard.js?v=lx20261111f';
import { bindTimeSettingEvents, renderTimeSettings } from './time_setting.js?v=lx20261111f';
import { bindPlayersDrawer } from './players_drawer.js?v=lx20261111f';
import { applyStyleToDocument, setPresentationStyle } from './style_mode.js?v=lx20261111f';
import { mountPowerControls } from './powerups.js?v=lx20261111f';

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
