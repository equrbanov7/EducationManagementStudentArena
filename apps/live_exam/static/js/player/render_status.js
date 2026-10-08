// LX-FE-PLAYER (2026-09-29): köməkçi görünüşlər — ilk yüklənmə, «müəllimi gözləyirik»,
// «oyunçu sessiyada yoxdur» (403: silinib / token etibarsız).
import { BOOTSTRAP, PHASES } from './config.js?v=lx20261008';
import { state } from './state.js?v=lx20261008';
import { announce, setQuestionChip, setTimer, stopTimeBar } from './ui.js?v=lx20261008';
import { esc, tr } from './utils.js?v=lx20261008';
import { mountView } from './views.js?v=lx20261008';

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

// 2026-10-08 (L3): gec qoşulan — cari sual (və onun cavabı) göstərilmir, növbəti sual gözlənilir.
export function renderLateJoin() {
    const { created } = mountView(
        "late-join",
        `<div class="lxp-idle lxp-idle--late">` +
            `<div class="lxp-dots lxp-dots--lg" aria-hidden="true"><span></span><span></span><span></span></div>` +
            `<h1 class="lxp-title">${esc(tr("lateJoinTitle", "Oyuna qoşuldun!"))}</h1>` +
            `<p class="lxp-sub">${esc(tr("lateJoinBody", "Oyun artıq gedir — növbəti sual başlayanda daxil olacaqsan. Keçən suallar üçün bal verilmir."))}</p>` +
            `</div>`,
        { tone: "idle" }
    );
    state.phase = PHASES.LATE_JOIN;
    if (created) {
        setQuestionChip(null);
        setTimer(false);
        stopTimeBar();
        announce(tr("lateJoinTitle", "Oyuna qoşuldun!"));
    }
}

export function renderRemoved() {
    const joinUrl = BOOTSTRAP.joinPageUrl || "/live/";
    // 2026-10-08 (L6): aparıcı çıxarıbsa — aydın mesaj və «başqa PIN» (eyni cihazla bu oyuna qayıtmaq olmur).
    const kicked = Boolean(state.kicked);
    const title = kicked ? tr("kickedTitle", "Müəllim səni oyundan çıxardı") : tr("removedTitle", "Bu oyunda deyilsən");
    const body = kicked
        ? tr("kickedBody", "Bu cihazla bu oyuna yenidən qoşulmaq mümkün deyil. Səhv olubsa, müəllimə yaz.")
        : tr("removedBody", "Oyunçu profilin tapılmadı — müəllim səni çıxarmış və ya oyun bağlanmış ola bilər.");
    const action = kicked
        ? `<a class="lxp-btn lxp-btn--primary" href="${esc(BOOTSTRAP.pinEntryUrl || "/live/")}">${esc(tr("kickedAction", "Başqa PIN daxil et"))}</a>`
        : `<a class="lxp-btn lxp-btn--primary" href="${esc(joinUrl)}">${esc(tr("rejoin", "Yenidən qoşul"))}</a>`;
    const { created } = mountView(
        kicked ? "kicked" : "removed",
        `<div class="lxp-idle lxp-idle--alert">` +
            `<h1 class="lxp-title">${esc(title)}</h1>` +
            `<p class="lxp-sub">${esc(body)}</p>` +
            action +
            `</div>`,
        { tone: "timeup" }
    );
    state.phase = PHASES.REMOVED;
    if (created) {
        setQuestionChip(null);
        setTimer(false);
        stopTimeBar();
        announce(title);
    }
}
