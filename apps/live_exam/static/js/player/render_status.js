// LX-FE-PLAYER (2026-09-29): köməkçi görünüşlər — ilk yüklənmə, «müəllimi gözləyirik»,
// «oyunçu sessiyada yoxdur» (403: silinib / token etibarsız).
import { BOOTSTRAP, PHASES } from './config.js?v=lx20260929';
import { state } from './state.js?v=lx20260929';
import { announce, setQuestionChip, setTimer, stopTimeBar } from './ui.js?v=lx20260929';
import { esc, tr } from './utils.js?v=lx20260929';
import { mountView } from './views.js?v=lx20260929';

export function renderBoot() {
    mountView(
        "boot",
        `<div class="lxp-idle">` +
            `<span class="lxp-spinner lxp-spinner--lg" aria-hidden="true"></span>` +
            `<p class="lxp-sub">${esc(tr("connecting", "Oyuna qoşulur…"))}</p>` +
            `</div>`,
        { tone: "idle" }
    );
}

export function renderIdle() {
    const { created } = mountView(
        "idle",
        `<div class="lxp-idle">` +
            `<div class="lxp-dots lxp-dots--lg" aria-hidden="true"><span></span><span></span><span></span></div>` +
            `<h1 class="lxp-title">${esc(tr("waitingTitle", "Az qaldı!"))}</h1>` +
            `<p class="lxp-sub">${esc(tr("waitingForHost", "Müəllimin növbəti addımı gözlənilir…"))}</p>` +
            `</div>`,
        { tone: "idle" }
    );
    state.phase = PHASES.IDLE;
    if (created) {
        setQuestionChip(null);
        setTimer(false);
        stopTimeBar();
    }
}

export function renderRemoved() {
    const joinUrl = BOOTSTRAP.joinPageUrl || "/live/";
    const { created } = mountView(
        "removed",
        `<div class="lxp-idle lxp-idle--alert">` +
            `<h1 class="lxp-title">${esc(tr("removedTitle", "Bu oyunda deyilsən"))}</h1>` +
            `<p class="lxp-sub">${esc(tr("removedBody", "Oyunçu profilin tapılmadı — müəllim səni çıxarmış və ya oyun bağlanmış ola bilər."))}</p>` +
            `<a class="lxp-btn lxp-btn--primary" href="${esc(joinUrl)}">${esc(tr("rejoin", "Yenidən qoşul"))}</a>` +
            `</div>`,
        { tone: "timeup" }
    );
    state.phase = PHASES.REMOVED;
    if (created) {
        setQuestionChip(null);
        setTimer(false);
        stopTimeBar();
        announce(tr("removedTitle", "Bu oyunda deyilsən"));
    }
}
