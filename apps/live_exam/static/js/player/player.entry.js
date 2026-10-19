// LX-FE-PLAYER (2026-09-29): iştirakçı ekranının giriş nöqtəsi.
import { SESSION_SETTINGS } from './config.js?v=lx20261019s';
import { fetchState, setSnapshotHandlers } from './api.js?v=lx20261019s';
import { bindPlayerEvents } from './events.js?v=lx20261019s';
import { bindCopyGuard } from './guard.js?v=lx20261019s';
import { handleAuthLost, handleSnapshot, handleSocketMessage } from './flow.js?v=lx20261019s';
import { resetWatchdog, startStatePolling } from './polling.js?v=lx20261019s';
import { renderBoot } from './render_status.js?v=lx20261019s';
import { applySessionSettings } from './settings.js?v=lx20261019s';
import { openPlayerSocket } from './sockets.js?v=lx20261019s';
import { renderPlayerIdentity, renderSoundToggle, setNetSignal, setNetStatus } from './ui.js?v=lx20261019s';

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

// LXNET (2026-10-02): qopma anında 150 telefon eyni millisaniyədə snapshot istəməsin.
const resyncSoon = () => window.setTimeout(fetchState, Math.floor(Math.random() * 600));

openPlayerSocket({
    onOpen: () => {
        setNetStatus("online");
        resetWatchdog();
        // Qopma zamanı buraxılmış mesajlar: snapshot vəziyyəti bərpa edir (socket açıldı → şəbəkə
        // işləyir: köhnəlmiş, ilişmiş sorğu varsa ləğv olunur).
        fetchState({ fresh: true });
    },
    onClose: () => {
        setNetStatus(navigator.onLine === false ? "offline" : "reconnecting");
        // Socket bağlandı — növbəti sorğu tsikli (3 s) gözlənilmədən HTTP ilə tutuşdur.
        resyncSoon();
    },
    onStall: () => {
        // LXNET: socket «açıq», amma ping cavabsızdır (TCP ilişib) — təzə socket açılır,
        // vəziyyət isə dərhal HTTP ilə (yeni bağlantı) gətirilir.
        setNetStatus("reconnecting");
        fetchState({ fresh: true });
    },
    onQuality: (level) => setNetSignal(level),
    onMessage: (data) => handleSocketMessage(data),
});

fetchState();
startStatePolling();
