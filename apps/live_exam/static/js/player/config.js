// LX-FE-PLAYER (2026-09-29): iştirakçı ekranının sabitləri və bootstrap məlumatı.
export const BOOTSTRAP = window.LIVE_EXAM_PLAYER_BOOTSTRAP || {};
export const I18N = window.LIVE_EXAM_PLAYER_I18N || {};
export const SESSION_SETTINGS = Object.assign({}, BOOTSTRAP.sessionSettings || {});
export const LANG = String(document.documentElement.lang || "az").slice(0, 2).toLowerCase();

export const DEFAULT_RESULT_DURATION_MS = 3500;
export const DEFAULT_LEADERBOARD_DURATION_MS = 5000;
export const LEADERBOARD_LIMIT = 5;
export const PODIUM_SIZE = 3;
export const STATE_POLL_INTERVAL_MS = 2500;
// WS ilə göndərilən cavabın təsdiqi (answer_saved) bu müddətdə gəlməsə HTTP ehtiyat yolu işə düşür.
export const ACK_TIMEOUT_MS = 3500;
export const TEXT_ANSWER_MAX_LENGTH = 60;
export const OPTION_SHAPES = ["triangle", "diamond", "circle", "square", "pentagon", "hexagon"];

export const PHASES = Object.freeze({
    IDLE: "idle",
    GET_READY: "get_ready",
    INTRO: "intro",
    QUESTION: "question",
    LOCKED: "locked",
    TIMEUP: "timeup",
    RESULT: "result",
    LEADERBOARD: "leaderboard",
    // Sahib 2026-09-30: son sualdan sonra «Nəticələr ekranda!» — yer final səhnəsi ilə açılır.
    SUSPENSE: "suspense",
    FINAL: "final",
    REMOVED: "removed",
    // 2026-10-08 (L3): gec qoşulub — növbəti sual sərhədini gözləyir.
    LATE_JOIN: "late_join",
});

export function prefersReducedMotion() {
    try {
        return Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (error) {
        return false;
    }
}
