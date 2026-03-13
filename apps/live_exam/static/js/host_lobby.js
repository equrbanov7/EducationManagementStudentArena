const $ = id => document.getElementById(id);

const UI = {
    startBtn: $("startBtn"),
    presentBtn: $("presentBtn"),
    revealBtn: $("revealBtn"),
    nextBtn: $("nextBtn"),
    finishBtn: $("finishBtn"),
    questionCount: $("questionCount"),
    autoMode: $("autoMode"),
    gameState: $("gameState"),
    lobbyHeader: $("lobbyHeader"),
    gameArea: $("gameArea"),
    presentationStage: $("presentationStage"),
    presentationContent: $("presentationContent"),
    playersSection: $("playersSection"),
    playersCount: $("playersCount"),
    playersList: $("playersList"),
    finalPodium: $("finalPodium"),
    podiumStage: $("podiumStage"),
    othersList: $("othersList"),
    confetti: $("confetti"),
    progressBox: $("progressBox"),
    answeredText: $("answeredText"),
    debugBtn: $("debugBtn"),
    debugLog: $("debugLog"),
    reactionOverlay: $("hostReactionOverlay"),
};

const PHASES = {
    IDLE: "idle",
    INTRO: "intro",
    COUNTDOWN: "countdown",
    QUESTION: "question",
    ANSWERS: "answers",
    REVEAL: "reveal",
    SCOREBOARD: "scoreboard",
};

const AudioCtor = window.AudioContext || window.webkitAudioContext;

const state = {
    sessionState: "lobby",
    phase: PHASES.IDLE,
    phaseSignature: "",
    questionKey: "",
    revealKey: "",
    currentQuestion: null,
    currentReveal: null,
    questionPlan: null,
    answeredCount: 0,
    totalPlayers: 0,
    countdownValue: null,
    frameId: 0,
    autoRevealTimeout: 0,
    autoNextTimeout: 0,
    audioContext: null,
    lastIntroSoundKey: "",
    lastCountdownSoundKey: "",
};

const I18N = window.LIVE_EXAM_HOST_I18N || {};
const tr = (key, fallback) => I18N[key] || fallback;
const fmt = (template, values) =>
    String(template || "").replace(/\{(\w+)\}/g, (_, key) => (values && key in values ? values[key] : `{${key}}`));
const esc = text => {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
};
const wsUrl = path => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${path}`;
const toMs = value => {
    const parsed = value ? new Date(value).getTime() : 0;
    return Number.isFinite(parsed) ? parsed : 0;
};
const questionKey = question => `${question?.id || "0"}:${question?.started_at || ""}`;
const revealKey = payload => `${payload?.question_id || "0"}:${payload?.revealed_at || ""}`;
const answerWord = count => tr(count === 1 ? "answersSingular" : "answersPlural", count === 1 ? "Answer" : "Answers");
const progressLabel = question => `${Number(question?.index || 0)} of ${Number(question?.total || 0)}`;
const avatarMarkup = (player, size, className = "") =>
    (window.LiveAvatarRenderer || { renderAvatarMarkup: () => "" }).renderAvatarMarkup(player || {}, {
        size,
        className,
        interactive: false,
    });

let debugOn = false;
const logs = [];
let presenterWindowRef = null;

function log(message) {
    console.log("[HOST]", message);
    if (!UI.debugLog) return;
    logs.unshift(`> ${new Date().toLocaleTimeString()} ${message}`);
    if (logs.length > 100) logs.length = 100;
    UI.debugLog.textContent = logs.join("\n");
}

UI.debugBtn?.addEventListener("click", () => {
    debugOn = !debugOn;
    UI.debugBtn.innerHTML = `<i class="fas fa-terminal"></i> ${tr("debugLabel", "Debug")} ${debugOn ? "▾" : "▸"}`;
    UI.debugLog.style.display = debugOn ? "block" : "none";
});

function clearPhaseLoop() {
    if (state.frameId) {
        cancelAnimationFrame(state.frameId);
        state.frameId = 0;
    }
}

function clearAutoTimers() {
    clearTimeout(state.autoRevealTimeout);
    clearTimeout(state.autoNextTimeout);
    state.autoRevealTimeout = 0;
    state.autoNextTimeout = 0;
}

function presenterUrl() {
    if (!CONFIG?.urls?.present) return "";
    return `${CONFIG.urls.present}${CONFIG.urls.present.includes("?") ? "&" : "?"}autofs=1`;
}

function openPresenterWindow() {
    if (CONFIG.presentationOnly || !CONFIG?.urls?.present) return null;
    try {
        presenterWindowRef = window.open(presenterUrl(), `liveExamPresentation_${CONFIG.pin}`);
        if (presenterWindowRef) {
            presenterWindowRef.focus();
            window.setTimeout(() => {
                try {
                    const root = presenterWindowRef?.document?.documentElement;
                    if (root && presenterWindowRef.document.visibilityState === "visible" && root.requestFullscreen) {
                        root.requestFullscreen({ navigationUI: "hide" }).catch(() => {});
                    }
                } catch (error) {
                    log(`Presenter fullscreen skipped: ${error.message || error}`);
                }
            }, 120);
        }
        return presenterWindowRef;
    } catch (error) {
        log(`Presenter window error: ${error.message || error}`);
        return null;
    }
}

async function tryEnterFullscreen() {
    if (!CONFIG.presentationOnly || !CONFIG.autoFullscreen) return;
    const root = document.documentElement;
    if (!root || document.fullscreenElement || !root.requestFullscreen) return;
    try {
        await root.requestFullscreen({ navigationUI: "hide" });
    } catch (error) {
        log(`Fullscreen request skipped: ${error.message || error}`);
    }
}

function getAudioContext() {
    if (!AudioCtor) return null;
    if (!state.audioContext) {
        state.audioContext = new AudioCtor();
    }
    return state.audioContext;
}

function unlockAudio() {
    const context = getAudioContext();
    if (!context || context.state !== "suspended") return;
    context.resume().catch(() => {});
}

function playTone(context, config) {
    const oscillator = context.createOscillator();
    const gainNode = context.createGain();
    const startTime = config.startTime;
    const duration = config.duration;

    oscillator.type = config.type || "triangle";
    oscillator.frequency.setValueAtTime(config.frequency, startTime);
    if (config.endFrequency) {
        oscillator.frequency.exponentialRampToValueAtTime(Math.max(20, config.endFrequency), startTime + duration);
    }

    gainNode.gain.setValueAtTime(0.0001, startTime);
    gainNode.gain.exponentialRampToValueAtTime(config.gain || 0.04, startTime + 0.02);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, startTime + duration);

    oscillator.connect(gainNode);
    gainNode.connect(context.destination);
    oscillator.start(startTime);
    oscillator.stop(startTime + duration + 0.02);
}

function playIntroSound(key) {
    if (!CONFIG.presentationOnly || state.lastIntroSoundKey === key) return;
    const context = getAudioContext();
    if (!context) return;

    const start = () => {
        const base = context.currentTime + 0.01;
        playTone(context, {
            startTime: base,
            duration: 0.22,
            frequency: 220,
            endFrequency: 320,
            gain: 0.045,
            type: "triangle",
        });
        playTone(context, {
            startTime: base + 0.16,
            duration: 0.28,
            frequency: 320,
            endFrequency: 430,
            gain: 0.05,
            type: "sine",
        });
        state.lastIntroSoundKey = key;
    };

    if (context.state === "suspended") {
        context.resume().then(start).catch(() => {});
        return;
    }
    start();
}

function playCountdownSound(key) {
    if (!CONFIG.presentationOnly || state.lastCountdownSoundKey === key) return;
    const context = getAudioContext();
    if (!context) return;

    const start = () => {
        const base = context.currentTime + 0.01;
        playTone(context, {
            startTime: base,
            duration: 0.12,
            frequency: 520,
            endFrequency: 420,
            gain: 0.04,
            type: "square",
        });
        state.lastCountdownSoundKey = key;
    };

    if (context.state === "suspended") {
        context.resume().then(start).catch(() => {});
        return;
    }
    start();
}

function schedulePhaseLoop(fn) {
    clearPhaseLoop();
    const tick = () => {
        fn();
        if (state.frameId) {
            state.frameId = requestAnimationFrame(tick);
        }
    };
    state.frameId = requestAnimationFrame(tick);
}

function stateLabel(value) {
    if (value === "question") return tr("stateQuestion", "Question");
    if (value === "reveal") return tr("stateReveal", "Reveal");
    if (value === "finished") return tr("stateFinished", "Finished");
    return tr("stateLobby", "Lobby");
}

function setPresentationMarkup(phase, signature, markup) {
    if (!UI.presentationStage || !UI.presentationContent) return;
    UI.presentationStage.dataset.phase = phase;
    if (state.phaseSignature === signature && state.phase === phase) {
        return;
    }
    state.phase = phase;
    state.phaseSignature = signature;
    UI.presentationContent.innerHTML = markup;
}

function setSessionState(nextState) {
    state.sessionState = nextState;
    UI.gameState.textContent = stateLabel(nextState);

    UI.startBtn.disabled = nextState !== "lobby";
    UI.revealBtn.disabled = nextState !== "question";
    UI.nextBtn.disabled = nextState !== "reveal";

    const isLobby = nextState === "lobby";
    const isPlay = nextState === "question" || nextState === "reveal";
    const isFinished = nextState === "finished";

    UI.lobbyHeader.style.display = CONFIG.presentationOnly ? "none" : (isLobby ? "block" : "none");
    UI.playersSection.style.display = CONFIG.presentationOnly ? "none" : (isLobby ? "block" : "none");
    UI.gameArea.style.display = CONFIG.presentationOnly ? "block" : (isPlay ? "block" : "none");
    UI.finalPodium.style.display = isFinished ? "grid" : "none";
    UI.progressBox.style.display = !CONFIG.presentationOnly && nextState === "question" ? "flex" : "none";

    if (isLobby) {
        clearPhaseLoop();
        clearAutoTimers();
        renderIdleStage();
    }

    log(fmt(tr("stateLog", "State: {state}"), { state: stateLabel(nextState) }));
}

function renderIdleStage() {
    setPresentationMarkup(
        PHASES.IDLE,
        "idle",
        `
            <section class="present-view present-view--center">
                <h1 class="stage-hero stage-hero--wordmark">${esc(tr("introTitle", "Quiz"))}</h1>
                <p class="stage-copy">${esc(tr("introSubtitle", "Get ready for the next round"))}</p>
            </section>
        `
    );
}

function updateAnsweredCounter() {
    const answered = Number(state.answeredCount || 0);
    const total = Number(state.totalPlayers || 0);
    UI.answeredText.textContent = `${answered} / ${total}`;

    const counter = $("answerCounterValue");
    const counterNumber = $("answerCounterNumber");
    const counterLabel = $("answerCounterLabel");
    const subline = $("answerCounterSubline");
    if (counter) {
        counter.textContent = `${answered} ${answerWord(answered)}`;
    }
    if (counterNumber) {
        counterNumber.textContent = `${answered}`;
    }
    if (counterLabel) {
        counterLabel.textContent = answerWord(answered);
    }
    if (subline) {
        subline.textContent = fmt(tr("playersAnswered", "{answered} answered"), { answered });
    }
}

function updateTimerBadge(nowMs) {
    const value = $("answerTimerValue");
    const badge = $("answerTimerBadge");
    if (!value || !badge || !state.questionPlan) return;
    const leftSeconds = Math.max(0, Math.ceil((state.questionPlan.endsAt - nowMs) / 1000));
    value.textContent = `${leftSeconds}`;
    badge.classList.toggle("is-warning", leftSeconds <= 10 && leftSeconds > 5);
    badge.classList.toggle("is-danger", leftSeconds <= 5);
}

function updateQuestionIntroProgress(nowMs) {
    const fill = $("questionOnlyBarFill");
    if (!fill || !state.questionPlan) return;
    const start = Number(state.questionPlan.countdownEnd || 0);
    const end = Number(state.questionPlan.answerStart || 0);
    const duration = Math.max(1, end - start);
    const progress = Math.max(0, Math.min(1, (nowMs - start) / duration));
    fill.style.width = `${Math.round(progress * 100)}%`;
}

function buildQuestionPlan(question) {
    const startedAt = toMs(question?.started_at);
    const getReadyMs = Math.max(0, Number(question?.get_ready_duration_ms || 0));
    const introMs = Math.max(0, Number(question?.intro_duration_ms || 0));
    const readyEndsAt = toMs(question?.ready_ends_at) || (startedAt + getReadyMs);
    const answerStart = toMs(question?.answer_starts_at) || (readyEndsAt + introMs);
    const endsAt = toMs(question?.ends_at);
    const hasCountdown = getReadyMs > 0;
    const quizDuration = hasCountdown ? Math.max(850, Math.min(1000, getReadyMs - 2200)) : 0;
    const countdownStart = hasCountdown ? startedAt + quizDuration : readyEndsAt;
    const countdownEnd = hasCountdown ? readyEndsAt : readyEndsAt;

    return {
        startedAt,
        quizEnd: hasCountdown ? startedAt + quizDuration : startedAt,
        countdownStart,
        countdownEnd,
        readyEndsAt,
        answerStart,
        endsAt,
        hasCountdown,
        getReadyMs,
        introMs,
    };
}

function distributionLookup(payload) {
    const counts = new Map();
    const rows = payload?.distribution?.counts || [];
    rows.forEach(row => {
        counts.set(Number(row.option_id || 0), Number(row.count || 0));
    });
    return {
        counts,
        totalAnswers: Number(payload?.distribution?.total_answers || 0),
    };
}

function renderIntroStage() {
    playIntroSound(`${state.questionKey}:quiz`);
    setPresentationMarkup(
        PHASES.INTRO,
        `${state.questionKey}:${PHASES.INTRO}`,
        `
            <section class="present-view present-view--center">
                <h1 class="stage-hero stage-hero--wordmark">${esc(tr("introTitle", "Quiz"))}</h1>
            </section>
        `
    );
}

function renderCountdownStage(question, number) {
    playCountdownSound(`${state.questionKey}:${number}`);
    setPresentationMarkup(
        PHASES.COUNTDOWN,
        `${state.questionKey}:${PHASES.COUNTDOWN}:${number}`,
        `
            <section class="present-view present-view--center">
                <div class="countdown-number" aria-label="${esc(
                    fmt(tr("countdownNumberLabel", "Round starts in {value}"), { value: number })
                )}">${number}</div>
            </section>
        `
    );
}

function renderQuestionOnlyStage(question) {
    setPresentationMarkup(
        PHASES.QUESTION,
        `${state.questionKey}:${PHASES.QUESTION}`,
        `
            <section class="present-view present-view--quiz">
                <div class="quiz-shell quiz-shell--question">
                    <div class="quiz-progress">${esc(progressLabel(question))}</div>
                    <div class="question-card question-card--solo">
                        <h2 class="question-card__title">${esc(question?.text || "")}</h2>
                    </div>
                    <div class="question-only-bar" aria-hidden="true">
                        <span id="questionOnlyBarFill"></span>
                    </div>
                </div>
            </section>
        `
    );
}

function optionTone(index) {
    return ["red", "blue", "yellow", "green"][index % 4];
}

function answerOptionMarkup(option, index) {
    return `
        <article class="host-option host-option--${optionTone(index)}">
            <div class="host-option__main">
                <span class="host-option__label">${esc(option?.label || String.fromCharCode(65 + index))}</span>
                <span class="host-option__text">${esc(option?.text || "")}</span>
            </div>
        </article>
    `;
}

function renderAnswersStage(question) {
    setPresentationMarkup(
        PHASES.ANSWERS,
        `${state.questionKey}:${PHASES.ANSWERS}`,
        `
            <section class="present-view present-view--quiz">
                <div class="quiz-shell">
                    <div class="quiz-progress">${esc(progressLabel(question))}</div>
                    <div class="question-card">
                        <h2 class="question-card__title">${esc(question?.text || "")}</h2>
                    </div>
                    <div id="answerTimerBadge" class="quiz-orb quiz-orb--timer">
                        <strong id="answerTimerValue">0</strong>
                        <span>${esc(tr("secondsLabel", "seconds"))}</span>
                    </div>
                    <div class="quiz-orb quiz-orb--counter">
                        <strong id="answerCounterNumber">0</strong>
                        <span id="answerCounterLabel">${esc(answerWord(0))}</span>
                    </div>
                </div>
                <div class="host-options-grid host-options-grid--kahoot">
                    ${(question?.options || []).map(answerOptionMarkup).join("")}
                </div>
            </section>
        `
    );

    updateAnsweredCounter();
}

function revealOptionMarkup(option, index, distribution, correctOptionIds) {
    const optionId = Number(option?.id || 0);
    const isCorrect = correctOptionIds.includes(optionId);

    return `
        <article class="host-option host-option--${optionTone(index)} is-reveal ${isCorrect ? "is-correct" : "is-wrong"}">
            <div class="host-option__main">
                <span class="host-option__label">${esc(option?.label || String.fromCharCode(65 + index))}</span>
                <span class="host-option__text">${esc(option?.text || "")}</span>
                <span class="host-option__verdict">${isCorrect ? "✓" : "✕"}</span>
            </div>
        </article>
    `;
}

function distributionBarMarkup(option, index, distribution, correctOptionIds) {
    const optionId = Number(option?.id || 0);
    const count = Number(distribution.counts.get(optionId) || 0);
    const totalAnswers = Math.max(0, Number(distribution.totalAnswers || 0));
    const ratio = totalAnswers > 0 ? Math.round((count / totalAnswers) * 100) : 0;
    const isCorrect = correctOptionIds.includes(optionId);

    return `
        <div class="distribution-bar distribution-bar--${optionTone(index)} ${isCorrect ? "is-correct" : ""}">
            <div class="distribution-bar__meta">
                <div class="distribution-bar__label-wrap">
                    <span class="distribution-bar__label">${esc(option?.label || String.fromCharCode(65 + index))}</span>
                    <span class="distribution-bar__answer">${esc(option?.text || "")}</span>
                </div>
                <div class="distribution-bar__stats">
                    <span>${count}</span>
                    <span>${ratio}%</span>
                    ${isCorrect ? '<span class="distribution-bar__correct">✓</span>' : ""}
                </div>
            </div>
            <div class="distribution-bar__track" aria-hidden="true">
                <span style="width:${ratio}%"></span>
            </div>
        </div>
    `;
}

function renderRevealStage(question, payload) {
    const distribution = distributionLookup(payload);
    const correctOptionIds = (payload?.correct_option_ids || []).map(value => Number(value));
    const answeredSummary = fmt(tr("playersAnswered", "{answered} answered"), { answered: distribution.totalAnswers });
    const noAnswersNote =
        distribution.totalAnswers > 0
            ? `<div class="distribution-note">${esc(answeredSummary)}</div>`
            : `<div class="distribution-note">${esc(tr("distributionNoAnswers", "No answers were submitted this round."))}</div>`;

    setPresentationMarkup(
        PHASES.REVEAL,
        `${state.revealKey}:${PHASES.REVEAL}`,
        `
            <section class="present-view present-view--quiz">
                <div class="quiz-shell quiz-shell--reveal">
                    <div class="quiz-progress">${esc(progressLabel(question))}</div>
                    <div class="question-card question-card--reveal">
                        <h2 class="question-card__title">${esc(question?.text || "")}</h2>
                    </div>
                </div>
                ${noAnswersNote}
                <div class="distribution-chart">
                    ${(question?.options || [])
                        .map((option, index) => distributionBarMarkup(option, index, distribution, correctOptionIds))
                        .join("")}
                </div>
                <div class="host-options-grid host-options-grid--kahoot host-options-grid--reveal">
                    ${(question?.options || [])
                        .map((option, index) => revealOptionMarkup(option, index, distribution, correctOptionIds))
                        .join("")}
                </div>
            </section>
        `
    );
}

function movementBadge(player, index, previousTop) {
    const previousIndex = (previousTop || []).findIndex(row => Number(row.player_id) === Number(player.player_id));
    if (previousIndex === -1) {
        return `<span class="scoreboard-row__movement scoreboard-row__movement--new">★ ${esc(
            tr("scoreboardNewEntry", "New in top 5")
        )}</span>`;
    }

    const moved = previousIndex - index;
    if (moved > 0) {
        return `<span class="scoreboard-row__movement">↑ ${moved}</span>`;
    }

    return "";
}

function renderScoreboardStage(payload) {
    const previousTop = payload?.previous_top || [];
    const rows = (payload?.top || []).slice(0, 5);

    setPresentationMarkup(
        PHASES.SCOREBOARD,
        `${state.revealKey}:${PHASES.SCOREBOARD}`,
        `
            <section class="present-view present-view--scoreboard">
                <div class="scoreboard-stage__header">
                    <div class="stage-pill">${esc(tr("scoreboardTitle", "Scoreboard"))}</div>
                    <h2 class="stage-title">${esc(tr("scoreboardSubtitle", "Top 5 players"))}</h2>
                </div>
                <div class="scoreboard-list">
                    ${rows
                        .map(
                            (player, index) => `
                                <article class="scoreboard-row ${index === 0 ? "is-first" : ""}">
                                    <div class="scoreboard-row__left">
                                        <div class="scoreboard-row__rank">${index + 1}</div>
                                        <div class="scoreboard-row__avatar">${avatarMarkup(
                                            player,
                                            58,
                                            "host-avatar host-avatar--scoreboard"
                                        )}</div>
                                        <div class="scoreboard-row__meta">
                                            <div class="scoreboard-row__name">${esc(player.nickname || "")}</div>
                                            ${movementBadge(player, index, previousTop)}
                                        </div>
                                    </div>
                                    <div class="scoreboard-row__score">${Number(player.score || 0)}</div>
                                </article>
                            `
                        )
                        .join("")}
                </div>
            </section>
        `
    );
}

function syncQuestionPresentation() {
    if (state.sessionState !== "question" || !state.currentQuestion || !state.questionPlan) {
        clearPhaseLoop();
        return;
    }

    const now = Date.now();
    const plan = state.questionPlan;

    if (plan.hasCountdown && now < plan.quizEnd) {
        renderIntroStage();
    } else if (plan.hasCountdown && now < plan.countdownEnd && plan.countdownEnd > plan.countdownStart) {
        const remainingSeconds = Math.max(1, Math.ceil((plan.countdownEnd - now) / 1000));
        const nextValue = Math.min(3, remainingSeconds);
        if (state.countdownValue !== nextValue) {
            state.countdownValue = nextValue;
            renderCountdownStage(state.currentQuestion, nextValue);
        }
    } else if (now < plan.answerStart) {
        renderQuestionOnlyStage(state.currentQuestion);
        updateQuestionIntroProgress(now);
    } else {
        renderAnswersStage(state.currentQuestion);
        updateAnsweredCounter();
        updateTimerBadge(now);
    }
}

function syncRevealPresentation() {
    if (state.sessionState !== "reveal" || !state.currentReveal) {
        clearPhaseLoop();
        return;
    }

    const leaderboardStartsAt = toMs(state.currentReveal.leaderboard_starts_at);
    const now = Date.now();

    if (leaderboardStartsAt && now >= leaderboardStartsAt) {
        renderScoreboardStage(state.currentReveal);
    } else {
        renderRevealStage(state.currentQuestion, state.currentReveal);
    }
}

function scheduleAutoReveal(question) {
    clearTimeout(state.autoRevealTimeout);
    if (CONFIG.presentationOnly || !UI.autoMode.checked || !question?.ends_at) return;
    const ms = Math.max(0, toMs(question.ends_at) - Date.now());
    state.autoRevealTimeout = setTimeout(() => {
        if (state.sessionState === "question") {
            UI.revealBtn.click();
        }
    }, ms + 180);
}

function scheduleAutoNext(payload) {
    clearTimeout(state.autoNextTimeout);
    if (CONFIG.presentationOnly || !UI.autoMode.checked || !payload?.next_question_at) return;
    const ms = Math.max(0, toMs(payload.next_question_at) - Date.now());
    state.autoNextTimeout = setTimeout(() => {
        if (state.sessionState === "reveal") {
            UI.nextBtn.click();
        }
    }, ms + 120);
}

function applyQuestionState(question, answeredCount, totalPlayers) {
    if (!question) return;

    state.totalPlayers = Number(totalPlayers || state.totalPlayers || 0);
    state.answeredCount = Number(answeredCount || 0);
    state.currentQuestion = question;
    state.currentReveal = null;
    state.questionPlan = buildQuestionPlan(question);

    const nextKey = questionKey(question);
    const shouldRestart = state.questionKey !== nextKey || state.sessionState !== "question";
    state.questionKey = nextKey;
    state.countdownValue = null;

    setSessionState("question");
    updateAnsweredCounter();
    scheduleAutoReveal(question);

    if (shouldRestart) {
        state.phaseSignature = "";
        schedulePhaseLoop(syncQuestionPresentation);
    } else {
        syncQuestionPresentation();
    }
}

function applyRevealState(payload, question) {
    if (!payload) return;

    if (question) {
        state.currentQuestion = question;
    }
    state.currentReveal = payload;

    const nextKey = revealKey(payload);
    const shouldRestart = state.revealKey !== nextKey || state.sessionState !== "reveal";
    state.revealKey = nextKey;

    clearTimeout(state.autoRevealTimeout);
    setSessionState("reveal");
    scheduleAutoNext(payload);

    if (shouldRestart) {
        state.phaseSignature = "";
        schedulePhaseLoop(syncRevealPresentation);
    } else {
        syncRevealPresentation();
    }
}

function renderPodium(top) {
    UI.confetti.innerHTML = "";
    const othersSection = UI.othersList?.closest(".others-section");
    const colors = ["#fbbf24", "#fb7185", "#38bdf8", "#34d399", "#a855f7", "#f97316", "#fde047"];
    const appendConfetti = (variant, styles) => {
        const piece = document.createElement("div");
        piece.className = `confetti-piece ${variant}`;
        Object.entries(styles).forEach(([key, value]) => {
            piece.style.setProperty(key, value);
        });
        UI.confetti.appendChild(piece);
    };

    for (let index = 0; index < 26; index += 1) {
        appendConfetti("confetti-piece--side-left", {
            "--color": colors[index % colors.length],
            "--size": `${8 + Math.random() * 10}px`,
            "--delay": `${4.2 + Math.random() * 0.6}s`,
            "--duration": `${1.6 + Math.random() * 0.8}s`,
            "--burst-x": `${180 + Math.random() * 280}px`,
            "--burst-y": `${-240 + Math.random() * 420}px`,
            "--spin": `${360 + Math.random() * 540}deg`,
            "--origin-y": `${-110 + Math.random() * 220}px`,
            "--shape-radius": Math.random() > 0.45 ? "50%" : "3px",
        });
        appendConfetti("confetti-piece--side-right", {
            "--color": colors[(index + 2) % colors.length],
            "--size": `${8 + Math.random() * 10}px`,
            "--delay": `${4.2 + Math.random() * 0.6}s`,
            "--duration": `${1.6 + Math.random() * 0.8}s`,
            "--burst-x": `${-180 - Math.random() * 280}px`,
            "--burst-y": `${-240 + Math.random() * 420}px`,
            "--spin": `${-360 - Math.random() * 540}deg`,
            "--origin-y": `${-110 + Math.random() * 220}px`,
            "--shape-radius": Math.random() > 0.45 ? "50%" : "3px",
        });
    }

    for (let index = 0; index < 62; index += 1) {
        appendConfetti("confetti-piece--top", {
            "--color": colors[(index + 4) % colors.length],
            "--size": `${7 + Math.random() * 9}px`,
            "--delay": `${4.7 + Math.random() * 1.5}s`,
            "--duration": `${3 + Math.random() * 1.6}s`,
            "--left": `${6 + Math.random() * 88}%`,
            "--drift-x": `${-110 + Math.random() * 220}px`,
            "--drop-rotation": `${540 + Math.random() * 720}deg`,
            "--shape-radius": Math.random() > 0.4 ? "50%" : "3px",
        });
    }

    UI.podiumStage.innerHTML = "";
    const podiumTop = {
        1: top[0] ? { ...top[0], place: 1, slot: "center" } : null,
        2: top[1] ? { ...top[1], place: 2, slot: "left" } : null,
        3: top[2] ? { ...top[2], place: 3, slot: "right" } : null,
    };
    const riseDelays = { 3: 0.35, 2: 2.35, 1: 4.35 };
    const celebrationDelays = { 3: 1.2, 2: 3.2, 1: 5.2 };
    const suffix = esc(tr("pointsSuffix", "pts"));

    [3, 2, 1].forEach(place => {
        const player = podiumTop[place];
        if (!player) return;

        const block = document.createElement("section");
        block.className = `podium-block podium-block--slot-${player.slot} podium-block--place-${player.place}`;
        block.style.setProperty("--podium-rise-delay", `${riseDelays[player.place]}s`);
        block.style.setProperty("--podium-celebrate-delay", `${celebrationDelays[player.place]}s`);
        block.dataset.accessory = player.accessory_key || player.accessoryKey || "accessory_none";
        block.innerHTML = `
            <div class="podium-card">
                <div class="podium-card__shine"></div>
                ${player.place === 1 ? '<div class="podium-crown-badge">👑</div>' : `<div class="podium-medal-badge">${player.place}</div>`}
                <div class="podium-avatar-shell">
                    <span class="podium-avatar-ring"></span>
                    <span class="podium-avatar-spark podium-avatar-spark--left"></span>
                    <span class="podium-avatar-spark podium-avatar-spark--right"></span>
                    ${avatarMarkup(
                        player,
                        player.place === 1 ? 132 : player.place === 2 ? 116 : 108,
                        "podium-avatar-live host-avatar"
                    )}
                </div>
                <div class="podium-name">${esc(player.nickname || "")}</div>
                <div class="podium-score">${Number(player.score || 0)} <span>${suffix}</span></div>
            </div>
            <div class="podium-stand">
                <div class="podium-stand__glow"></div>
                <div class="podium-stand__place">${player.place}</div>
            </div>
        `;
        UI.podiumStage.appendChild(block);
    });

    UI.othersList.innerHTML = "";
    const others = top.slice(3, 10);
    if (othersSection) {
        othersSection.style.display = others.length ? "" : "none";
    }
    others.forEach((player, index) => {
        const row = document.createElement("div");
        row.className = "other-row";
        row.style.setProperty("--other-delay", `${6.35 + index * 0.12}s`);
        row.innerHTML = `
            <div class="other-info">
                <span class="other-rank">${index + 4}</span>
                ${avatarMarkup(player, 44, "other-avatar-live host-avatar")}
                <span class="other-name">${esc(player.nickname || "")}</span>
            </div>
            <span class="other-score">${Number(player.score || 0)}</span>
        `;
        UI.othersList.appendChild(row);
    });
}

function applyStateSnapshot(snapshot) {
    if (!snapshot || !snapshot.ok) return;

    if (snapshot.total_players != null) {
        state.totalPlayers = Number(snapshot.total_players || 0);
    }
    if (snapshot.answered_count != null) {
        state.answeredCount = Number(snapshot.answered_count || 0);
        updateAnsweredCounter();
    }

    if (snapshot.state === "question" && snapshot.question) {
        applyQuestionState(snapshot.question, snapshot.answered_count, snapshot.total_players);
        return;
    }

    if (snapshot.state === "reveal" && snapshot.question) {
        applyRevealState(
            {
                question_id: snapshot.question.id,
                correct_option_ids: snapshot.correct_option_ids || [],
                distribution: snapshot.distribution || { total_answers: 0, counts: [] },
                results: snapshot.results || [],
                top: snapshot.top || [],
                previous_top: snapshot.previous_top || [],
                revealed_at: snapshot.revealed_at,
                leaderboard_starts_at: snapshot.leaderboard_starts_at,
                next_question_at: snapshot.next_question_at,
            },
            snapshot.question
        );
        return;
    }

    if (snapshot.state === "finished") {
        clearPhaseLoop();
        clearAutoTimers();
        setSessionState("finished");
        renderPodium(snapshot.top || []);
        return;
    }

    setSessionState("lobby");
}

async function post(url, data = null) {
    try {
        const options = {
            method: "POST",
            headers: {
                "X-CSRFToken": CONFIG.csrf,
            },
        };
        if (data) options.body = data;
        const response = await fetch(url, options);
        const payload = await response.json();
        if (payload?.ok) {
            await syncState();
        }
        return payload;
    } catch (error) {
        log(fmt(tr("postError", "POST error: {message}"), { message: error.message || "" }));
        return { ok: false };
    }
}

async function syncState() {
    try {
        const response = await fetch(CONFIG.urls.state, {
            headers: { Accept: "application/json" },
        });
        if (!response.ok) {
            log(`State sync failed: ${response.status}`);
            return null;
        }
        const snapshot = await response.json();
        applyStateSnapshot(snapshot);
        return snapshot;
    } catch (error) {
        log(fmt(tr("playMessageError", "Play message error: {message}"), { message: error.message || "" }));
        return null;
    }
}

function spawnReaction(eventData) {
    if (!UI.reactionOverlay) return;
    const meta = (window.LiveAvatarCatalog || {}).reactions?.[eventData?.reaction_key] || {};
    const burst = document.createElement("div");
    burst.className = "host-reaction-burst";
    burst.innerHTML = `
        <span class="host-reaction-burst__emoji">${meta.emoji || eventData?.emoji || "✨"}</span>
        <span class="host-reaction-burst__name">${esc(eventData?.player?.nickname || "")}</span>
    `;
    burst.style.left = `${16 + Math.random() * 68}%`;
    burst.style.setProperty("--reaction-drift", `${-26 + Math.random() * 52}px`);
    UI.reactionOverlay.appendChild(burst);
    setTimeout(() => burst.remove(), 2300);
}

const lobbyWS = new WebSocket(wsUrl(`/ws/live/${CONFIG.pin}/lobby/`));
lobbyWS.onopen = () => log(tr("wsLobbyOpen", "Lobby WS open"));
lobbyWS.onclose = () => log(tr("wsLobbyClosed", "Lobby WS closed"));
lobbyWS.onmessage = event => {
    try {
        const message = JSON.parse(event.data);
        const data = message.data || message;

        if (data.type === "lobby_state") {
            state.totalPlayers = Number(data.count || 0);
            UI.playersCount.textContent = state.totalPlayers;
            updateAnsweredCounter();

            UI.playersList.innerHTML = "";
            (data.players || []).forEach(player => {
                const chip = document.createElement("div");
                chip.className = "player-chip";
                chip.innerHTML = `
                    <div class="avatar">${avatarMarkup(player, 54, "host-avatar host-avatar--chip")}</div>
                    <div class="name">${esc(player.nickname || "")}</div>
                `;
                UI.playersList.appendChild(chip);
            });
            return;
        }

        if (data.type === "reaction_event") {
            spawnReaction(data);
        }
    } catch (error) {
        log(fmt(tr("lobbyMessageError", "Lobby message error: {message}"), { message: error.message || "" }));
    }
};

const playWS = new WebSocket(wsUrl(`/ws/live/${CONFIG.pin}/play/`));
playWS.onopen = async () => {
    log(tr("wsPlayOpen", "Play WS open"));
    await syncState();
};
playWS.onclose = () => log(tr("wsPlayClosed", "Play WS closed"));
playWS.onmessage = event => {
    try {
        const message = JSON.parse(event.data);
        const data = message.data || message;

        if (data.type === "question_published") {
            state.answeredCount = 0;
            applyQuestionState(data.question, 0, state.totalPlayers);
            return;
        }

        if (data.type === "answer_progress") {
            state.answeredCount = Number(data.answered_count || 0);
            state.totalPlayers = Number(data.total_players || state.totalPlayers || 0);
            updateAnsweredCounter();

            if (
                !CONFIG.presentationOnly
                && state.answeredCount >= state.totalPlayers
                && state.totalPlayers > 0
                && state.sessionState === "question"
            ) {
                log(tr("allAnsweredAutoReveal", "All answered, auto reveal!"));
                clearTimeout(state.autoRevealTimeout);
                setTimeout(() => {
                    if (state.sessionState === "question") {
                        UI.revealBtn.click();
                    }
                }, 400);
            }
            return;
        }

        if (data.type === "reveal") {
            applyRevealState(data, state.currentQuestion);
            return;
        }

        if (data.type === "finished") {
            clearPhaseLoop();
            clearAutoTimers();
            setSessionState("finished");
            renderPodium(data.top || []);
        }
    } catch (error) {
        log(fmt(tr("playMessageError", "Play message error: {message}"), { message: error.message || "" }));
    }
};

UI.startBtn.onclick = () => {
    openPresenterWindow();
    const formData = new FormData();
    const count = parseInt(UI.questionCount.value, 10) || 1;
    formData.append("question_count", count);
    post(CONFIG.urls.start, formData);
};

UI.presentBtn.onclick = () => openPresenterWindow();
UI.revealBtn.onclick = () => post(CONFIG.urls.reveal);
UI.nextBtn.onclick = () => post(CONFIG.urls.next);
UI.finishBtn.onclick = () => post(CONFIG.urls.finish);

UI.questionCount?.addEventListener("focus", function onFocus() {
    this.select();
});

UI.questionCount?.addEventListener("blur", function onBlur() {
    let value = parseInt(this.value, 10) || 1;
    if (value < 1) value = 1;
    if (value > CONFIG.maxQuestions) value = CONFIG.maxQuestions;
    this.value = value;
});

UI.questionCount?.addEventListener("keydown", event => {
    if ([8, 46, 9, 27, 13, 37, 38, 39, 40].includes(event.keyCode)) return;
    if ((event.ctrlKey || event.metaKey) && [65, 67, 86, 88].includes(event.keyCode)) return;
    if ((event.keyCode >= 48 && event.keyCode <= 57) || (event.keyCode >= 96 && event.keyCode <= 105)) return;
    event.preventDefault();
});

setSessionState("lobby");
log(tr("hostReady", "Host ready"));
if (CONFIG.presentationOnly) {
    setTimeout(() => {
        tryEnterFullscreen();
    }, 80);
    document.addEventListener("pointerdown", () => {
        unlockAudio();
        tryEnterFullscreen();
    }, { once: true });
    document.addEventListener("keydown", event => {
        if (event.key && event.key.toLowerCase() === "f") {
            unlockAudio();
            tryEnterFullscreen();
        }
    });
}
syncState();
