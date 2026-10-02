// LX-FE-PLAYER (2026-09-29): başlıq (sual sayğacı, taymer, səs), alt panel (avatar, xal, yer),
// bağlantı zolağı, toast və ekran oxuyucusu üçün aria-live elanları.
import { BOOTSTRAP, prefersReducedMotion } from './config.js?v=lx20261002';
import { UI } from './dom.js?v=lx20261002';
import { audioState, isMuted } from './audio.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';
import { fmt, formatNumber, miniAvatar, tr } from './utils.js?v=lx20261002';

let toastTimer = null;
let netTimer = null;
let netShownKind = "";
let timeBarKey = "";
let scoreRaf = 0;

export function announce(text) {
    if (!UI.live || !text) return;
    UI.live.textContent = "";
    window.requestAnimationFrame(() => {
        UI.live.textContent = text;
    });
}

export function setQuestionChip(question) {
    if (!UI.questionChip) return;
    if (!question || !question.index) {
        UI.questionChip.hidden = true;
        UI.questionChip.textContent = "";
        return;
    }
    UI.questionChip.hidden = false;
    UI.questionChip.textContent = fmt(tr("questionShort", "{index}/{total}"), {
        index: question.index,
        total: question.total || question.index,
    });
    UI.questionChip.setAttribute(
        "aria-label",
        fmt(tr("questionCounter", "Sual {index} / {total}"), { index: question.index, total: question.total || "?" })
    );
}

export function setTimer(show, msLeft = 0) {
    if (!UI.timerBox) return;
    UI.timerBox.hidden = !show;
    if (!show) {
        UI.timerBox.classList.remove("is-warning", "is-danger");
        return;
    }
    const seconds = Math.max(0, Math.ceil(msLeft / 1000));
    if (UI.timerText.textContent !== String(seconds)) {
        UI.timerText.textContent = String(seconds);
    }
    UI.timerBox.classList.toggle("is-danger", seconds <= 5);
    UI.timerBox.classList.toggle("is-warning", seconds > 5 && seconds <= 10);
}

// Vaxt zolağı: CSS transition (transform: scaleX) — hər kadrda JS işi yoxdur, GPU kompozit edir.
export function startTimeBar(key, remainingMs, totalMs) {
    if (!UI.timeBar || !UI.timeBarFill) return;
    if (timeBarKey === key) return;
    timeBarKey = key;
    const total = Math.max(1, Number(totalMs) || 1);
    const remaining = Math.max(0, Math.min(total, Number(remainingMs) || 0));
    const fill = UI.timeBarFill;
    UI.timeBar.hidden = false;
    fill.style.transition = "none";
    fill.style.transform = `scaleX(${(remaining / total).toFixed(4)})`;
    // reflow — başlanğıc vəziyyət tətbiq olunsun, sonra keçid başlasın
    void fill.offsetWidth;
    if (!prefersReducedMotion()) {
        fill.style.transition = `transform ${remaining}ms linear`;
    }
    fill.style.transform = "scaleX(0)";
}

export function stopTimeBar() {
    timeBarKey = "";
    if (!UI.timeBar || !UI.timeBarFill) return;
    UI.timeBar.hidden = true;
    UI.timeBarFill.style.transition = "none";
    UI.timeBarFill.style.transform = "scaleX(1)";
}

export function setScore(value, { animate = false } = {}) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || !UI.playerScore) return;
    const from = Number(state.player.score) || 0;
    state.player.score = parsed;
    if (scoreRaf) {
        window.cancelAnimationFrame(scoreRaf);
        scoreRaf = 0;
    }
    if (!animate || prefersReducedMotion() || from === parsed) {
        UI.playerScore.textContent = formatNumber(parsed);
        return;
    }
    const started = performance.now();
    const duration = 900;
    const step = (now) => {
        const progress = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        UI.playerScore.textContent = formatNumber(Math.round(from + (parsed - from) * eased));
        scoreRaf = progress < 1 ? window.requestAnimationFrame(step) : 0;
    };
    UI.playerScore.classList.remove("is-bumped");
    void UI.playerScore.offsetWidth;
    UI.playerScore.classList.add("is-bumped");
    scoreRaf = window.requestAnimationFrame(step);
}

export function setRank(rank) {
    if (!UI.playerRank) return;
    const value = Number(rank);
    if (!Number.isFinite(value) || value <= 0) {
        UI.playerRank.hidden = true;
        return;
    }
    UI.playerRank.hidden = false;
    UI.playerRank.textContent = `#${value}`;
    UI.playerRank.setAttribute("aria-label", fmt(tr("rankAria", "Yerin: {rank}"), { rank: value }));
}

const STATIC_FALLBACKS = { pointsShort: "xal" };

export function renderPlayerIdentity() {
    if (BOOTSTRAP.pin) document.title = `${tr("pageTitle", "Canlı oyun")} | ${BOOTSTRAP.pin}`;
    document.querySelectorAll("[data-lxp-i18n]").forEach((el) => {
        const key = el.dataset.lxpI18n;
        el.textContent = tr(key, STATIC_FALLBACKS[key] || el.textContent || "");
    });
    if (UI.playerName) UI.playerName.textContent = state.player.nickname || tr("youLabel", "Sən");
    if (UI.playerAvatar) UI.playerAvatar.innerHTML = miniAvatar(state.player, 44, "lxp-me__img");
    setScore(state.player.score || 0);
}

export function showToast(message, kind = "info", durationMs = 3200) {
    if (!UI.toast || !message) return;
    UI.toast.textContent = message;
    UI.toast.dataset.kind = kind;
    UI.toast.hidden = false;
    UI.toast.classList.remove("is-visible");
    void UI.toast.offsetWidth;
    UI.toast.classList.add("is-visible");
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
        UI.toast.classList.remove("is-visible");
        toastTimer = window.setTimeout(() => {
            UI.toast.hidden = true;
            toastTimer = null;
        }, 260);
    }, durationMs);
}

// Bağlantı zolağı: "online" | "reconnecting" | "offline". Qısa qopmalarda (≤1.2 s) zolaq çıxmır.
export function setNetStatus(kind) {
    if (!UI.netBanner) return;
    if (netTimer) {
        window.clearTimeout(netTimer);
        netTimer = null;
    }
    if (kind === "online") {
        if (!netShownKind) return;
        netShownKind = "";
        UI.netBanner.dataset.kind = "back";
        UI.netBanner.textContent = tr("netBack", "Yenidən onlayn!");
        netTimer = window.setTimeout(() => {
            UI.netBanner.hidden = true;
            netTimer = null;
        }, 1600);
        return;
    }
    const text =
        kind === "offline"
            ? tr("netOffline", "İnternet yoxdur — bağlantı gözlənilir")
            : tr("netReconnecting", "Bağlantı bərpa olunur…");
    const show = () => {
        netShownKind = kind;
        UI.netBanner.dataset.kind = kind;
        UI.netBanner.textContent = text;
        UI.netBanner.hidden = false;
    };
    if (netShownKind || kind === "offline") {
        show();
    } else {
        netTimer = window.setTimeout(() => {
            netTimer = null;
            show();
        }, 1200);
    }
}

// LXNET (2026-10-02): başlıqdakı bağlantı göstəricisi — "good" | "weak" | "down" (ping RTT-dən).
const SIGNAL_TEXT = {
    good: () => tr("netGood", "Bağlantı yaxşıdır"),
    weak: () => tr("netWeak", "Bağlantı zəifdir — sual bir az gec gələ bilər"),
    down: () => tr("netReconnecting", "Bağlantı bərpa olunur…"),
};

export function setNetSignal(level) {
    const el = UI.netSignal;
    const text = SIGNAL_TEXT[level];
    if (!el || !text) return;
    if (el.dataset.level === level && !el.hidden) return;
    el.dataset.level = level;
    el.hidden = false;
    el.setAttribute("aria-label", text());
    el.title = text();
}

export function renderSoundToggle() {
    if (!UI.soundToggle) return;
    const muted = isMuted();
    const locked = audioState() === "locked";
    UI.soundToggle.setAttribute("aria-pressed", muted ? "false" : "true");
    UI.soundToggle.dataset.state = muted ? "off" : locked ? "locked" : "on";
    UI.soundToggle.setAttribute(
        "aria-label",
        muted ? tr("soundTurnOn", "Səsi aç") : tr("soundTurnOff", "Səsi söndür")
    );
    UI.soundToggle.title = muted
        ? tr("soundTurnOn", "Səsi aç")
        : locked
          ? tr("tapForSound", "Səs üçün ekrana toxun")
          : tr("soundTurnOff", "Səsi söndür");
}
