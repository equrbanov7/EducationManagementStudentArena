import {
    DEFAULT_LEADERBOARD_DURATION_MS,
    DEFAULT_RESULT_DURATION_MS,
    I18N,
    OPTION_SHAPES,
    SESSION_SETTINGS,
} from './config.js';
import { state } from './state.js';

export const tr = (key, fallback) => I18N[key] || fallback;
export const fmt = (template, values) =>
    String(template || "").replace(/\{(\w+)\}/g, (_, key) => (values && key in values ? values[key] : `{${key}}`));

export const wsUrl = (path) => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${path}`;

export const esc = (value) => {
    const div = document.createElement("div");
    div.textContent = value || "";
    return div.innerHTML;
};

export const ts = (value) => (value ? new Date(value).getTime() : 0);
export const nowMs = () => Date.now() + Number(state.serverTimeOffsetMs || 0);
export const avatarMarkup = (player, size, className = "") =>
    window.LiveAvatarRenderer.renderAvatarMarkup(player || {}, { size, className, interactive: false });
export const showQuestionsOnDevices = () => Boolean(SESSION_SETTINGS.show_questions_on_devices);
export const topSignature = (rows) =>
    (Array.isArray(rows) ? rows : [])
        .map((row) =>
            [
                Number(row?.player_id || row?.id || 0),
                String(row?.nickname || ""),
                Number(row?.score || 0),
            ].join(":")
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

function extractTimelineMeta(payload) {
    if (!payload) return null;

    const kind = payload.type === "finished" || payload.state === "finished"
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
        phaseAtMs = ts(payload.finished_at) || ts(payload.next_question_at) || ts(payload.revealed_at) || ts(question?.ends_at);
    } else if (kind === "reveal") {
        phaseAtMs = ts(payload.revealed_at) || ts(question?.ends_at) || ts(payload.question_ends_at);
    } else if (kind === "question") {
        phaseAtMs = ts(question?.started_at) || ts(payload.question_started_at);
    }

    return {
        phaseRank: timelinePhaseRank(kind),
        phaseAtMs,
        questionId,
    };
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

export function updateServerTimeOffset(payload, receivedAtMs = Date.now()) {
    const serverMs = ts(payload && payload.server_time);
    if (!serverMs) {
        return;
    }
    const sample = serverMs - receivedAtMs;
    if (!Number.isFinite(sample)) {
        return;
    }
    if (!Number.isFinite(state.serverTimeOffsetMs) || state.serverTimeOffsetMs === 0) {
        state.serverTimeOffsetMs = sample;
        return;
    }
    state.serverTimeOffsetMs = Math.round((state.serverTimeOffsetMs * 3 + sample) / 4);
}

export function shouldApplyTimelinePayload(payload) {
    const nextMeta = extractTimelineMeta(payload);
    return compareTimelineMeta(nextMeta, state.timelineMeta) >= 0;
}

export function rememberTimelinePayload(payload) {
    const nextMeta = extractTimelineMeta(payload);
    if (!nextMeta) return;
    if (compareTimelineMeta(nextMeta, state.timelineMeta) >= 0) {
        state.timelineMeta = nextMeta;
    }
}

export function ordinal(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) return tr("resultNoRank", "No rank");
    const mod100 = number % 100;
    if (mod100 >= 11 && mod100 <= 13) return `${number}th`;
    const mod10 = number % 10;
    if (mod10 === 1) return `${number}st`;
    if (mod10 === 2) return `${number}nd`;
    if (mod10 === 3) return `${number}rd`;
    return `${number}th`;
}

export function formatClock(milliseconds) {
    const safe = Math.max(0, milliseconds);
    const totalSeconds = Math.ceil(safe / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function isMulti(question) {
    return Boolean(question && question.multi);
}

export function maxSelect(question) {
    const value = Number(question && question.max_select);
    return Number.isFinite(value) && value > 0 ? value : 1;
}

export function normalizeTopRows(rows) {
    return (Array.isArray(rows) ? rows : []).map((row, index) => {
        const fallbackKey = `${row && row.nickname ? row.nickname : "Player"}-${index}`;
        const playerId = Number(row && (row.player_id || row.id || 0));
        return {
            player_id: playerId,
            nickname: (row && row.nickname) || "Player",
            avatar_key: row && row.avatar_key,
            accessory_key: row && row.accessory_key,
            score: Number((row && row.score) || 0) || 0,
            _key: String(playerId || fallbackKey),
        };
    });
}

export function cloneTopRows(rows) {
    return normalizeTopRows(rows).map((row) => ({ ...row }));
}

export function setStoredTop(rows) {
    state.lastTop = cloneTopRows(rows);
}

export function findPersonalResult(results) {
    const rows = Array.isArray(results) ? results : [];
    return rows.find((row) => Number(row.player_id) === Number(state.player.id)) || null;
}

export function isOwnPlayerResult(result) {
    if (!result || result.player_id == null) return true;
    return Number(result.player_id) === Number(state.player.id);
}

export function getPersonalResult(payload) {
    if (payload && payload.player_answer && isOwnPlayerResult(payload.player_answer)) {
        return Object.assign({}, payload.player_answer);
    }
    if (state.currentAnswer && isOwnPlayerResult(state.currentAnswer)) {
        return Object.assign({}, state.currentAnswer);
    }
    const fromResults = findPersonalResult(payload && payload.results);
    if (fromResults) return fromResults;
    return null;
}

export function getRevealKey(payload) {
    return `${payload.question_id || state.currentQuestion?.id || "question"}:${payload.revealed_at || state.currentQuestion?.ends_at || ""}`;
}

export function getRevealTimings(payload) {
    const revealedAt = ts(payload && payload.revealed_at) || nowMs();
    const resultDurationMs = Math.max(0, Number(payload && payload.result_duration_ms) || DEFAULT_RESULT_DURATION_MS);
    const leaderboardDurationMs = Math.max(
        0,
        Number(payload && payload.leaderboard_duration_ms) || DEFAULT_LEADERBOARD_DURATION_MS
    );
    const leaderboardStartsAt = ts(payload && payload.leaderboard_starts_at) || (revealedAt + resultDurationMs);
    const nextQuestionAt = ts(payload && payload.next_question_at) || (leaderboardStartsAt + leaderboardDurationMs);

    return {
        revealedAt,
        resultDurationMs,
        leaderboardDurationMs,
        leaderboardStartsAt,
        nextQuestionAt,
    };
}

export function buildQuestionCard(question, extraMarkup = "") {
    return `
        <div class="question-card">
            <div class="question-card__eyebrow">Round ${Number(question.index || 0)} of ${Number(question.total || 0)}</div>
            <div class="question-card__text">${esc(
                showQuestionsOnDevices() ? question.text || "" : tr("questionHiddenBody", "The question is on the main screen.")
            )}</div>
            ${extraMarkup}
        </div>
    `;
}

export function optionShapeKey(option, index) {
    const fallback = OPTION_SHAPES[index % OPTION_SHAPES.length] || "circle";
    const raw = String(option?.shape || fallback).toLowerCase();
    return raw.replace(/[^a-z0-9_-]/g, "") || fallback;
}

export function optionMarkerLabel(option, index) {
    if (option?.shape_label) return option.shape_label;
    const shape = optionShapeKey(option, index).replace(/[-_]/g, " ");
    return shape.charAt(0).toUpperCase() + shape.slice(1);
}

export function optionMarkerMarkup(option, index) {
    const shape = optionShapeKey(option, index);
    const label = optionMarkerLabel(option, index);
    return `
        <span class="option-letter option-letter--shape" aria-label="${esc(label)}" title="${esc(label)}">
            <span class="answer-shape answer-shape--${shape}" aria-hidden="true"></span>
        </span>
    `;
}
