import { bindDebugToggle, log, tr } from './utils.js';
import { state } from './state.js';
import { setSfxVolume } from './audio.js';
import { setSessionState } from './presentation.js';
import { applySessionSettings } from './settings.js';
import { startStatePolling, clearPendingStateSync, stopStatePolling } from './api.js';
import { closeHostSockets, connectHostSockets, ensureInitialStateSync } from './sockets.js';
import { bindAudioUnlockEvents, bindHostEvents } from './events.js';
import { installHostController } from './controller.js';

window.setSfxVolume = setSfxVolume;

bindDebugToggle();
connectHostSockets();
bindHostEvents();

setSessionState("lobby");
applySessionSettings(state.sessionSettings);
log(tr("hostReady", "Host ready"));

bindAudioUnlockEvents();
ensureInitialStateSync();
startStatePolling();

window.addEventListener("beforeunload", () => {
    stopStatePolling();
    clearPendingStateSync();
    closeHostSockets();
});

installHostController();
