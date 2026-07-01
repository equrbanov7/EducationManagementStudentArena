import { PHASES } from './config.js';
import { playRoundEndSound } from './audio.js';
import {
    renderFinal,
    renderGetReady,
    renderIdle,
    renderIntro,
    renderLeaderboard,
    renderLocked,
    renderQuestion,
    renderResult,
    renderWaiting,
    updateWaitingProgress,
} from './render.js';
import { applySessionSettings } from './settings.js';
import { state } from './state.js';
import { clearPhaseTimer, clearTicker, queuePhaseTransition } from './timers.js';
import { pickWaitingMessage, setQuestionChip, setRoundHint } from './ui.js';
import {
    getPersonalResult,
    getRevealKey,
    getRevealTimings,
    isOwnPlayerResult,
    nowMs,
    rememberTimelinePayload,
    setStoredTop,
    shouldApplyTimelinePayload,
    tr,
    ts,
    updateServerTimeOffset,
} from './utils.js';

export function startTicker() {
    clearTicker();
    state.ticker = window.setInterval(syncQuestionPhase, 120);
}

export function syncQuestionPhase() {
    if (
        !state.currentQuestion ||
        state.phase === PHASES.RESULT ||
        state.phase === PHASES.LEADERBOARD ||
        state.phase === PHASES.FINAL
    ) {
        return;
    }

    if (state.currentAnswer) {
        renderWaiting(state.waitingMessage || pickWaitingMessage());
        return;
    }

    const now = nowMs();
    const readyEndsAt = ts(state.currentQuestion.ready_ends_at) || ts(state.currentQuestion.started_at);
    const answerStartsAt = ts(state.currentQuestion.answer_starts_at) || readyEndsAt;
    const endsAt = ts(state.currentQuestion.ends_at);

    if (now < readyEndsAt) {
        renderGetReady(state.currentQuestion);
        return;
    }

    if (now < answerStartsAt) {
        renderIntro(state.currentQuestion);
        return;
    }

    if (now < endsAt) {
        renderQuestion(state.currentQuestion);
        return;
    }

    renderLocked();
}

export function applyQuestionState(question, playerAnswer, previousTop) {
    const isNewQuestion =
        !state.currentQuestion ||
        Number(state.currentQuestion.id) !== Number(question.id) ||
        state.currentQuestion.started_at !== question.started_at;

    clearPhaseTimer();
    state.revealPayload = null;
    state.currentQuestion = question;
    state.resultSignature = "";
    state.finalSignature = "";

    if (isNewQuestion) {
        state.selectedIds = new Set();
        state.currentAnswer = null;
        state.pendingScore = null;
        state.submitting = false;
        state.waitingMessage = "";
        state.phase = "";
        state.resultSignature = "";
        state.leaderboardSignature = "";
        setQuestionChip(question);
    }

    if (previousTop && previousTop.length) {
        setStoredTop(previousTop);
    }

    if (playerAnswer) {
        state.currentAnswer = Object.assign({}, state.currentAnswer || {}, playerAnswer);
        state.pendingScore = playerAnswer.total_score != null && Number.isFinite(Number(playerAnswer.total_score))
            ? Number(playerAnswer.total_score)
            : state.pendingScore;
        state.waitingMessage = state.waitingMessage || pickWaitingMessage();
    }

    startTicker();
    syncQuestionPhase();
}

export function applyRevealState(payload) {
    clearTicker();
    state.finalSignature = "";

    if (payload.question) {
        state.currentQuestion = payload.question;
    }
    if (!state.currentQuestion && payload.question_id) {
        state.currentQuestion = Object.assign({}, state.currentQuestion || {}, { id: payload.question_id });
    }

    if (payload.previous_top && payload.previous_top.length) {
        setStoredTop(payload.previous_top);
    }

    const personalResult = getPersonalResult(payload);
    if (personalResult) {
        state.currentAnswer = Object.assign({}, state.currentAnswer || {}, personalResult);
        state.pendingScore = personalResult.total_score != null && Number.isFinite(Number(personalResult.total_score))
            ? Number(personalResult.total_score)
            : state.pendingScore;
    }

    const revealKey = getRevealKey(payload);
    const timings = getRevealTimings(payload);
    const now = nowMs();

    state.revealPayload = payload;

    if (state.revealKey !== revealKey) {
        state.revealKey = revealKey;
        playRoundEndSound(revealKey);
    }

    if (now >= timings.leaderboardStartsAt) {
        renderLeaderboard(payload);
        return;
    }

    renderResult(payload);
    queuePhaseTransition(() => {
        if (state.revealKey === revealKey && state.revealPayload) {
            renderLeaderboard(state.revealPayload);
        }
    }, timings.leaderboardStartsAt - now);
}

export function applyStateSnapshot(snapshot) {
    updateServerTimeOffset(snapshot);
    if (!snapshot || !snapshot.ok) {
        if (!state.currentQuestion && state.phase !== PHASES.FINAL) {
            renderIdle();
        }
        return;
    }

    if (!shouldApplyTimelinePayload(snapshot)) {
        return;
    }
    rememberTimelinePayload(snapshot);

    if (snapshot.settings) {
        applySessionSettings(snapshot.settings);
    }

    state.totalPlayers = Number(snapshot.total_players || state.totalPlayers || 0);
    state.answeredCount = Number(snapshot.answered_count || 0);

    if (snapshot.state === "finished") {
        renderFinal(snapshot);
        return;
    }

    if (!snapshot.question) {
        renderIdle();
        return;
    }

    if (snapshot.state === "reveal") {
        state.currentQuestion = snapshot.question;
        applyRevealState(snapshot);
        return;
    }

    applyQuestionState(snapshot.question, snapshot.player_answer || null, snapshot.previous_top || []);
}

export function handleAnswerSaved(data) {
    if (!isOwnPlayerResult(data)) {
        return;
    }
    state.submitting = false;
    state.currentAnswer = Object.assign({}, state.currentAnswer || {}, data, {
        // `??` instead of `||`: a legitimate total of 0 must not fall through
        // to stale values.
        total_score: data.total_score ?? data.score ?? state.pendingScore ?? state.player.score,
    });
    state.pendingScore = state.currentAnswer.total_score != null && Number.isFinite(Number(state.currentAnswer.total_score))
        ? Number(state.currentAnswer.total_score)
        : state.pendingScore;
    state.waitingMessage = pickWaitingMessage();
    syncQuestionPhase();
}

export function handleSocketMessage(message) {
    const data = message.data || message;
    updateServerTimeOffset(data);
    switch (data.type) {
        case "session_settings":
            applySessionSettings(data.settings);
            if (state.currentQuestion) {
                syncQuestionPhase();
            }
            break;
        case "question_published":
            if (!shouldApplyTimelinePayload(data)) {
                break;
            }
            rememberTimelinePayload(data);
            state.answeredCount = 0;
            state.totalPlayers = Math.max(state.totalPlayers, 0);
            applyQuestionState(data.question, null, data.previous_top || []);
            break;
        case "answer_saved":
            handleAnswerSaved(data);
            break;
        case "answer_progress":
            if (state.currentQuestion && Number(data.question_id || 0) !== Number(state.currentQuestion.id || 0)) {
                break;
            }
            state.answeredCount = Number(data.answered_count || 0);
            state.totalPlayers = Number(data.total_players || state.totalPlayers || 0);
            if (state.phase === PHASES.WAITING || state.phase === PHASES.LOCKED) {
                updateWaitingProgress();
            }
            break;
        case "reveal":
            if (!shouldApplyTimelinePayload(data)) {
                break;
            }
            rememberTimelinePayload(data);
            applyRevealState(data);
            break;
        case "finished":
            if (!shouldApplyTimelinePayload(data)) {
                break;
            }
            rememberTimelinePayload(data);
            renderFinal(data);
            break;
        case "error":
            state.submitting = false;
            if (state.currentQuestion && !state.currentAnswer) {
                renderQuestion(state.currentQuestion);
            }
            setRoundHint(data.message || "Unable to continue.");
            break;
        default:
            break;
    }
}
