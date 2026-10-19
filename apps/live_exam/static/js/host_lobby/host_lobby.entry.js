import { bindDebugToggle, log, tr } from './utils.js?v=lx20261019s';
import { state } from './state.js?v=lx20261019s';
import { setSfxVolume, stopAllLoops } from './audio.js?v=lx20261019s';
import { hydrateIcons } from './icons.js?v=lx20261019s';
import { setSessionState } from './presentation.js?v=lx20261019s';
import { applySessionSettings } from './settings.js?v=lx20261019s';
import {
    clearPendingStateSync,
    startLobbyResync,
    startStatePolling,
    stopLobbyResync,
    stopStatePolling,
    syncState,
} from './api.js?v=lx20261019s';
import { closeHostSockets, connectHostSockets, ensureInitialStateSync } from './sockets.js?v=lx20261019s';
import { bindAudioUnlockEvents, bindHostEvents } from './events.js?v=lx20261019s';
import { installHostController } from './controller.js?v=lx20261019s';
import { mountSoundDock } from './sound_dock.js?v=lx20261019s';
import { mountTypedDrawer } from './typed_drawer.js?v=lx20261019s';
import { bindCopyGuard } from './copy_guard.js?v=lx20261019s';
import { bindTimeSettingEvents, renderTimeSettings } from './time_setting.js?v=lx20261019s';
import { bindPlayersDrawer } from './players_drawer.js?v=lx20261019s';
import { applyStyleToDocument, setPresentationStyle } from './style_mode.js?v=lx20261019s';

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
