import { bombText } from '../host_lobby/bomb_text.js?v=lx20261110p';
import { installBombUI } from './bombs.js?v=lx20261110p';
import { state } from './state.js?v=lx20261110p';
// LX-FE-PLAYER (2026-09-29): iştirakçı ekranının giriş nöqtəsi.
import { BOOTSTRAP, SESSION_SETTINGS, prefersReducedMotion } from './config.js?v=lx20261110p';
import { fetchState, setSnapshotHandlers } from './api.js?v=lx20261110p';
import { bindPlayerEvents } from './events.js?v=lx20261110p';
import { bindCopyGuard } from './guard.js?v=lx20261110p';
import { handleAuthLost, handleSnapshot, handleSocketMessage } from './flow.js?v=lx20261110p';
import { resetWatchdog, startStatePolling } from './polling.js?v=lx20261110p';
import { renderBoot } from './render_status.js?v=lx20261110p';
import { applySessionSettings } from './settings.js?v=lx20261110p';
import { openPlayerSocket } from './sockets.js?v=lx20261110p';
import { renderPlayerIdentity, renderSoundToggle, setNetSignal, setNetStatus } from './ui.js?v=lx20261110p';
import { playSound } from './audio.js?v=lx20261110p';
import { buzz, HAPTIC } from './haptics.js?v=lx20261110p';

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

let bombStorage;
try {
    bombStorage = window.sessionStorage;
} catch (_) {
    bombStorage = null;
}
installBombUI({
    state, pin: BOOTSTRAP.pin, document, storage: bombStorage,
    reducedMotion: prefersReducedMotion, labels: bombText(document.documentElement.lang),
    // 2026-11-10: partlayış səsi + ağır vibrasiya (bir dəfə, açarla).
    onExplode: (key) => { playSound("boom", key); buzz(HAPTIC.explode); },
});
