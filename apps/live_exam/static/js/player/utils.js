// LX-FE-PLAYER (2026-09-29): ümumi köməkçilər — i18n, vaxt, zaman xətti, sıralama.
import {
    DEFAULT_LEADERBOARD_DURATION_MS,
    DEFAULT_RESULT_DURATION_MS,
    I18N,
    LANG,
    SESSION_SETTINGS,
} from './config.js?v=lx20261002';
import { clockOffsetMs, recordPush, recordRoundTrip } from './clock.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';

// Tərcümə hələ kompilyasiya olunmayıbsa {% trans %} msgid-i («answer_locked») qaytarır —
// belə açarı xam göstərmirik, JS-dəki (az) ehtiyat mətni işlədirik.
const UNTRANSLATED_KEY = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$/;

export function tr(key, fallback) {
    const value = I18N[key];
    if (typeof value !== "string") return fallback;
    const trimmed = value.trim();
    if (!trimmed || UNTRANSLATED_KEY.test(trimmed)) return fallback;
    return value;
}

export const fmt = (template, values) =>
    String(template == null ? "" : template).replace(/\{(\w+)\}/g, (match, key) =>
        values && Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match
    );

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (value) => String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ESCAPES[ch]);

export const ts = (value) => {
    if (!value) return 0;
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : 0;
};
export const nowMs = () => Date.now() + Number(state.serverTimeOffsetMs || 0);
export const wsUrl = (path) => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${path}`;

export function avatarMarkup(player, size, className = "") {
    const renderer = window.LiveAvatarRenderer;
    if (!renderer || typeof renderer.renderAvatarMarkup !== "function") return "";
    return renderer.renderAvatarMarkup(player || {}, { size, className, interactive: false });
}

// Kiçik avatar (siyahılar, podium, alt panel): data-URL <img> — 1 DOM qovşağı, bir dəfə rasterləşir
// (tam SVG ~60 qovşaqdır; zəif Android-də liderlər siyahısı yüngül qalsın). CSP img-src data: icazəlidir.
export function miniAvatar(player, size, className = "lxp-mini") {
    const renderer = window.LiveAvatarRenderer;
    if (renderer && typeof renderer.renderAvatarDataUrl === "function") {
        const src = renderer.renderAvatarDataUrl(player || {}, { crop: "portrait" });
        return `<img class="${className}" src="${esc(src)}" width="${size}" height="${size}" alt="" decoding="async">`;
    }
    return avatarMarkup(player, size, className);
}

export const showQuestionsOnDevices = () => SESSION_SETTINGS.show_questions_on_devices !== false;

export function isMulti(question) {
    return Boolean(question && question.multi);
}

export function maxSelect(question) {
    const value = Number(question && question.max_select);
    return Number.isFinite(value) && value > 0 ? value : 1;
}

export function isTextQuestion(question) {
    return String((question && question.answer_input) || "").toLowerCase() === "text";
}

export function toInt(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.round(parsed) : fallback;
}

export function hasNumber(value) {
    return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
}

// --- Zaman xətti: köhnə (gecikmiş) snapshot yeni WS mesajını geri qaytarmasın ---------------

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
    const questionId = Number(payload.question_id || (question && question.id) || 0);
    let phaseAtMs = 0;
    if (kind === "finished") {
        phaseAtMs =
            ts(payload.finished_at) || ts(payload.next_question_at) || ts(payload.revealed_at) || ts(question?.ends_at);
    } else if (kind === "reveal") {
        phaseAtMs = ts(payload.revealed_at) || ts(question?.ends_at) || ts(payload.question_ends_at);
    } else if (kind === "question") {
        phaseAtMs = ts(question?.started_at) || ts(payload.question_started_at);
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
    if (nextMeta && compareTimelineMeta(nextMeta, state.timelineMeta) >= 0) {
        state.timelineMeta = nextMeta;
    }
}

// LXNET (2026-10-02): push mesajı yalnız aşağı sərhəddir — təxmin clock.js-də (NTP üsulu).
export function updateServerTimeOffset(payload, receivedAtMs = Date.now()) {
    if (!payload || !payload.server_time) return;
    recordPush(payload.server_time, receivedAtMs);
    state.serverTimeOffsetMs = clockOffsetMs();
    state.hasServerOffset = true;
}

// Gediş-gəliş nümunəsi (WS pong, HTTP snapshot): `t0`/`t1` — Date.now() göndəriş/qəbul anları.
export function recordServerRoundTrip(t0, serverIso, t1) {
    if (!serverIso) return;
    recordRoundTrip(t0, serverIso, t1);
    state.serverTimeOffsetMs = clockOffsetMs();
    state.hasServerOffset = true;
}

// --- Sıralama / format ----------------------------------------------------------------------

function azOrdinalSuffix(n) {
    if (n >= 1000 && n % 1000 === 0) return "ci";
    if (n >= 100 && n % 100 === 0) return "cü";
    const lastDigit = n % 10;
    if (lastDigit === 0) {
        const tens = Math.floor((n % 100) / 10);
        return { 1: "cu", 2: "ci", 3: "cu", 4: "cı", 5: "ci", 6: "cı", 7: "ci", 8: "ci", 9: "cı" }[tens] || "ci";
    }
    return { 1: "ci", 2: "ci", 3: "cü", 4: "cü", 5: "ci", 6: "cı", 7: "ci", 8: "ci", 9: "cu" }[lastDigit];
}

export function ordinal(value) {
    const n = Math.round(Number(value));
    if (!Number.isFinite(n) || n <= 0) return "";
    if (LANG === "en") {
        const mod100 = n % 100;
        if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
        return `${n}${{ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"}`;
    }
    if (LANG === "tr") return `${n}.`;
    if (LANG === "ru") return `${n}-е`;
    return `${n}-${azOrdinalSuffix(n)}`;
}

// Rəqəm formatı: az/ru/tr — «9 100» (dar boşluq), en — «9,100»; onluq ayırıcı az/ru/tr-də vergül.
export function formatNumber(value) {
    const n = toInt(value, 0);
    const digits = String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, LANG === "en" ? "," : "\u202f");
    return n < 0 ? `-${digits}` : digits;
}

export function formatSeconds(ms) {
    const seconds = Math.max(0, Number(ms) || 0) / 1000;
    const text = seconds < 10 ? seconds.toFixed(1) : String(Math.round(seconds));
    return LANG === "en" ? text : text.replace(".", ",");
}

export function normalizeTopRows(rows) {
    return (Array.isArray(rows) ? rows : []).map((row, index) => {
        const playerId = Number((row && (row.player_id || row.id)) || 0);
        return {
            player_id: playerId,
            nickname: (row && row.nickname) || "",
            avatar_key: row && row.avatar_key,
            accessory_key: row && row.accessory_key,
            score: toInt(row && row.score, 0),
            _key: String(playerId || `row-${index}`),
        };
    });
}

export const isOwnRow = (row) => Number(row && row.player_id) === Number(state.player.id);

export function getRevealKey(payload) {
    const questionId = (payload && payload.question_id) || state.currentQuestion?.id || "q";
    return `${questionId}:${(payload && payload.revealed_at) || state.currentQuestion?.ends_at || ""}`;
}

export function getRevealTimings(payload) {
    const revealedAt = ts(payload && payload.revealed_at) || nowMs();
    const resultDurationMs = Math.max(0, Number(payload && payload.result_duration_ms) || DEFAULT_RESULT_DURATION_MS);
    const leaderboardDurationMs = Math.max(
        0,
        Number(payload && payload.leaderboard_duration_ms) || DEFAULT_LEADERBOARD_DURATION_MS
    );
    const leaderboardStartsAt = ts(payload && payload.leaderboard_starts_at) || revealedAt + resultDurationMs;
    const nextQuestionAt = ts(payload && payload.next_question_at) || leaderboardStartsAt + leaderboardDurationMs;
    return { revealedAt, leaderboardStartsAt, nextQuestionAt };
}

export function pickFirst(...values) {
    for (const value of values) {
        if (value !== undefined && value !== null && value !== "") return value;
    }
    return undefined;
}
