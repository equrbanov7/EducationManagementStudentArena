// LX-FE-PLAYER (2026-09-29): vəziyyət maşını. Mənbələr: WS mesajları, HTTP snapshot, cavab
// hadisələri. Qaydalar:
//  * UI HƏMİŞƏ server vəziyyətinə yaxınlaşır (snapshot sualı/reveal-i/finalı yenidən qurur);
//  * köhnə mesaj yenisini geri qaytarmır (zaman xətti müqayisəsi, utils.js);
//  * hər faza açarla render olunur → təkrar mesaj ikiqat animasiya/səs vermir;
//  * faza dəyişəndə bütün taymerlər təmizlənir.
import { BOOTSTRAP, PHASES } from './config.js?v=lx20261002';
import { handleAnswerError, handleAnswerSaved, setAnswerHooks } from './answer.js?v=lx20261002';
import { fetchState } from './api.js?v=lx20261002';
import { renderFinal } from './finale.js?v=lx20261002';
import { isFinalReveal, renderFinalSuspense, stageRevealOffsetMs } from './final_gate.js?v=lx20261002';
import { stopStatePolling } from './polling.js?v=lx20261002';
import { setRank } from './ui.js?v=lx20261002';
import {
    questionKeyOf,
    renderGetReady,
    renderIntro,
    renderLocked,
    renderQuestion,
    renderTimeUp,
    updateSelectionUI,
} from './render_round.js?v=lx20261002';
import { answeredButUnknown, renderLeaderboard, renderResult } from './render_reveal.js?v=lx20261002';
import { renderIdle, renderRemoved } from './render_status.js?v=lx20261002';
import { applySessionSettings } from './settings.js?v=lx20261002';
import { closePlayerSocket, sendJson } from './sockets.js?v=lx20261002';
import { state } from './state.js?v=lx20261002';
import {
    clearAckTimer,
    clearAllTimers,
    clearPhaseTimer,
    clearTicker,
    queuePhaseTransition,
    scheduleBoundary,
    startTicker,
} from './timers.js?v=lx20261002';
import {
    getRevealKey,
    getRevealTimings,
    nowMs,
    rememberTimelinePayload,
    shouldApplyTimelinePayload,
    ts,
    updateServerTimeOffset,
} from './utils.js?v=lx20261002';
import { currentViewEl } from './views.js?v=lx20261002';

let revealRefetchKey = "";
let finalRefetchDone = false;
// Final «darvazası»: {payload, revealed, timer} — öz yer final səhnəsi onu açanda göstərilir.
let finalGate = null;
// Sürprizi qorumaq üçün gözləmə yalnız bu qədərdən uzun olanda göstərilir (ms).
const FINAL_GATE_MIN_WAIT_MS = 250;
// `finished_at` bu qədər təzədirsə canlı hadisədir (səhnə ilə sinxron anker).
const FINAL_FRESH_EVENT_MS = 5000;

function resetRound() {
    state.selectedIds = new Set();
    state.currentAnswer = null;
    state.pendingSubmit = null;
    state.typedDraft = "";
    state.answerOpenedAt = 0;
    clearAckTimer();
}

// LXNET (2026-10-02): sual telefona çatdı → server öz saatı ilə qeyd edir (gec çatana ədalətli
// sürət ankeri + host-un «N/M aldı» sayğacı). WS bağlıdırsa HTTP snapshot bunu özü qeyd edir.
function acknowledgeQuestion(question) {
    if (!question || question.id == null || state.seenQuestionId === Number(question.id)) return;
    if (sendJson({ type: "seen", question_id: Number(question.id) })) state.seenQuestionId = Number(question.id);
}

// Növbəti faza sərhədinə (hazır ol → giriş → cavab → vaxt bitdi) dəqiq taymer: 200 ms-lik
// tiker plitələri orta hesabla ~100 ms gec açırdı.
function scheduleNextBoundary(question, now) {
    const marks = [ts(question.ready_ends_at), ts(question.answer_starts_at), ts(question.ends_at)];
    const next = marks.filter((mark) => mark && mark > now).sort((a, b) => a - b)[0];
    if (next) scheduleBoundary(syncQuestionPhase, next - now + 5);
}

function isOwn(answer) {
    return Boolean(answer) && (answer.player_id == null || Number(answer.player_id) === Number(state.player.id));
}

function hasRecordedAnswer(answer) {
    return (
        isOwn(answer) &&
        Boolean(
            answer.saved ||
                (Array.isArray(answer.choice_ids) && answer.choice_ids.length) ||
                answer.is_correct !== undefined ||
                answer.your_text
        )
    );
}

export function syncQuestionPhase() {
    const question = state.currentQuestion;
    if (!question || state.revealPayload || finalGate || state.phase === PHASES.FINAL || state.phase === PHASES.REMOVED) {
        return;
    }
    const now = nowMs();
    const startedAt = ts(question.started_at);
    const readyEndsAt = ts(question.ready_ends_at) || startedAt;
    const answerStartsAt = ts(question.answer_starts_at) || readyEndsAt;
    const endsAt = ts(question.ends_at);

    scheduleNextBoundary(question, now);
    if (state.currentAnswer || state.pendingSubmit) {
        renderLocked(question, Math.max(0, endsAt - now));
        return;
    }
    if (Number(question.get_ready_duration_ms || 0) > 0 && now < readyEndsAt) {
        renderGetReady(question, readyEndsAt - now);
        return;
    }
    if (now < answerStartsAt) {
        renderIntro(question, answerStartsAt - now, Math.max(1, answerStartsAt - readyEndsAt));
        return;
    }
    if (!endsAt || now < endsAt) {
        renderQuestion(question, Math.max(0, endsAt - now));
        return;
    }
    renderTimeUp(question);
}

export function applyQuestion(question, playerAnswer) {
    if (!question || question.id == null) return;
    const previous = state.currentQuestion;
    const isNew =
        !previous || Number(previous.id) !== Number(question.id) || previous.started_at !== question.started_at;
    if (isNew) resetRound();
    state.currentQuestion = question;
    state.revealPayload = null;
    acknowledgeQuestion(question);
    clearPhaseTimer();
    if (hasRecordedAnswer(playerAnswer)) {
        state.currentAnswer = Object.assign({}, state.currentAnswer || {}, playerAnswer, { saved: true });
        state.pendingSubmit = null;
        clearAckTimer();
    }
    startTicker(syncQuestionPhase, 200);
    syncQuestionPhase();
}

export function applyReveal(payload) {
    if (!payload) return;
    const questionId = Number(payload.question_id || (payload.question && payload.question.id) || 0);
    const previous = state.currentQuestion;
    const sameQuestion = previous && Number(previous.id) === questionId;
    if (!sameQuestion) resetRound();
    if (payload.question) {
        state.currentQuestion = Object.assign({}, sameQuestion ? previous : {}, payload.question);
    } else if (!sameQuestion) {
        state.currentQuestion = { id: questionId };
    }
    if (hasRecordedAnswer(payload.player_answer)) {
        state.currentAnswer = Object.assign({}, state.currentAnswer || {}, payload.player_answer, { saved: true });
    }
    // Raund bitdi: təsdiqlənməmiş göndəriş artıq heç nəyi dəyişə bilməz.
    state.pendingSubmit = null;
    clearAckTimer();
    clearTicker();

    const key = getRevealKey(payload);
    state.revealKey = key;
    state.revealPayload = payload;
    if (answeredButUnknown(payload) && revealRefetchKey !== key) {
        // Cavab verilib, amma şəxsi nəticə gəlməyib — snapshot tam nəticəni gətirir (bir dəfə).
        revealRefetchKey = key;
        fetchState();
    }
    // Sahib 2026-09-30: son sualda liderlər lövhəsi YOX — nəticədən sonra «Nəticələr ekranda!».
    const final = isFinalReveal(payload);
    const afterResult = final ? renderFinalSuspense : renderLeaderboard;
    const { leaderboardStartsAt } = getRevealTimings(payload);
    const now = nowMs();
    if (now >= leaderboardStartsAt) {
        clearPhaseTimer();
        afterResult(payload);
        return;
    }
    renderResult(payload);
    if (final) setRank(null); // əvvəlki sualın yeri sürprizdən əvvəl göstərilməsin
    queuePhaseTransition(() => {
        if (state.revealKey === key && state.revealPayload) afterResult(state.revealPayload);
    }, leaderboardStartsAt - now);
}

function revealFinal() {
    if (!finalGate || finalGate.revealed) return;
    finalGate.revealed = true;
    finalGate.timer = null;
    renderFinal(finalGate.payload);
}

export function applyFinished(payload) {
    const data = payload || {};
    if (finalGate) {
        // Təkrar `finished` (WS + snapshot): məlumat tamamlanır, açılma VAXTI dəyişmir.
        finalGate.payload = Object.assign({}, finalGate.payload, data, {
            my_stats: data.my_stats || finalGate.payload.my_stats,
            rank: data.rank || finalGate.payload.rank,
        });
        if (finalGate.revealed) renderFinal(finalGate.payload);
        return;
    }
    const wasPlaying = Boolean(state.phase) && state.phase !== PHASES.IDLE && state.phase !== PHASES.REMOVED;
    clearAllTimers();
    state.revealPayload = null;
    state.pendingSubmit = null;
    stopStatePolling();
    // Öz yer final səhnəsi onu açanda göstərilir; səhnə `finished` anında başlayır (aparıcı eyni
    // hadisəni alır). Anker: təzə `finished_at` (WS) → o an; köhnə anker (snapshot-da son reveal
    // vaxtı) + oyunu canlı izləyən telefon → indi; səhifə oyundan sonra açılıbsa → gözləmə yox.
    const now = nowMs();
    const finishedAt = ts(data.finished_at);
    const fresh = finishedAt && now - finishedAt >= 0 && now - finishedAt <= FINAL_FRESH_EVENT_MS;
    const anchor = fresh ? finishedAt : wasPlaying ? now : finishedAt || now;
    const wait = anchor + stageRevealOffsetMs(data) - now;
    finalGate = { payload: data, revealed: false, timer: null };
    if (wait > FINAL_GATE_MIN_WAIT_MS) {
        renderFinalSuspense();
        finalGate.timer = window.setTimeout(revealFinal, wait);
    } else {
        revealFinal();
    }
    if (payload && !payload.my_stats && !finalRefetchDone) {
        // Şəxsi statistika (my_stats) ümumi yayımda olmaya bilər — bir dəfə snapshot çəkirik.
        finalRefetchDone = true;
        window.setTimeout(fetchState, 900);
    }
    // Oyun bitib: 90 boş WebSocket serverdə açıq qalmasın.
    window.setTimeout(closePlayerSocket, 2500);
}

export function handleAuthLost() {
    if (state.phase === PHASES.FINAL || finalGate) return;
    state.removed = true;
    clearAllTimers();
    stopStatePolling();
    closePlayerSocket();
    renderRemoved();
}

export function handleSnapshot(snapshot) {
    if (!snapshot || !snapshot.ok) return;
    if (!shouldApplyTimelinePayload(snapshot)) return;
    rememberTimelinePayload(snapshot);
    if (snapshot.settings) applySessionSettings(snapshot.settings);
    if (Number(snapshot.total_players)) state.totalPlayers = Number(snapshot.total_players);
    switch (snapshot.state) {
        case "finished":
            applyFinished(snapshot);
            return;
        case "reveal":
            if (snapshot.question || state.currentQuestion) applyReveal(snapshot);
            else renderIdle();
            return;
        case "question":
            if (snapshot.question) applyQuestion(snapshot.question, snapshot.player_answer);
            else renderIdle();
            return;
        case "lobby":
            if (BOOTSTRAP.waitRoomUrl) {
                window.location.replace(BOOTSTRAP.waitRoomUrl);
                return;
            }
            renderIdle();
            return;
        default:
            renderIdle();
    }
}

export function handleSocketMessage(message) {
    const data = (message && message.data) || message;
    if (!data || typeof data !== "object") return;
    updateServerTimeOffset(data);
    switch (data.type) {
        case "session_settings":
            applySessionSettings(data.settings);
            if (state.currentQuestion && !state.revealPayload) syncQuestionPhase();
            break;
        case "question_published":
            if (!shouldApplyTimelinePayload(data)) break;
            rememberTimelinePayload(data);
            applyQuestion(data.question, data.player_answer || null);
            break;
        case "answer_saved":
            handleAnswerSaved(data);
            break;
        case "reveal":
            if (!shouldApplyTimelinePayload(data)) break;
            rememberTimelinePayload(data);
            applyReveal(data);
            break;
        case "finished":
            if (!shouldApplyTimelinePayload(data)) break;
            rememberTimelinePayload(data);
            applyFinished(data);
            break;
        case "error":
            handleAnswerError(data.message);
            break;
        default:
            break;
    }
}

function shakeTile(optionId) {
    const root = currentViewEl();
    const tile = root && root.querySelector(`[data-option-id="${Number(optionId)}"]`);
    const counter = root && root.querySelector("[data-lxp-multicount]");
    [tile, counter].forEach((el) => {
        if (!el) return;
        el.classList.remove("is-denied");
        void el.offsetWidth;
        el.classList.add("is-denied");
    });
}

setAnswerHooks({
    onSelectionChange: () => updateSelectionUI(),
    onSelectionDenied: shakeTile,
    onSubmitStarted: () => syncQuestionPhase(),
    onAnswerSaved: () => syncQuestionPhase(),
    onSubmitFailed: () => {
        syncQuestionPhase();
        fetchState();
    },
    onReveal: (payload) => {
        if (!shouldApplyTimelinePayload(payload)) return;
        rememberTimelinePayload(payload);
        applyReveal(payload);
    },
});

export { questionKeyOf };
