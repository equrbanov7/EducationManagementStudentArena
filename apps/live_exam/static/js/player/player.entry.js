// LX-FE-PLAYER (2026-09-29): iştirakçı ekranının giriş nöqtəsi.
import { SESSION_SETTINGS } from './config.js?v=lx20260930';
import { fetchState, setSnapshotHandlers } from './api.js?v=lx20260930';
import { bindPlayerEvents } from './events.js?v=lx20260930';
import { bindCopyGuard } from './guard.js?v=lx20260930';
import { handleAuthLost, handleSnapshot, handleSocketMessage } from './flow.js?v=lx20260930';
import { resetWatchdog, startStatePolling } from './polling.js?v=lx20260930';
import { renderBoot } from './render_status.js?v=lx20260930';
import { applySessionSettings } from './settings.js?v=lx20260930';
import { openPlayerSocket } from './sockets.js?v=lx20260930';
import { renderPlayerIdentity, renderSoundToggle, setNetStatus } from './ui.js?v=lx20260930';

applySessionSettings(SESSION_SETTINGS);
renderPlayerIdentity();
renderSoundToggle();
renderBoot();
bindPlayerEvents();
bindCopyGuard();

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
