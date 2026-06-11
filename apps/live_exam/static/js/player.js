const $ = (id) => document.getElementById(id);

const BOOTSTRAP = window.LIVE_EXAM_PLAYER_BOOTSTRAP || {};
const I18N = window.LIVE_EXAM_PLAYER_I18N || {};
const SESSION_SETTINGS = Object.assign({}, BOOTSTRAP.sessionSettings || {});
const tr = (key, fallback) => I18N[key] || fallback;
const fmt = (template, values) =>
    String(template || "").replace(/\{(\w+)\}/g, (_, key) => (values && key in values ? values[key] : `{${key}}`));

const UI = {
    questionChip: $("questionChip"),
    quizTitleText: $("quizTitleText"),
    connStatus: $("connStatus"),
    connStatusText: document.querySelector("#connStatus .live-player-connection__text"),
    timerBox: $("timerBox"),
    timerText: $("timerText"),
    phasePanelInner: $("phasePanelInner"),
    optionsShell: $("optionsShell"),
    optionsContainer: $("optionsContainer"),
    multiActions: $("multiActions"),
    selectCounter: $("selectCounter"),
    submitBtn: $("submitBtn"),
    playerAvatar: $("playerAvatar"),
    playerName: $("playerName"),
    playerScore: $("playerScore"),
    roundProgressText: $("roundProgressText"),
};

const WAITING_MESSAGES = Array.isArray(BOOTSTRAP.waitingMessages) && BOOTSTRAP.waitingMessages.length
    ? BOOTSTRAP.waitingMessages
    : ["Easy does it!", "Nice move!", "Let's see how you did!", "Good call!", "Locked in!"];

const DEFAULT_RESULT_DURATION_MS = 1600;
const DEFAULT_LEADERBOARD_DURATION_MS = 5000;
const LEADERBOARD_LIMIT = 5;
const PODIUM_SIZE = 3;
const AudioCtor = window.AudioContext || window.webkitAudioContext;
const STATE_POLL_INTERVAL_MS = 2500;

const PHASES = Object.freeze({
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

const state = {
    player: Object.assign({ score: 0 }, BOOTSTRAP.player || {}),
    currentQuestion: null,
    selectedIds: new Set(),
    currentAnswer: null,
    pendingScore: null,
    phase: "",
    waitingMessage: "",
    lastWaitingMessage: "",
    answeredCount: 0,
    totalPlayers: 0,
    submitting: false,
    ticker: null,
    pollTimer: null,
    phaseTimer: null,
    revealKey: "",
    revealPayload: null,
    lastTop: [],
    resultSignature: "",
    leaderboardSignature: "",
    finalSignature: "",
    lastRoundSoundKey: "",
    lastScoreSoundKey: "",
    lastFinalSoundKey: "",
    audioContext: null,
    serverTimeOffsetMs: 0,
    timelineMeta: null,
};

const wsUrl = (path) => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${path}`;
const esc = (value) => {
    const div = document.createElement("div");
    div.textContent = value || "";
    return div.innerHTML;
};
const ts = (value) => (value ? new Date(value).getTime() : 0);
const nowMs = () => Date.now() + Number(state.serverTimeOffsetMs || 0);
const avatarMarkup = (player, size, className = "") =>
    window.LiveAvatarRenderer.renderAvatarMarkup(player || {}, { size, className, interactive: false });
const showQuestionsOnDevices = () => Boolean(SESSION_SETTINGS.show_questions_on_devices);
const OPTION_SHAPES = ["triangle", "diamond", "circle", "square", "pentagon", "hexagon"];
const topSignature = (rows) =>
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

function updateServerTimeOffset(payload, receivedAtMs = Date.now()) {
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

function shouldApplyTimelinePayload(payload) {
    const nextMeta = extractTimelineMeta(payload);
    return compareTimelineMeta(nextMeta, state.timelineMeta) >= 0;
}

function rememberTimelinePayload(payload) {
    const nextMeta = extractTimelineMeta(payload);
    if (!nextMeta) return;
    if (compareTimelineMeta(nextMeta, state.timelineMeta) >= 0) {
        state.timelineMeta = nextMeta;
    }
}

function applySessionSettings(nextSettings) {
    Object.assign(SESSION_SETTINGS, nextSettings || {});
    document.body.dataset.liveTheme = SESSION_SETTINGS.theme_key || "aurora";
}

function ordinal(value) {
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

function formatClock(milliseconds) {
    const safe = Math.max(0, milliseconds);
    const totalSeconds = Math.ceil(safe / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function isMulti(question) {
    return Boolean(question && question.multi);
}

function maxSelect(question) {
    const value = Number(question && question.max_select);
    return Number.isFinite(value) && value > 0 ? value : 1;
}

function setRoundHint(text) {
    if (UI.roundProgressText) {
        UI.roundProgressText.textContent = text || "";
    }
}

function setConnection(kind) {
    if (!UI.connStatus || !UI.connStatusText) {
        return;
    }
    UI.connStatus.classList.remove("is-online", "is-offline");
    if (kind === "online") {
        UI.connStatus.classList.add("is-online");
        UI.connStatusText.textContent = tr("connectionOnline", "Online");
        return;
    }
    if (kind === "offline") {
        UI.connStatus.classList.add("is-offline");
        UI.connStatusText.textContent = tr("connectionOffline", "Offline");
        return;
    }
    UI.connStatusText.textContent = tr("connectionConnecting", "Connecting");
}

function setTimerState(show, milliseconds = 0) {
    UI.timerBox.classList.toggle("is-visible", Boolean(show));
    UI.timerBox.classList.remove("is-warning", "is-danger");
    if (!show) {
        UI.timerText.textContent = "--:--";
        return;
    }

    UI.timerText.textContent = formatClock(milliseconds);
    const seconds = Math.ceil(Math.max(0, milliseconds) / 1000);
    if (seconds <= 5) {
        UI.timerBox.classList.add("is-danger");
    } else if (seconds <= 10) {
        UI.timerBox.classList.add("is-warning");
    }
}

function setQuestionChip(question) {
    if (!question || !question.index) {
        UI.questionChip.textContent = tr("questionLabel", "Question");
        return;
    }
    UI.questionChip.textContent = `${tr("questionLabel", "Question")} ${question.index}`;
}

function setScore(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return;
    state.player.score = parsed;
    UI.playerScore.textContent = String(parsed);
}

function renderPlayerIdentity() {
    if (UI.quizTitleText) {
        UI.quizTitleText.textContent = BOOTSTRAP.quizTitle || "Quiz";
    }
    UI.playerName.textContent = state.player.nickname || "Player";
    UI.playerAvatar.innerHTML = avatarMarkup(state.player, 72, "player-avatar");
    setScore(state.player.score || 0);
}

function clearTicker() {
    if (state.ticker) {
        window.clearInterval(state.ticker);
        state.ticker = null;
    }
}

function clearPhaseTimer() {
    if (state.phaseTimer) {
        window.clearTimeout(state.phaseTimer);
        state.phaseTimer = null;
    }
}

function queuePhaseTransition(callback, delay) {
    clearPhaseTimer();
    state.phaseTimer = window.setTimeout(() => {
        state.phaseTimer = null;
        callback();
    }, Math.max(0, delay));
}

function hideOptions() {
    UI.optionsShell.style.display = "none";
    UI.optionsContainer.innerHTML = "";
    UI.multiActions.style.display = "none";
    UI.submitBtn.disabled = true;
}

function disableOptions() {
    document.querySelectorAll(".option-btn").forEach((button) => {
        button.disabled = true;
    });
    UI.submitBtn.disabled = true;
}

function updateCounter() {
    if (!isMulti(state.currentQuestion)) {
        UI.multiActions.style.display = "none";
        return;
    }
    const maximum = maxSelect(state.currentQuestion);
    UI.multiActions.style.display = "flex";
    UI.selectCounter.textContent = `Selected ${state.selectedIds.size} / ${maximum}`;
    UI.submitBtn.disabled = state.selectedIds.size === 0 || state.submitting;
}

function pickWaitingMessage() {
    const pool = WAITING_MESSAGES.filter((message) => message !== state.lastWaitingMessage);
    const source = pool.length ? pool : WAITING_MESSAGES;
    const choice = source[Math.floor(Math.random() * source.length)] || WAITING_MESSAGES[0];
    state.lastWaitingMessage = choice;
    return choice;
}

function normalizeTopRows(rows) {
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

function cloneTopRows(rows) {
    return normalizeTopRows(rows).map((row) => ({ ...row }));
}

function setStoredTop(rows) {
    state.lastTop = cloneTopRows(rows);
}

function findPersonalResult(results) {
    const rows = Array.isArray(results) ? results : [];
    return rows.find((row) => Number(row.player_id) === Number(state.player.id)) || null;
}

function isOwnPlayerResult(result) {
    if (!result || result.player_id == null) return true;
    return Number(result.player_id) === Number(state.player.id);
}

function getPersonalResult(payload) {
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

function getRevealKey(payload) {
    return `${payload.question_id || state.currentQuestion?.id || "question"}:${payload.revealed_at || state.currentQuestion?.ends_at || ""}`;
}

function getRevealTimings(payload) {
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

function buildQuestionCard(question, extraMarkup = "") {
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

function optionShapeKey(option, index) {
    const fallback = OPTION_SHAPES[index % OPTION_SHAPES.length] || "circle";
    const raw = String(option?.shape || fallback).toLowerCase();
    return raw.replace(/[^a-z0-9_-]/g, "") || fallback;
}

function optionMarkerLabel(option, index) {
    if (option?.shape_label) return option.shape_label;
    const shape = optionShapeKey(option, index).replace(/[-_]/g, " ");
    return shape.charAt(0).toUpperCase() + shape.slice(1);
}

function optionMarkerMarkup(option, index) {
    const shape = optionShapeKey(option, index);
    const label = optionMarkerLabel(option, index);
    return `
        <span class="option-letter option-letter--shape" aria-label="${esc(label)}" title="${esc(label)}">
            <span class="answer-shape answer-shape--${shape}" aria-hidden="true"></span>
        </span>
    `;
}

function getAudioContext() {
    if (!AudioCtor) return null;
    if (!state.audioContext) {
        state.audioContext = new AudioCtor();
    }
    return state.audioContext;
}

function unlockAudio() {
    const ctx = getAudioContext();
    if (!ctx || ctx.state !== "suspended") return;
    ctx.resume().catch(() => {});
}

function playTone(ctx, config) {
    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();
    const startTime = config.startTime;
    const duration = config.duration;
    const peak = config.gain;

    oscillator.type = config.type || "sine";
    oscillator.frequency.setValueAtTime(config.frequency, startTime);
    if (config.endFrequency) {
        oscillator.frequency.exponentialRampToValueAtTime(Math.max(20, config.endFrequency), startTime + duration);
    }

    gainNode.gain.setValueAtTime(0.0001, startTime);
    gainNode.gain.exponentialRampToValueAtTime(peak, startTime + 0.02);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);

    oscillator.connect(gainNode);
    gainNode.connect(ctx.destination);
    oscillator.start(startTime);
    oscillator.stop(startTime + duration + 0.02);
}

function playRoundEndSound(revealKey) {
    if (state.lastRoundSoundKey === revealKey) return;

    const ctx = getAudioContext();
    if (!ctx) return;

    const start = () => {
        const base = ctx.currentTime + 0.01;
        playTone(ctx, {
            startTime: base,
            duration: 0.12,
            frequency: 520,
            endFrequency: 420,
            gain: 0.045,
            type: "triangle",
        });
        playTone(ctx, {
            startTime: base + 0.06,
            duration: 0.26,
            frequency: 320,
            endFrequency: 220,
            gain: 0.06,
            type: "sine",
        });
        state.lastRoundSoundKey = revealKey;
    };

    if (ctx.state === "suspended") {
        ctx.resume().then(start).catch(() => {});
        return;
    }
    start();
}

function playLeaderboardSound(revealKey) {
    if (state.lastScoreSoundKey === revealKey) return;

    const ctx = getAudioContext();
    if (!ctx) return;

    const start = () => {
        const base = ctx.currentTime + 0.01;
        [290, 360, 430].forEach((frequency, index) => {
            playTone(ctx, {
                startTime: base + index * 0.08,
                duration: 0.12,
                frequency,
                endFrequency: frequency * 1.03,
                gain: 0.035,
                type: "square",
            });
        });
        playTone(ctx, {
            startTime: base + 0.02,
            duration: 0.34,
            frequency: 180,
            endFrequency: 140,
            gain: 0.022,
            type: "triangle",
        });
        state.lastScoreSoundKey = revealKey;
    };

    if (ctx.state === "suspended") {
        ctx.resume().then(start).catch(() => {});
        return;
    }
    start();
}

function playFinalSound(finalKey) {
    if (state.lastFinalSoundKey === finalKey) return;

    const ctx = getAudioContext();
    if (!ctx) return;

    const start = () => {
        const base = ctx.currentTime + 0.02;
        [261.63, 329.63, 392, 523.25, 659.25].forEach((frequency, index) => {
            playTone(ctx, {
                startTime: base + index * 0.09,
                duration: index === 4 ? 0.58 : 0.24,
                frequency,
                endFrequency: frequency * 1.015,
                gain: index === 4 ? 0.048 : 0.032,
                type: index < 3 ? "triangle" : "sine",
            });
        });
        playTone(ctx, {
            startTime: base + 0.03,
            duration: 0.82,
            frequency: 130.81,
            endFrequency: 98,
            gain: 0.018,
            type: "sine",
        });
        state.lastFinalSoundKey = finalKey;
    };

    if (ctx.state === "suspended") {
        ctx.resume().then(start).catch(() => {});
        return;
    }
    start();
}

function animateNumber(element, fromValue, toValue, duration = 900) {
    if (!element) return;
    const from = Number(fromValue);
    const to = Number(toValue);
    if (!Number.isFinite(from) || !Number.isFinite(to) || from === to) {
        element.textContent = String(toValue);
        return;
    }

    const startedAt = performance.now();
    const step = (timestamp) => {
        const progress = Math.min(1, (timestamp - startedAt) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        const value = Math.round(from + ((to - from) * eased));
        element.textContent = String(value);
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };

    window.requestAnimationFrame(step);
}

function renderIdle() {
    clearTicker();
    clearPhaseTimer();
    state.phase = PHASES.IDLE;
    state.currentQuestion = null;
    state.currentAnswer = null;
    state.revealPayload = null;
    state.resultSignature = "";
    state.leaderboardSignature = "";
    state.finalSignature = "";
    hideOptions();
    setTimerState(false);
    setQuestionChip(null);
    setRoundHint(tr("waitingForHost", "Waiting for the host to start the next round."));
    UI.phasePanelInner.innerHTML = `
        <div class="phase-shell">
            <div class="phase-kicker"><i class="fa-solid fa-circle-play"></i><span>Live Exam</span></div>
            <div class="phase-arch"></div>
            <h1 class="phase-title">${esc(tr("getReadyTitle", "Get ready"))}</h1>
            <p class="phase-subtitle">${esc(tr("waitingForHost", "Waiting for the host to start the next round."))}</p>
        </div>
    `;
}

function renderGetReady(question) {
    if (state.phase !== PHASES.GET_READY) {
        hideOptions();
        setTimerState(false);
        setQuestionChip(question);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                <div class="phase-kicker"><i class="fa-solid fa-bolt"></i><span>Live mode</span></div>
                <div class="phase-arch"></div>
                <h1 class="phase-title">${esc(tr("getReadyTitle", "Get ready"))}</h1>
                <p class="phase-subtitle">${esc(tr("getReadyBody", "Loading the first question..."))}</p>
            </div>
        `;
        state.phase = PHASES.GET_READY;
    }
    setRoundHint(tr("getReadyBody", "Loading the first question..."));
}

function renderIntro(question) {
    if (state.phase !== PHASES.INTRO) {
        hideOptions();
        setTimerState(false);
        setQuestionChip(question);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                ${buildQuestionCard(
                    question,
                    `
                        <div class="intro-progress">
                                <div class="intro-progress__track">
                                    <div class="intro-progress__meter" data-intro-meter></div>
                                </div>
                                <div class="intro-progress__meta">
                                <span>${esc(
                                    showQuestionsOnDevices()
                                        ? tr("introHint", "Read the question. Answers are about to appear.")
                                        : tr("introHintMainScreen", "Look at the main screen. Answers unlock soon.")
                                )}</span>
                                <span data-intro-countdown></span>
                            </div>
                        </div>
                    `
                )}
            </div>
        `;
        state.phase = PHASES.INTRO;
    }
    updateIntroProgress(question);
    setRoundHint(
        showQuestionsOnDevices()
            ? tr("introHint", "Read the question. Answers are about to appear.")
            : tr("introHintMainScreen", "Look at the main screen. Answers unlock soon.")
    );
}

function updateIntroProgress(question) {
    const meter = UI.phasePanelInner.querySelector("[data-intro-meter]");
    const countdown = UI.phasePanelInner.querySelector("[data-intro-countdown]");
    if (!meter || !countdown) return;

    const readyEndsAt = ts(question.ready_ends_at) || ts(question.started_at);
    const answerStartsAt = ts(question.answer_starts_at);
    const now = nowMs();
    const total = Math.max(1, answerStartsAt - readyEndsAt);
    const elapsed = Math.max(0, Math.min(total, now - readyEndsAt));
    const percent = Math.max(0, Math.min(100, (elapsed / total) * 100));
    meter.style.width = `${percent}%`;

    const seconds = Math.max(1, Math.ceil((answerStartsAt - now) / 1000));
    countdown.textContent = `${tr("introUnlocking", "Answers unlock in")} ${seconds}s`;
}

function renderOptions(question) {
    UI.optionsContainer.innerHTML = "";

    (question.options || []).forEach((option, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `option-btn opt-${index % 6}`;
        button.dataset.id = String(option.id);
        if (state.selectedIds.has(option.id)) {
            button.classList.add("selected");
        }
        button.innerHTML = `
            ${optionMarkerMarkup(option, index)}
            <span class="option-text">${esc(
                showQuestionsOnDevices() ? option.text || "" : tr("optionHiddenBody", "Match this answer on the main screen.")
            )}</span>
        `;
        button.addEventListener("click", () => handleOptionClick(button, option.id));
        UI.optionsContainer.appendChild(button);
    });
}

function renderQuestion(question) {
    if (state.phase !== PHASES.QUESTION) {
        setQuestionChip(question);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                ${buildQuestionCard(question)}
            </div>
        `;
        renderOptions(question);
        UI.optionsShell.style.display = "grid";
        state.phase = PHASES.QUESTION;
    }

    document.querySelectorAll(".option-btn").forEach((button) => {
        button.disabled = state.submitting;
    });
    updateCounter();
    setRoundHint(tr("questionPrompt", "Pick your answer before the timer runs out."));
    const endsAt = ts(question.ends_at);
    setTimerState(true, Math.max(0, endsAt - nowMs()));
}

function renderWaiting(message) {
    if (state.phase !== PHASES.WAITING) {
        hideOptions();
        setTimerState(false);
        setQuestionChip(state.currentQuestion);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                <div class="phase-arch"></div>
                <h1 class="phase-title">${esc(message)}</h1>
                <p class="phase-subtitle">${esc(tr("waitingBody", "Hold tight while the rest of the class answers."))}</p>
                <div class="waiting-progress">
                    <div class="waiting-progress__track">
                        <div class="waiting-progress__meter" data-waiting-meter></div>
                    </div>
                    <div class="waiting-progress__meta">
                        <span data-waiting-count></span>
                    </div>
                </div>
            </div>
        `;
        state.phase = PHASES.WAITING;
    }
    updateWaitingProgress();
    setRoundHint(tr("answerLocked", "Answer locked in"));
}

function renderLocked() {
    if (state.phase !== PHASES.LOCKED) {
        hideOptions();
        setTimerState(false);
        setQuestionChip(state.currentQuestion);
        UI.phasePanelInner.innerHTML = `
            <div class="phase-shell">
                <div class="phase-kicker"><i class="fa-solid fa-hourglass-end"></i><span>Round closed</span></div>
                <div class="phase-arch"></div>
                <h1 class="phase-title">${esc(tr("answerTimeout", "Time is up. Waiting for the round to close."))}</h1>
                <p class="phase-subtitle">${esc(tr("waitingBody", "Hold tight while the rest of the class answers."))}</p>
                <div class="waiting-progress">
                    <div class="waiting-progress__track">
                        <div class="waiting-progress__meter" data-waiting-meter></div>
                    </div>
                    <div class="waiting-progress__meta">
                        <span data-waiting-count></span>
                    </div>
                </div>
            </div>
        `;
        state.phase = PHASES.LOCKED;
    }
    updateWaitingProgress();
    setRoundHint(tr("answerTimeout", "Time is up. Waiting for the round to close."));
}

function updateWaitingProgress() {
    const count = UI.phasePanelInner.querySelector("[data-waiting-count]");
    const meter = UI.phasePanelInner.querySelector("[data-waiting-meter]");
    const total = Math.max(0, Number(state.totalPlayers || 0));
    const answered = Math.max(0, Number(state.answeredCount || 0));
    if (count) {
        if (total > 0) {
            count.textContent = fmt(tr("waitingProgress", "{answered} of {total} answered"), {
                answered,
                total,
            });
        } else {
            count.textContent = tr("waitingBody", "Hold tight while the rest of the class answers.");
        }
    }
    if (meter) {
        const percent = total > 0 ? Math.max(0, Math.min(100, (answered / total) * 100)) : 0;
        meter.style.width = `${percent}%`;
    }
}

function renderResult(payload) {
    clearTicker();
    hideOptions();
    setTimerState(false);
    setQuestionChip(state.currentQuestion);

    const personalResult = getPersonalResult(payload);
    const hasAnswer = Boolean(personalResult);
    const isCorrect = Boolean(personalResult && personalResult.is_correct);
    const title = isCorrect ? tr("resultCorrect", "Correct") : tr("resultIncorrect", "Incorrect");
    const icon = isCorrect ? "fa-check" : "fa-xmark";
    const rankText = hasAnswer && personalResult.answer_rank
        ? ordinal(personalResult.answer_rank)
        : tr("resultNoRank", "No rank");
    const points = hasAnswer ? Number(personalResult.awarded_points || 0) : 0;
    // IMPORTANT: guard against null before Number() — Number(null) === 0 and is
    // "finite", which used to zero every non-answering player's total score at
    // reveal time. Server payloads remain the source of truth; when neither a
    // personal result nor a pending score exists, keep the last known total.
    const personalTotalScore = hasAnswer && personalResult.total_score != null
        ? Number(personalResult.total_score)
        : NaN;
    const pendingScoreValue = state.pendingScore != null ? Number(state.pendingScore) : NaN;
    const totalScore = Number.isFinite(personalTotalScore)
        ? personalTotalScore
        : (Number.isFinite(pendingScoreValue) ? pendingScoreValue : Number(state.player.score) || 0);
    const resultSignature = [
        getRevealKey(payload),
        hasAnswer ? 1 : 0,
        isCorrect ? 1 : 0,
        points,
        totalScore,
        Number(personalResult?.answer_rank || 0),
    ].join(":");

    if (state.phase === PHASES.RESULT && state.resultSignature === resultSignature) {
        return;
    }

    setScore(totalScore);
    state.pendingScore = null;
    state.phase = PHASES.RESULT;
    state.resultSignature = resultSignature;

    const subtitle = hasAnswer
        ? `${tr("resultAnswered", "You answered")} ${rankText}`
        : tr("resultNoAnswer", "No answer submitted");

    UI.phasePanelInner.innerHTML = `
        <div class="result-shell ${isCorrect ? "is-correct" : "is-wrong"}">
            <div class="result-shell__icon"><i class="fa-solid ${icon}"></i></div>
            <h1 class="result-shell__title">${esc(title)}</h1>
            <div class="result-stats">
                <div class="result-stat">
                    <div class="result-stat__label">${esc(tr("resultEarned", "Earned"))}</div>
                    <div class="result-stat__value">${points > 0 ? `+${points}` : "0"}</div>
                </div>
                <div class="result-stat">
                    <div class="result-stat__label">${esc(tr("resultAnswered", "You answered"))}</div>
                    <div class="result-stat__value">${esc(rankText)}</div>
                </div>
            </div>
            <p class="result-shell__subtitle">${esc(subtitle)}</p>
        </div>
    `;

    setRoundHint(isCorrect ? tr("resultCorrect", "Correct") : subtitle);
}

function renderLeaderboard(payload) {
    clearTicker();
    hideOptions();
    setTimerState(false);
    setQuestionChip(state.currentQuestion);

    const revealKey = getRevealKey(payload);
    const currentRows = normalizeTopRows(payload && payload.top).slice(0, LEADERBOARD_LIMIT);
    const previousRows = normalizeTopRows(
        payload && payload.previous_top && payload.previous_top.length ? payload.previous_top : state.lastTop
    );
    const leaderboardSignature = `${revealKey}|${topSignature(previousRows)}|${topSignature(currentRows)}`;

    if (state.phase === PHASES.LEADERBOARD && state.leaderboardSignature === leaderboardSignature) {
        return;
    }

    state.phase = PHASES.LEADERBOARD;
    state.revealPayload = payload;
    state.resultSignature = "";
    state.leaderboardSignature = leaderboardSignature;
    state.finalSignature = "";

    UI.phasePanelInner.innerHTML = `
        <div class="leaderboard-shell">
            <div class="phase-kicker"><i class="fa-solid fa-trophy"></i><span>${esc(tr("scoreboardTopFive", "Top 5 players"))}</span></div>
            <h1 class="leaderboard-shell__title">${esc(tr("scoreboardTitle", "Leaderboard"))}</h1>
            <p class="phase-subtitle">${esc(tr("scoreboardSubtitle", "Updated totals after this round."))}</p>
            <div class="leaderboard-list" id="leaderboardList"></div>
        </div>
    `;

    const list = document.getElementById("leaderboardList");
    if (!list) {
        setStoredTop(payload && payload.top);
        return;
    }

    if (!currentRows.length) {
        list.innerHTML = `<div class="final-row"><span class="final-row__name">${esc(tr("waitingForHost", "Waiting for the host to start the next round."))}</span></div>`;
        setStoredTop(payload && payload.top);
        return;
    }

    const previousRankMap = new Map(previousRows.map((row, index) => [row._key, index + 1]));
    const previousScoreMap = new Map(previousRows.map((row) => [row._key, row.score]));
    const currentRankMap = new Map(currentRows.map((row, index) => [row._key, index + 1]));

    const startRows = currentRows
        .slice()
        .sort((a, b) => {
            const aPrev = previousRankMap.get(a._key) || (100 + (currentRankMap.get(a._key) || 0));
            const bPrev = previousRankMap.get(b._key) || (100 + (currentRankMap.get(b._key) || 0));
            return aPrev - bPrev;
        });

    list.innerHTML = startRows
        .map((row) => {
            const currentRank = currentRankMap.get(row._key) || 0;
            const previousRank = previousRankMap.get(row._key) || 0;
            const movedUpBy = previousRank > 0 && previousRank > currentRank ? previousRank - currentRank : 0;
            const enteredTop = !previousRank;
            const movementLabel = movedUpBy > 0
                ? `↑ ${movedUpBy}`
                : (enteredTop ? "↑" : "");

            return `
                <article
                    class="leaderboard-row ${Number(row.player_id) === Number(state.player.id) ? "is-self" : ""} ${movementLabel ? "is-rising" : ""}"
                    data-player-key="${esc(row._key)}"
                    style="order:${previousRank || (100 + currentRank)}">
                    <div class="leaderboard-row__left">
                        <span class="leaderboard-row__rank" data-rank>${currentRank}</span>
                        <span class="leaderboard-row__avatar">${avatarMarkup(row, 44, "leaderboard-row__avatar-art")}</span>
                        <span class="leaderboard-row__name">${esc(row.nickname)}</span>
                    </div>
                    <div class="leaderboard-row__right">
                        <span class="leaderboard-row__score" data-score-value>${Math.round(row.score)}</span>
                        ${
                            movementLabel
                                ? `<span class="leaderboard-row__movement" aria-hidden="true">${esc(movementLabel)}</span>`
                                : ""
                        }
                    </div>
                </article>
            `;
        })
        .join("");

    const rowElements = new Map(
        Array.from(list.querySelectorAll("[data-player-key]")).map((element) => [element.dataset.playerKey, element])
    );

    const firstRects = new Map(
        Array.from(rowElements.entries()).map(([key, element]) => [key, element.getBoundingClientRect()])
    );

    currentRows.forEach((row, index) => {
        const element = rowElements.get(row._key);
        if (!element) return;
        element.style.order = String(index + 1);
        const rankEl = element.querySelector("[data-rank]");
        if (rankEl) {
            rankEl.textContent = String(index + 1);
        }
    });

    list.offsetHeight;

    const lastRects = new Map(
        Array.from(rowElements.entries()).map(([key, element]) => [key, element.getBoundingClientRect()])
    );

    rowElements.forEach((element, key) => {
        const firstRect = firstRects.get(key);
        const lastRect = lastRects.get(key);
        const deltaY = firstRect && lastRect ? firstRect.top - lastRect.top : 0;
        if (deltaY) {
            element.style.transition = "none";
            element.style.transform = `translateY(${deltaY}px)`;
        }
    });

    list.offsetHeight;

    rowElements.forEach((element) => {
        element.style.transition = "transform 680ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 240ms ease";
        element.style.transform = "translateY(0)";
    });

    currentRows.forEach((row) => {
        const element = rowElements.get(row._key);
        const scoreEl = element?.querySelector("[data-score-value]");
        const previousScore = previousScoreMap.get(row._key);
        if (!scoreEl) return;
        if (Number.isFinite(previousScore) && previousScore !== row.score) {
            animateNumber(scoreEl, previousScore, row.score, 920);
            return;
        }
        scoreEl.textContent = String(Math.round(row.score));
    });

    playLeaderboardSound(revealKey);

    setStoredTop(payload && payload.top);
    setRoundHint(tr("scoreboardTitle", "Leaderboard"));
}

function renderFinal(payload) {
    const finalRows = normalizeTopRows(payload && payload.top);
    const finalSignature = `${String(payload?.finished_at || "")}|${topSignature(finalRows)}`;
    if (state.phase === PHASES.FINAL && state.finalSignature === finalSignature) {
        return;
    }

    clearTicker();
    clearPhaseTimer();
    stopStatePolling();
    hideOptions();
    setTimerState(false);
    setQuestionChip(null);
    state.phase = PHASES.FINAL;
    state.revealPayload = null;
    state.resultSignature = "";
    state.finalSignature = finalSignature;
    state.leaderboardSignature = "";
    playFinalSound(finalSignature || "final");

    const ownFinalRow = finalRows.find((row) => Number(row.player_id) === Number(state.player.id));
    if (ownFinalRow) {
        setScore(ownFinalRow.score);
    }

    const podiumPlaces = finalRows.slice(0, PODIUM_SIZE);
    const others = finalRows.slice(PODIUM_SIZE);
    const suffix = esc(tr("pointsSuffix", "pts"));

    const podiumOrder = [
        podiumPlaces[1] ? { ...podiumPlaces[1], place: 2, slot: "left" } : null,
        podiumPlaces[0] ? { ...podiumPlaces[0], place: 1, slot: "center" } : null,
        podiumPlaces[2] ? { ...podiumPlaces[2], place: 3, slot: "right" } : null,
    ].filter(Boolean);

    const podiumMarkup = podiumOrder.map(player => `
        <div class="final-podium-block final-podium-block--place-${player.place} final-podium-block--slot-${player.slot}">
            <div class="final-podium-card">
                ${player.place === 1 ? '<div class="final-podium-crown">👑</div>' : `<div class="final-podium-medal">${player.place}</div>`}
                <div class="final-podium-avatar">${avatarMarkup(player, player.place === 1 ? 80 : 64, "player-avatar")}</div>
                <div class="final-podium-name">${esc(player.nickname || "Player")}</div>
                <div class="final-podium-score">${Number(player.score || 0)} ${suffix}</div>
            </div>
            <div class="final-podium-stand">
                <div class="final-podium-stand__place">${player.place}</div>
            </div>
        </div>
    `).join("");

    const othersMarkup = others.map((player, index) => `
        <div class="final-row">
            <div class="final-row__meta">
                <span class="final-row__rank">${index + 4}</span>
                ${avatarMarkup(player, 44, "player-avatar")}
                <span class="final-row__name">${esc(player.nickname || "Player")}</span>
            </div>
            <span class="final-row__score">${Number(player.score || 0)} ${suffix}</span>
        </div>
    `).join("");

    UI.phasePanelInner.innerHTML = `
        <div class="final-shell">
            <div class="phase-kicker"><i class="fa-solid fa-flag-checkered"></i><span>${esc(tr("leaderboardTitle", "Top players"))}</span></div>
            <div class="final-shell__trophy">🏆</div>
            <h1 class="phase-title">${esc(tr("finalTitle", "Final results"))}</h1>
            <p class="phase-subtitle">${esc(tr("finalBody", "The live exam is complete."))}</p>
            <div class="final-podium-stage">${podiumMarkup}</div>
            ${others.length ? `<div class="final-others-title">${esc(tr("scoreboardTitle", "Leaderboard"))}</div>` : ""}
            <div class="final-leaderboard">${othersMarkup}</div>
        </div>
    `;
    setStoredTop(finalRows);
    setRoundHint(tr("finalTitle", "Final results"));
}

function startTicker() {
    clearTicker();
    state.ticker = window.setInterval(syncQuestionPhase, 120);
}

function syncQuestionPhase() {
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

function handleOptionClick(button, optionId) {
    unlockAudio();

    if (state.phase !== PHASES.QUESTION || state.submitting || state.currentAnswer) return;

    if (!isMulti(state.currentQuestion)) {
        state.selectedIds = new Set([optionId]);
        document.querySelectorAll(".option-btn").forEach((item) => item.classList.remove("selected"));
        button.classList.add("selected");
        window.setTimeout(() => {
            if (state.phase === PHASES.QUESTION && !state.currentAnswer && !state.submitting) {
                submitAnswer();
            }
        }, 120);
        return;
    }

    const maximum = maxSelect(state.currentQuestion);
    if (state.selectedIds.has(optionId)) {
        state.selectedIds.delete(optionId);
        button.classList.remove("selected");
    } else {
        if (state.selectedIds.size >= maximum) return;
        state.selectedIds.add(optionId);
        button.classList.add("selected");
    }
    updateCounter();
}

function submitAnswer() {
    unlockAudio();

    if (!state.currentQuestion || !state.selectedIds.size || state.submitting || state.currentAnswer) return;

    state.submitting = true;
    disableOptions();
    setRoundHint(tr("answerSending", "Locking in your answer..."));

    const answerStart = ts(state.currentQuestion.answer_starts_at) || ts(state.currentQuestion.started_at) || nowMs();
    const answerMs = Math.max(0, nowMs() - answerStart);

    const payload = {
        type: "answer",
        question_id: state.currentQuestion.id,
        answer_ms: answerMs,
    };

    if (isMulti(state.currentQuestion)) {
        payload.option_ids = Array.from(state.selectedIds);
    } else {
        payload.option_id = Array.from(state.selectedIds)[0];
    }

    try {
        if (playWS && playWS.readyState === WebSocket.OPEN) {
            playWS.send(JSON.stringify(payload));
            return;
        }
        submitAnswerFallback(payload);
    } catch (error) {
        submitAnswerFallback(payload);
    }
}

function applyQuestionState(question, playerAnswer, previousTop) {
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

function applyRevealState(payload) {
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

function applyStateSnapshot(snapshot) {
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

async function fetchInitialState() {
    try {
        const response = await fetch(BOOTSTRAP.stateUrl || `/live/state/${BOOTSTRAP.pin}/`, {
            headers: { Accept: "application/json" },
        });
        if (!response.ok) {
            if (!playWS || playWS.readyState !== WebSocket.OPEN) {
                setConnection("offline");
            }
            if (!state.currentQuestion && state.phase !== PHASES.FINAL) {
                renderIdle();
            }
            return;
        }
        const receivedAtMs = Date.now();
        const snapshot = await response.json();
        updateServerTimeOffset(snapshot, receivedAtMs);
        if (!playWS || playWS.readyState !== WebSocket.OPEN) {
            setConnection("online");
        }
        applyStateSnapshot(snapshot);
    } catch (error) {
        console.error("live player state fetch failed", error);
        if (!playWS || playWS.readyState !== WebSocket.OPEN) {
            setConnection("offline");
        }
        if (!state.currentQuestion && state.phase !== PHASES.FINAL) {
            renderIdle();
        }
    }
}

function stopStatePolling() {
    if (state.pollTimer) {
        window.clearInterval(state.pollTimer);
        state.pollTimer = null;
    }
}

function startStatePolling() {
    if (state.pollTimer) return;
    state.pollTimer = window.setInterval(() => {
        if (!document.hidden && (!playWS || playWS.readyState !== WebSocket.OPEN)) {
            fetchInitialState();
        }
    }, STATE_POLL_INTERVAL_MS);
}

async function submitAnswerFallback(payload) {
    try {
        const response = await fetch(BOOTSTRAP.answerUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-CSRFToken": BOOTSTRAP.csrf,
            },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.message || "Unable to send your answer.");
        }
        handleAnswerSaved(data.answer || {});
        if (data.reveal) {
            applyRevealState(data.reveal);
            return;
        }
        fetchInitialState();
    } catch (error) {
        state.submitting = false;
        renderQuestion(state.currentQuestion);
        setRoundHint(error && error.message ? error.message : "Unable to send your answer.");
    }
}

function handleAnswerSaved(data) {
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

function handleSocketMessage(message) {
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

UI.submitBtn.addEventListener("click", () => {
    if (state.phase === PHASES.QUESTION) {
        submitAnswer();
    }
});

["pointerdown", "touchstart", "keydown"].forEach((eventName) => {
    document.addEventListener(eventName, unlockAudio, { passive: true });
});

renderPlayerIdentity();
applySessionSettings(SESSION_SETTINGS);
renderIdle();
setConnection("connecting");

let _initialFetchDone = false;
const playWS = new WebSocket(wsUrl(`/ws/live/${BOOTSTRAP.pin}/play/`));

playWS.onopen = () => {
    setConnection("online");
    if (!_initialFetchDone) {
        _initialFetchDone = true;
        fetchInitialState();
    }
};

playWS.onclose = () => {
    setConnection("offline");
};

playWS.onerror = () => {
    setConnection("offline");
};

playWS.onmessage = (event) => {
    try {
        handleSocketMessage(JSON.parse(event.data));
    } catch (error) {
        console.error("live player message parse failed", error);
    }
};

startStatePolling();
if (!_initialFetchDone) {
    _initialFetchDone = true;
    fetchInitialState();
}

window.addEventListener("beforeunload", () => {
    stopStatePolling();
    clearTicker();
    clearPhaseTimer();
    if (playWS && playWS.readyState === WebSocket.OPEN) {
        playWS.close();
    }
});
