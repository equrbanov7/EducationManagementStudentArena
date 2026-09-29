// LX-FE-PLAYER (2026-09-29): iştirakçı ekranının giriş nöqtəsi.
import { SESSION_SETTINGS } from './config.js?v=lx20260929';
import { fetchState, setSnapshotHandlers } from './api.js?v=lx20260929';
import { bindPlayerEvents } from './events.js?v=lx20260929';
import { handleAuthLost, handleSnapshot, handleSocketMessage } from './flow.js?v=lx20260929';
import { resetWatchdog, startStatePolling } from './polling.js?v=lx20260929';
import { renderBoot } from './render_status.js?v=lx20260929';
import { applySessionSettings } from './settings.js?v=lx20260929';
import { openPlayerSocket } from './sockets.js?v=lx20260929';
import { renderPlayerIdentity, renderSoundToggle, setNetStatus } from './ui.js?v=lx20260929';

applySessionSettings(SESSION_SETTINGS);
renderPlayerIdentity();
renderSoundToggle();
renderBoot();
bindPlayerEvents();

setSnapshotHandlers({
    onSnapshot: handleSnapshot,
    onAuthLost: handleAuthLost,
});

openPlayerSocket({
    onOpen: () => {
        setNetStatus("online");
        resetWatchdog();
        // Qopma zamanı buraxılmış mesajlar: snapshot vəziyyəti bərpa edir.
        fetchState();
    },
    onClose: () => {
        setNetStatus(navigator.onLine === false ? "offline" : "reconnecting");
    },
    onMessage: (event) => {
        let data = null;
        try {
            data = JSON.parse(event.data);
        } catch (error) {
            return;
        }
        handleSocketMessage(data);
    },
});

fetchState();
startStatePolling();
