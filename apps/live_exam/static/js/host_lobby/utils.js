import { UI } from './dom.js?v=lx20260930';
import { state } from './state.js?v=lx20260930';

export const I18N = window.LIVE_EXAM_HOST_I18N || {};
export const hostShellSubscribers = new Set();

// Tərcümə hələ kompilyasiya olunmayıbsa şablon msgid-in özünü (məs. "stage_replay")
// qaytarır — belə halda JS-dəki Azərbaycan dilində ehtiyat mətn göstərilir.
const looksUntranslated = (value) => /^[a-z0-9]+(?:_[a-z0-9]+)+$/.test(value);
export const tr = (key, fallback) => {
    const value = I18N[key];
    return value && !looksUntranslated(value) ? value : fallback;
};
export const controlsEnabled = () => CONFIG.controlsEnabled !== false;
export const fmt = (template, values) =>
    String(template || "").replace(/\{(\w+)\}/g, (_, key) => (values && key in values ? values[key] : `{${key}}`));
export const esc = (text) =>
    String(text == null ? "" : text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
export const wsUrl = (path) => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${path}`;
export const safeDisplay = (node, value) => {
    if (node) node.style.display = value;
};
export const toMs = (value) => {
    const parsed = value ? new Date(value).getTime() : 0;
    return Number.isFinite(parsed) ? parsed : 0;
};
export const nowMs = () => Date.now() + Number(state.serverTimeOffsetMs || 0);
export const questionKey = (question) => `${question?.id || "0"}:${question?.started_at || ""}`;
export const revealKey = (payload) => `${payload?.question_id || "0"}:${payload?.revealed_at || ""}`;
export const lang = () => String(CONFIG.languageCode || document.documentElement.lang || "az").slice(0, 2).toLowerCase();
export const reducedMotion = () => Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
export const usesPresentationStageLayout = () => document.body.classList.contains("host-presentation-page");

export const progressLabel = (question) =>
    fmt(tr("questionOf", "Sual {index} / {total}"), {
        index: Number(question?.index || 0),
        total: Number(question?.total || 0),
    });
export const answerWord = () => tr("answersLabel", "cavab");

export function formatNumber(value) {
    try {
        return new Intl.NumberFormat(lang()).format(Number(value || 0));
    } catch (error) {
        return String(Number(value || 0));
    }
}

export function formatSeconds(ms) {
    const seconds = Math.max(0, Number(ms || 0)) / 1000;
    try {
        return new Intl.NumberFormat(lang(), { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(seconds);
    } catch (error) {
        return seconds.toFixed(1);
    }
}

/** Mətn uzunluğu sinfi — başlanğıc şrift ölçüsü CSS-də (data-len) verilir. */
export function lengthClass(text) {
    const n = String(text || "").length;
    if (n <= 60) return "s";
    if (n <= 120) return "m";
    if (n <= 200) return "l";
    return "xl";
}

/**
 * Konteynerə sığana qədər şrifti addım-addım kiçildir (CSS: font-size: var(--fit-size, …)).
 * Yalnız vəziyyət dəyişəndə çağırılır (hər kadrda yox) — layout xərci azdır.
 */
export function fitText(element, { min = 16, step = 0.9 } = {}) {
    if (!element || !element.isConnected) return;
    element.style.removeProperty("--fit-size");
    let size = parseFloat(window.getComputedStyle(element).fontSize) || 32;
    for (let guard = 0; guard < 16; guard += 1) {
        // Dözüm: diakritika / aşağı çıxıntılar (ə, ı, ş, g…) sətir qutusundan bir neçə px
        // çıxır — bu «daşma» deyil; yalnız həqiqi əlavə sətir kiçiltmə tələb edir.
        const tolerance = Math.max(4, size * 0.3);
        const overflow =
            element.scrollHeight > element.clientHeight + tolerance || element.scrollWidth > element.clientWidth + 2;
        if (!overflow || size <= min) break;
        size = Math.max(min, Math.floor(size * step));
        element.style.setProperty("--fit-size", `${size}px`);
    }
}

export function fitAll(root, selector, options) {
    (root || document).querySelectorAll(selector).forEach((element) => fitText(element, options));
}

const countUps = new WeakMap();

/** Rəqəmi `from`-dan `to`-ya animasiya ilə sayır (yalnız textContent). */
export function countUp(element, from, to, duration = 900) {
    if (!element) return;
    const previous = countUps.get(element);
    if (previous) cancelAnimationFrame(previous);
    const start = Number(from || 0);
    const end = Number(to || 0);
    if (reducedMotion() || duration <= 0 || start === end) {
        element.textContent = formatNumber(end);
        return;
    }
    const t0 = performance.now();
    const tick = (now) => {
        const k = Math.min(1, (now - t0) / duration);
        const eased = 1 - (1 - k) ** 3;
        element.textContent = formatNumber(Math.round(start + (end - start) * eased));
        if (k < 1) countUps.set(element, requestAnimationFrame(tick));
        else countUps.delete(element);
    };
    countUps.set(element, requestAnimationFrame(tick));
}

/** PIN-i oxunaqlı qruplara bölür (boşluq simvolu YOX — kopyalananda PIN bütöv qalır). */
export function pinMarkup(pin) {
    const value = String(pin || "");
    const size = value.length <= 6 ? 3 : Math.ceil(value.length / 2);
    const groups = [];
    for (let i = 0; i < value.length; i += size) groups.push(value.slice(i, i + size));
    return groups.map((group) => `<span class="hx-pin__group">${esc(group)}</span>`).join("");
}

export const avatarMarkup = (player, size, className = "", extra = {}) =>
    (window.LiveAvatarRenderer || { renderAvatarMarkup: () => "" }).renderAvatarMarkup(player || {}, {
        size,
        className,
        interactive: false,
        ...extra,
    });

export const avatarImageMarkup = (player, size, className = "") => {
    const renderer = window.LiveAvatarRenderer || {};
    if (typeof renderer.renderAvatarDataUrl !== "function") {
        return avatarMarkup(player, size, className);
    }
    const resolvedSize = Number(size) > 0 ? Number(size) : 72;
    const classes = ["host-avatar-image", className].filter(Boolean).join(" ");
    return `<img class="${esc(classes)}" src="${renderer.renderAvatarDataUrl(player || {})}" alt="" width="${resolvedSize}" height="${resolvedSize}" decoding="async">`;
};

export const topSignature = (rows) =>
    (Array.isArray(rows) ? rows : [])
        .map((player) =>
            [Number(player?.player_id || player?.id || 0), String(player?.nickname || ""), Number(player?.score || 0)].join(":")
        )
        .join("|");

function timelinePhaseRank(kind) {
    switch (kind) {
        case "question":
            return 1;
        case "reveal":
            return 2;
        case "finished":
            return 3;
        default:
            return 0;
    }
}

export function updateServerTimeOffset(payload, receivedAtMs = Date.now()) {
    const serverMs = toMs(payload?.server_time);
    if (!serverMs) return;
    const sample = serverMs - receivedAtMs;
    if (!Number.isFinite(sample)) return;
    if (!Number.isFinite(state.serverTimeOffsetMs) || state.serverTimeOffsetMs === 0) {
        state.serverTimeOffsetMs = sample;
        return;
    }
    state.serverTimeOffsetMs = Math.round((state.serverTimeOffsetMs * 3 + sample) / 4);
}

function extractTimelineMeta(payload) {
    if (!payload) return null;
    const kind =
        payload.type === "finished" || payload.state === "finished"
            ? "finished"
            : payload.type === "reveal" || payload.state === "reveal"
              ? "reveal"
              : payload.type === "question_published" || payload.state === "question"
                ? "question"
                : "lobby";
    const question = payload.question || null;
    const questionId = Number(payload.question_id || question?.id || 0);
    let phaseAtMs = 0;
    if (kind === "finished") {
        phaseAtMs =
            toMs(payload.finished_at) || toMs(payload.next_question_at) || toMs(payload.revealed_at) || toMs(question?.ends_at);
    } else if (kind === "reveal") {
        phaseAtMs = toMs(payload.revealed_at) || toMs(question?.ends_at) || toMs(payload.question_ends_at);
    } else if (kind === "question") {
        phaseAtMs = toMs(question?.started_at) || toMs(payload.question_started_at);
    }
    return { phaseRank: timelinePhaseRank(kind), phaseAtMs, questionId };
}

function compareTimelineMeta(nextMeta, currentMeta) {
    if (!nextMeta) return 0;
    if (!currentMeta) return 1;
    if (nextMeta.phaseAtMs !== currentMeta.phaseAtMs) {
        return nextMeta.phaseAtMs > currentMeta.phaseAtMs ? 1 : -1;
    }
    if (nextMeta.phaseRank !== currentMeta.phaseRank) {
        return nextMeta.phaseRank > currentMeta.phaseRank ? 1 : -1;
    }
    if (nextMeta.questionId && currentMeta.questionId && nextMeta.questionId !== currentMeta.questionId) {
        return nextMeta.questionId > currentMeta.questionId ? 1 : -1;
    }
    return 0;
}

export function shouldApplyTimelinePayload(payload) {
    return compareTimelineMeta(extractTimelineMeta(payload), state.timelineMeta) >= 0;
}

export function rememberTimelinePayload(payload) {
    const nextMeta = extractTimelineMeta(payload);
    if (!nextMeta) return;
    if (compareTimelineMeta(nextMeta, state.timelineMeta) >= 0) {
        state.timelineMeta = nextMeta;
    }
}

export function buildJoinUrl() {
    const twoStepJoin = state.sessionSettings.two_step_join !== false;
    let origin = location.origin;
    try {
        origin = new URL(CONFIG.entryUrl || location.origin).origin;
    } catch (error) {
        origin = location.origin;
    }
    if (twoStepJoin) {
        const url = new URL("/live/", `${origin}/`);
        url.searchParams.set("pin", CONFIG.pin);
        return url.toString();
    }
    return `${origin}/live/join/${encodeURIComponent(CONFIG.pin)}/`;
}

export function currentQrUrl() {
    const base = CONFIG.qrUrl || "";
    if (!base) return "";
    const cacheKey = state.sessionSettings.two_step_join === false ? "direct" : "pin";
    return `${base}${base.includes("?") ? "&" : "?"}mode=${cacheKey}`;
}

export function joinUrlLabel(rawUrl) {
    if (!rawUrl) return "";
    try {
        const parsed = new URL(rawUrl);
        const path = parsed.pathname === "/" ? "" : parsed.pathname.replace(/\/$/, "");
        return `${parsed.host}${path}`;
    } catch (error) {
        return String(rawUrl).replace(/^https?:\/\//, "").replace(/\/$/, "");
    }
}

export function publicHostState() {
    return {
        sessionState: state.sessionState,
        phase: state.phase,
        totalPlayers: Number(state.totalPlayers || 0),
        answeredCount: Number(state.answeredCount || 0),
        players: Array.isArray(state.players) ? [...state.players] : [],
        settings: Object.assign({}, state.sessionSettings),
        isLocked: Boolean(state.isLocked),
    };
}

export function notifyHostShell() {
    const snapshot = publicHostState();
    hostShellSubscribers.forEach((listener) => {
        try {
            listener(snapshot);
        } catch (error) {
            console.error("live host shell subscriber error", error);
        }
    });
    window.dispatchEvent(new CustomEvent("live-host-state", { detail: snapshot }));
}

export function markStateMutation() {
    state.lastStateMutationAt = nowMs();
}

const logs = [];
let debugOn = false;

export function log(message) {
    // 2026-09-13 frontend auditi F13: konsola yalnız «Debug» paneli açıq olanda yazılır.
    if (debugOn) console.log("[HOST]", message);
    if (!UI.debugLog) return;
    logs.unshift(`> ${new Date().toLocaleTimeString()} ${message}`);
    if (logs.length > 100) logs.length = 100;
    UI.debugLog.textContent = logs.join("\n");
}

export function bindDebugToggle() {
    UI.debugBtn?.addEventListener("click", () => {
        debugOn = !debugOn;
        UI.debugBtn.setAttribute("aria-expanded", debugOn ? "true" : "false");
        UI.debugLog.classList.toggle("is-open", debugOn);
    });
}
