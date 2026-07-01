export const BOOTSTRAP = window.LIVE_EXAM_PLAYER_BOOTSTRAP || {};
export const I18N = window.LIVE_EXAM_PLAYER_I18N || {};
export const SESSION_SETTINGS = Object.assign({}, BOOTSTRAP.sessionSettings || {});

export const WAITING_MESSAGES = Array.isArray(BOOTSTRAP.waitingMessages) && BOOTSTRAP.waitingMessages.length
    ? BOOTSTRAP.waitingMessages
    : ["Easy does it!", "Nice move!", "Let's see how you did!", "Good call!", "Locked in!"];

export const DEFAULT_RESULT_DURATION_MS = 1600;
export const DEFAULT_LEADERBOARD_DURATION_MS = 5000;
export const LEADERBOARD_LIMIT = 5;
export const PODIUM_SIZE = 3;
export const AudioCtor = window.AudioContext || window.webkitAudioContext;
export const STATE_POLL_INTERVAL_MS = 2500;
export const OPTION_SHAPES = ["triangle", "diamond", "circle", "square", "pentagon", "hexagon"];

export const PHASES = Object.freeze({
    IDLE: "idle",
    GET_READY: "get_ready",
    INTRO: "intro",
    QUESTION: "question",
    WAITING: "waiting",
    LOCKED: "locked",
    RESULT: "result",
    LEADERBOARD: "leaderboard",
    FINAL: "final",
});
